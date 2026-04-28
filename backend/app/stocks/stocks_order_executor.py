"""
eTrader v5.0 — Stocks Order Executor (Capa 6+)
Ejecuta órdenes MARKET y LIMIT para el módulo de Stocks.

Soporta:
  - Ejecución MARKET (inmediata a precio de mercado)
  - Colocación LIMIT (precio calculado por Smart LIMIT)
  - Paper Mode + Live IB Mode
  - DCA (recompras escalonadas)
  - Cierre total de posiciones (SELL close_all)
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.core.symbol_state import SymbolStateMachine

sm = SymbolStateMachine.get_instance()
MODULE = "stocks_order_exec"


def _get_config() -> dict:
    """Load stocks configuration from DB."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_config").select("key, value").execute()
        cfg = {r["key"]: r["value"] for r in (res.data or [])}
        
        pct_trade = float(cfg.get("max_pct_per_trade", 0.02))
        if pct_trade > 1: pct_trade = pct_trade / 100.0 # 2 -> 0.02

        pct_max_total = float(cfg.get("max_total_risk_pct", 0.30))
        if pct_max_total > 1: pct_max_total = pct_max_total / 100.0 # 30 -> 0.30

        return {
            "paper_mode": str(cfg.get("paper_mode_active", "true")).lower() == "true",
            "total_capital": float(cfg.get("total_capital_usd", 5000)),
            "max_pct_per_trade": pct_trade,
            "max_total_risk_pct": pct_max_total,
            "max_positions": int(cfg.get("max_concurrent_positions", 5)),
        }

        return {
            "paper_mode": str(cfg.get("paper_mode_active", "true")).lower() == "true",
            "total_capital": float(cfg.get("total_capital_usd", 5000)),
            "max_pct_per_trade": pct,
            "max_positions": int(cfg.get("max_concurrent_positions", 5)),
        }
    except Exception as e:
        log_warning(MODULE, f"Config load error: {e}")
        return {
            "paper_mode": True,
            "total_capital": 5000,
            "max_pct_per_trade": 0.20,
            "max_positions": 5,
        }


def _calculate_shares(capital: float, max_pct: float, price: float) -> int:
    """
    Calcula la cantidad de acciones basada en riesgo, redondeando a múltiplos de 5.
    Mínimo 5 acciones.
    """
    if price <= 0: return 0
    
    target_usd = capital * max_pct
    raw_shares = target_usd / price
    
    # Redondear al múltiplo de 5 inferior más cercano
    shares = int(raw_shares // 5) * 5
    
    # Mínimo absoluto de 5 acciones si el capital lo permite
    if shares < 5 and target_usd >= (5 * price):
        shares = 5
        
    return shares


def _send_telegram_sync(message: str):
    """Best-effort Telegram notification (sync wrapper)."""
    try:
        import asyncio
        from app.workers.alerts_service import send_telegram_message
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(message))
        except RuntimeError:
            asyncio.run(send_telegram_message(message))
    except Exception:
        pass


def execute_market_order(
    ticker: str,
    direction: str,
    rule_code: str,
    context: dict,
    rule: dict,
) -> dict:
    """
    Ejecuta o simula una orden MARKET.
    En paper mode: registra en stocks_orders + stocks_positions.
    En live mode: envía a IB TWS API.
    """
    sb = get_supabase()
    config = _get_config()
    paper = config["paper_mode"]

    price = float(context.get("price", 0))
    if price <= 0:
        log_warning(MODULE, f"Aborting MARKET order for {ticker}: Invalid price ${price}")
        return {"success": False, "reason": "Precio inválido"}

    capital = config["total_capital"]
    max_pct = config["max_pct_per_trade"]
    max_total_risk_pct = config["max_total_risk_pct"]
    
    # ── VALIDACIÓN 1: RIESGO TOTAL ACUMULADO ──
    open_pos_res = sb.table("stocks_positions").select("total_cost").eq("status", "open").execute()
    current_investment = sum(float(p["total_cost"] or 0) for p in (open_pos_res.data or []))
    max_allowed_investment = capital * max_total_risk_pct

    if current_investment >= max_allowed_investment:
        log_warning(MODULE, f"Aborting MARKET order for {ticker}: Total risk limit reached (${current_investment:.0f}/${max_allowed_investment:.0f})")
        return {"success": False, "reason": f"Máximo riesgo total alcanzado (${current_investment:.0f}/${max_allowed_investment:.0f})"}

    # ── VALIDACIÓN 2: TAMAÑO DE LOTE (Múltiplos de 5 + Mínimo 5) ──
    shares = _calculate_shares(capital, max_pct, price)
    
    if shares < 5:
        log_warning(MODULE, f"Aborting MARKET order for {ticker}: Insufficient capital for min batch of 5 (Target: ${capital * max_pct:.0f} vs Need: ${5*price:.0f})")
        return {"success": False, "reason": f"Capital insuficiente para lote mínimo de 5 (${capital * max_pct:.0f} vs {5*price:.0f} p/lote)"}
    
    # Validar que no superemos el riesgo total con esta nueva compra
    if current_investment + (shares * price) > max_allowed_investment:
        # Intentar ajustar shares a lo que quede
        remaining_cap = max_allowed_investment - current_investment
        shares = int(remaining_cap // (price * 5)) * 5
        if shares <= 0:
            log_warning(MODULE, f"Aborting MARKET order for {ticker}: Adding even 5 shares would exceed Max Total Risk")
            return {"success": False, "reason": "La nueva compra superaría el Máximo Riesgo Total permitido"}

    now = datetime.now(timezone.utc).isoformat()

    # Registrar orden
    order_data = {
        "ticker": ticker,
        "group_name": rule.get("group_name"),
        "rule_code": rule_code,
        "order_type": "market",
        "direction": direction,
        "shares": shares,
        "market_price": price,
        "ia_score": context.get("ia_score"),
        "tech_score": context.get("tech_score"),
        "movement_type": context.get("movement_type"),
        "rvol": context.get("rvol"),
        "status": "filled" if paper else "pending",
        "filled_price": price if paper else None,
        "filled_at": now if paper else None,
        "created_at": now,
    }

    sb.table("stocks_orders").insert(order_data).execute()

    # Si SELL + close_all: cerrar posición
    if direction == "sell" and rule.get("close_all", False):
        _close_all_positions(ticker, price)

    # En STOCKS solo permitimos LONG (BUY).
    # Si la orden es SELL, solo ejecutamos el cierre de lo que ya existe.
    if direction.lower() == "buy":
        _open_or_update_position(
            ticker, price, shares,
            rule.get("group_name"),
        )
    else:
        # Forzar que cualquier SELL sea un cierre total
        _close_all_positions(ticker, price)

    mode_str = "[PAPER]" if paper else "[LIVE]"
    log_info(MODULE,
        f"{mode_str} 📊 MARKET {direction.upper()} {ticker} "
        f"x{shares} @ ${price:.2f} (regla: {rule_code})"
    )

    _send_telegram_sync(
        f"{mode_str} 📊 STOCKS MARKET {direction.upper()}\n"
        f"Ticker: {ticker}\n"
        f"Regla: {rule_code}\n"
        f"Precio: ${price:.2f}\n"
        f"Shares: {shares}\n"
        f"IA: {context.get('ia_score', 0):.1f}/10\n"
        f"Tech: {context.get('tech_score', 0):.0f}/100\n"
        f"Movimiento: {context.get('movement_type')}"
    )

    return {
        "success": True,
        "order_type": "market",
        "direction": direction,
        "ticker": ticker,
        "price": price,
        "shares": shares,
        "paper": paper,
    }


def place_limit_order(
    ticker: str,
    direction: str,
    rule_code: str,
    context: dict,
    rule: dict,
) -> dict:
    """
    Coloca una orden LIMIT en stocks_orders con status 'pending'.
    Precio calculado por Smart LIMIT.
    """
    sb = get_supabase()

    # Lógica de cálculo de precio LIMIT
    limit_price = context.get("smart_limit_price") or context.get("limit_price")
    band_name = context.get("band_name") or ("Intrinsic_Value" if "smart_limit_price" in context else "BB_Lower")

    if not limit_price or float(limit_price) <= 0:
        return {"success": False, "reason": "Precio LIMIT no disponible"}

    limit_price = float(limit_price)
    trigger_pct = float(rule.get("limit_trigger_pct") or 0.005)

    if direction == "buy":
        trigger_price = limit_price * (1 + trigger_pct)
    else:
        trigger_price = limit_price * (1 - trigger_pct)

    # ── VALIDACIÓN 1: RIESGO TOTAL ACUMULADO ──
    config = _get_config()
    capital = config["total_capital"]
    max_total_risk_pct = config["max_total_risk_pct"]
    open_pos_res = sb.table("stocks_positions").select("total_cost").eq("status", "open").execute()
    current_investment = sum(float(p["total_cost"] or 0) for p in (open_pos_res.data or []))
    max_allowed_investment = capital * max_total_risk_pct

    if direction == "buy" and current_investment >= max_allowed_investment:
        return {"success": False, "reason": f"Máximo riesgo total alcanzado (${current_investment:.0f}/${max_allowed_investment:.0f})"}

    # ── VALIDACIÓN 2: TAMAÑO DE LOTE (Múltiplos de 5 + Mínimo 5) ──
    shares = _calculate_shares(capital, config["max_pct_per_trade"], limit_price)
    
    if direction == "buy" and shares < 5:
        return {"success": False, "reason": f"Capital insuficiente para lote mínimo de 5 (${capital * config['max_pct_per_trade']:.0f} vs {5*limit_price:.0f} p/lote)"}
    
    if direction == "buy" and current_investment + (shares * limit_price) > max_allowed_investment:
        remaining_cap = max_allowed_investment - current_investment
        shares = int(remaining_cap // (limit_price * 5)) * 5
        if shares <= 0:
            return {"success": False, "reason": "La nueva compra superaría el Máximo Riesgo Total permitido"}

    # Expiración: 5 días para S02 (120h), 4h para el resto
    ttl_hours = 120 if (rule_code == "S02" or rule_code == "PRO_BUY_LMT") else 4
    now = datetime.now(timezone.utc)

    # Cancelar órdenes anteriores del mismo ticker/dirección
    sb.table("stocks_orders") \
        .update({"status": "cancelled"}) \
        .eq("ticker", ticker) \
        .eq("direction", direction) \
        .eq("status", "pending") \
        .execute()

    # Registrar nueva orden LIMIT
    order_data = {
        "ticker": ticker,
        "group_name": rule.get("group_name"),
        "rule_code": rule_code,
        "order_type": "limit",
        "direction": direction,
        "shares": shares,
        "limit_price": limit_price,
        "trigger_price": trigger_price,
        "estimated_price": limit_price,
        "target_band": band_name,
        "market_price": context.get("price"),
        "ia_score": context.get("ia_score"),
        "tech_score": context.get("tech_score"),
        "movement_type": context.get("movement_type"),
        "rvol": context.get("rvol"),
        "status": "pending",
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "created_at": now.isoformat(),
    }

    sb.table("stocks_orders").insert(order_data).execute()

    # Enriquecer alerta con valor intrínseco si existe
    intrinsic_info = f"Precio Intrínseco: ${context.get('intrinsic_price', 0):.2f}\n" if context.get("intrinsic_price") else ""

    log_info(MODULE,
        f"📍 LIMIT {direction.upper()} {ticker} "
        f"@ ${limit_price:.4f} ({band_name}) "
        f"trigger ${trigger_price:.4f} TTL={ttl_hours}h"
    )

    _send_telegram_sync(
        f"📍 STOCKS LIMIT {direction.upper()}\n"
        f"Ticker: {ticker}\n"
        f"Regla: {rule_code}\n"
        f"Banda: {band_name}\n"
        f"{intrinsic_info}"
        f"Precio LIMIT: ${limit_price:.4f}\n"
        f"Trigger (0.5%): ${trigger_price:.4f}\n"
        f"Precio actual: ${context.get('price', 0):.2f}\n"
        f"TTL: {ttl_hours}h"
    )

    return {
        "success": True,
        "order_type": "limit",
        "direction": direction,
        "ticker": ticker,
        "limit_price": limit_price,
        "trigger_price": trigger_price,
        "band": band_name,
        "ttl_hours": ttl_hours,
    }


def check_and_fill_pending_limits():
    """
    Revisa órdenes LIMIT pendientes y las rellena
    si el precio actual cruzó el trigger_price.
    Llamado periódicamente desde el scheduler.
    """
    sb = get_supabase()
    now = datetime.now(timezone.utc)

    # Obtener órdenes pendientes no expiradas
    pending = sb.table("stocks_orders") \
        .select("*") \
        .eq("status", "pending") \
        .eq("order_type", "limit") \
        .execute()

    if not pending.data:
        return []

    filled = []
    for order in pending.data:
        ticker = order["ticker"]

        # Check TTL expiration
        expires_at = order.get("expires_at")
        if expires_at:
            from dateutil.parser import parse as parse_dt
            exp = parse_dt(expires_at)
            if now > exp:
                sb.table("stocks_orders") \
                    .update({"status": "expired"}) \
                    .eq("id", order["id"]) \
                    .execute()
                log_info(MODULE, f"⏰ LIMIT {ticker} expirada")
                continue

        # Get current price
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist = t.history(period="1d", interval="1m")
            if hist.empty:
                continue
            current_price = float(hist["Close"].iloc[-1])
        except Exception:
            continue

        limit_price = float(order.get("limit_price", 0))
        direction = order["direction"]

        # Check if price reached the limit
        should_fill = False
        if direction == "buy" and current_price <= limit_price:
            should_fill = True
        elif direction == "sell" and current_price >= limit_price:
            should_fill = True

        if should_fill:
            sb.table("stocks_orders") \
                .update({
                    "status": "filled",
                    "filled_price": current_price,
                    "filled_at": now.isoformat(),
                }) \
                .eq("id", order["id"]) \
                .execute()

            if direction == "buy":
                # Usar la cantidad guardada en la orden o recalcular con la regla del 5
                shares = int(order.get("shares") or 0)
                if shares < 5:
                    shares = _calculate_shares(config["total_capital"], config["max_pct_per_trade"], current_price)
                
                if shares < 5:
                    log_warning(MODULE, f"Cancelando fill para {ticker}: Capital insuficiente para mínimo 5 shares")
                    continue

                _open_or_update_position(
                    ticker, current_price, shares,
                    order.get("group_name"),
                )
            elif direction == "sell":
                _close_all_positions(ticker, current_price)

            log_info(MODULE,
                f"✅ LIMIT FILLED {direction.upper()} {ticker} "
                f"@ ${current_price:.2f} (limit ${limit_price:.2f})"
            )
            filled.append({
                "ticker": ticker,
                "direction": direction,
                "filled_price": current_price,
            })

    return filled


def _open_or_update_position(
    ticker: str,
    price: float,
    shares: float,
    group_name: str = None,
):
    """Open a new position or update existing via DCA."""
    sb = get_supabase()

    existing = sb.table("stocks_positions") \
        .select("*") \
        .eq("ticker", ticker) \
        .eq("status", "open") \
        .limit(1) \
        .execute()

    now = datetime.now(timezone.utc).isoformat()

    if existing.data:
        # DCA update
        from app.stocks.dca_manager import update_position_after_buy
        update_position_after_buy(ticker, price, shares)
    else:
        # New position
        # --- SL/TP LOGIC: Swing 4H (Same as Crypto) ---
        # Default: ATR=2% of price, SL=2xATR (4%), TP=2.5xSL (10%)
        atr_fallback = price * 0.02
        sl_price = round(price - (atr_fallback * 2.0), 2)
        tp_price = round(price + (atr_fallback * 2.0 * 2.5), 2)

        # ── SLVM: Calcular Stop Loss Virtual ──
        slv_price = None
        try:
            from app.strategy.virtual_sl_recovery import calculate_slv
            snap_res = sb.table("market_snapshot").select("*").eq("symbol", ticker).limit(1).execute()
            snap_slv = snap_res.data[0] if snap_res.data else {}
            slv_data = calculate_slv(
                entry_price=price, side="long", symbol=ticker,
                snap=snap_slv, market_type='stocks_spot',
            )
            slv_price = slv_data['slv_price']
            log_info(MODULE, f'SLVM [{ticker}]: SLV=${slv_price:.2f} ({slv_data["distance_pips"]:.1f} pips, {slv_data["source"]})')
        except Exception as slv_e:
            log_warning(MODULE, f'SLVM calc error for {ticker}: {slv_e}')

        # 1. Create Opportunity for tracking
        opp_row = {
            "ticker": ticker,
            "status": "executed",
            "meta_score": 70,
            "stop_loss": sl_price,
            "target_1": tp_price,
            "rr_ratio": 2.5,
            "created_at": now
        }
        sb.table("trade_opportunities").insert(opp_row).execute()

        # 2. Insert Position
        sb.table("stocks_positions").insert({
            "ticker": ticker,
            "group_name": group_name,
            "direction": "long",
            "shares": shares,
            "avg_price": price,
            "total_cost": round(shares * price, 2),
            "current_price": price,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "dca_count": 0,
            "first_buy_at": now,
            "updated_at": now,
            "status": "open",
            # ── SLVM Fields ──
            "slv_price": slv_price,
            "recovery_mode": False,
            "recovery_cycles": 0,
        }).execute()
        
        # Hook into state machine
        sm.on_position_opened(ticker, "long", {"symbol": ticker, "side": "long", "status": "open"})
        
        log_info(MODULE, f"📈 Posición ABIERTA: {ticker} x{shares} @ ${price:.2f} | SL/TP created in trade_opportunities")


def _close_all_positions(ticker: str, price: float):
    """Close all open positions for a ticker."""
    sb = get_supabase()

    positions = sb.table("stocks_positions") \
        .select("*") \
        .eq("ticker", ticker) \
        .eq("status", "open") \
        .execute()

    if not positions.data:
        return

    now = datetime.now(timezone.utc).isoformat()
    for pos in positions.data:
        def safe_float(v, default=0.0):
            try:
                return float(v) if v is not None else default
            except:
                return default

        avg = safe_float(pos.get("avg_price") or pos.get("entry_price"))
        shares = safe_float(pos.get("shares"))
        pnl = (price - avg) * shares
        pnl_pct = ((price - avg) / avg * 100) if avg > 0 else 0

        sb.table("stocks_positions") \
            .update({
                "status": "closed",
                "current_price": price,
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl_pct, 2),
                "updated_at": now,
            }) \
            .eq("id", pos["id"]) \
            .execute()

        log_info(MODULE,
            f"📉 Posición CERRADA: {ticker} x{shares} "
            f"avg=${avg:.2f} exit=${price:.2f} "
            f"PnL=${pnl:.2f} ({pnl_pct:.2f}%)"
        )
        
    sm.on_position_closed(ticker, "close_all", all_closed=True)
