"""
ANTIGRAVITY · Candle Signal Execution Service v1.1
Lanza MARKET orders cuando aparecen señales BUY/SELL en 4H/1D.

Estrategias:
  Crypto & Forex:
    - Aa41 → BUY signals
    - Bb41 → SELL signals

  Stocks:
    - Inversiones Pro / BUY  / V01 → PRO_CANDLE_BUY
    - Inversiones Pro / SELL / V02 → PRO_CANDLE_SELL
    - Hot by Volume  / BUY  / V03 → HOT_CANDLE_BUY
    - Hot by Volume  / SELL / V04 → HOT_CANDLE_SELL

Filtro de Fibonacci:
  BUY  → solo si fibonacci_zone ∈ {+2, +1, 0, -1, -2, -3, -4, -5, -6}  (zone ≤ +2)
  SELL → solo si fibonacci_zone ∈ {-2, -1, 0, +1, +2, +3, +4, +5, +6}  (zone ≥ -2)

Regla de cierre:
  Cuando aparece señal BUY o SELL, se cierran TODAS las posiciones
  activas del par/ticker y luego se abre 1 nueva posición.
"""

import math
import os
import sys
import traceback
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.strategy.capital_protection import (
    evaluate_counter_trend_sizing,
    check_cooldown,
    PROTECTION_CONFIG
)
from app.core.crypto_symbols import (
    normalize_crypto_symbol,
    crypto_symbol_match_variants,
    resolve_crypto_position_quantity,
)
from app.candle_signals.candle_patterns import PatternResult
from app.strategy.position_guards import (
    can_open_position,
    check_signal_interval,
)

MODULE = "candle_signal_exec"


def _is_uuid_str(value) -> bool:
    try:
        uuid_mod.UUID(str(value).strip())
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _order_uuid_for_position(order_id) -> str | None:
    """positions.order_id es UUID FK; rechazar exchange/paper ids (PAPER_*, etc.)."""
    if order_id is None:
        return None
    s = str(order_id).strip()
    if _is_uuid_str(s):
        return s
    log_warning(MODULE, f"Ignorando order_id no-UUID para tabla positions: {order_id!r}")
    return None


def _ensure_crypto_sl_tp(
    price:       float,
    side:        str,
    snap:        dict = None,
    market_type: str  = 'crypto_futures'
) -> tuple:
    """
    Calcula SL backstop amplio y dos niveles de TP (parcial y final).
    """
    price = float(price or 0)
    side = (side or "buy").lower()
    
    if side in ('long', 'buy', 'BUY'):
        if snap:
            lower_6 = float(snap.get('lower_6', 0))
            if lower_6 > 0 and lower_6 < price * 0.95:
                sl = lower_6 * 0.9995  # 0.05% debajo de lower_6
            else:
                sl = price * 0.92      # fallback: 8% abajo
        else:
            sl = price * 0.92

        # TP1 en upper_3 o +3%
        upper_3 = float(snap.get('upper_3', 0)) if snap else 0
        tp1 = upper_3 if upper_3 > price * 1.01 else price * 1.03
        
        # TP2 en upper_6 o +6%
        upper_6 = float(snap.get('upper_6', 0)) if snap else 0
        tp2 = upper_6 if upper_6 > tp1 * 1.01 else tp1 * 1.05

    else:  # short
        if snap:
            upper_6 = float(snap.get('upper_6', 0))
            if upper_6 > 0 and upper_6 > price * 1.05:
                sl = upper_6 * 1.0005
            else:
                sl = price * 1.08
        else:
            sl = price * 1.08

        # TP1 en lower_3 o -3%
        lower_3 = float(snap.get('lower_3', 0)) if snap else 0
        tp1 = lower_3 if lower_3 < price * 0.99 else price * 0.97
        
        # TP2 en lower_6 o -6%
        lower_6 = float(snap.get('lower_6', 0)) if snap else 0
        tp2 = lower_6 if lower_6 < tp1 * 0.99 else tp1 * 0.95

    return round(sl, 8), round(tp1, 8), round(tp2, 8)


# ─── FIBONACCI BAND ZONE VALIDATION ──────────────────────────────────────────
# BUY  → price must be at or below zone +2 (zones: +2,+1,0,-1,-2,-3,-4,-5,-6)
# SELL → price must be at or above zone -2 (zones: -2,-1,0,+1,+2,+3,+4,+5,+6)
BUY_ALLOWED_ZONES = {+2, +1, 0, -1, -2, -3, -4, -5, -6}
SELL_ALLOWED_ZONES = {-2, -1, 0, +1, +2, +3, +4, +5, +6}


def _get_fibonacci_zone(market: str, pair_or_ticker: str) -> int:
    """
    Fetch the current Fibonacci band zone for a symbol.
    
    Sources:
      Crypto/Forex: market_snapshot.fibonacci_zone
      Stocks: technical_scores.signals_json.fib_zone_15m
    
    Returns:
      int zone (-6 to +6), 0 if not found
    """
    sb = get_supabase()
    try:
        if market in ("crypto", "forex"):
            # Crypto uses BTCUSDT format in market_snapshot
            symbol = normalize_crypto_symbol(pair_or_ticker)
            res = sb.table("market_snapshot") \
                .select("fibonacci_zone") \
                .eq("symbol", symbol) \
                .limit(1) \
                .execute()
            if res.data:
                return int(res.data[0].get("fibonacci_zone", 0))

        elif market == "stocks":
            res = sb.table("technical_scores") \
                .select("signals_json") \
                .eq("ticker", pair_or_ticker) \
                .limit(1) \
                .execute()
            if res.data:
                sj = res.data[0].get("signals_json") or {}
                # Use 15m zone as primary, fall back to 1d
                zone = sj.get("fib_zone_15m", sj.get("fib_zone_1d", 0))
                return int(zone) if zone is not None else 0

    except Exception as e:
        log_warning(MODULE, f"Failed to fetch fibonacci zone for {pair_or_ticker}: {e}")

    return 0  # default: center zone (always passes both BUY and SELL filters)


def _validate_fibonacci_zone(action: str, fib_zone: int) -> bool:
    """
    Validate if the current Fibonacci zone allows the given action.
    
    BUY  → zone must be ≤ +2 (i.e. at basis or below — not overbought)
    SELL → zone must be ≥ -2 (i.e. at basis or above — not oversold)
    """
    if action == "BUY":
        return fib_zone in BUY_ALLOWED_ZONES
    elif action == "SELL":
        return fib_zone in SELL_ALLOWED_ZONES
    return False


# ─── STRATEGY CODES ──────────────────────────────────────────────────────────
STRATEGY_CODES = {
    "crypto": {
        "BUY":  "Aa41",
        "SELL": "Bb41",
    },
    "forex": {
        "BUY":  "Aa41",
        "SELL": "Bb41",
    },
    "stocks": {
        # Inversiones Pro
        "PRO_BUY":  "PRO_CANDLE_BUY",    # V01
        "PRO_SELL": "PRO_CANDLE_SELL",    # V02
        # Hot by Volume
        "HOT_BUY":  "HOT_CANDLE_BUY",    # V03
        "HOT_SELL": "HOT_CANDLE_SELL",    # V04
    },
}


def _send_telegram_sync(message: str):
    """Best-effort Telegram notification."""
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


def _get_strategy_code(market: str, action: str, pool_type: str = "") -> str:
    """
    Get strategy code based on market and action.
    For stocks, pool_type determines PRO vs HOT.
    """
    if market in ("crypto", "forex"):
        return STRATEGY_CODES[market].get(action, "Aa41")

    if market == "stocks":
        is_pro = pool_type and any(
            tag in pool_type.upper() for tag in ("PRO", "GIANT", "LEADER", "VALUE")
        )
        if action == "BUY":
            return STRATEGY_CODES["stocks"]["PRO_BUY" if is_pro else "HOT_BUY"]
        else:
            return STRATEGY_CODES["stocks"]["PRO_SELL" if is_pro else "HOT_SELL"]

    return "Aa41"


# ═══════════════════════════════════════════════════════════════════════════════
#  CRYPTO — Execute via Binance API
# ═══════════════════════════════════════════════════════════════════════════════

def execute_crypto_signal(
    pair: str,
    pattern: PatternResult,
    timeframe: str,
    candle_data: dict,
    fib_zone: int = 0,
) -> dict:
    """
    Execute a candle signal for Crypto via Binance.
    
    Steps:
      1. Close ALL active positions for this pair
      2. Open 1 new MARKET position in signal direction
      3. Save to positions table
    """
    sb = get_supabase()
    action = pattern.action
    strategy_code = _get_strategy_code("crypto", action)
    now_iso = datetime.now(timezone.utc).isoformat()

    log_info(MODULE,
        f"🕯️ CRYPTO CANDLE SIGNAL: {action} {normalize_crypto_symbol(pair)} | "
        f"Pattern: {pattern.pattern_name} (ID:{pattern.pattern_id}) | "
        f"TF: {timeframe} | Confidence: {pattern.confidence:.0f} | "
        f"Fib Zone: {fib_zone:+d}"
    )

    # ── STEP 1: Execute pre-requisites ──
    from app.core.memory_store import BOT_STATE
    is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False
    binance_symbol = normalize_crypto_symbol(pair)

    # ── GUARD #3: Anti-spam de señales (Corrección #3) ──
    signal_check = check_signal_interval(binance_symbol, action)
    if not signal_check['allowed']:
        log_info(MODULE, f"🚫 SIGNAL GUARD: {signal_check['reason']}")
        return {"success": False, "reason": "signal_spam_guard", "pair": binance_symbol}

    # ── GUARD #2: Cooldown post-SL + max 1 por símbolo (Corrección #2) ──
    open_pos_res = sb.table("positions").select("id, symbol, side").eq("status", "open").execute()
    open_pos_list = open_pos_res.data or []
    guard_check = can_open_position(
        symbol=binance_symbol,
        direction='long' if action == 'BUY' else 'short',
        market_type='crypto_futures',
        open_positions=open_pos_list,
    )
    if not guard_check['allowed']:
        log_info(MODULE, f"🚫 POSITION GUARD: {guard_check['reason']}")
        return {"success": False, "reason": "position_guard", "pair": binance_symbol, "detail": guard_check['reason']}

    # Cerrar posiciones: 
    # 1. Forzar cierre de las opuestas (Hedge no permitido)
    # 2. Cierre opcional por beneficio si son de la misma dirección (Rotación por vela) - AHORA MANEJADO PARA MULTI-LAYER
    
    # NUEVO: Buscar si ya existe una posición abierta con esta misma estrategia
    existing_same = sb.table("positions").select("*").eq("status", "open").eq("symbol", binance_symbol).eq("rule_code", strategy_code).execute().data or []
    
    if existing_same:
        # Regla 1: 1 compra por vela y estrategia
        # Determinamos si la última compra fue en esta misma vela (TF: 4H o 1D en Crypto)
        # Parseo robusto de fecha ISO (maneja milisegundos variables y zona horaria)
        last_pos = sorted(existing_same, key=lambda x: x['opened_at'], reverse=True)[0]
        raw_date = last_pos['opened_at']
        try:
            if '.' in raw_date:
                base, rest = raw_date.split('.', 1)
                import re
                match = re.match(r"(\d+)(.*)", rest)
                if match:
                    ms, tz = match.groups()
                    ms = ms.ljust(6, '0')[:6] 
                    raw_date = f"{base}.{ms}{tz}"
            ts = raw_date.replace('Z', '+00:00')
            opened_at = datetime.fromisoformat(ts)
        except Exception as de:
            log_warning(MODULE, f"Date parsing error for {binance_symbol}: {de}. Using fallback.")
            opened_at = datetime.now(timezone.utc) - timedelta(days=1)
        now = datetime.now(timezone.utc)
        
        # Aproximación del open_time de la vela actual
        # TF de Crypto suele ser '4H' o '1D'.
        if timeframe == "4H":
            candle_start = now - timedelta(hours=now.hour % 4, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
        else: # 1D
            candle_start = now - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
            
        if opened_at >= candle_start:
            log_info(MODULE, f"⏸️ Omitiendo {binance_symbol} {strategy_code}: Ya se abrió una posición en esta vela ({timeframe}).")
            return {"success": False, "reason": "one_trade_per_candle", "pair": binance_symbol}

        # Regla 2: Mejora de precio
        last_entry = float(last_pos.get('entry_price', 0))
        current_price = float(candle_data.get("close", 0))
        if action == "BUY" and current_price >= last_entry:
            log_info(MODULE, f"⏸️ Omitiendo BUY {binance_symbol}: Precio {current_price} no es menor que anterior {last_entry}.")
            return {"success": False, "reason": "price_improvement_required", "pair": binance_symbol}
        if action == "SELL" and current_price <= last_entry:
            log_info(MODULE, f"⏸️ Omitiendo SELL {binance_symbol}: Precio {current_price} no es mayor que anterior {last_entry}.")
            return {"success": False, "reason": "price_improvement_required", "pair": binance_symbol}
            
        # Si ya existe misma estrategia, nos aseguramos de cerrar las OPUESTAS de OTRAS estrategias
        # (Esto evita tener BUY de una estrategia y SELL de otra al mismo tiempo)
        _close_all_positions_crypto(binance_symbol, strategy_code, new_signal_action=action, only_opposite=True)
        log_info(MODULE, f"💎 Agregando CAPA {len(existing_same)+1} para {binance_symbol} strategy {strategy_code}")
    else:
        # Si no hay misma estrategia, procedemos con el cierre de las OPUESTAS (o las mismas si fuera refresco)
        close_meta = _close_all_positions_crypto(binance_symbol, strategy_code, new_signal_action=action, only_opposite=False)
        if close_meta.get("skipped_due_to_invalid_size"):
            log_warning(MODULE, f"🚫 CANDLE SIGNAL abortado {binance_symbol}: tamaño 0.")
            return {"success": False, "reason": "invalid_position_size", "pair": binance_symbol}
        if close_meta.get("skipped_due_to_loss"):
            log_info(MODULE, f"🚫 CANDLE SIGNAL omitido {binance_symbol}: posición previa en pérdida.")
            return {"success": False, "reason": "candle_signal_requires_profit_exit", "pair": binance_symbol}

    # ── CHECK 1: Limit per symbol (Compliance with Cant. Operación x Par/Cripto) ──
    from app.core.supabase_client import get_risk_config
    risk_config = get_risk_config()
    max_per_symbol = int(risk_config.get('max_positions_per_symbol', 4))
    
    # Contar TODAS las posiciones abiertas de este símbolo (no solo de esta estrategia)
    total_open_symbol = sb.table("positions").select("id", count='exact').eq("symbol", binance_symbol).eq("status", "open").execute().count
    
    if total_open_symbol >= max_per_symbol:
        log_warning(
            MODULE,
            f"🚫 LÍMITE ALCANZADO para {binance_symbol}: {total_open_symbol}/{max_per_symbol} posiciones abiertas totales."
        )
        return {
            "success": False,
            "reason": "max_positions_per_symbol_reached",
            "pair": binance_symbol,
        }

    # ── CHECK 2: Total Market Risk Limit (30% sum of Stop Losses) ──
    from app.strategy.risk_controls import check_total_market_risk
    from app.core.capital_manager import get_total_operating_capital
    capital = get_total_operating_capital('forex')
    inv_pct = 2.0  # Default 2% for forex risk
    leverage = 100.0
    
    target_inv = capital * (inv_pct / 100) # e.g. $20.00 if capital is $1000  if not risk_check["passed"]:
        log_warning(MODULE, f"🚫 RIESGO TOTAL CRIPTO ALCANZADO: {risk_check['reason']}")
        return {
            "success": False,
            "reason": "max_total_risk_reached",
            "pair": binance_symbol,
            "detail": risk_check["reason"]
        }

    # ── STEP 2: Execute MARKET order ──
    price = float(candle_data.get("close", 0) or 0)
    if price <= 0:
        return {"success": False, "reason": "Precio inválido"}

    from app.core.memory_store import MARKET_SNAPSHOT_CACHE
    from app.strategy.dynamic_sl_manager import calculate_backstop_sl

    current_snap = MARKET_SNAPSHOT_CACHE.get(binance_symbol, {})

    atr_fallback = price * 0.02
    if action == "BUY":
        tp = round(price + atr_fallback * 2.0 * 2.5, 8)
    else:
        tp = round(price - atr_fallback * 2.0 * 2.5, 8)

    backstop_data = calculate_backstop_sl(
        entry_price = price,
        side        = 'long' if action == 'BUY' else 'short',
        snap        = current_snap,
        market_type = 'crypto_futures',
    )
    
    sl = backstop_data['backstop_price']
    sl, tp1, tp2 = _ensure_crypto_sl_tp(price, action, snap=current_snap)
    
    log_info('SL_MANAGER',
        f'{binance_symbol}: Backstop SL = '
        f'{backstop_data["backstop_price"]:.6f} '
        f'({backstop_data["source"]}) '
        f'({backstop_data["pct_from_entry"]:.2f}% '
        f'del precio de entrada)'
    qty_display: float | None = None
    entry_display = price

    price = entry_display    # ── STEP 2: Calculate quantity based on risk ──
    from app.core.capital_manager import get_total_operating_capital
    capital_total = get_total_operating_capital('crypto')
    
    # ── LOG: COMPOUNDING CHECK ──
    log_info(MODULE, f"💰 CAPITAL OPERATIVO (CRIPTO): ${capital_total:,.2f}")

    dist_sl = _calculate_sl_distance_crypto(action, price, candle_data)
    risk_pct = float(risk_config.get('max_risk_per_trade_pct', 5.0)) # Usando el nuevo 5%
    risk_usd_per_trade = capital_total * (risk_pct / 100.0)
    quantity_raw = risk_usd_per_trade / dist_sl
    
    # Cap by max notional allowed (leverage)
    leverage = float(risk_config.get('leverage_crypto', 15.0))
    max_notional = capital_total * leverage
    quantity = min(quantity_raw, max_notional / price)

    if is_paper:
        paper_size = round(quantity, 4)
        order_row_id = _save_candle_order_crypto(
            sb, binance_symbol, action, strategy_code, price, pattern, timeframe, "paper", paper_size, sl, tp1, tp2
        )
        order_uuid = _order_uuid_for_position(order_row_id)
        if not order_uuid:
            log_warning(MODULE, f"No se pudo generar order_uuid para position en {binance_symbol}")

        if not _save_candle_position_crypto(
            sb, binance_symbol, action, strategy_code, price, pattern, timeframe, order_uuid, paper_size, sl, tp1, tp2
        ):
            log_error(MODULE, f"[PAPER] No se abrió posición en DB para {binance_symbol}")
            return {"success": False, "reason": "db_save_failed"}

        qty_display = paper_size
        log_info(MODULE, f"[PAPER] ✅ SL-BASED Crypto {action} {binance_symbol} @ {price} | Qty: {paper_size} (Risk: ${risk_usd_per_trade})")
    else:
        # Live mode: Binance MARKET order
        try:
            from app.execution.binance_connector import get_client, get_symbol_info_cached, round_step_size
            client = get_client()
            
            info = get_symbol_info_cached(client, binance_symbol)
            step_size = info.get("step_size", 0.001)
            quantity_live = round_step_size(quantity, step_size)

            if quantity_live <= 0:
                return {"success": False, "reason": "Cantidad insuficiente tras redondeo"}

            if action == "BUY":
                entry_order = client.order_market_buy(symbol=binance_symbol, quantity=quantity)
            else:
                entry_order = client.order_market_sell(symbol=binance_symbol, quantity=quantity)

            fills = entry_order.get("fills", [])
            if fills:
                avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / sum(float(f["qty"]) for f in fills)
            else:
                avg_price = price

            # Recalculate backstop with actual avg_price for live
            backstop_data_live = calculate_backstop_sl(
                entry_price = float(avg_price),
                side        = 'long' if action == 'BUY' else 'short',
                snap        = current_snap,
                market_type = 'crypto_futures',
            )
            sl_live = backstop_data_live['backstop_price']

            sl_live, tp1_live, tp2_live = _ensure_crypto_sl_tp(float(avg_price), action, snap=current_snap)
            order_row_id = _save_candle_order_crypto(
                sb, binance_symbol, action, strategy_code, avg_price, pattern, timeframe, "live", quantity, sl_live, tp1_live, tp2_live
            )
            order_uuid = _order_uuid_for_position(order_row_id)
            if not order_row_id:
                log_warning(MODULE, f"No se pudo guardar orden live en Supabase para {binance_symbol}; position sin order_id.")
            if not _save_candle_position_crypto(
                sb, binance_symbol, action, strategy_code, avg_price, pattern, timeframe, order_uuid, quantity, sl_live, tp1_live, tp2_live
            ):
                log_error(
                    MODULE,
                    f"[LIVE] Binance ejecutó pero falló guardar posición en DB para {binance_symbol} — revisar Supabase / no Telegram.",
                )
                return {
                    "success": False,
                    "reason": "crypto_live_position_not_saved",
                    "pair": binance_symbol,
                }

            qty_display = float(quantity)
            entry_display = float(avg_price)
            log_info(MODULE, f"[LIVE] ✅ Crypto {action} {binance_symbol} @ {avg_price} | Strategy: {strategy_code}")

        except Exception as e:
            log_error(MODULE, f"Crypto MARKET order failed: {e}\n{traceback.format_exc()}")
            return {"success": False, "reason": str(e)}

    # Solo notificar si hay posición persistida (paper o live)
    _send_telegram_sync(
        f"🕯️ CRYPTO CANDLE SIGNAL (ejecutado)\n"
        f"{'🟢 BUY' if action == 'BUY' else '🔴 SELL'} {binance_symbol}\n"
        f"Cantidad: {qty_display}\n"
        f"Patrón: {pattern.pattern_name}\n"
        f"Temporalidad: {timeframe}\n"
        f"Confianza: {pattern.confidence:.0f}%\n"
        f"Estrategia: {strategy_code}\n"
        f"Precio: {entry_display:.4f}\n"
        f"Modo: {'PAPER' if is_paper else 'LIVE'}"
    )

    return {"success": True, "action": action, "pair": binance_symbol, "strategy": strategy_code}


def _close_all_positions_crypto(binance_symbol: str, strategy_code: str, new_signal_action: str = None, only_opposite: bool = False) -> dict:
    """
    Cierra posiciones abiertas del par (formato canónico SOLUSDT, incluye legacy SOL/USDT).

    Reglas:
      - Cantidad efectiva desde positions.size o orders.quantity.
      - Si new_signal_action es opuesta a la posición existente: CIERRE FORZADO (no importa PnL).
      - Si es la misma dirección: Solo cierra si hay beneficio (min_profit_exit_usd/pct).
    """
    sb = get_supabase()
    out = {
        "closed_count": 0,
        "remaining_open_count": 0,
        "skipped_due_to_loss": False,
        "skipped_due_to_invalid_size": False,
    }
    try:
        variants = crypto_symbol_match_variants(binance_symbol)
        res = (
            sb.table("positions")
            .select("*")
            .eq("status", "open")
            .in_("symbol", variants)
            .execute()
        )
        positions = res.data or []
        out["remaining_open_count"] = len(positions)

        if not positions:
            return out

        from app.core.memory_store import BOT_STATE

        is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False
        min_usd = float(BOT_STATE.config_cache.get("min_profit_exit_usd", 1.0))
        min_pct = float(BOT_STATE.config_cache.get("min_profit_exit_pct", 0.30))

        close_price_live = None
        if not is_paper:
            from app.execution.binance_connector import get_current_price

            close_price_live = get_current_price(binance_symbol)
            if close_price_live <= 0:
                log_warning(MODULE, f"No se pudo obtener precio de cierre para {binance_symbol}")
                return out

        previews = []
        for pos in positions:
            if is_paper:
                close_price = float(pos.get("current_price", pos.get("entry_price", 0)))
            else:
                close_price = float(close_price_live or 0)

            if close_price <= 0:
                log_warning(MODULE, f"Precio de cierre inválido para posición {pos.get('id')} {binance_symbol}")
                return out

            entry_price = float(pos.get("entry_price", 0) or 0)
            size = resolve_crypto_position_quantity(sb, pos)
            if size <= 0:
                out["skipped_due_to_invalid_size"] = True
                log_error(
                    MODULE,
                    f"Posición {pos.get('id')} {pos.get('symbol')}: size=0 y sin quantity en orders — abortando cierre vela.",
                )
                return out

            side_u = (pos.get("side") or "").upper()
            size_abs = abs(size) # Usamos valor absoluto para el cálculo pecuniario
            if side_u in ("LONG", "BUY"):
                pnl = (close_price - entry_price) * size_abs
                pnl_pct = ((close_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            else:
                pnl = (entry_price - close_price) * size_abs
                pnl_pct = ((entry_price - close_price) / entry_price * 100) if entry_price > 0 else 0.0

            is_opposite = False
            if new_signal_action:
                p_side = (pos.get("side") or "").upper()
                if new_signal_action.upper() == "BUY":
                    is_opposite = p_side in ("SHORT", "SELL")
                else:
                    is_opposite = p_side in ("LONG", "BUY")

            previews.append((pos, size, pnl, pnl_pct, close_price, is_opposite))

        eps = 1e-9
        has_opposite = any(preview[5] for preview in previews) # preview[5] is is_opposite

        for _pos, _sz, pnl, pnl_pct, _cpx, is_opposite in previews:
            if is_opposite:
                log_info(MODULE, f"⚠️ FORZANDO CIERRE por reversión de dirección ({_pos.get('side')} -> {new_signal_action}) en {binance_symbol}")
                continue # Pasa a cerrar

            # Si hay una reversión en curso, NO bloqueamos el ciclo por posiciones de la MISMA dirección en pérdida
            # Pero solo las cerramos si tienen profit. Si no tienen profit y es la misma dirección, se quedan como CAPAS.
            if pnl <= eps:
                if not has_opposite and not only_opposite:
                    out["skipped_due_to_loss"] = True
                    log_info(
                        MODULE,
                        f"🚫 No cierre vela {binance_symbol}: PnL no positivo (usd={pnl:.4f}, pct={pnl_pct:.4f}).",
                    )
                    return out
                else:
                    log_info(MODULE, f"ℹ️ Manteniendo capa same-side en pérdida durante reversión: {_pos.get('id')}")
                    continue

            profit_ok = (pnl >= min_usd) or (pnl_pct >= min_pct)
            if not profit_ok:
                if not has_opposite and not only_opposite:
                    out["skipped_due_to_loss"] = True
                    log_info(
                        MODULE,
                        f"🚫 No cierre vela {binance_symbol}: beneficio insuficiente vs umbrales "
                        f"(usd={pnl:.4f} need>={min_usd} OR pct={pnl_pct:.4f}% need>={min_pct}%).",
                    )
                    return out
                else:
                    log_info(MODULE, f"ℹ️ Manteniendo capa same-side con bajo profit durante reversión: {_pos.get('id')}")
                    continue

        log_info(
            MODULE,
            f"🔄 Cerrando posiciones elegibles de {binance_symbol} (señal vela → {strategy_code})",
        )

        for pos, size, pnl, pnl_pct, close_px, is_opposite in previews:
            # Re-evaluamos si debe cerrarse
            should_close = is_opposite
            if not should_close and not only_opposite:
                if pnl > eps:
                    should_close = (pnl >= min_usd) or (pnl_pct >= min_pct)
            
            if not should_close:
                continue

            try:
                # El valor de la inversión (notional) se basa en el tamaño absoluto
                notional = float(pos.get("entry_price", 0) or 0) * abs(size)
                pnl_pct_row = round((pnl / notional * 100), 4) if notional > 0 else round(pnl_pct, 4)

                sb.table("positions").update(
                    {
                        "status": "closed",
                        "symbol": binance_symbol,
                        "close_reason": f"candle_signal_{strategy_code}",
                        "realized_pnl": round(pnl, 4),
                        "realized_pnl_pct": pnl_pct_row,
                        "size": size,
                        "current_price": close_px,
                        "closed_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", pos["id"]).execute()

                out["closed_count"] += 1
                out["remaining_open_count"] -= 1
                log_info(
                    MODULE,
                    f"  ↳ Cerrada {pos['id'][:8]}... side={pos.get('side')} PnL: {pnl:.4f} ({pnl_pct_row}%) qty={size}",
                )

        # ── CANCELAR ÓRDENES HUÉRFANAS ──
        # Si cerramos algo (o hay reversión), limpiamos pending_orders para evitar ejecuciones contradictorias
        if out["closed_count"] > 0 or has_opposite:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                for sym_v in variants:
                    sb.table("pending_orders").update({
                        "status": "cancelled",
                        "cancelled_at": now_iso,
                        "updated_at": now_iso
                    }).eq("symbol", sym_v).eq("status", "pending").execute()
                log_info(MODULE, f"🧹 Órdenes pendientes canceladas para {binance_symbol}")
            except Exception as cancel_e:
                log_warning(MODULE, f"Error cancelando órdenes huérfanas: {cancel_e}")

                # REGLA 7: Cooldown if closed with loss
                if pnl < 0:
                    BOT_STATE.last_close_cycles[binance_symbol] = BOT_STATE.current_cycle

            except Exception as e:
                log_error(MODULE, f"Error cerrando posición {pos.get('id')}: {e}")

    except Exception as e:
        log_error(MODULE, f"Error cerrando posiciones crypto: {e}")

    return out


def _save_candle_order_crypto(sb, binance_symbol, action, strategy_code, price, pattern, tf, mode, quantity=0, sl=0.0, tp1=0.0, tp2=0.0):
    """Save order record for crypto candle signal."""
    try:
        sym = normalize_crypto_symbol(binance_symbol)
        price_f = float(price or 0)
        qty_f = float(quantity or 0)
        
        # Obtener snap desde cache si no viene
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        snap = MARKET_SNAPSHOT_CACHE.get(binance_symbol, {})
        
        sl_f, tp1_f, tp2_f = _ensure_crypto_sl_tp(price_f, action, snap=snap)
        row = {
            "symbol": sym,
            "side": action,
            "order_type": "MARKET",
            "status": "open",
            "entry_price": price_f,
            "stop_loss_price": sl_f,
            "take_profit_price": tp2_f, # Full TP
            "stop_price": sl_f,
            "limit_price": tp2_f,
            "rule_code": strategy_code,
            "quantity": qty_f,
            "is_paper": mode == "paper",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        res = sb.table("orders").insert(row).execute()
        if not res.data:
            return None
        oid = res.data[0].get("id")
        return str(oid) if oid else None
    except Exception as e:
        log_error(MODULE, f"CRITICAL: Crypto Order save failed to Supabase: {e}")
        return None

def _save_candle_position_crypto(sb, binance_symbol, action, strategy_code, price, pattern, tf, order_id, quantity=0, sl=0.0, tp1=0.0, tp2=0.0) -> bool:
    """Save position record for crypto candle signal. Returns True si la fila quedó en Supabase."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        
        side = "LONG" if action == "BUY" else "SHORT"
        sym = normalize_crypto_symbol(binance_symbol)
        price_f = float(price or 0)
        qty_f = float(quantity or 0)
        # NUEVO: Signo algebraico para la cantidad (Negativo para SELL/SHORT)
        final_qty = abs(qty_f) if action == "BUY" else -abs(qty_f)
        
        # Obtener snap desde cache si no viene
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        snap = MARKET_SNAPSHOT_CACHE.get(binance_symbol, {})
        
        sl_f, tp1_f, tp2_f = _ensure_crypto_sl_tp(price_f, action, snap=snap)
        oid = _order_uuid_for_position(order_id)

        payload = {
            "symbol": sym,
            "side": side,
            "entry_price": price_f,
            "avg_entry_price": price_f,
            "current_price": price_f,
            "size": final_qty if final_qty != 0 else (1.0 if action == "BUY" else -1.0),
            "stop_loss": sl_f,
            "sl_price": sl_f,
            "sl_backstop_price": sl_f,
            "sl_type": "backstop",
            "sl_dynamic_price": None,
            "highest_price_reached": price_f,
            "lowest_price_reached": price_f,
            "take_profit": tp2_f,
            "tp_partial_price": tp1_f,
            "tp_full_price": tp2_f,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "status": "open",
            "rule_code": strategy_code,
            "rule_entry": strategy_code,
            "regime_entry": "candle_signal",
            "opened_at": now_iso,
        }
        if oid:
            payload["order_id"] = oid

        res = sb.table("positions").insert(payload).execute()
        
        if not res.data:
            log_error(MODULE, f"CRITICAL: Supabase rejected position insert for {sym}")
            return False
        log_info(MODULE, f"💾 Posición guardada en DB: {sym} ID:{res.data[0]['id'][:8]}...")
        return True

    except Exception as e:
        log_error(MODULE, f"CRITICAL: Failed to save crypto position to Supabase: {e}\n{traceback.format_exc()}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  FOREX — Execute via cTrader (paper or live)
# ═══════════════════════════════════════════════════════════════════════════════

def execute_forex_signal(
    pair: str,
    pattern: PatternResult,
    timeframe: str,
    candle_data: dict,
    fib_zone: int = 0,
) -> dict:
    """
    Execute a candle signal for Forex.
    
    Steps:
      1. Close ALL active positions for this pair
      2. Open 1 new position (paper or live via cTrader)
    """
    sb = get_supabase()
    action = pattern.action
    strategy_code = _get_strategy_code("forex", action)
    now_iso = datetime.now(timezone.utc).isoformat()
    price = candle_data.get("close", 0)

    log_info(MODULE,
        f"🕯️ FOREX CANDLE SIGNAL: {action} {pair} | "
        f"Pattern: {pattern.pattern_name} (ID:{pattern.pattern_id}) | "
        f"TF: {timeframe} | Confidence: {pattern.confidence:.0f} | "
        f"Fib Zone: {fib_zone:+d}"
    )

    # ── GUARD #3: Anti-spam de señales Forex (Corrección #3) ──
    signal_check = check_signal_interval(pair, action)
    if not signal_check['allowed']:
        log_info(MODULE, f"🚫 SIGNAL GUARD (FOREX): {signal_check['reason']}")
        return {"success": False, "reason": "signal_spam_guard", "pair": pair}

    # ── GUARD #2: Cooldown post-SL Forex (Corrección #2) ──
    open_pos_res = sb.table("forex_positions").select("id, symbol, side").eq("status", "open").execute()
    open_pos_list = open_pos_res.data or []
    guard_check = can_open_position(
        symbol=pair,
        direction='long' if action == 'BUY' else 'short',
        market_type='forex_futures',
        open_positions=open_pos_list,
    )
    if not guard_check['allowed']:
        log_info(MODULE, f"🚫 POSITION GUARD (FOREX): {guard_check['reason']}")
        return {"success": False, "reason": "position_guard", "pair": pair, "detail": guard_check['reason']}

    # ── STEP 1: Hedge OFF (Netting) ──
    # Si hay opuestas, cerramos todo lo de la dirección contraria antes de seguir
    opp_side = "short" if action == "BUY" else "long"
    _close_all_positions_forex(pair, strategy_code, price, only_side=opp_side)
    
    # ── STEP 2: Reglas Multi-layer (Misma estrategia) ──
    existing_same = sb.table("forex_positions").select("*").eq("symbol", pair).eq("status", "open").eq("rule_code", strategy_code).execute().data or []
    
    if existing_same:
        # Regla 1: 1 por vela
        last_pos = sorted(existing_same, key=lambda x: x['opened_at'], reverse=True)[0]
        raw_date = last_pos['opened_at']
        try:
            if '.' in raw_date:
                base, rest = raw_date.split('.', 1)
                import re
                match = re.match(r"(\d+)(.*)", rest)
                if match:
                    ms, tz = match.groups()
                    ms = ms.ljust(6, '0')[:6] 
                    raw_date = f"{base}.{ms}{tz}"
            ts = raw_date.replace('Z', '+00:00')
            opened_at = datetime.fromisoformat(ts)
        except Exception as de:
            opened_at = datetime.now(timezone.utc) - timedelta(days=1)
            
        now = datetime.now(timezone.utc)
        
        # En Forex, TF suele ser 4H o 1D en candle_worker, pero detectamos 15m/1H en otros
        # Para Forex general usamos 1H como vela de seguridad si no viene TF
        tf_h = 4 if timeframe == "4H" else (24 if timeframe == "1D" else 0.25) # 15m = 0.25h
        candle_start = now - timedelta(hours=now.hour % tf_h if tf_h >= 1 else 0, 
                                        minutes=now.minute % (tf_h*60) if tf_h < 1 else now.minute,
                                        seconds=now.second, microseconds=now.microsecond)
        
        if opened_at >= candle_start:
            log_info(MODULE, f"⏸️ Omitiendo Forex {pair} {strategy_code}: Ya se abrió en esta vela.")
            return {"success": False, "reason": "one_trade_per_candle"}

        # Regla 2: Mejora de precio
        last_entry = float(last_pos.get('entry_price', 0))
        if action == "BUY" and price >= last_entry:
            log_info(MODULE, f"⏸️ Omitiendo Forex BUY {pair}: Precio {price} >= {last_entry}")
            return {"success": False, "reason": "price_improvement"}
        if action == "SELL" and price <= last_entry:
            log_info(MODULE, f"⏸️ Omitiendo Forex SELL {pair}: Precio {price} <= {last_entry}")
            return {"success": False, "reason": "price_improvement"}
            
        log_info(MODULE, f"💎 Agregando capa Forex {len(existing_same)+1} para {pair}")
    
    # ── CHECK 1: Limit per symbol (Forex) ──
    from app.core.supabase_client import get_risk_config
    risk_config = get_risk_config()
    max_per_symbol = int(risk_config.get('max_positions_per_symbol', 4))
    
    total_open_symbol = sb.table("forex_positions").select("id", count='exact').eq("symbol", pair).eq("status", "open").execute().count
    
    if total_open_symbol >= max_per_symbol:
        log_warning(MODULE, f"🚫 LÍMITE ALCANZADO para {pair}: {total_open_symbol}/{max_per_symbol} posiciones.")
        return {
            "success": False,
            "reason": "max_positions_per_symbol_reached",
            "pair": pair,
        }

    # ── CHECK 2: Total Market Risk Limit ──
    from app.strategy.risk_controls import check_total_market_risk
    from app.core.memory_store import BOT_STATE
    global_capital = float(BOT_STATE.config_cache.get('capital_total', 5000))
    
    risk_check = check_total_market_risk('forex', global_capital, sb)
    if not risk_check["passed"]:
        log_warning(MODULE, f"🚫 RIESGO TOTAL ALCANZADO (FOREX): {risk_check['reason']}")
        return {
            "success": False,
            "reason": "max_total_risk_reached",
            "pair": pair,
            "detail": risk_check["reason"]
        }

    # ── STEP 2: Open new position ──
    mode = os.getenv("FOREX_MODE", "paper")

    # Calculate size based on dynamic capital manager (Interés Compuesto)
    from app.core.capital_manager import get_total_operating_capital
    capital = get_total_operating_capital('forex')
    
    # Risk % is used as the investment portion per trade
    inv_pct = 2.0 # Usando 2% base para forex compounding
    leverage = 100.0
    
    target_inv = capital * (inv_pct / 100) # e.g. $20.00 if capital is $1000
    
    # Notional = Inversion * Leverage
    target_notional = target_inv * leverage # e.g. $500.00
    
    # Contract size: 100k for currencies, usually 100 for Gold (XAU)
    multiplier = 100.0 if "XAU" in pair.upper() else 100000.0
    pip_size = 0.01 if "JPY" in pair.upper() or "XAU" in pair.upper() else 0.0001
    
    # Notional = Lots * Multiplier * Price
    # Lots = Notional / (Multiplier * Price)
    lots = target_notional / (multiplier * price) if price > 0 else 0.01
    
    # Rounding and limits
    lots = round(max(lots, 0.01), 3)
    if "XAU" not in pair.upper():
        lots = round(lots, 2) # Standard forex lots
    
    lots = min(lots, 10.0)

    # SL/TP calculation
    atr = 20 * pip_size  # fallback ATR
    if action == "BUY":
        sl = round(price - atr * 2, 6)
        tp = round(price + atr * 3, 6)
    else:
        sl = round(price + atr * 2, 6)
        tp = round(price - atr * 3, 6)

    # Aplicar signo algebraico a los lotes (Negativo para SELL)
    final_lots = -abs(lots) if action == "SELL" else abs(lots)

    # Save position
    pos_data = {
        "symbol": pair,
        "side": action.lower(),
        "lots": final_lots,
        "entry_price": price,
        "sl_price": sl,
        "tp_price": tp,
        "status": "open",
        "mode": mode,
        "rule_code": strategy_code,
        "opened_at": now_iso,
    }
    try:
        sb.table("forex_positions").insert(pos_data).execute()
    except Exception as e:
        log_error(MODULE, f"Forex position save failed: {e}")
        return {"success": False, "reason": str(e)}

    mode_str = f"[{mode.upper()}]"
    log_info(MODULE,
        f"{mode_str} ✅ Forex {action} {pair} @ {price:.5f} | "
        f"Lots: {final_lots} | SL: {sl:.5f} | TP: {tp:.5f} | Strategy: {strategy_code}"
    )

    _send_telegram_sync(
        f"🕯️ FOREX CANDLE SIGNAL\n"
        f"{'🟢 BUY' if action == 'BUY' else '🔴 SELL'} {pair}\n"
        f"Patrón: {pattern.pattern_name}\n"
        f"Temporalidad: {timeframe}\n"
        f"Confianza: {pattern.confidence:.0f}%\n"
        f"Estrategia: {strategy_code}\n"
        f"Precio: {price:.5f}\n"
        f"SL: {sl:.5f} | TP: {tp:.5f}\n"
        f"Modo: {mode.upper()}"
    )

    return {"success": True, "action": action, "pair": pair, "strategy": strategy_code}


def _close_all_positions_forex(pair: str, strategy_code: str, current_price: float, only_side: str = None):
    """Close active forex positions for a pair. Handles synonyms (buy/long, sell/short)."""
    sb = get_supabase()
    try:
        res = sb.table("forex_positions").select("*").eq("symbol", pair).eq("status", "open").execute()
        positions = res.data or []

        if only_side:
            side_map = {
                "long": ["long", "buy"],
                "short": ["short", "sell"]
            }
            targets = side_map.get(only_side.lower(), [only_side.lower()])
            positions = [p for p in positions if p.get("side", "").lower() in targets]

        if not positions:
            return

        log_info(MODULE,
            f"🔄 Cerrando TODAS las {len(positions)} posiciones activas de {pair} "
            f"(nueva señal detectada → {strategy_code})"
        )

        pip_size = 0.0001 if "JPY" not in pair and "XAU" not in pair else 0.01
        pip_val = 10.0 if "JPY" not in pair and "XAU" not in pair else 1.0

        now_iso = datetime.now(timezone.utc).isoformat()
        for pos in positions:
            try:
                entry = float(pos.get("entry_price", 0))
                lots = float(pos.get("lots", 0.01))
                side = pos.get("side", "long").lower()

                pips_pnl = (current_price - entry) / pip_size if side == "long" else (entry - current_price) / pip_size
                pnl_usd = pips_pnl * pip_val * abs(lots)

                sb.table("forex_positions").update({
                    "status": "closed",
                    "current_price": current_price,
                    "close_reason": f"candle_signal_{strategy_code}",
                    "pnl_usd": round(pnl_usd, 2),
                    "pnl_pips": round(pips_pnl, 1),
                    "closed_at": now_iso,
                }).eq("id", pos["id"]).execute()

                log_info(MODULE, f"  ↳ Cerrada forex {pos['id'][:8]}... side={side} PnL: {pnl_usd:.2f} USD ({pips_pnl:.1f} pips)")

                # REGLA 7: Cooldown if closed with loss
                from app.core.memory_store import BOT_STATE
                if pnl_usd < 0:
                    BOT_STATE.last_close_cycles[pair] = BOT_STATE.current_cycle

            except Exception as e:
                log_error(MODULE, f"Error cerrando forex pos {pos.get('id')}: {e}")

    except Exception as e:
        log_error(MODULE, f"Error cerrando posiciones forex: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  STOCKS — Execute via Paper/IB
# ═══════════════════════════════════════════════════════════════════════════════

def execute_stocks_signal(
    ticker: str,
    pattern: PatternResult,
    timeframe: str,
    candle_data: dict,
    pool_type: str = "HOT",
    fib_zone: int = 0,
) -> dict:
    """
    Execute a candle signal for Stocks.
    
    Strategies:
      PRO: Inversiones Pro / BUY-V01, SELL-V02
      HOT: Hot by Volume  / BUY-V03, SELL-V04
    
    Steps:
      1. Close ALL active positions for this ticker
      2. Open 1 new MARKET position
    """
    sb = get_supabase()
    action = pattern.action
    strategy_code = _get_strategy_code("stocks", action, pool_type)
    now_iso = datetime.now(timezone.utc).isoformat()
    price = candle_data.get("close", 0)

    if price <= 0:
        return {"success": False, "reason": "Precio inválido"}

    log_info(MODULE,
        f"🕯️ STOCKS CANDLE SIGNAL: {action} {ticker} | "
        f"Pattern: {pattern.pattern_name} (ID:{pattern.pattern_id}) | "
        f"TF: {timeframe} | Pool: {pool_type} | Strategy: {strategy_code} | "
        f"Fib Zone: {fib_zone:+d}"
    )

    # ── STEP 1: Multi-layer vs Reversal ──
    # Para Stocks solo tenemos BUY signals (Inversiones Pro / BUY)
    # Por lo que no hay "opposite" como tal en short, pero cerramos si estamos refrescando.
    
    # Para Stocks, usamos group_name como identificador de estrategia
    group_id = f"Candle Signal {pool_type} {strategy_code}"
    existing_same = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").eq("group_name", group_id).execute().data or []
    
    if existing_same:
        # Regla 1: 1 por vela
        last_pos = sorted(existing_same, key=lambda x: x['first_buy_at'], reverse=True)[0]
        raw_date = last_pos['first_buy_at']
        try:
            if '.' in raw_date:
                base, rest = raw_date.split('.', 1)
                import re
                match = re.match(r"(\d+)(.*)", rest)
                if match:
                    ms, tz = match.groups()
                    ms = ms.ljust(6, '0')[:6] 
                    raw_date = f"{base}.{ms}{tz}"
            ts = raw_date.replace('Z', '+00:00')
            opened_at = datetime.fromisoformat(ts)
        except Exception as de:
            opened_at = datetime.now(timezone.utc) - timedelta(days=1)

        now = datetime.now(timezone.utc)
        
        # TF: 4H o 1D
        tf_h = 4 if timeframe == "4H" else 24
        candle_start = now - timedelta(hours=now.hour % tf_h, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)

        if opened_at >= candle_start:
            log_info(MODULE, f"⏸️ Omitiendo Stock {ticker} {strategy_code}: Ya se abrió en esta vela.")
            return {"success": False, "reason": "one_trade_per_candle"}

        # Regla 2: Mejora de precio (Solo BUY para stocks)
        last_entry = float(last_pos.get('avg_price', 0))
        if action == "BUY" and price >= last_entry:
            log_info(MODULE, f"⏸️ Omitiendo Stock BUY {ticker}: Precio {price} >= {last_entry}")
            return {"success": False, "reason": "price_improvement"}
            
        log_info(MODULE, f"💎 Agregando capa Stock {len(existing_same)+1} para {ticker}")
    else:
        _close_all_stocks_positions(ticker, price, strategy_code)

    # ── CHECK 1: Limit per symbol (Stocks) ──
    from app.core.supabase_client import get_risk_config
    risk_config = get_risk_config()
    max_per_symbol = int(risk_config.get('max_positions_per_symbol', 4))
    
    total_open_symbol = sb.table("stocks_positions").select("id", count='exact').eq("ticker", ticker).eq("status", "open").execute().count
    
    if total_open_symbol >= max_per_symbol:
        log_warning(MODULE, f"🚫 LÍMITE ALCANZADO para {ticker}: {total_open_symbol}/{max_per_symbol} posiciones.")
        return {
            "success": False,
            "reason": "max_positions_per_symbol_reached",
            "pair": ticker,
        }

    # ── STEP 2: Open new position (only if BUY — for SELL we only close) ──
    if action == "BUY":
        # 1. Obtener capital operativo dinámico (Interés Compuesto)
        from app.core.capital_manager import get_total_operating_capital
        capital = get_total_operating_capital('stocks')
        inv_pct = 2.0  # 2% de porción por trade
        
        # 2. Calcular shares con la regla profesional (múltiplos de 5)
        shares = _calculate_shares(capital, inv_pct / 100, price)
        
        if shares < 5:
            log_warning(MODULE, f"🚫 Capital insuficiente para comprar el lote mínimo de 5 acciones de {ticker} (${capital*inv_pct:.0f} vs ${5*price:.0f})")
            return {"success": False, "reason": "insufficient_capital_for_lot_5"}

        # SL/TP
        atr_est = price * 0.02
        sl = round(price - atr_est * 2.0, 2)
        tp = round(price + atr_est * 2.0 * 2.5, 2)

        # Save order
        sb.table("stocks_orders").insert({
            "ticker": ticker,
            "group_name": f"Candle Signal {pool_type}",
            "rule_code": strategy_code,
            "order_type": "market",
            "direction": "buy",
            "shares": shares,
            "market_price": price,
            "status": "filled",
            "filled_price": price,
            "filled_at": now_iso,
            "created_at": now_iso,
        }).execute()

        # Aplicar signo algebraico (Negativo para SHORT/SELL)
        final_shares = int(shares)
        if action == "SELL":
             final_shares = -abs(final_shares)
        else:
             final_shares = abs(final_shares)

        # Save position
        sb.table("stocks_positions").insert({
            "ticker": ticker,
            "group_name": f"Candle Signal {pool_type} {strategy_code}",
            "direction": "long" if action == "BUY" else "short",
            "shares": final_shares,
            "avg_price": price,
            "total_cost": round(abs(final_shares) * price, 2),
            "current_price": price,
            "stop_loss": sl,
            "take_profit": tp,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "dca_count": 0,
            "first_buy_at": now_iso,
            "updated_at": now_iso,
            "status": "open",
        }).execute()

        log_info(MODULE,
            f"✅ Stocks BUY {ticker} x{shares} @ ${price:.2f} | "
            f"SL: ${sl:.2f} | TP: ${tp:.2f} | Strategy: {strategy_code}"
        )
    else:
        # SELL signals only close positions — we don't short stocks in this model
        log_info(MODULE, f"✅ Stocks SELL signal processed — positions closed for {ticker}")

    _send_telegram_sync(
        f"🕯️ STOCKS CANDLE SIGNAL\n"
        f"{'🟢 BUY' if action == 'BUY' else '🔴 SELL'} {ticker}\n"
        f"Patrón: {pattern.pattern_name}\n"
        f"Temporalidad: {timeframe}\n"
        f"Confianza: {pattern.confidence:.0f}%\n"
        f"Estrategia: {strategy_code}\n"
        f"Pool: {pool_type}\n"
        f"Precio: ${price:.2f}"
    )

    return {"success": True, "action": action, "ticker": ticker, "strategy": strategy_code}


def _close_all_stocks_positions(ticker: str, price: float, strategy_code: str):
    """Close ALL open stock positions for a ticker (triggered by SELL signal)."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
        positions = res.data or []

        if not positions:
            return

        log_info(MODULE,
            f"🔄 Cerrando {len(positions)} posiciones LONG de {ticker} "
            f"(SELL signal detectada → {strategy_code})"
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        for pos in positions:
            try:
                def safe_float(v, default=0.0):
                    try:
                        return float(v) if v is not None else default
                    except:
                        return default

                avg = safe_float(pos.get("avg_price") or pos.get("entry_price"))
                shares = safe_float(pos.get("shares"))
                pnl = (price - avg) * shares
                pnl_pct = ((price - avg) / avg * 100) if avg > 0 else 0

                sb.table("stocks_positions").update({
                    "status": "closed",
                    "current_price": price,
                    "unrealized_pnl": round(pnl, 2),
                    "unrealized_pnl_pct": round(pnl_pct, 2),
                    "updated_at": now_iso,
                }).eq("id", pos["id"]).execute()

                # Also record the sell order
                sb.table("stocks_orders").insert({
                    "ticker": ticker,
                    "group_name": "Candle Signal Close",
                    "rule_code": strategy_code,
                    "order_type": "market",
                    "direction": "sell",
                    "shares": int(shares),
                    "market_price": price,
                    "status": "filled",
                    "filled_price": price,
                    "filled_at": now_iso,
                    "created_at": now_iso,
                }).execute()

                log_info(MODULE,
                    f"  ↳ Cerrada {ticker} x{shares:.0f} "
                    f"avg=${avg:.2f} exit=${price:.2f} PnL=${pnl:.2f} ({pnl_pct:.2f}%)"
                )

                # REGLA 7: Cooldown if closed with loss
                from app.core.memory_store import BOT_STATE
                if pnl < 0:
                    BOT_STATE.last_close_cycles[ticker] = BOT_STATE.current_cycle
            except Exception as e:
                log_error(MODULE, f"Error cerrando stocks pos {pos.get('id')}: {e}")

    except Exception as e:
        log_error(MODULE, f"Error buscando stocks positions: {e}")


def _close_opposite_stocks_positions(ticker: str, price: float, strategy_code: str, opposite_dir: str):
    """Close stock positions in opposite direction (if shorting were supported)."""
    sb = get_supabase()
    try:
        res = (
            sb.table("stocks_positions")
            .select("*")
            .eq("ticker", ticker)
            .eq("status", "open")
            .eq("direction", opposite_dir)
            .execute()
        )
        if not res.data:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        for pos in res.data:
            avg = float(pos.get("avg_price", 0))
            shares = float(pos.get("shares", 0))
            pnl = (price - avg) * shares if pos.get("direction") == "long" else (avg - price) * shares

            sb.table("stocks_positions").update({
                "status": "closed",
                "current_price": price,
                "unrealized_pnl": round(pnl, 2),
                "updated_at": now_iso,
            }).eq("id", pos["id"]).execute()

    except Exception as e:
        log_error(MODULE, f"Error closing opposite stocks positions: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  UNIFIED DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════

def execute_candle_signal(
    market: str,
    pair_or_ticker: str,
    pattern: PatternResult,
    timeframe: str,
    candle_data: dict,
    pool_type: str = "HOT",
) -> dict:
    """
    Unified dispatcher — routes candle signals to the correct market executor.
    """
    if pattern.action not in ("BUY", "SELL"):
        return {"success": False, "reason": f"Action is {pattern.action}, not BUY/SELL"}

    # ── REGLA 7: COOLDOWN PROTECTION ──
    # Evitar re-entrar si acabamos de cerrar con pérdida recientemente
    from app.core.memory_store import BOT_STATE
    last_close = BOT_STATE.last_close_cycles.get(pair_or_ticker, 0)
    current_cycle = BOT_STATE.current_cycle
    
    market_type_map = {
        'crypto': 'crypto_futures',
        'forex': 'forex_futures',
        'stocks': 'stocks_spot'
    }
    m_type = market_type_map.get(market, 'crypto_futures')
    
    cd_check = check_cooldown(pair_or_ticker, last_close, current_cycle, m_type)
    if cd_check['in_cooldown']:
        log_info("PROTECTION", f"🚫 COOLDOWN [{pair_or_ticker}]: {cd_check['reason']}")
        return {"success": False, "reason": "cooldown_active"}

    # ── FIBONACCI BAND ZONE FILTER ──
    fib_zone = _get_fibonacci_zone(market, pair_or_ticker)
    zone_valid = _validate_fibonacci_zone(pattern.action, fib_zone)

    if not zone_valid:
        strategy_code = _get_strategy_code(market, pattern.action, pool_type)
        log_info(MODULE,
            f"🚫 FIBONACCI FILTER BLOCKED: {pattern.action} {pair_or_ticker} | "
            f"Zone: {fib_zone:+d} | Pattern: {pattern.pattern_name} | "
            f"Strategy: {strategy_code} | "
            f"Allowed zones for {pattern.action}: "
            f"{'≤ +2' if pattern.action == 'BUY' else '≥ -2'}"
        )
        # Save to audit as blocked
        _save_candle_signal(market, pair_or_ticker, pattern, timeframe, candle_data, pool_type,
                           fib_zone=fib_zone, blocked=True)
        return {
            "success": False,
            "reason": f"Fibonacci zone {fib_zone:+d} not valid for {pattern.action}",
            "fib_zone": fib_zone,
        }

    # Save signal to candle_signals table for audit (passed filter)
    _save_candle_signal(market, pair_or_ticker, pattern, timeframe, candle_data, pool_type,
                       fib_zone=fib_zone, blocked=False)

    if market == "crypto":
        return execute_crypto_signal(pair_or_ticker, pattern, timeframe, candle_data, fib_zone)
    elif market == "forex":
        return execute_forex_signal(pair_or_ticker, pattern, timeframe, candle_data, fib_zone)
    elif market == "stocks":
        return execute_stocks_signal(pair_or_ticker, pattern, timeframe, candle_data, pool_type, fib_zone)
    else:
        return {"success": False, "reason": f"Unknown market: {market}"}


def _save_candle_signal(market, pair, pattern, timeframe, candle_data, pool_type,
                       fib_zone: int = 0, blocked: bool = False):
    """Persist signal to candle_signals audit table."""
    try:
        sb = get_supabase()
        strategy_code = _get_strategy_code(market, pattern.action, pool_type)

        sb.table("candle_signals").insert({
            "pair": pair,
            "market": market,
            "timeframe": timeframe,
            "pattern_id": pattern.pattern_id,
            "pattern_name": pattern.pattern_name,
            "signal_type": pattern.signal,
            "action": pattern.action,
            "confidence": round(pattern.confidence, 1),
            "candles_used": pattern.candles_used,
            "strategy_code": strategy_code,
            "pool_type": pool_type if market == "stocks" else None,
            "ohlc_open": candle_data.get("open"),
            "ohlc_high": candle_data.get("high"),
            "ohlc_low": candle_data.get("low"),
            "ohlc_close": candle_data.get("close"),
            "ohlc_volume": candle_data.get("volume"),
            "executed": not blocked,
            "result_status": "blocked_fib_zone" if blocked else "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log_warning(MODULE, f"Failed to save candle signal audit: {e}")
