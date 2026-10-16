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

MODULE = "stocks_order_exec"


def is_ib_bridge_alive() -> bool:
    """Retorna True si el agente IBKR Bridge en APOLO reportó heartbeat en los últimos 60 segundos."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_config").select("value").eq("key", "ib_bridge_heartbeat").limit(1).execute()
        if not res.data:
            return False
        val = res.data[0].get("value")
        if not val:
            return False
        import ast, json
        try:
            data = json.loads(val)
        except Exception:
            data = ast.literal_eval(val)
        if not data.get("connected"):
            return False
        ts_str = data.get("timestamp")
        if not ts_str:
            return False
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        age_sec = (datetime.now(timezone.utc) - ts).total_seconds()
        return age_sec <= 60
    except Exception:
        return False


def _is_after_1515_et(now_dt=None) -> bool:
    """Retorna True si la hora de Nueva York es >= 15:15 ET (últimas 3 velas de mercado)."""
    from datetime import time as dt_time
    from zoneinfo import ZoneInfo
    if now_dt is None:
        try:
            now_dt = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        except Exception:
            now_dt = datetime.now().astimezone(ZoneInfo('America/New_York'))
    elif getattr(now_dt, 'tzinfo', None) is not None:
        try:
            now_dt = now_dt.astimezone(ZoneInfo('America/New_York'))
        except Exception:
            pass
    return now_dt.time() >= dt_time(15, 15)


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
            "max_positions": int(cfg.get("max_active_stocks") or cfg.get("max_concurrent_positions", 3)),
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
    Si el puente IB TWS (APOLO) está activo: envía orden como 'pending' para ejecución real en TWS Paper Trading.
    En paper mode sin puente: registra en stocks_orders + stocks_positions directamente.
    """
    sb = get_supabase()
    config = _get_config()
    paper = config["paper_mode"]

    price = float(context.get("price", 0))
    if price <= 0:
        log_warning(MODULE, f"Aborting MARKET order for {ticker}: Invalid price ${price}")
        return {"success": False, "reason": "Precio inválido"}

    # ── VALIDACIÓN 0: CUTOFF INTRADÍA 15:15 ET (ÚLTIMAS 3 VELAS) ──
    if direction.lower() == "buy":
        mock_now = context.get("now_dt")
        if _is_after_1515_et(mock_now):
            log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: Cutoff 15:15 ET alcanzado (últimas 3 velas). Apertura {rule_code} bloqueada.")
            return {
                "success": False,
                "reason": "Cutoff 15:15 ET alcanzado (últimas 3 velas de mercado). Nuevas aperturas bloqueadas para evitar liquidación prematura EOD."
            }

        # ── VALIDACIÓN 0.1: BLOQUEO UNIVERSAL EMA3 1H DESCENDENTE / AGOTAMIENTO / EMA3<=EMA9 ──
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            live_1h = get_live_1h_candle_and_sipv(ticker, price)
            if not live_1h.get("is_ema3_1h_ascending", True):
                slope = live_1h.get("ema3_slope_1h", 0.0)
                log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: EMA3 1H es descendente/plana ({slope:+.4f}). No se compran acciones en modo descendente.")
                return {
                    "success": False,
                    "reason": f"Bloqueo de seguridad: EMA3 1H descendente/plana ({slope:+.4f}). Acción en modo agotamiento o distribución."
                }
            if not live_1h.get("is_ema3_above_ema9", True):
                ema3_val = live_1h.get("ema3_1h_live", 0.0)
                ema9_val = live_1h.get("ema9_1h", 0.0)
                log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: EMA3 1H ({ema3_val:.2f}) <= EMA9 1H ({ema9_val:.2f}). Falta cruce alcista en 1 hora.")
                return {
                    "success": False,
                    "reason": f"Bloqueo de seguridad: EMA3 1H ({ema3_val:.2f}) <= EMA9 1H ({ema9_val:.2f}). No permitida compra sin confirmación alcista en 1H."
                }

            # ── VALIDACIÓN 0.15: GUARDIA ADUANA DE IMPULSO COMPRADOR (ADX >= 18 & +DI > -DI & Anti-Falling Knife) ──
            minus_di = float(live_1h.get("minus_di_5m") or 15.0)
            plus_di = float(live_1h.get("plus_di_5m") or 25.0)
            adx_val = float(live_1h.get("adx_5m") or 25.0)
            is_red_1h = bool(live_1h.get("is_red_candle_1h", False))
            is_last_green = bool(live_1h.get("is_last_candle_green", True))
            lower_wick = float(live_1h.get("lower_wick_ratio") or 0.0)

            # 1. Bloqueo si vendedores dominan (-DI > +DI)
            if minus_di > plus_di:
                log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: Fuerza vendedora dominante (-DI {minus_di:.1f} > +DI {plus_di:.1f}). Sin impulso comprador.")
                return {
                    "success": False,
                    "reason": f"Aduana Entrada Rechazada: Fuerza vendedora dominante (-DI {minus_di:.1f} > +DI {plus_di:.1f}). No hay impulso positivo para LONG."
                }

            # 2. Bloqueo si ADX es menor a 18 (mercado sin fuerza/aletargado)
            if adx_val < 18.0:
                log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: ADX {adx_val:.1f} < 18.0. Mercado sin fuerza de tendencia.")
                return {
                    "success": False,
                    "reason": f"Aduana Entrada Rechazada: ADX ({adx_val:.1f} < 18.0) insuficiente. Se exigen acciones con fuerza y potencial de crecimiento."
                }

            # 3. Bloqueo de Cuchillo Cayendo (1H Roja + 5m Roja sin absorción en soporte)
            if is_red_1h and not is_last_green and lower_wick < 0.30:
                log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: Vela 1H y 5m rojas simultáneas sin absorción (Mecha inf {lower_wick*100:.0f}% < 30%).")
                return {
                    "success": False,
                    "reason": f"Aduana Entrada Rechazada: Caída roja continua en 1H y 5m sin absorción ni rebote positivo."
                }
        except Exception as e_1h:
            log_debug(MODULE, f"Bypass verificación 1H live: {e_1h}")

        # ── VALIDACIÓN 0.2: COOLDOWN POST-CIERRE (15M NORMAL / 60M SI HUBO PÉRDIDA PREVIA) ──
        # Evita re-abrir la misma posición si cerró recientemente (y 60 min si fue pérdida para erradicar whipsaws)
        try:
            now_u = datetime.now(timezone.utc)
            last_tj = sb.table('trades_journal') \
                .select('exit_date, pnl_pct, pnl_usd, result') \
                .eq('ticker', ticker) \
                .order('exit_date', desc=True) \
                .limit(1) \
                .execute()
            if last_tj.data:
                ex_dt_str = last_tj.data[0].get('exit_date')
                last_pnl_pct = float(last_tj.data[0].get('pnl_pct') or 0.0)
                last_result = str(last_tj.data[0].get('result') or '').lower()
                is_prev_loss = (last_pnl_pct < 0 or last_result == 'loss')
                required_cooldown = 60.0 if is_prev_loss else 15.0

                if ex_dt_str:
                    ex_dt = datetime.fromisoformat(str(ex_dt_str).replace('Z', '+00:00'))
                    mins_since_exit = (now_u - ex_dt).total_seconds() / 60.0
                    if mins_since_exit < required_cooldown and not context.get('force_buy', False):
                        loss_tag = f" tras PÉRDIDA previa ({last_pnl_pct:+.2f}%)" if is_prev_loss else ""
                        log_warning(MODULE, f"⏳ Cooldown activo para {ticker}: cerrado hace {mins_since_exit:.1f}m (< {required_cooldown:.0f} min){loss_tag}. Re-apertura bloqueada.")
                        return {
                            "success": False,
                            "reason": f"Cooldown activo: posición cerrada hace {mins_since_exit:.1f}m. Mínimo de descanso requerido: {required_cooldown:.0f} minutos{loss_tag}."
                        }
        except Exception as e_cd:
            log_debug(MODULE, f"Error validando cooldown de salida para {ticker}: {e_cd}")

        # ── VALIDACIÓN 0.3: BLOQUEO GAP EXHAUSTION (> 25% EN APERTURA / FILTRO ANTI-LQDA) ──
        gap_pct = float(context.get("gap_pct") or 0.0)
        is_opening_window = context.get("is_opening_window")
        if is_opening_window is None:
            try:
                from zoneinfo import ZoneInfo
                now_ny = datetime.now(ZoneInfo("America/New_York"))
                mkt_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
                cutoff_opening = now_ny.replace(hour=10, minute=15, second=0, microsecond=0)
                is_opening_window = (mkt_open <= now_ny <= cutoff_opening)
            except Exception:
                is_opening_window = False

        if gap_pct > 25.0 and is_opening_window:
            log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: Gap Up excesivo ({gap_pct:+.1f}% > +25%). Riesgo extremo de agotamiento en apertura (Filtro Anti-LQDA).")
            return {
                "success": False,
                "reason": f"Bloqueo Gap Exhaustion: Gap excesivo ({gap_pct:+.1f}% > +25%). Prohibido comprar en primeros 45 minutos (Filtro Anti-LQDA)."
            }

        # ── VALIDACIÓN 0.5: DIAGNÓSTICO TÉCNICO EN ROJO (NO OPERAR) ──
        from app.stocks.diagnostic_validator import can_operate_pre_trade
        atr_fb = price * 0.02
        prop_sl = round(price - (atr_fb * 2.0), 2)
        prop_tp = round(price + (atr_fb * 5.0), 2)
        can_op, diag_msg, _ = can_operate_pre_trade(ticker, price, prop_sl, prop_tp)
        if not can_op:
            log_warning(MODULE, f"⛔ Aborting BUY for {ticker}: {diag_msg}")
            _send_telegram_sync(f"⛔ COMPRA BLOQUEADA {ticker}\n{diag_msg}")
            return {"success": False, "reason": diag_msg}

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

    # Manejo de Tranches en Sweet Spot (+5% a +25%, Caso WFF)
    is_sweet_spot = context.get("is_sweet_spot", False) or (5.0 <= gap_pct <= 25.0 and rule_code in ["PRO_BUY_MKT", "SWEET_SPOT_BUY", "ALPHA_RUNNER_BUY"])
    tranche_step = int(context.get("tranche_step") or 1)

    if is_sweet_spot or rule_code == "SWEET_SPOT_BUY":
        # Verificaciones de Piramidación Livermore para Tranche 2 y 3
        if tranche_step in [2, 3]:
            if context.get("prev_candle_green") is False:
                log_warning(MODULE, f"⛔ Aborting Tranche {tranche_step} for {ticker}: Vela previa fue ROJA. Prohibido piramidar en debilidad.")
                return {
                    "success": False,
                    "reason": f"Abortado Tranche {tranche_step}: Vela previa fue ROJA. Solo se piramida en velas positivas."
                }
            if context.get("open_ge_close") is False:
                log_warning(MODULE, f"⛔ Aborting Tranche {tranche_step} for {ticker}: Open < Close anterior (gap bajista).")
                return {
                    "success": False,
                    "reason": f"Abortado Tranche {tranche_step}: Open < Close anterior. Falta continuidad alcista."
                }

        # Asignación de 1/3 por cada paso (33%, 33%, 34%)
        if tranche_step == 1:
            shares = max(5, int((shares * 0.33) // 5) * 5)
        elif tranche_step == 2:
            shares = max(5, int((shares * 0.33) // 5) * 5)
        elif tranche_step == 3:
            shares = max(5, int((shares * 0.34) // 5) * 5)

    elif rule_code == "FT_RUNNER_BUY":
        # Tranche inicial ligero (30%) para permitir Scaling-In / Pyramiding
        shares = max(5, int((shares * 0.30) // 5) * 5)
    elif rule_code == "FT_REENTRY_BUY":
        # Tranche de recompra (35%) para añadir a posición ganadora
        shares = max(5, int((shares * 0.35) // 5) * 5)

    # HARD CAP DE SEGURIDAD POR ACCIÓN: Máximo 10% del capital total en una sola acción
    max_trade_cap_usd = capital * min(max_pct, 0.10)
    if (shares * price) > max_trade_cap_usd:
        shares = int(max_trade_cap_usd // (price * 5)) * 5
        if shares < 5 and max_trade_cap_usd >= (5 * price):
            shares = 5
    
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
    ib_live = is_ib_bridge_alive()

    # Si el puente IBKR está activo en APOLO, enviar como 'pending' para que TWS ejecute la orden
    initial_status = "pending" if (ib_live or not paper) else "filled"

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
        "status": initial_status,
        "filled_price": price if initial_status == "filled" else None,
        "filled_at": now if initial_status == "filled" else None,
        "created_at": now,
    }

    sb.table("stocks_orders").insert(order_data).execute()

    # Si SELL + close_all: cerrar posición
    if direction == "sell" and rule.get("close_all", False):
        _close_all_positions(ticker, price)

    # En STOCKS solo permitimos LONG (BUY).
    # Si la orden va hacia IBKR TWS (ib_live=True), el callback de TWS abrirá la posición al llenar la orden.
    if direction.lower() == "buy":
        if not ib_live:
            _open_or_update_position(
                ticker, price, shares,
                rule.get("group_name"),
            )
        else:
            log_info(MODULE, f"📡 [IBKR BRIDGE APOLO] Orden BUY {ticker} x{shares} enviada a TWS Paper (puerto 7497).")
    else:
        # Forzar que cualquier SELL sea un cierre total
        _close_all_positions(ticker, price)

    mode_str = "[IBKR PAPER]" if ib_live else ("[PAPER]" if paper else "[LIVE]")
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
        "ib_routed": ib_live,
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

    # ── VALIDACIÓN 0: CUTOFF INTRADÍA 15:15 ET (ÚLTIMAS 3 VELAS) ──
    if direction.lower() == "buy":
        mock_now = context.get("now_dt")
        if _is_after_1515_et(mock_now):
            log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: Cutoff 15:15 ET alcanzado (últimas 3 velas). Apertura {rule_code} bloqueada.")
            return {
                "success": False,
                "reason": "Cutoff 15:15 ET alcanzado (últimas 3 velas de mercado). Nuevas aperturas bloqueadas para evitar liquidación prematura EOD."
            }

        # ── VALIDACIÓN 0.1: BLOQUEO UNIVERSAL EMA3 1H DESCENDENTE / AGOTAMIENTO / EMA3<=EMA9 ──
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            live_1h = get_live_1h_candle_and_sipv(ticker, limit_price)
            if not live_1h.get("is_ema3_1h_ascending", True):
                slope = live_1h.get("ema3_slope_1h", 0.0)
                log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: EMA3 1H es descendente/plana ({slope:+.4f}). No se compran acciones en modo descendente.")
                return {
                    "success": False,
                    "reason": f"Bloqueo de seguridad: EMA3 1H descendente/plana ({slope:+.4f}). Acción en modo agotamiento o distribución."
                }
            if not live_1h.get("is_ema3_above_ema9", True):
                ema3_val = live_1h.get("ema3_1h_live", 0.0)
                ema9_val = live_1h.get("ema9_1h", 0.0)
                log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: EMA3 1H ({ema3_val:.2f}) <= EMA9 1H ({ema9_val:.2f}). Falta cruce alcista en 1 hora.")
                return {
                    "success": False,
                    "reason": f"Bloqueo de seguridad: EMA3 1H ({ema3_val:.2f}) <= EMA9 1H ({ema9_val:.2f}). No permitida compra sin confirmación alcista en 1H."
                }

            # ── VALIDACIÓN 0.15: GUARDIA ADUANA DE IMPULSO COMPRADOR (ADX >= 18 & +DI > -DI & Anti-Falling Knife) ──
            minus_di = float(live_1h.get("minus_di_5m") or 15.0)
            plus_di = float(live_1h.get("plus_di_5m") or 25.0)
            adx_val = float(live_1h.get("adx_5m") or 25.0)
            is_red_1h = bool(live_1h.get("is_red_candle_1h", False))
            is_last_green = bool(live_1h.get("is_last_candle_green", True))
            lower_wick = float(live_1h.get("lower_wick_ratio") or 0.0)

            # 1. Bloqueo si vendedores dominan (-DI > +DI)
            if minus_di > plus_di:
                log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: Fuerza vendedora dominante (-DI {minus_di:.1f} > +DI {plus_di:.1f}). Sin impulso comprador.")
                return {
                    "success": False,
                    "reason": f"Aduana Entrada Rechazada: Fuerza vendedora dominante (-DI {minus_di:.1f} > +DI {plus_di:.1f}). No hay impulso positivo para LONG."
                }

            # 2. Bloqueo si ADX es menor a 18 (mercado sin fuerza/aletargado)
            if adx_val < 18.0:
                log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: ADX {adx_val:.1f} < 18.0. Mercado sin fuerza de tendencia.")
                return {
                    "success": False,
                    "reason": f"Aduana Entrada Rechazada: ADX ({adx_val:.1f} < 18.0) insuficiente. Se exigen acciones con fuerza y potencial de crecimiento."
                }

            # 3. Bloqueo de Cuchillo Cayendo (1H Roja + 5m Roja sin absorción en soporte)
            if is_red_1h and not is_last_green and lower_wick < 0.30:
                log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: Vela 1H y 5m rojas simultáneas sin absorción (Mecha inf {lower_wick*100:.0f}% < 30%).")
                return {
                    "success": False,
                    "reason": f"Aduana Entrada Rechazada: Caída roja continua en 1H y 5m sin absorción ni rebote positivo."
                }
        except Exception as e_1h:
            log_debug(MODULE, f"Bypass verificación 1H live: {e_1h}")

        # ── VALIDACIÓN 0.2: COOLDOWN POST-CIERRE (15M NORMAL / 60M SI HUBO PÉRDIDA PREVIA) ──
        try:
            now_u = datetime.now(timezone.utc)
            last_tj = sb.table('trades_journal') \
                .select('exit_date, pnl_pct, pnl_usd, result') \
                .eq('ticker', ticker) \
                .order('exit_date', desc=True) \
                .limit(1) \
                .execute()
            if last_tj.data:
                ex_dt_str = last_tj.data[0].get('exit_date')
                last_pnl_pct = float(last_tj.data[0].get('pnl_pct') or 0.0)
                last_result = str(last_tj.data[0].get('result') or '').lower()
                is_prev_loss = (last_pnl_pct < 0 or last_result == 'loss')
                required_cooldown = 60.0 if is_prev_loss else 15.0

                if ex_dt_str:
                    ex_dt = datetime.fromisoformat(str(ex_dt_str).replace('Z', '+00:00'))
                    mins_since_exit = (now_u - ex_dt).total_seconds() / 60.0
                    if mins_since_exit < required_cooldown and not context.get('force_buy', False):
                        loss_tag = f" tras PÉRDIDA previa ({last_pnl_pct:+.2f}%)" if is_prev_loss else ""
                        log_warning(MODULE, f"⏳ Cooldown activo para {ticker}: cerrado hace {mins_since_exit:.1f}m (< {required_cooldown:.0f} min){loss_tag}. Re-apertura bloqueada.")
                        return {
                            "success": False,
                            "reason": f"Cooldown activo: posición cerrada hace {mins_since_exit:.1f}m. Mínimo de descanso requerido: {required_cooldown:.0f} minutos{loss_tag}."
                        }
        except Exception as e_cd:
            log_debug(MODULE, f"Error validando cooldown de salida para {ticker}: {e_cd}")

        # ── VALIDACIÓN 0.3: BLOQUEO GAP EXHAUSTION (> 25% EN APERTURA / FILTRO ANTI-LQDA) ──
        gap_pct = float(context.get("gap_pct") or 0.0)
        is_opening_window = context.get("is_opening_window")
        if is_opening_window is None:
            try:
                from zoneinfo import ZoneInfo
                now_ny = datetime.now(ZoneInfo("America/New_York"))
                mkt_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
                cutoff_opening = now_ny.replace(hour=10, minute=15, second=0, microsecond=0)
                is_opening_window = (mkt_open <= now_ny <= cutoff_opening)
            except Exception:
                is_opening_window = False

        if gap_pct > 25.0 and is_opening_window:
            log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: Gap Up excesivo ({gap_pct:+.1f}% > +25%). Riesgo extremo de agotamiento en apertura (Filtro Anti-LQDA).")
            return {
                "success": False,
                "reason": f"Bloqueo Gap Exhaustion: Gap excesivo ({gap_pct:+.1f}% > +25%). Prohibido comprar en primeros 45 minutos (Filtro Anti-LQDA)."
            }

        # ── VALIDACIÓN 0.5: DIAGNÓSTICO TÉCNICO EN ROJO (NO OPERAR) ──
        from app.stocks.diagnostic_validator import can_operate_pre_trade
        atr_fb = limit_price * 0.02
        prop_sl = round(limit_price - (atr_fb * 2.0), 2)
        prop_tp = round(limit_price + (atr_fb * 5.0), 2)
        can_op, diag_msg, _ = can_operate_pre_trade(ticker, limit_price, prop_sl, prop_tp)
        if not can_op:
            log_warning(MODULE, f"⛔ Aborting LIMIT BUY for {ticker}: {diag_msg}")
            _send_telegram_sync(f"⛔ COMPRA LIMIT BLOQUEADA {ticker}\n{diag_msg}")
            return {"success": False, "reason": diag_msg}

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

    # Expiración: si context/rule define ttl_minutes (ej. 5m para pullbacks), usarlo; de lo contrario 120h para S02/PRO_BUY_LMT o 4h
    ttl_minutes = context.get("ttl_minutes") or rule.get("ttl_minutes")
    ttl_hours = 120 if (rule_code == "S02" or rule_code == "PRO_BUY_LMT") else 4
    now = datetime.now(timezone.utc)
    if ttl_minutes:
        expires_at_dt = now + timedelta(minutes=float(ttl_minutes))
        ttl_label = f"{float(ttl_minutes):.0f}m"
    else:
        expires_at_dt = now + timedelta(hours=ttl_hours)
        ttl_label = f"{ttl_hours}h"

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
        "expires_at": expires_at_dt.isoformat(),
        "created_at": now.isoformat(),
    }

    sb.table("stocks_orders").insert(order_data).execute()

    # Enriquecer alerta con valor intrínseco si existe
    intrinsic_info = f"Precio Intrínseco: ${context.get('intrinsic_price', 0):.2f}\n" if context.get("intrinsic_price") else ""

    log_info(MODULE,
        f"📍 LIMIT {direction.upper()} {ticker} "
        f"@ ${limit_price:.4f} ({band_name}) "
        f"trigger ${trigger_price:.4f} TTL={ttl_label}"
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
        f"TTL: {ttl_label}"
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
            from app.strategy.virtual_sl_recovery import calculate_slv, calculate_hard_stop_pips
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
        slv_hs_pips = calculate_hard_stop_pips(ticker, 'stocks_spot', snap_slv)
        
        sb.table("stocks_positions").insert({
            "ticker": ticker,
            "group_name": group_name,
            "direction": "long",
            "shares": shares,
            "avg_price": price,
            "total_cost": round(shares * price, 2),
            "current_price": price,
            "stop_loss": sl_price,
            "trailing_sl_price": sl_price,
            "highest_price_reached": price,
            "take_profit": tp_price,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "dca_count": 0,
            "first_buy_at": now,
            "updated_at": now,
            "status": "open",
            # ── SLVM Fields ──
            "slv_price": slv_price,
            "slv_hard_stop_pips": slv_hs_pips,
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

        # Si el puente IBKR está activo en APOLO, despachar orden SELL a TWS Paper
        if is_ib_bridge_alive() and shares > 0:
            try:
                sb.table("stocks_orders").insert({
                    "ticker": ticker,
                    "group_name": pos.get("group_name", "STOCKS"),
                    "rule_code": "EMERGENCY_EXIT",
                    "order_type": "market",
                    "direction": "sell",
                    "shares": int(shares),
                    "market_price": price,
                    "status": "pending",
                    "created_at": now
                }).execute()
                log_info(MODULE, f"📡 [IBKR BRIDGE] Orden SELL enviada a APOLO para liquidar {shares}x {ticker} en TWS Paper.")
            except Exception as ib_err:
                log_error(MODULE, f"Error despachando SELL a IB Bridge: {ib_err}")
        
    sm.on_position_closed(ticker, "close_all", all_closed=True)
