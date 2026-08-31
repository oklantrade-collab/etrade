"""
Monitor de posiciones para ciclo de 5m.
Detecta liquidaciones, SL/TP ejecutados por Binance,
y cualquier discrepancia entre el bot y el exchange.
"""
import asyncio
import pandas as pd
from datetime import datetime, timezone
from app.core.memory_store import BOT_STATE
from app.core.logger import log_info, log_warning, log_error
from app.core.crypto_symbols import normalize_crypto_symbol, crypto_symbol_match_variants
from app.strategy.capital_protection import (
    ProtectionState,
    evaluate_break_even,
    evaluate_trailing_stop,
    PROTECTION_CONFIG,
    calculate_pnl,
    evaluate_all_protections
)
from app.strategy.position_guards import (
    check_time_based_sl,
    register_sl_event,
    update_peak_pnl,
)

from app.core.symbol_state import SymbolStateMachine

MODULE = "POSITION_MONITOR"
sm = SymbolStateMachine.get_instance()
_CENTINELA_MONITOR_CRYPTO = None
async def check_signal_reversal(
    position:     dict,
    current_mtf:  float,
    current_price: float,
    config:       dict,
    snap:         dict = None
) -> dict:
    """
    Cierra la posición cuando la EMA3/EMA9 en 5 minutos gira en contra
    ÚNICAMENTE si hay ganancia positiva (pnl_pct > 0).

    Nunca cierra con pérdida por esta regla (para pérdidas -> SL).
    No cierra por titubeos de MTF o 15M si la EMA3 en 5m sigue a favor.
    """
    if not config.get('exit_on_signal_reversal', True):
        return {'should_exit': False}

    if not position:
        return {'should_exit': False}

    side  = (position.get('side') or '').lower()
    entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    
    if entry == 0:
        return {'should_exit': False}

    # Calcular P&L actual (%)
    if side in ('long', 'buy'):
        pnl_pct = (current_price - entry) / entry * 100
    else:
        pnl_pct = (entry - current_price) / entry * 100

    # 1. Obtener EMAs rápidas de 5M (EMA3 y EMA9)
    from app.core.memory_store import MEMORY_STORE
    symbol = position.get('symbol')
    df_5m = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df') if symbol else None
    
    ema3 = ema9 = 0.0
    if df_5m is not None and not df_5m.empty:
        if 'ema_3' in df_5m.columns:
            ema3 = float(df_5m['ema_3'].iloc[-1])
        else:
            ema3 = float(df_5m['close'].ewm(span=3, adjust=False).mean().iloc[-1])
            
        if 'ema_9' in df_5m.columns:
            ema9 = float(df_5m['ema_9'].iloc[-1])
        else:
            ema9 = float(df_5m['close'].ewm(span=9, adjust=False).mean().iloc[-1])
    elif snap:
        # Fallback si no hay df_5m
        ema3 = float(snap.get('ema_3') or 0)
        ema9 = float(snap.get('ema_9') or 0)

    # 2. Verificar cruce en contra en 5M
    ema_reversed_5m = False
    if ema3 > 0 and ema9 > 0:
        if side in ('long', 'buy') and ema3 < ema9:
            ema_reversed_5m = True
        elif side in ('short', 'sell') and ema3 > ema9:
            ema_reversed_5m = True

    # 3. Regla estricta con Fee-Net Guard: Solo salir si PnL >= min_profit_pct (cobertura de comisión Binance)
    min_profit_pct = float(config.get('min_profit_exit_pct', 0.25))
    
    # Check if position is a cascade/rebote position
    origen = str(position.get('origen', '')).upper()
    rule_code = str(position.get('rule_code', ''))
    if origen == 'REBOTE' or rule_code.startswith(('AaReb', 'BbReb', 'REBOTE', 'Aa12')):
        return {'should_exit': False}
        
    if pnl_pct >= min_profit_pct and ema_reversed_5m:
        from app.strategy.candle_momentum_guard import should_allow_exit
        df_15m = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df') if symbol else None
        allow, allow_msg = should_allow_exit(
            position=position,
            current_price=current_price,
            df_15m=df_15m,
            df_5m=df_5m,
            exit_rule_id='early_profit_protect_ema_5m',
            market_type='crypto_futures',
            snap=snap
        )
        if not allow:
            log_info(MODULE, f"Early profit protect 5M suprimido para {symbol}: {allow_msg}")
            return {'should_exit': False}

        return {
            'should_exit': True,
            'reason': 'early_profit_protect_ema_5m',
            'exit_execution_type': 'MARKET_URGENT',
            'pnl_pct': round(pnl_pct, 4),
            'detail': f'Early Profit Protect (MARKET URGENTE): Cruce EMA3/EMA9 5M en contra (EMA3={ema3:.5f}, EMA9={ema9:.5f}) con P&L neto positivo (+{pnl_pct:.2f}% >= {min_profit_pct:.2f}%). Ejecutando cierre a mercado urgente.'
        }

    return {'should_exit': False}

async def check_sl_proximity_alert(
    symbol:        str,
    current_price: float,
    sl_price:      float,
    danger_threshold_pct: float = 3.0,
    escalation_drop_pct:  float = 1.0,
    pos_id:        str = ""
) -> None:
    """Envía alerta de SL cercano de forma inteligente para evitar spam."""
    # Normalizar símbolo para evitar duplicados por formato (BTC/USDT vs BTCUSDT)
    norm_symbol = symbol.replace("/", "").upper()
    alert_key = f"{norm_symbol}_{pos_id}" if pos_id else norm_symbol
    
    # Inicialización por símbolo solo si no existe
    if alert_key not in BOT_STATE.sl_alerts:
        BOT_STATE.sl_alerts[alert_key] = {
            'in_danger_zone':    False,
            'last_distance_pct': 100.0,
            'last_alert_sent':   None,
            'last_alert_price':  0.0
        }

    state = BOT_STATE.sl_alerts[alert_key]
    distance_pct = abs(current_price - sl_price) / sl_price * 100 if sl_price > 0 else 100

    currently_in_danger = distance_pct < danger_threshold_pct
    was_in_danger       = state['in_danger_zone']
    last_distance       = state['last_distance_pct']
    last_price          = state['last_alert_price']
    last_time           = state['last_alert_sent']

    from app.workers.alerts_service import send_telegram_message

    # --- PROTECCIÓN ANTI-SPAM EXTRA ---
    # Si el precio es IDÉNTICO al de la última alerta, no enviar nada (previene spam si hay datos estáticos)
    if currently_in_danger and abs(current_price - last_price) < 0.0001:
        return

    # Si se envió una alerta hace menos de 15 minutos con una distancia similar, esperar.
    # Excepción: si el peligro aumenta significativamente (> 1% de caída extra)
    now = datetime.now(timezone.utc)
    # is_recent = last_time and (now - last_time).total_seconds() < 900 # 15 mins (Opcional, ya tenemos price check)
    
    significant_drop = (last_distance - distance_pct >= escalation_drop_pct)

    # CASO 1: Primera vez que entra en zona
    if currently_in_danger and not was_in_danger:
        msg = (f"⚠️ PRECIO CERCANO AL SL [{norm_symbol}]\n"
               f"Precio: ${current_price:,.2f} → SL: ${sl_price:,.2f}\n"
               f"Distancia: {distance_pct:.1f}% — Monitorear")
        await send_telegram_message(msg)
        state['in_danger_zone']    = True
        state['last_distance_pct'] = distance_pct
        state['last_alert_price']  = current_price
        state['last_alert_sent']   = now
        log_warning(MODULE, f"SL Danger Zone START for {norm_symbol}: {distance_pct:.1f}%")
        return

    # CASO 2: Ya estaba en peligro, pero empeoró significativamente
    if currently_in_danger and was_in_danger and significant_drop:
        emoji = "🚨" if distance_pct < 1.0 else "🔴" if distance_pct < 2.0 else "⚠️"
        urgency = "PELIGRO CRÍTICO" if distance_pct < 1.0 else "PELIGRO ALTO" if distance_pct < 2.0 else "MONITOREAR"
        
        msg = (f"{emoji} SL MÁS CERCANO [{norm_symbol}]\n"
               f"Precio: ${current_price:,.2f} → SL: ${sl_price:,.2f}\n"
               f"Distancia: {distance_pct:.1f}% — {urgency}\n"
               f"(Antes: {last_distance:.1f}%)")
        await send_telegram_message(msg)
        state['last_distance_pct'] = distance_pct
        state['last_alert_price']  = current_price
        state['last_alert_sent']   = now
        log_warning(MODULE, f"SL Danger Zone ESCALATION for {norm_symbol}: {distance_pct:.1f}%")
        return

    # CASO 3: Salió de la zona de peligro
    if not currently_in_danger and was_in_danger:
        msg = (f"✅ ZONA DE PELIGRO SUPERADA [{norm_symbol}]\n"
               f"Precio: ${current_price:,.2f} → SL: ${sl_price:,.2f}\n"
               f"Distancia: {distance_pct:.1f}% — Riesgo normalizado")
        await send_telegram_message(msg)
        state['in_danger_zone']    = False
        state['last_distance_pct'] = distance_pct
        state['last_alert_price']  = current_price
        state['last_alert_sent']   = now
        log_info(MODULE, f"SL Danger Zone RECOVERY for {norm_symbol}: {distance_pct:.1f}%")
        return

async def check_margin_call_alert(
    symbol: str,
    pnl_usd: float,
    sb,
    pos_id: str = ""
) -> None:
    """Verifica si la posición amenaza el capital total de la cuenta."""
    try:
        # Obtener margin_call_alert_pct desde trading_config
        config_res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
        config = config_res.data or {}
        
        # Default 20% si no existe
        alert_pct = float(config.get('margin_call_alert_pct', 20.0))
        
        regime_params = config.get('regime_params') or {}
        # Obtener el balance del broker (usaremos el de crypto o forex según haya disponible)
        balance = float(regime_params.get('broker_balance') or regime_params.get('broker_balance_forex') or 1000.0)
        
        if balance <= 0:
            return
            
        # PNL USD es positivo, no hay amenaza
        if pnl_usd >= 0:
            return
            
        loss_pct_of_capital = (abs(pnl_usd) / balance) * 100
        
        # Evitar spam: solo enviar si cruzó el umbral y no se ha enviado recientemente
        if not hasattr(BOT_STATE, 'margin_alerts'):
            BOT_STATE.margin_alerts = {}
            
        norm_symbol = symbol.replace("/", "").upper()
        alert_key = f"{norm_symbol}_{pos_id}" if pos_id else norm_symbol
        last_alert = BOT_STATE.margin_alerts.get(alert_key, 0)
        
        # Alerta cada 5% adicional
        if loss_pct_of_capital >= alert_pct and (loss_pct_of_capital - last_alert) >= 5.0:
            from app.workers.alerts_service import send_telegram_message
            await send_telegram_message(
                f"🚨 ALERTA URGENTE (MARGIN CALL) 🚨\n"
                f"La posición en {symbol} está amenazando tu capital.\n"
                f"Pérdida Flotante: -${abs(pnl_usd):.2f}\n"
                f"Representa: {loss_pct_of_capital:.2f}% de tu balance total (${balance:.2f}).\n"
                f"El límite de seguridad es {alert_pct}%.\n"
                f"Revisa el margen disponible de inmediato."
            )
            BOT_STATE.margin_alerts[alert_key] = loss_pct_of_capital
            
    except Exception as e:
        log_error(MODULE, f"Error en check_margin_call_alert para {symbol}: {e}")

# Cache en memoria para estados de protección
_protection_cache = {}

async def check_sl_with_erep(
    symbol:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_4h:         pd.DataFrame,
    market_type:   str,
    supabase,
    df_5m:         pd.DataFrame = None,
) -> bool:
    """
    Verifica si el precio tocó el SL y decide si cerrar normalmente o activar EREP.

    Se llama en el ciclo de 15m SOLO cuando el precio está cerca o en el SL.
    """
    from app.strategy.erep_manager import evaluate_erep_phase, execute_erep_action
    
    sl_price = float(position.get('stop_loss_price') or
                     position.get('sl_dynamic_price') or
                     position.get('sl_price') or
                     position.get('stop_loss') or 0)
    side     = str(position.get('side', 'long'))
    is_long  = side.lower() in ('long', 'buy')

    if sl_price <= 0 and not bool(position.get('erep_active')):
        return False

    # ¿Tocó el SL?
    sl_touched = (
        (is_long  and current_price <= sl_price) or
        (not is_long and current_price >= sl_price)
    )

    erep_active = bool(position.get('erep_active'))

    if not sl_touched and not erep_active:
        return False  # Normal, sin acción

    async def open_position(symbol: str, side: str, size: float, price: float, reason: str, supabase):
        res = supabase.table("positions").select("*").eq("id", position["id"]).execute()
        if res.data:
            pos = res.data[0]
            q1 = float(pos.get("erep_q1") or pos.get("size") or 0)
            p1 = float(pos.get("erep_p1_price") or pos.get("entry_price") or 0)
            
            combined_size = q1 + size
            combined_price = (p1 * q1 + price * size) / combined_size
            
            supabase.table("positions").update({
                "size": combined_size,
                "entry_price": combined_price,
                "avg_entry_price": combined_price,
            }).eq("id", pos["id"]).execute()
            
            now = datetime.now(timezone.utc).isoformat()
            try:
                supabase.table('paper_trades').insert({
                    'symbol': symbol,
                    'side': pos['side'],
                    'entry_price': price,
                    'exit_price': price,
                    'total_pnl_usd': 0.0,
                    'total_pnl_pct': 0.0,
                    'close_reason': 'EREP_P2',
                    'closed_at': now,
                    'mode': 'paper',
                    'rule_code': 'EREP_P2'
                }).execute()
            except Exception as e:
                log_error("POSITION_MONITOR", f"Error inserting EREP order: {e}")

    async def close_position(*args, **kwargs):
        # Support both positional: close_position(symbol, price, reason, supabase)
        # and keyword: close_position(symbol, side, size, price, reason, supabase)
        price = current_price
        reason = 'erep_close'
        if len(args) >= 3:
            reason = args[2]
        if len(args) >= 2:
            price = args[1]
            
        if 'price' in kwargs:
            price = kwargs['price']
        if 'reason' in kwargs:
            reason = kwargs['reason']
        elif 'close_reason' in kwargs:
            reason = kwargs['close_reason']
            
        res = supabase.table("positions").select("*").eq("id", position["id"]).execute()
        if res.data:
            pos = res.data[0]
            await _execute_paper_close(pos, price, reason, supabase)

    # ── SI EREP YA ESTÁ ACTIVO ─────────────────
    if erep_active:
        action = evaluate_erep_phase(
            position, current_price,
            snap, df_15m, df_4h, market_type, df_5m
        )
        result = await execute_erep_action(
            action        = action,
            position      = position,
            current_price = current_price,
            symbol        = symbol,
            market_type   = market_type,
            supabase      = supabase,
            open_func     = open_position,
            close_func    = close_position,
        )
        return result.get('executed') == 'closed'

    # ── SL RECIÉN TOCADO ───────────────────────
    if sl_touched:
        sl_type = str(position.get('sl_type') or '')
        if sl_type.startswith('trailing'):
            entry = float(position.get('avg_entry_price') or position.get('entry_price') or current_price)
            side = str(position.get('side', 'long')).lower()
            pnl_usd = (current_price - entry) if side in ('long', 'buy') else (entry - current_price)
            
            if pnl_usd <= 0:
                log_info(MODULE, f"Trailing SL hit for {symbol}, but PNL<=0. Diverting to EREP unconditionally.")
                # Do NOT close here. Let it fall through to EREP setup below.
            else:
                await close_position(symbol, current_price, 'sl_trailing', supabase)
                return True
            
        entry = float(position.get('avg_entry_price') or position.get('entry_price') or current_price)
        from app.core.crypto_symbols import resolve_crypto_position_quantity
        q1 = resolve_crypto_position_quantity(supabase, position)
        
        supabase.table('positions').update({
            'erep_phase':   1,
            'erep_p1_price': entry,
            'erep_q1':      q1,
            'erep_market_type': market_type,
        }).eq('id', position['id']).execute()

        position['erep_phase']   = 1
        position['erep_p1_price'] = entry
        position['erep_q1']      = q1
        position['erep_market_type'] = market_type

        action = evaluate_erep_phase(
            position, current_price,
            snap, df_15m, df_4h, market_type, df_5m
        )

        if action['action'] == 'close_sl':
            await close_position(symbol, current_price, 'sl_normal', supabase)
            return True

        await execute_erep_action(
            action, position, current_price,
            symbol, market_type, supabase,
            open_position, close_position
        )
        return False

    return False


async def check_crypto_erep(
    symbol:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    supabase,
) -> bool:
    """
    EREP para Crypto.
    """
    from app.core.memory_store import get_memory_df
    df_5m  = get_memory_df(symbol, "5m")
    df_15m = get_memory_df(symbol, "15m")
    df_4h  = get_memory_df(symbol, "4h")
    
    return await check_sl_with_erep(
        symbol=symbol,
        position=position,
        current_price=current_price,
        snap=snap,
        df_15m=df_15m,
        df_4h=df_4h,
        market_type='crypto_futures',
        supabase=supabase,
        df_5m=df_5m
    )

async def trigger_trailing_stop_reentry(symbol, side, size, df_15m, supabase):
    """
    Plaza las órdenes LIMIT de re-entrada (Q1 a EMA9 y Q2 a EMA20)
    cuando el Trailing Stop cierra sin tocar la banda de Bollinger.
    """
    try:
        if df_15m is None or len(df_15m) < 20:
            return
            
        df = df_15m.copy()
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        last_row = df.iloc[-1]
        ema9 = float(last_row['ema9'])
        ema20 = float(last_row['ema20'])
        
        is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
        trade_type_val = 'swing_ema'
        mode_val = 'paper' # standard paper mode
        
        # Sizing 40/60
        orders = [
            {'limit_price': ema9, 'pct': 40, 'name': 'Order 1 (EMA9)'},
            {'limit_price': ema20, 'pct': 60, 'name': 'Order 2 (EMA20)'}
        ]
        
        from datetime import datetime, timezone, timedelta
        for op in orders:
            limit_px = round(op['limit_price'], 4 if is_forex else 8)
            qty_val = round(size * (op['pct'] / 100.0), 4 if is_forex else 8)
            
            if qty_val <= 0:
                continue
                
            new_order = {
                'symbol': symbol,
                'direction': side.lower(),
                'order_type': 'limit',
                'trade_type': trade_type_val,
                'rule_code': 'AaApexEma' if side.lower() in ('long', 'buy') else 'BbApexEma',
                'limit_price': limit_px,
                'sl_price': 0,
                'tp1_price': 0,
                'tp2_price': 0,
                'band_name': op['name'],
                'status': 'pending',
                'mode': mode_val,
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
                'sizing_pct': op['pct'] / 100.0,
                'timeframe': '15m',
                'movement_type': 'trend_ema',
                'signal_quality': 'high',
                'fib_zone_entry': 0
            }
            
            try:
                from app.strategy.swing_orders import enforce_global_limit_max
                import asyncio
                # Try to use current loop, or just run it safely if sync context
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(enforce_global_limit_max(supabase, mode_val, 5))
                except RuntimeError:
                    asyncio.run(enforce_global_limit_max(supabase, mode_val, 5))
            except Exception as e:
                pass
            
            supabase.table('pending_orders').insert(new_order).execute()
            log_info('TS_REENTRY', f"🎯 [TS RE-ENTRY LIMIT] {symbol} {side.upper()}: {op['name']} colocada a {limit_px} | Cantidad: {qty_val}")
            
            # Telegram notification
            try:
                from app.workers.alerts_service import send_telegram_message
                await send_telegram_message(
                    f"🎯 RE-ENTRADA TRAILING STOP [{symbol}]\n"
                    f"Dirección: {side.upper()}\n"
                    f"Nivel: {op['name']}\n"
                    f"Precio LIMIT: {limit_px}\n"
                    f"Cantidad: {qty_val}\n"
                    f"Modo: {mode_val.upper()}"
                )
            except Exception as tg_e:
                log_error('TS_REENTRY', f"Error enviando Telegram: {tg_e}")
    except Exception as e:
        log_error('TS_REENTRY', f"Error colocando órdenes de re-entrada para {symbol}: {e}")

async def check_protections(
    symbol:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    supabase
) -> bool:
    """
    Verifica y aplica las protecciones de Break-Even y Trailing Stop.
    Retorna True si la posición fue cerrada por el SL dinámico.
    """
    pos_id = str(position.get('id', symbol))

    # Inicializar estado si no existe
    if pos_id not in _protection_cache:
        # Resolver side
        side_raw = str(position.get('side') or 'long').lower()
        highest_band_reached = position.get('highest_band_reached') or ''
        bb_touched_val = 'bb_touched' in str(highest_band_reached)
        
        _protection_cache[pos_id] = ProtectionState(
            position_id  = pos_id,
            symbol       = symbol,
            side         = side_raw,
            entry_price  = float(position.get('avg_entry_price') or position.get('entry_price') or 0),
            current_sl   = float(position.get('sl_price') or position.get('stop_loss') or 0),
            original_sl  = float(position.get('sl_backstop_price') or position.get('sl_price') or 0),
            market_type  = 'crypto_futures',
            rule_code    = position.get('rule_code') or position.get('rule_entry') or '',
            bb_touched   = bb_touched_val
        )
        # Campos adicionales no presentes en el constructor base pero necesarios para el flujo
        state = _protection_cache[pos_id]
        state.remaining_size = float(abs(float(position.get('size') or 0)))

    state = _protection_cache[pos_id]
    state.cycles_open += 1
    
    # Asegurar que el SL en el estado coincida con el de la DB por si hubo cambios externos
    state.current_sl = float(position.get('sl_price') or position.get('stop_loss') or 0)

    # ── TRACK PEAK P&L (máximo P&L alcanzado durante la vida de la posición) ──
    entry_p = state.entry_price
    if entry_p > 0:
        is_long = state.side in ('long', 'buy')
        current_pnl_pct = ((current_price - entry_p) / entry_p * 100) if is_long else ((entry_p - current_price) / entry_p * 100)
        if current_pnl_pct > state.highest_pnl_pct:
            state.highest_pnl_pct = current_pnl_pct
            try:
                supabase.table('positions').update({
                    'peak_pnl_pct': round(current_pnl_pct, 4)
                }).eq('id', pos_id).execute()
            except Exception:
                pass  # Non-critical, silently continue

    # ── CARGAR DATOS ──────────────────────────
    from app.core.memory_store import get_memory_df
    df_15m = get_memory_df(symbol, "15m")
    df_5m = get_memory_df(symbol, "5m")

    # ── CHECK 1: Break-Even ───────────────────
    be = evaluate_break_even(state, current_price, df_15m, df_5m)
    if be['action'] == 'activate_be':
        new_sl = be['be_price']
        try:
            supabase.table('positions').update({
                'sl_price': new_sl,
                'stop_loss': new_sl,
                'sl_type': 'break_even',
                'sl_dynamic_price': new_sl,
                'protection_activated': True
            }).eq('id', pos_id).execute()

            state.be_activated = True
            state.be_price     = new_sl
            state.current_sl   = new_sl
            position['sl_price'] = new_sl # Update local ref

            log_info('PROTECTION', f'🎯 BE [{symbol}]: {be["reason"]}')
            
            from app.workers.alerts_service import send_telegram_message
            await send_telegram_message(
                f'🎯 BREAK-EVEN ACTIVADO [{symbol}]\n'
                f'Razón: {be["reason"]}\n'
                f'SL movido a: {new_sl:.6f}\n'
                f'Precio actual: {current_price:.6f}'
            )
        except Exception as e:
            log_error(MODULE, f"Error actualizando BE para {symbol}: {e}")

    # ── CHECK 1.4.5: STOP LOSS VIRTUAL FIBONACCI (eTrade 100% Control, Crypto & Forex) ──
    try:
        from app.strategy.quantum_squeeze_hedge import evaluate_fib_band_virtual_sl
        fib_sl_res = evaluate_fib_band_virtual_sl(position, df_15m, current_price, symbol)
        if fib_sl_res and fib_sl_res.get('action') == 'close_virtual_fib_sl':
            log_info('PROTECTION', f"🛡️ [VIRTUAL FIB SL TRIGGERED] [{symbol}]: {fib_sl_res.get('reason')}")
            closed = await _execute_paper_close(position, current_price, 'qshr_fib_band_virtual_sl', supabase)
            if closed:
                return
    except Exception as fib_sl_e:
        log_error(MODULE, f"Error evaluando SL Virtual Fibonacci Crypto {symbol}: {fib_sl_e}")

    # ── CHECK 1.5: Motor Dual de Salida (Bollinger Exhaustion & CASCADA Fib Stagnation) ──
    try:
        from app.strategy.quantum_squeeze_hedge import evaluate_qshr_trailing_and_exit
        dual_exit = evaluate_qshr_trailing_and_exit(position, df_5m, df_15m, current_price, symbol, market_type='crypto')
        if dual_exit:
            action = dual_exit.get('action')
            if action in ('close_bollinger_exhaustion', 'close_cascada_fib_stagnation'):
                log_info('PROTECTION', f"🎯 [DUAL EXIT {action.upper()}] [{symbol}]: {dual_exit.get('reason')}")
                closed = await _execute_paper_close(position, current_price, dual_exit.get('rule_code', 'dual_exit'), supabase)
                if closed:
                    return
            elif action == 'adjust_trailing_sl':
                new_sl = float(dual_exit.get('sl_price', 0))
                if new_sl > 0:
                    try:
                        supabase.table('positions').update({
                            'sl_price': new_sl,
                            'stop_loss': new_sl,
                            'trailing_sl_price': new_sl,
                            'sl_type': 'cascada_fib_trail',
                            'protection_activated': True
                        }).eq('id', pos_id).execute()
                        state.current_sl = new_sl
                        position['sl_price'] = new_sl
                        log_info('PROTECTION', f"📈 [CASCADA FIB SL SYNC] [{symbol}]: SL ceñido a {new_sl}")
                    except Exception as sl_e:
                        log_error(MODULE, f"Error actualizando Fib SL Crypto {pos_id}: {sl_e}")
    except Exception as dual_e:
        log_error(MODULE, f"Error evaluando Dual Exit Crypto {symbol}: {dual_e}")

    # ── CHECK 1.6: QUANTUM SQUEEZE CLUSTER EXIT (15m SIPV Take Profit) ──
    try:
        from app.strategy.quantum_squeeze_hedge import evaluate_cluster_exit
        sym_positions = [p for p in BOT_STATE.positions.values() if p.get('symbol') == symbol and p.get('status') == 'open']
        cluster_res = evaluate_cluster_exit(symbol, sym_positions, df_5m, df_15m, current_price, market_type='crypto_futures')
        if cluster_res and cluster_res.get('action') == 'cluster_take_profit':
            log_info('PROTECTION', f"🎯 [CRYPTO QSHR CLUSTER TAKE PROFIT] [{symbol}]: {cluster_res.get('reason')}")
            for p_pos in sym_positions:
                await _execute_paper_close(p_pos, current_price, 'qshr_cluster_tp_15m', supabase)
            return
    except Exception as cl_e:
        log_error(MODULE, f"Error evaluando Cluster Exit Crypto {symbol}: {cl_e}")

    # ── CHECK 1.7: QUANTUM SQUEEZE TREND BOOSTER & HEDGE ──
    try:
        from app.strategy.quantum_squeeze_hedge import evaluate_qshr_hedge_signal
        sym_positions = [p for p in BOT_STATE.positions.values() if p.get('symbol') == symbol and p.get('status') == 'open']
        qshr_res = evaluate_qshr_hedge_signal(symbol, df_5m, df_15m, active_position=position, market_type='crypto_futures')
        if qshr_res:
            q_action = qshr_res.get('action')
            q_reason = qshr_res.get('reason')
            if q_action in ('open_booster_long', 'open_booster_short'):
                if len(sym_positions) >= 2:
                    log_info('BOOSTER', f"⛔ [CRYPTO BOOSTER MAX LIMIT] {symbol}: Ya existen {len(sym_positions)} posiciones abiertas (Máx: 2). Booster omitido.")
                else:
                    booster_side = 'long' if 'long' in q_action else 'short'
                    log_info('BOOSTER', f"🚀 [CRYPTO QSHR TREND BOOSTER {booster_side.upper()}] {symbol}: {q_reason}")
                    
                    from app.rebote_aduana.aduana_validator import AduanaValidator
                    aduana = AduanaValidator()
                    res_open = supabase.table('positions').select('*').eq('status', 'open').execute()
                    open_symbols = list(set([r['symbol'] for r in (res_open.data or []) if r.get('symbol')]))
                    max_active = int(BOT_STATE.config_cache.get('max_active_symbols_crypto') or 3)
                    max_per_sym = 2
                    
                    entry_px = float(position.get('avg_entry_price') or position.get('entry_price') or current_price)
                    pnl_pct = ((current_price - entry_px) / entry_px * 100) if booster_side == 'long' else ((entry_px - current_price) / entry_px * 100)
                    
                    market_data = {
                        'df_15m': df_15m,
                        'df_5m': df_5m,
                        'squeeze_velocity': float(qshr_res.get('velocity', 2.5)),
                        'unrealized_pnl_pct': pnl_pct,
                        'open_symbols': open_symbols,
                        'max_active_symbols': max_active,
                        'current_symbol_positions': len(sym_positions),
                        'max_positions_per_symbol': max_per_sym
                    }
                    val_res = aduana.validate(
                        symbol=symbol, side=booster_side, order_type='MARKET',
                        market_data=market_data, strategy=qshr_res.get('rule_code', 'Bb33_QSHR_BOOSTER')
                    )
                    if val_res.approved:
                        cap_op = float(BOT_STATE.config_cache.get("capital_operativo", 100))
                        sizing_usd = max(18.0, cap_op * 0.10)
                        qty = sizing_usd / current_price
                        is_paper = BOT_STATE.config_cache.get("paper_trading", False) is not False
                        if is_paper:
                            await _execute_paper_open(
                                symbol=symbol, side=booster_side, price=current_price,
                                size=qty, rule_code=qshr_res.get('rule_code', 'Bb33_QSHR_BOOSTER'),
                                regime={'category': 'favorable_trend'}, levels={},
                                vel_config={'adx_val': 30, 'multiplier': 1.0}, supabase=supabase
                            )
                            # Sincronizar cluster SL
                            cluster_sl = qshr_res.get('sl_price')
                            if cluster_sl:
                                for p in sym_positions:
                                    try:
                                        supabase.table('positions').update({'sl_price': cluster_sl, 'stop_loss': cluster_sl}).eq('id', p['id']).execute()
                                    except: pass
            elif q_action in ('close_and_flip_long', 'close_and_flip_short'):
                flip_side = qshr_res['flip_side']
                flip_rule = qshr_res.get('flip_rule', 'Bb33_QSHR_FLIP')
                log_info('QSHR_CRYPTO', f"🔄 [CRYPTO CUT & FLIP TRIGGER] {symbol}: Cerrando {position.get('side', '').upper()} y girando a {flip_side.upper()} ({q_reason})")
                is_paper = BOT_STATE.config_cache.get("paper_trading", False) is not False
                if is_paper:
                    await _execute_paper_close(position, current_price, 'qshr_cut_and_flip', supabase)
                    cap_op = float(BOT_STATE.config_cache.get("capital_operativo", 100))
                    sizing_usd = max(18.0, cap_op * 0.15)
                    qty = sizing_usd / current_price
                    await _execute_paper_open(
                        symbol=symbol, side=flip_side, price=current_price,
                        size=qty, rule_code=flip_rule,
                        regime={'category': 'favorable_trend'}, levels={},
                        vel_config={'adx_val': 30, 'multiplier': 1.5}, supabase=supabase
                    )
            elif q_action in ('close_original_long', 'close_original_short'):
                log_info('QSHR_CRYPTO', f"🛡️ [CRYPTO QSHR EMERGENCY CUT] {symbol}: {q_reason}")
                is_paper = BOT_STATE.config_cache.get("paper_trading", False) is not False
                if is_paper:
                    await _execute_paper_close(position, current_price, 'qshr_early_invalidation', supabase)
    except Exception as boost_e:
        log_error(MODULE, f"Error evaluando Crypto QSHR / Booster {symbol}: {boost_e}")

    # ── CHECK 1.7.5: RANGE_BAND_TOUCH_EXIT (Cierre en Límite de Rango Lateral con PnL > 0) ──
    try:
        from app.strategy.capital_protection import evaluate_range_bollinger_exit
        range_res = evaluate_range_bollinger_exit(
            state=state,
            current_price=current_price,
            df_15m=df_15m,
            snap=snap
        )
        if range_res.get('action') == 'close_market':
            log_info('PROTECTION', f"🎯 [CRYPTO RANGE BAND EXIT] [{symbol}]: {range_res.get('reason')}")
            from app.strategy.candle_momentum_guard import should_allow_exit
            allow, allow_msg = should_allow_exit(position, current_price, df_15m, df_5m, 'range_bollinger_touch_exit', 'crypto_futures', snap=snap)
            if not allow:
                log_info('PROTECTION', f"🎯 [CRYPTO RANGE BAND EXIT] [{symbol}]: Bloqueado por {allow_msg}")
            else:
                is_paper = BOT_STATE.config_cache.get("paper_trading", False) is not False
                if is_paper:
                    closed = await _execute_paper_close(position, current_price, 'range_bollinger_touch_exit', supabase)
                    if closed:
                        return 'closed'
    except Exception as rb_e:
        log_error(MODULE, f"Error evaluando Crypto Range Band Touch Exit {symbol}: {rb_e}")

    # ── CHECK 1.8: DYNAMIC TAKE PROFIT v6 (5 RULES) ──
    try:
        from app.strategy.profit_capture import evaluate_dynamic_tp_v6
        entry_px = float(position.get('avg_entry_price') or position.get('entry_price') or current_price)
        pos_side = position.get('side', 'long').lower()
        curr_pnl_pct = ((current_price - entry_px) / entry_px * 100.0) if pos_side in ('long', 'buy') else ((entry_px - current_price) / entry_px * 100.0)
        max_pct_seen = max(float(position.get('max_pnl_pct') or 0.0), curr_pnl_pct)
        position['max_pnl_pct'] = max_pct_seen
        
        tp_v6_res = evaluate_dynamic_tp_v6(
            symbol=symbol,
            side=pos_side,
            current_price=current_price,
            entry_price=entry_px,
            df_15m=df_15m,
            df_5m=df_5m,
            snap=snap,
            max_pnl_pct=max_pct_seen,
            partial_already_taken=position.get('partial_closed', False),
            market_type='crypto_futures'
        )
        if tp_v6_res['should_close'] and not tp_v6_res.get('is_partial'):
            from app.strategy.candle_momentum_guard import should_allow_exit
            rc_lower = str(tp_v6_res['rule_code']).lower()
            exit_id = rc_lower if rc_lower.startswith('tp_') else f"tp_{rc_lower}"
            allow, allow_msg = should_allow_exit(position, current_price, df_15m, df_5m, exit_id, 'crypto_futures', snap=snap)
            if not allow:
                log_info('PROTECTION', f"🎯 [CRYPTO DYNAMIC TP v6] [{symbol}]: Bloqueado por {allow_msg}")
            else:
                log_info('PROTECTION', f"🎯 [CRYPTO DYNAMIC TP v6] [{symbol}]: Cierre por {tp_v6_res['rule_code']} ({tp_v6_res['reason']})")
                await _execute_paper_close(position, current_price, exit_id, supabase)
                return
    except Exception as tp_v6_err:
        log_error(MODULE, f"Error evaluando Dynamic TP v6 Crypto {symbol}: {tp_v6_err}")

    # ── CHECK 2: Trailing Stop ────────────────
    
    trail = evaluate_trailing_stop(state, current_price, df_15m=df_15m, df_5m=df_5m, snap=snap)
    
    # Handle bb_touched update
    if trail.get('update_bb_touched') or trail['action'] == 'update_bb_touched':
        try:
            curr_band = position.get('highest_band_reached') or ''
            new_band = f"{curr_band};bb_touched" if curr_band else "bb_touched"
            supabase.table('positions').update({
                'highest_band_reached': new_band
            }).eq('id', pos_id).execute()
            position['highest_band_reached'] = new_band
            state.bb_touched = True
            log_info('PROTECTION', f'🎯 BB TOUCHED [{symbol}]: Actualizado highest_band_reached en DB.')
        except Exception as e:
            log_error(MODULE, f"Error actualizando bb_touched para {symbol}: {e}")
            
    if trail['action'] == 'update_sl':
        new_sl = trail['new_sl']
        try:
            supabase.table('positions').update({
                'sl_price': new_sl,
                'stop_loss': new_sl,
                'trailing_sl_price': new_sl,
                'sl_type': trail.get('sl_type', f'trailing_l{trail["new_level"]}'),
                'protection_activated': True
            }).eq('id', pos_id).execute()

            state.trailing_level = trail['new_level']
            state.current_sl     = new_sl
            position['sl_price'] = new_sl # Update local ref

            log_info('PROTECTION', f'📈 TRAIL L{trail["new_level"]} [{symbol}]: {trail["reason"]}')
        except Exception as e:
            log_error(MODULE, f"Error actualizando Trail para {symbol}: {e}")
            
    elif trail['action'] == 'close_market':
        origen = str(position.get('origen', '')).upper()
        rule_code = str(position.get('rule_code', ''))
        if origen == 'REBOTE' or rule_code.startswith(('AaReb', 'BbReb', 'REBOTE', 'Aa12')):
            log_info('PROTECTION', f"🌊 [CASCADA] Ignorando TS Close para posición CASCADA/REBOTE {symbol}. Delegado a CascadaManager.")
        else:
            from app.strategy.candle_momentum_guard import should_allow_exit
            allow, allow_msg = should_allow_exit(position, current_price, df_15m, df_5m, 'ts_close', 'crypto_futures', snap=snap)
            if not allow:
                log_info('PROTECTION', f"🔴 TS CLOSE BLOQUEADO [{symbol}]: {allow_msg}")
            else:
                log_info('PROTECTION', f'🔴 TS CLOSE TRIGGERED [{symbol}]: precio={current_price:.6f}. Reason={trail["reason"]}')
                closed = await _execute_paper_close(position, current_price, 'ts_close', supabase)
                if closed:
                    # Register SL cooldown
                    side = (position.get('side') or 'long').lower()
                    register_sl_event(symbol, side)
                
                # Si no tocó BB, re-entramos con órdenes límite!
                if not trail.get('bb_touched', False):
                    qty = float(position.get('size') or 0)
                    await trigger_trailing_stop_reentry(symbol, side, qty, df_15m, supabase)
                    
                return 'closed'

    # ── CHECK 3: SL backstop hit ──────────────
    sl = state.current_sl
    side = state.side
    if sl > 0:
        sl_hit = (
            (side in ('long','buy') and current_price <= sl) or
            (side not in ('long','buy') and current_price >= sl)
        )
        if sl_hit:
            log_info('PROTECTION', f'🔴 SL HIT [{symbol}]: precio={current_price:.6f} sl={sl:.6f}. Routing to EREP Phase 1...')
            
            entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
            from app.core.crypto_symbols import resolve_crypto_position_quantity
            qty = resolve_crypto_position_quantity(supabase, position)
            
            try:
                supabase.table('positions').update({
                    'erep_phase': 1,
                    'erep_p1_price': entry,
                    'erep_q1': qty,
                    'erep_market_type': 'crypto_futures',
                }).eq('id', pos_id).execute()
            except Exception as e:
                log_error('PROTECTION', f"Error activating EREP in check_protections: {e}")
                
            _protection_cache.pop(pos_id, None)
            return 'erep_activated'

    return False

async def check_open_positions_5m(
    provider,
    supabase,
    telegram_bot
) -> list[dict]:
    """
    Ejecutar en cada ciclo de 5m.
    1. Verifica posiciones en Binance (si hay conexión real)
    2. Maneja cierres parciales y totales para PAPER TRADING via market_snapshot
    """
    events = []
    
    # Register heartbeat in safety_manager
    from app.core.safety_manager import register_heartbeat
    register_heartbeat('position_monitor')
    
    # --- PHASE 1: Real Exchange Sync ---
    open_positions_mem = BOT_STATE.positions
    if open_positions_mem:
        symbols = list(open_positions_mem.keys())
        for symbol in symbols:
            try:
                real = await provider.get_position(symbol)
                binance_is_open = abs(float(real.get('positionAmt', 0))) > 0
                if not binance_is_open:
                    await _handle_unexpected_close(symbol, open_positions_mem[symbol], real, supabase, telegram_bot)
                    events.append({'symbol': symbol, 'event': 'unexpected_close'})
            except: pass

    # --- PHASE 2: Paper Trading monitor (SL/TP) ---
    try:
        # Get latest configuration
        config = {}
        try:
            config_res = supabase.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
            if config_res and hasattr(config_res, 'data'):
                config = config_res.data or {}
        except: pass

        # Get latest snapshot for MTFs
        mtf_scores = {}
        snap_data = []
        try:
            snap_res = supabase.table('market_snapshot').select('symbol, price, mtf_score, adx').execute()
            if snap_res and hasattr(snap_res, 'data') and snap_res.data:
                snap_data = snap_res.data
                mtf_scores = {r['symbol'].replace("/", ""): float(r.get('mtf_score') or 0) for r in snap_data}
        except: pass
        
        # Get active positions from Supabase
        pos_res = supabase.table('positions').select('*').eq('status', 'open').execute()
        if not pos_res or not hasattr(pos_res, 'data') or not pos_res.data:
            return events

        for pos in pos_res.data:
            symbol = pos.get('symbol', 'UNKNOWN')
            norm_symbol = normalize_crypto_symbol(symbol) if symbol != 'UNKNOWN' else 'UNKNOWN'
            try:
                # 0. DETECCIÓN DE PRECIO (ROBUSTA)
                # Prioridad 1: Binance Ticker (Live). Prioridad 2: Market Snapshot (DB).
                price = None
                try:
                    ticker = await provider.get_ticker(norm_symbol)
                    price = float(ticker['price'])
                except:
                    # Fallback to snapshot price
                    snap_row = next((r for r in snap_res.data if r['symbol'].replace("/", "") == norm_symbol), None)
                    if snap_row:
                        price = float(snap_row.get('price') or 0)
                
                if not price or price <= 0:
                    log_warning(MODULE, f"Skipping monitor for {norm_symbol}: Price not available")
                    continue
                
                # 0.1 SISTEMA DE PROTECCIÓN DE CAPITAL (4 Pasos)
                # Inyectamos el monitor de protecciones dinámicas (BE, Trailing, Backstop)
                current_snap_obj = next((r for r in snap_res.data if r['symbol'].replace("/", "") == norm_symbol), {})

                # ── EREP Integration ──
                try:
                    if await check_crypto_erep(norm_symbol, pos, price, current_snap_obj, supabase):
                        events.append({'symbol': norm_symbol, 'event': 'erep_close'})
                        continue
                    
                    # Recargar posición local para verificar si EREP ya está activo
                    fresh_pos = supabase.table('positions').select('erep_active', 'erep_phase').eq('id', pos['id']).execute()
                    if fresh_pos.data and fresh_pos.data[0].get('erep_active'):
                        # Si EREP está activamente ejecutándose, salteamos el resto de las evaluaciones normales
                        continue
                except Exception as erep_err:
                    log_warning(MODULE, f"Error checking EREP for {norm_symbol}: {erep_err}")

                closed_status = await check_protections(norm_symbol, pos, price, current_snap_obj, supabase)
                if closed_status == 'closed':
                    # Register SL cooldown when closed by protection (TS close/trailing hit)
                    side = (pos.get('side') or 'long').lower()
                    register_sl_event(norm_symbol, side)
                    events.append({'symbol': norm_symbol, 'event': 'protection_close'})
                    continue
                elif closed_status == 'erep_activated':
                    events.append({'symbol': norm_symbol, 'event': 'erep_activated'})
                    continue

                # 0.1.1 TIME-BASED SL (Corrección #1)
                # Cierra posiciones zombi que llevan demasiado tiempo sin ganancia.
                # 🛡️ Solo se evalúa si el P&L es positivo para evitar consolidar pérdidas en posiciones zombie.
                entry_p_z = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                is_long_z = (pos.get('side') or 'long').lower() in ['long', 'buy']
                qty_z = float(pos.get('size') or 0)
                upnl_z = (price - entry_p_z) * qty_z if is_long_z else (entry_p_z - price) * qty_z

                if upnl_z >= 0:
                    time_sl = check_time_based_sl(pos, snap=current_snap_obj)
                    if time_sl.get('should_close'):
                        await _execute_paper_close(pos, price, time_sl['reason'], supabase)
                        register_sl_event(norm_symbol, (pos.get('side') or 'long').lower())
                        events.append({'symbol': norm_symbol, 'event': 'time_based_sl'})

                        from app.workers.alerts_service import send_telegram_message
                        await send_telegram_message(
                            f"🕐 TIME-BASED SL [{norm_symbol}]\n"
                            f"Tiempo: {time_sl['hours_open']:.1f}h "
                            f"(máx={time_sl['max_hours']}h)\n"
                            f"Peak PnL: {time_sl['peak_pnl']:.3f}%\n"
                            f"Velocidad: {time_sl['velocity']}\n"
                            f"→ Cerrado para limitar exposición"
                        )
                        log_info(MODULE, time_sl['detail'])
                        continue

                # 0.2 ACTUALIZACIÓN DE P&L PARA DASHBOARD
                entry_p = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                side = (pos.get('side') or 'long').lower()
                sl = float(pos.get('sl_price') or pos.get('stop_loss') or 0)
                tp_p = float(pos.get('tp_partial_price') or 0)
                tp_f = float(pos.get('tp_full_price') or pos.get('take_profit') or 0)
                mtf_score = mtf_scores.get(norm_symbol) or 0
                
                from app.core.crypto_symbols import resolve_crypto_position_quantity
                current_qty = resolve_crypto_position_quantity(supabase, pos)
                from app.core.pnl_calculator import calculate_pnl
                upnl, upnl_pct = calculate_pnl(pos.get('market_type') or ('forex' if 'EUR' in symbol or 'GBP' in symbol or 'JPY' in symbol or 'XAU' in symbol else 'crypto'), side, entry_p, price, current_qty, symbol, supabase)

                try:
                    supabase.table('positions').update({
                        'current_price': price,
                        'unrealized_pnl': round(upnl, 4)
                    }).eq('id', pos['id']).execute()
                except Exception as upd_e:
                    log_warning(MODULE, f"Silent update fail for {symbol}: {upd_e}")

                # ── HALCÓN CENTINELA: Evaluación Proactiva Multi-Timeframe ──
                try:
                    from app.halcon_centinela.arbitrage import check_closing_in_progress
                    if not check_closing_in_progress(str(pos.get('id')), 'positions'):
                        from app.halcon_centinela.centinela_monitor import CentinelaMonitor
                        from app.halcon_centinela.config import CentinelaDecision
                        global _CENTINELA_MONITOR_CRYPTO
                        if _CENTINELA_MONITOR_CRYPTO is None:
                            _CENTINELA_MONITOR_CRYPTO = CentinelaMonitor(supabase=supabase, market_type='crypto')
                        
                        eval_pos = dict(pos)
                        eval_pos['current_price'] = price
                        eval_pos['current_pnl'] = upnl
                        eval_pos['direction'] = side
                        eval_res = _CENTINELA_MONITOR_CRYPTO._evaluate_single_position(eval_pos)
                        
                        if eval_res and upnl >= 1.0:
                            decision = eval_res.get('decision')
                            if decision == CentinelaDecision.CIERRE_TOTAL.value:
                                reason = f"HALCON_CENTINELA_CIERRE_TOTAL (Score: {eval_res.get('score_final', 0)})"
                                await _execute_paper_close(pos, price, reason, supabase)
                                events.append({'symbol': norm_symbol, 'event': 'centinela_close'})
                                log_info(MODULE, f"🦅 [CENTINELA CRYPTO] Closed {norm_symbol} via proactive exit: score={eval_res.get('score_final')}, pnl=${upnl:.2f}")
                                continue
                            elif decision == CentinelaDecision.CIERRE_PARCIAL.value:
                                await _execute_paper_partial_close(pos, price, supabase)
                                events.append({'symbol': norm_symbol, 'event': 'centinela_partial_close'})
                                log_info(MODULE, f"🦅 [CENTINELA CRYPTO] Partial Close for {norm_symbol}: score={eval_res.get('score_final')}, pnl=${upnl:.2f}")
                                continue
                except Exception as cent_err:
                    log_warning(MODULE, f"Error evaluating Centinela for crypto {norm_symbol}: {cent_err}")

                # 1. STOP LOSS (Full Close) via Dynamic SL Manager
                from app.strategy.dynamic_sl_manager import evaluate_sl_action
                from app.core.memory_store import get_memory_df
                df_4h = get_memory_df(norm_symbol, "4h")
                df_1d = get_memory_df(norm_symbol, "1d")

                # We use snapshot info mapped to what evaluate_sl_action expects
                snap_for_sl = next((r for r in snap_res.data if r['symbol'].replace("/", "") == norm_symbol), {})

                sl_action = evaluate_sl_action(
                    position      = pos,
                    current_price = price,
                    snap          = snap_for_sl,
                    df_4h         = df_4h,
                    df_1d         = df_1d,
                    market_type   = 'crypto_futures',
                )
                
                action = sl_action.get('action')

                if action == 'close_backstop':
                    log_warning(MODULE, f"🔴 BACKSTOP HIT: {norm_symbol} @ {price:.6f}. Routing to EREP Phase 1...")
                    supabase.table('positions').update({
                        'erep_phase': 1,
                        'erep_p1_price': entry_p,
                        'erep_q1': current_qty,
                        'erep_market_type': 'crypto_futures',
                    }).eq('id', pos['id']).execute()
                    events.append({'symbol': norm_symbol, 'event': 'erep_activated'})
                    continue

                if action == 'trigger_dynamic_sl':
                    log_warning(MODULE, f"🔴 DYNAMIC SL HIT: {norm_symbol} @ {price:.6f}. Routing to EREP Phase 1...")
                    supabase.table('positions').update({
                        'erep_phase': 1,
                        'erep_p1_price': entry_p,
                        'erep_q1': current_qty,
                        'erep_market_type': 'crypto_futures',
                    }).eq('id', pos['id']).execute()
                    events.append({'symbol': norm_symbol, 'event': 'erep_activated'})
                    continue

                if action == 'activate_dynamic_sl':
                    sl_dynamic_price = sl_action['sl_price']
                    sipv             = sl_action['sipv']
                    
                    log_info(MODULE, f'⚡ ACTIVANDO DYNAMIC SL {norm_symbol}: {sl_dynamic_price:.6f} ({sl_action["reason"]})')
                    
                    try:
                        supabase.table('positions').update({
                            'sl_dynamic_price':    sl_dynamic_price,
                            'sl_type':             'dynamic',
                            'sl_activated_at':     datetime.now(timezone.utc).isoformat(),
                            'sl_activation_reason': sipv.get('pattern', 'sipv'),
                            'stop_loss':     sl_dynamic_price,
                        }).eq('id', pos['id']).execute()
                        if pos.get('mode') != 'paper' and not pos.get('is_paper'):
                            from app.strategy.dynamic_sl_manager import send_sl_to_exchange
                            await send_sl_to_exchange(
                                symbol      = norm_symbol,
                                side        = side,
                                sl_price    = sl_dynamic_price,
                                quantity    = pos.get('size'),
                                position_id = pos['id'],
                                supabase    = supabase,
                                market_type = 'crypto_futures'
                            )
                    except Exception as upd_e:
                        log_warning(MODULE, f"Silent dynamic SL update fail for {symbol}: {upd_e}")

                if action == 'update_trailing':
                    try:
                        supabase.table('positions').update({
                            'trailing_sl_price': sl_action['sl_price'],
                            'highest_price_reached': sl_action.get('new_max'),
                            'lowest_price_reached': sl_action.get('new_min'),
                        }).eq('id', pos['id']).execute()
                    except Exception as upd_e:
                        log_warning(MODULE, f"Silent trailing SL update fail for {symbol}: {upd_e}")

                # ── EVALUACIÓN ANCLA SL & TP (v5.0 / v6.0) ──
                try:
                    from app.strategy.ancla_manager import AnclaManager
                    from app.rebote_aduana.aduana_exit_gate import GLOBAL_ADUANA_EXIT_GATE, ExitOrderRequest
                    
                    ancla_mgr = AnclaManager()
                    df_15m_ancla = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
                    df_4h_ancla = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
                    df_1d_ancla = MEMORY_STORE.get(symbol, {}).get('1d', {}).get('df')
                    fib_levels_ancla = snap.get('fib_levels', {}) if snap else {}
                    
                    if df_15m_ancla is not None and not df_15m_ancla.empty:
                        pos['current_price'] = price
                        # 1. Stop Loss Dinámico ANCLA (15M)
                        sl_calc = ancla_mgr.calculate_sl_dynamic(pos, df_15m_ancla, fib_levels_ancla)
                        if sl_calc['armed'] and sl_calc['sl_price'] > 0:
                            req_sl = ExitOrderRequest(
                                position_id=str(pos['id']),
                                symbol=norm_symbol,
                                side='sell' if side == 'long' else 'buy',
                                order_type='STOP',
                                price=sl_calc['sl_price'],
                                volume=float(pos.get('volume', pos.get('size', 0))),
                                classification='ACTIVA',
                                module_origin='ANCLA_SL'
                            )
                            GLOBAL_ADUANA_EXIT_GATE.arbitrate_and_register_order(req_sl)
                            
                        # 2. Take Profit Etapa 1 ANCLA
                        mode = ancla_mgr.get_mode_for_strategy(pos.get('rule_code', ''))
                        df_macro = df_1d_ancla if (mode == 'swing' and df_1d_ancla is not None) else df_4h_ancla
                        df_sensor = df_4h_ancla if (mode == 'swing' and df_4h_ancla is not None) else df_15m_ancla
                        
                        if df_macro is not None and df_sensor is not None:
                            tp1_calc = ancla_mgr.calculate_tp1_stage(pos, df_macro, df_sensor, mode=mode)
                            if tp1_calc['should_place_tp1'] and tp1_calc['tp1_price'] > 0:
                                req_tp = ExitOrderRequest(
                                    position_id=str(pos['id']),
                                    symbol=norm_symbol,
                                    side='sell' if side == 'long' else 'buy',
                                    order_type='LIMIT',
                                    price=tp1_calc['tp1_price'],
                                    volume=float(pos.get('volume', pos.get('size', 0))) * (tp1_calc['volume_pct'] / 100.0),
                                    classification='ACTIVA',
                                    module_origin='ANCLA_TP1'
                                )
                                GLOBAL_ADUANA_EXIT_GATE.arbitrate_and_register_order(req_tp)
                except Exception as ancla_err:
                    log_warning(MODULE, f"ANCLA monitor error for {symbol}: {ancla_err}")

                # ── 1.5 REBOTE & ADUANA: Salida por Clímax en Bandas Extremas (LOWER_5/6 o UPPER_5/6) ──
                try:
                    df_15m_reb = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
                    df_5m_reb = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
                    if df_15m_reb is not None and not df_15m_reb.empty:
                        from app.rebote_aduana.rebote_engine import ReboteEngine
                        from app.rebote_aduana.aduana_exit_gate import GLOBAL_ADUANA_EXIT_GATE, ExitOrderRequest
                        _reb_engine = ReboteEngine()
                        climax_exit, climax_reason, climax_meta = _reb_engine.evaluate_climax_exit(
                            symbol=norm_symbol,
                            direction=side,
                            current_price=price,
                            df_15m=df_15m_reb,
                            df_5m=df_5m_reb,
                            position=pos,
                            snap=current_snap_obj
                        )
                        if climax_exit:
                            req_climax = ExitOrderRequest(
                                position_id=str(pos['id']),
                                symbol=norm_symbol,
                                side='buy' if side in ('short', 'sell') else 'sell',
                                order_type='MARKET',
                                price=price,
                                volume=float(pos.get('size') or pos.get('lots') or 0),
                                classification='ACTIVA',
                                module_origin='CLIMAX_REBOTE_EXIT',
                                metadata=climax_meta
                            )
                            arb_res = GLOBAL_ADUANA_EXIT_GATE.arbitrate_and_register_order(req_climax)
                            if arb_res.get('approved'):
                                log_info(MODULE, f"🎯 [ADUANA / REBOTE EXIT] {climax_reason}")
                                await _execute_paper_close(pos, price, 'rebote_climax'[:20], supabase, snap=current_snap_obj)
                                events.append({'symbol': symbol, 'event': 'climax_rebote_exit'})
                                
                                from app.workers.alerts_service import send_telegram_message
                                await send_telegram_message(
                                    f"🎯 REBOTE + ADUANA EXIT [{norm_symbol}]\n"
                                    f"Dirección: {side.upper()}\n"
                                    f"Precio Cierre: ${price:.4f}\n"
                                    f"PnL: +{climax_meta.get('pnl_pct', 0.0):.2f}%\n"
                                    f"Motivo: {climax_reason}"
                                )
                                continue
                except Exception as reb_climax_err:
                    log_warning(MODULE, f"Error en evaluación REBOTE/ADUANA Clímax para {symbol}: {reb_climax_err}")

                # 2. TAKE PROFIT PARTIAL (50% Close)
                is_tp_p = (side == 'long' and price >= tp_p) or (side == 'short' and price <= tp_p) if (tp_p > 0 and not pos.get('partial_closed')) else False
                if is_tp_p:
                    await _execute_paper_partial_close(pos, price, supabase)
                    events.append({'symbol': symbol, 'event': 'tp_partial_hit'})
                    continue

                # 3. TAKE PROFIT FULL (Full Close)
                is_tp_f = (side == 'long' and price >= tp_f) or (side == 'short' and price <= tp_f) if tp_f > 0 else False
                if is_tp_f:
                    await _execute_paper_close(pos, price, 'tp_full', supabase)
                    events.append({'symbol': symbol, 'event': 'tp_full_hit'})
                    continue

                # 4. DYNAMIC HOLDING MAX (Based on market velocity / ADX)
                try:
                    from app.core.parameter_guard import get_velocity_config
                    # Get ADX from snapshot
                    snap_adx = {r['symbol'].replace("/", ""): float(r.get('adx') or 25)
                                for r in snap_res.data} if snap_res.data else {}
                    current_adx = snap_adx.get(norm_symbol, 25)
                    vel_config = get_velocity_config(current_adx)
                    holding_max = vel_config['holding_max']
                    
                    # Bypassear holding max para estrategias swing/4h/1d
                    rule_code = str(pos.get('rule_code') or pos.get('rule_entry') or '').lower()
                    is_swing = any(x in rule_code for x in ['_4h', '_1d', '31a', '31b', '41'])
                    
                    if is_swing:
                        # Las estrategias Swing no se cierran por tiempo en velas de 5m
                        pass
                    else:
                        # Calculate bars held
                        opened_at = pos.get('opened_at')
                        if opened_at:
                            from datetime import datetime, timezone
                            opened_dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                            now_dt = datetime.now(timezone.utc)
                            elapsed_min = (now_dt - opened_dt).total_seconds() / 60
                            bars_held = int(elapsed_min / 5)  # 5m bars
                            
                            # Calcular PNL para evitar cierres por tiempo en pérdida
                            entry_p = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                            if entry_p > 0:
                                if side == 'long':
                                    hold_pnl = (price - entry_p) / entry_p * 100
                                else:
                                    hold_pnl = (entry_p - price) / entry_p * 100
                            else:
                                hold_pnl = 0

                            if bars_held >= holding_max and hold_pnl >= 0:
                                close_reason = f'hold_{vel_config["velocity"][:10]}'
                                from app.strategy.candle_momentum_guard import should_allow_exit
                                df_15m_hold = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
                                df_5m_hold = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
                                allow, allow_msg = should_allow_exit(pos, price, df_15m_hold, df_5m_hold, close_reason, 'crypto_futures', snap=snap)
                                if not allow:
                                    log_info(MODULE, f"Max holding close suprimido para {norm_symbol}: {allow_msg}")
                                    continue

                                await _execute_paper_close(pos, price, close_reason, supabase)
                                events.append({'symbol': symbol, 'event': 'max_holding_close'})
                                
                                from app.workers.alerts_service import send_telegram_message
                                await send_telegram_message(
                                    f"⏱️ CIERRE POR TIEMPO [{norm_symbol}]\n"
                                    f"Velocidad: {vel_config['velocity'].upper()}\n"
                                    f"Holding: {bars_held} velas "
                                    f"(máx: {holding_max})\n"
                                    f"P&L: {hold_pnl:.2f}%"
                                )
                                log_info(MODULE, f"Max holding close for {norm_symbol}: {bars_held}/{holding_max} bars ({vel_config['velocity']})")
                                continue
                except Exception as vel_e:
                    log_warning(MODULE, f"Velocity holding check error for {norm_symbol}: {vel_e}")

                # 5. SL PROXIMITY ALERT (Inteligente)
                await check_sl_proximity_alert(
                    symbol               = norm_symbol,
                    current_price        = price,
                    sl_price             = sl,
                    danger_threshold_pct = 3.0,
                    escalation_drop_pct  = 1.0,
                    pos_id               = str(pos.get('id', ''))
                )
                
                # 5b. MARGIN CALL ALERT (Amenaza al Capital)
                entry_p_margin = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                if entry_p_margin > 0:
                    is_long_margin = (pos.get('side') or 'long').lower() in ['long', 'buy']
                    qty_margin = float(pos.get('size') or 0)
                    upnl_usd_margin = (price - entry_p_margin) * qty_margin if is_long_margin else (entry_p_margin - price) * qty_margin
                    
                    await check_margin_call_alert(
                        symbol  = norm_symbol,
                        pnl_usd = upnl_usd_margin,
                        sb      = supabase,
                        pos_id  = str(pos.get('id', ''))
                    )

                # 6. SIGNAL REVERSAL (Early Exit / SL Prevention)
                # Evalúa si la tendencia giró para salir antes del SL o asegurar TP.
                rev_res = await check_signal_reversal(pos, mtf_score, price, config, snap=current_snap_obj)
                
                if rev_res.get('should_modify_oco_breakeven'):
                    target_tp = rev_res.get('target_tp_price')
                    rev_start_str = pos.get('sl_activated_at')
                    is_rev_be = pos.get('sl_type') == 'reversal_be'
                    
                    now_utc = datetime.now(timezone.utc)
                    if not rev_start_str or not is_rev_be:
                        try:
                            supabase.table('positions').update({
                                'tp_full_price': target_tp,
                                'take_profit': target_tp,
                                'sl_type': 'reversal_be',
                                'sl_activated_at': now_utc.isoformat(),
                                'sl_activation_reason': 'ema_reversal_exact_be'
                            }).eq('id', pos['id']).execute()
                            pos['sl_type'] = 'reversal_be'
                            pos['sl_activated_at'] = now_utc.isoformat()
                            
                            from app.workers.alerts_service import send_telegram_message
                            await send_telegram_message(
                                f"🛡️ REVERSIÓN DETECTADA [{norm_symbol}]\n"
                                f"Ajustando TP a Break-Even: {target_tp:.6f}\n"
                                f"Inicia contador de 45m para cierre de emergencia."
                            )
                        except Exception as e:
                            log_error(MODULE, f"Error updating reversal_be for {norm_symbol}: {e}")
                    else:
                        try:
                            rev_dt = datetime.fromisoformat(rev_start_str.replace('Z', '+00:00'))
                            elapsed_min = (now_utc - rev_dt).total_seconds() / 60
                            if elapsed_min >= 45:
                                entry_p_rev = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                                loss_pct = 0
                                if entry_p_rev > 0:
                                    if side == 'long':
                                        loss_pct = (entry_p_rev - price) / entry_p_rev * 100
                                    else:
                                        loss_pct = (price - entry_p_rev) / entry_p_rev * 100
                                
                                if 0 <= loss_pct <= 0.50:
                                    reason = 'ema_reversal_timeout_market'
                                    await _execute_paper_close(pos, price, reason, supabase)
                                    events.append({'symbol': norm_symbol, 'event': 'signal_reversal_timeout'})
                                    
                                    from app.workers.alerts_service import send_telegram_message
                                    await send_telegram_message(
                                        f"⏳ CIERRE POR TIMEOUT DE REVERSIÓN [{norm_symbol}]\n"
                                        f"Tiempo superado: {elapsed_min:.1f}m\n"
                                        f"Pérdida aceptada: -{loss_pct:.2f}%\n"
                                        f"Detalle: Cerrado por Market para evitar mayor caída (límite 0.5%)."
                                    )
                                    continue
                        except Exception as e:
                            log_error(MODULE, f"Error checking reversal timeout for {norm_symbol}: {e}")

                if rev_res.get('should_exit'):
                    reason = rev_res.get('reason', 'signal_reversal')
                    await _execute_paper_close(pos, price, reason, supabase)
                    events.append({'symbol': symbol, 'event': 'signal_reversal_exit'})
                    
                    from app.workers.alerts_service import send_telegram_message
                    await send_telegram_message(
                        f"⚠️ SALIDA ANTICIPADA [{norm_symbol}]\n"
                        f"Razón: {reason.replace('_', ' ').upper()}\n"
                        f"P&L: {upnl / (entry_p * float(pos.get('size') or 1)) * 100:.2f}%\n"
                        f"Detalle: {rev_res.get('detail')}"
                    )
                    continue
            except Exception as pos_err:
                import traceback
                log_error(MODULE, f"Error monitoring position ID {pos.get('id')} ({symbol}): {pos_err}\n{traceback.format_exc()}")
                continue
    except Exception as e:
        log_error(MODULE, f"Error in paper monitoring: {e}")

    return events

async def _run_protection_crypto(pos: dict, price: float, supabase):
    """Aplica el motor de protección de capital a posiciones de Cripto."""
    symbol = pos['symbol']
    pos_id = pos['id']
    
    # Obtener o inicializar estado en BOT_STATE
    if not hasattr(BOT_STATE, 'protection_cache'):
        BOT_STATE.protection_cache = {}
        
    if pos_id not in BOT_STATE.protection_cache:
        BOT_STATE.protection_cache[pos_id] = ProtectionState(
            position_id=pos_id,
            symbol=symbol,
            side=pos['side'].lower(),
            entry_price=float(pos.get('avg_entry_price') or pos.get('entry_price') or 0),
            current_sl=float(pos.get('sl_price') or pos.get('stop_loss') or 0),
            original_sl=float(pos.get('sl_backstop_price') or pos.get('sl_price') or pos.get('stop_loss') or 0),
            market_type='crypto_futures',
            rule_code=pos.get('rule_code')
        )
    
    state = BOT_STATE.protection_cache[pos_id]
    
    # Track highest and lowest price continuously for accurate dynamic trailing stop
    if state.side in ('long', 'buy'):
        state.highest_price = max(state.highest_price, price) if state.highest_price > 0 else max(state.entry_price, price)
    else:
        state.lowest_price = min(state.lowest_price, price) if state.lowest_price > 0 else min(state.entry_price, price)
        
    from app.core.memory_store import get_memory_df
    df_15m = get_memory_df(symbol, "15m")
    df_5m = get_memory_df(symbol, "5m")
    
    result = evaluate_all_protections(state, price, None, df_15m=df_15m, df_5m=df_5m)
    
    if result.get('has_action') and 'primary' in result:
        primary = result['primary']
        action = primary.get('action')
        
        if action in ('activate_be', 'update_sl'):
            new_sl = primary.get('be_price') if action == 'activate_be' else primary.get('new_sl')
            new_tp = primary.get('new_tp')
            log_info(MODULE, f"🛡️ [PROTECTION] {symbol}: Moviendo SL a {new_sl} ({primary.get('reason')})")
            if new_tp:
                log_info(MODULE, f"🛡️ [PROTECTION] {symbol}: Actualizando TP a {new_tp}")
            # Persistencia en DB
            try:
                update_fields = {
                    'sl_price': new_sl,
                    'stop_loss': new_sl,
                    'sl_update_reason': primary.get('reason')
                }
                if new_tp:
                    update_fields['take_profit'] = new_tp
                    update_fields['tp_full_price'] = new_tp

                supabase.table('positions').update(update_fields).eq('id', pos_id).execute()
                # Actualizar objeto local para el resto del ciclo
                pos['sl_price'] = new_sl
                pos['stop_loss'] = new_sl
                if new_tp:
                    pos['take_profit'] = new_tp
                    pos['tp_full_price'] = new_tp
                # Actualizar estado interno
                state.current_sl = new_sl
                if action == 'activate_be': state.be_activated = True
                if action == 'update_sl': state.trailing_level = primary.get('new_level', state.trailing_level)
            except Exception as e:
                log_error(MODULE, f"Error updating protection SL for {symbol}: {e}")
        
        elif action == 'close_market':
            log_info(MODULE, f"🛡️ [PROTECTION] {symbol}: Cierre por señal inversa confirmado")
            await _execute_paper_close(pos, price, 'inverse_signal', supabase)

async def _execute_paper_open(
    symbol, side, price, size, rule_code, regime, levels, vel_config, supabase
):
    """
    Simula la apertura de una posición paper y persiste en Supabase.
    Aplica SL y TP dinámicos basados en la velocidad (ADX).
    """
    from app.core.logger import log_info

    symbol = normalize_crypto_symbol(symbol)

    # 1. REVERSIÓN FORZADA (Hedge no permitido)
    async with BOT_STATE.order_lock:
        opposite_side = 'SHORT' if side.upper() in ['LONG', 'BUY'] else 'LONG'
        opp_res = supabase.table('positions').select('*').in_('symbol', crypto_symbol_match_variants(symbol)).eq('status', 'open').execute()
        
        to_close = []
        for p in (opp_res.data or []):
            p_side = (p.get('side') or '').upper()
            if opposite_side == 'SHORT' and p_side in ['SHORT', 'SELL']:
                to_close.append(p)
            elif opposite_side == 'LONG' and p_side in ['LONG', 'BUY']:
                to_close.append(p)
        
        if to_close:
            total_value = 0.0
            total_pnl = 0.0
            for pos in to_close:
                pos_entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or 0)
                pos_size = float(pos.get('size') or 1.0)
                p_side = (pos.get('side') or '').upper()
                if pos_entry > 0:
                    pos_val = pos_entry * pos_size
                    if p_side in ['LONG', 'BUY']:
                        pos_pnl = (price - pos_entry) * pos_size
                    else:
                        pos_pnl = (pos_entry - price) * pos_size
                    total_value += pos_val
                    total_pnl += pos_pnl
            
            total_pnl_pct = (total_pnl / total_value * 100) if total_value > 0 else 0.0
            
            # Obtener el límite máximo de pérdida configurado en DB según mercado (por defecto -0.05%)
            is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
            max_rev_key = 'max_reversal_loss_pct_forex' if is_forex else 'max_reversal_loss_pct_crypto'
            try:
                MAX_REVERSAL_LOSS_PCT = float(BOT_STATE.config_cache.get(max_rev_key, -0.05))
            except:
                MAX_REVERSAL_LOSS_PCT = -0.05
            
            if total_pnl_pct < MAX_REVERSAL_LOSS_PCT:
                log_warning(MODULE, f"🚫 REVERSIÓN BLOQUEADA: La pérdida acumulada en {symbol} es {total_pnl_pct:.3f}% (límite {MAX_REVERSAL_LOSS_PCT}%). Se mantiene la posición original y se aborta la nueva entrada.")
                return None

            log_info(MODULE, f"🔄 REVERSIÓN: Cerrando {len(to_close)} posiciones opuestas ({opposite_side}) en {symbol} (PnL: {total_pnl_pct:.3f}%) antes de abrir {side.upper()}")
            for pos in to_close:
                await _execute_paper_close(pos, price, f'reversal_{side.lower()}', supabase)

        # 2. Límite GLOBAL (max_open_trades) y SÍMBOLO usando LOCK para atomicidad
        try:
            from app.core.supabase_client import get_risk_config
            BOT_STATE.config_cache.update(get_risk_config())
        except: pass
        max_global = int(BOT_STATE.config_cache.get('max_open_trades') or 15)
        
        # --- BLOQUEO DE SÍMBOLO EN MEMORIA ---
        if BOT_STATE.opening_locks.get(symbol):
            log_warning(MODULE, f"🛑 BLOQUEO DE SEGURIDAD: {symbol} ya está en proceso de apertura. Abortando duplicado.")
            return None
        
        BOT_STATE.opening_locks[symbol] = True
        
        try:
            # Consultar DB directamente para conteo global exacto
            try:
                # Usar select('id') sin limit(0) para mayor confiabilidad en el conteo
                global_res = supabase.table('positions').select('id').eq('status', 'open').execute()
                current_global = len(global_res.data) if global_res.data is not None else 0
            except Exception as e:
                log_error(MODULE, f"Error consultando límite global: {e}. Bloqueando apertura por seguridad.")
                current_global = 999
            
            if current_global >= max_global:
                log_warning(MODULE, f"GLOBAL_LIMIT: {symbol} bloqueado ({rule_code}). Límite de {max_global} alcanzado (Actual en DB: {current_global}).")
                return None

            # 3. Límite POR SÍMBOLO
            max_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 3))
            
            try:
                variants = crypto_symbol_match_variants(symbol)
                # Usar count='exact' para máxima precisión
                sym_pos_res = supabase.table('positions').select('id, rule_code, opened_at, entry_price, side', count='exact').in_('symbol', variants).eq('status', 'open').execute()
                
                db_count = sym_pos_res.count if sym_pos_res.count is not None else 0
                existing_data = sym_pos_res.data or []
                current_sym = max(db_count, len(existing_data))
            except Exception as e:
                log_error(MODULE, f"Error consultando límite por símbolo ({symbol}): {e}")
                current_sym = 999

            if current_sym >= max_symbol:
                log_warning(MODULE, f"SYMBOL_LIMIT_BLOCKED: {symbol} has {current_sym} open (limit {max_symbol}). Variants: {variants}")
                return None
            
            log_info(MODULE, f"LIMIT_CHECK_OK: {symbol} count is {current_sym}/{max_symbol}.")
            
            # 3.1 DCA & COOL-DOWN PROTECTION (Basado en Forex logic)
            now_utc = datetime.now(timezone.utc)
            from datetime import timedelta
            
            # 3.1.1 Spam Protection (Historial reciente)
            try:
                since = (now_utc - timedelta(minutes=15)).isoformat()
                hist = supabase.table('positions').select('opened_at').in_('symbol', variants).eq('rule_code', rule_code).gte('opened_at', since).order('opened_at', desc=True).limit(1).execute()
                if hist.data:
                    log_warning(MODULE, f"SPAM_BLOCK: {symbol} rule {rule_code} ejecutada hace menos de 15 min. Abortando.")
                    return None
            except Exception as hist_e:
                log_warning(MODULE, f"Error checking crypto history: {hist_e}")

            # 3.1.2 DCA Price Improvement (Misma regla)
            same_rule_pos = [p for p in existing_data if p.get('rule_code') == rule_code]
            if same_rule_pos:
                last_pos = sorted(same_rule_pos, key=lambda x: x['opened_at'], reverse=True)[0]
                last_entry = float(last_pos.get('entry_price') or 0)
                
                # Para LONG: nuevo precio debe ser MENOR que el anterior (mejora costo)
                # Para SHORT: nuevo precio debe ser MAYOR que el anterior (mejora costo)
                is_long = side.lower() in ['long', 'buy']
                if is_long and price >= last_entry:
                    log_warning(MODULE, f"DCA_BLOCK: {symbol} LONG price {price} >= {last_entry}. No mejora costo.")
                    return None
                if not is_long and price <= last_entry:
                    log_warning(MODULE, f"DCA_BLOCK: {symbol} SHORT price {price} <= {last_entry}. No mejora costo.")
                    return None

            # 4. EJECUCIÓN
            log_info(MODULE, f"✅ LÍMITES OK: Abriendo {side.upper()} en {symbol} (Global: {current_global}/{max_global}, Sym: {current_sym}/{max_symbol})")
            res = await _execute_paper_open_unlocked(
                symbol, side, price, size, rule_code, regime, levels, vel_config, supabase
            )
            return res
        except Exception as e:
            log_error(MODULE, f"Error crítico en validación de límites para {symbol}: {e}")
            return None
        finally:
            BOT_STATE.opening_locks[symbol] = False

async def _execute_paper_open_unlocked(
    symbol, side, price, size, rule_code, regime, levels, vel_config, supabase
):
    """Lógica interna de apertura sin lock (ya envuelto por _execute_paper_open)"""
    from datetime import datetime, timezone
    from app.core.position_sizing import calculate_sl_tp
    
    # ── DETERMINAR EL CICLO DE LA REGLA DE ESTRATEGIA ──
    is_scalp = True
    try:
        from app.strategy.strategy_engine import StrategyEngine
        engine = StrategyEngine.get_instance()
        rule = engine.rules.get(rule_code) if engine.loaded else None
        cycle = rule.get('cycle', '15m') if rule else '15m'
        is_scalp = cycle in ['5m', '15m', '30m']
    except Exception as rule_err:
        log_warning(MODULE, f"Error obteniendo ciclo para {rule_code}: {rule_err}. Asumiendo scalp.")

    # Obtener configuración de TP según banda de velocidad
    # tp_band viene como 'lower_2', extraemos el nivel (2)
    try:
        band_str = vel_config.get('tp_band', 'lower_6')
        import re
        match = re.search(r'(\d+)', band_str)
        level_num = match.group(1) if match else "6"
        
        # Mapear a la dirección correcta
        prefix = 'upper' if side == 'long' else 'lower'
        tp_target_col = f"{prefix}_{level_num}"
        # parcial un nivel menos
        partial_num = str(max(1, int(level_num) - 1))
        tp_partial_col = f"{prefix}_{partial_num}"
        
        tp_full    = float(levels.get(tp_target_col, price * (1.015 if side == 'long' else 0.985) if is_scalp else price * (1.1 if side == 'long' else 0.9)))
        tp_partial = float(levels.get(tp_partial_col, price * (1.010 if side == 'long' else 0.990) if is_scalp else price * (1.05 if side == 'long' else 0.95)))
        
        # ── TP DINÁMICO: Validar que el TP cumpla un RR mínimo vs SL ──
        # Si la banda asignada por velocidad está muy cerca del precio (bandas comprimidas),
        # iterar hacia bandas más lejanas hasta encontrar una con RR >= 1.2
        MIN_RR_CRYPTO = 1.2
        TP_BAND_PCT_CRYPTO = 0.95
        
        sl_ref = float(levels.get('lower_6' if side == 'long' else 'upper_6', 0))
        if sl_ref > 0:
            sl_dist = abs(price - sl_ref)
            tp_dist = abs(tp_full - price)
            
            if sl_dist > 0 and (tp_dist / sl_dist) < MIN_RR_CRYPTO:
                # TP insuficiente, buscar banda superior
                bands_to_check = [f"{prefix}_{i}" for i in range(int(level_num) + 1, 7)]
                for band_name in bands_to_check:
                    band_val = float(levels.get(band_name, 0))
                    if band_val <= 0:
                        continue
                    band_dist = abs(band_val - price) * TP_BAND_PCT_CRYPTO
                    if band_dist > 0 and (band_dist / sl_dist) >= MIN_RR_CRYPTO:
                        if side == 'long':
                            tp_full = price + band_dist
                        else:
                            tp_full = price - band_dist
                        log_info(MODULE, f"TP DINÁMICO CRYPTO [{symbol}]: Banda {band_name} (95%) seleccionada. RR=1:{band_dist/sl_dist:.1f}")
                        break
                else:
                    # Fallback: usar RR mínimo fijo
                    tp_fallback_dist = sl_dist * MIN_RR_CRYPTO
                    if side == 'long':
                        tp_full = price + tp_fallback_dist
                    else:
                        tp_full = price - tp_fallback_dist
                    log_info(MODULE, f"TP DINÁMICO CRYPTO [{symbol}]: Ninguna banda cumple RR. Fallback {tp_fallback_dist:.2f}")
    except:
        if is_scalp:
            tp_full    = price * (1.015 if side == 'long' else 0.985)
            tp_partial = price * (1.010 if side == 'long' else 0.990)
        else:
            tp_full    = price * (1.08 if side == 'long' else 0.92)
            tp_partial = price * (1.04 if side == 'long' else 0.96)

    # Calculamos SL con el multiplicador dinámico de velocidad y buffer extra
    buffer_pct = float(BOT_STATE.config_cache.get('sl_extra_buffer_pct', 0.5))
    
    atr_fallback_pct = 0.003 if is_scalp else 0.020
    sl_dict = calculate_sl_tp(
        side        = side,
        entry_price = price,
        atr         = float(levels.get('atr', price * atr_fallback_pct)),
        atr_mult    = float(vel_config.get('sl_mult', 1.0)),
        levels      = levels,
        sl_buffer_pct = buffer_pct
    )
    
    # ── VALIDACIÓN DE COHERENCIA Y BLINDAJE SL vs ENTRY (V2 Engine) ──
    sl_final = sl_dict['sl_price']
    
    # 1. Blindaje de Distancia Mínima
    # BTC y ETH: 0.5%, Altcoins: 1.0%
    is_major = any(x in symbol for x in ['BTC', 'ETH'])
    min_sl_dist_pct = 0.005 if is_major else 0.010
    
    # 2. Blindaje de Distancia Máxima (1% para scalp, 2% para swing)
    max_sl_dist_pct = 0.010 if is_scalp else 0.020
    
    if side.lower() in ['long', 'buy']:
        min_safe_sl = price * (1 - min_sl_dist_pct)
        if sl_final > min_safe_sl:
            log_warning(MODULE, f"🛡️ {symbol}: Blindaje SL Mínimo activado para LONG. SL original={sl_final:.6f} movido a {min_safe_sl:.6f} (dist min {min_sl_dist_pct*100}%)")
            sl_final = min_safe_sl
            
        if sl_final >= price and sl_final > 0:
            sl_final = price * (1 - min_sl_dist_pct)
            log_warning(MODULE, f"{symbol}: SL V2 corregido para LONG. SL={sl_final:.6f} < Entry={price:.6f}")
            
        max_safe_sl = price * (1 - max_sl_dist_pct)
        if sl_final < max_safe_sl:
            log_warning(MODULE, f"🛡️ {symbol}: Blindaje SL Máximo activado para LONG. SL original={sl_final:.6f} movido a {max_safe_sl:.6f} (max {max_sl_dist_pct*100}%)")
            sl_final = max_safe_sl
            
    elif side.lower() in ['short', 'sell']:
        min_safe_sl = price * (1 + min_sl_dist_pct)
        if sl_final < min_safe_sl:
            log_warning(MODULE, f"🛡️ {symbol}: Blindaje SL Mínimo activado para SHORT. SL original={sl_final:.6f} movido a {min_safe_sl:.6f} (dist min {min_sl_dist_pct*100}%)")
            sl_final = min_safe_sl
            
        if sl_final <= price and sl_final > 0:
            sl_final = price * (1 + min_sl_dist_pct)
            log_warning(MODULE, f"{symbol}: SL V2 corregido para SHORT. SL={sl_final:.6f} > Entry={price:.6f}")
            
        max_safe_sl = price * (1 + max_sl_dist_pct)
        if sl_final > max_safe_sl:
            log_warning(MODULE, f"🛡️ {symbol}: Blindaje SL Máximo activado para SHORT. SL original={sl_final:.6f} movido a {max_safe_sl:.6f} (max {max_sl_dist_pct*100}%)")
            sl_final = max_safe_sl
            
    sl_dict['sl_price'] = sl_final

    # ── SLVM: Calcular Stop Loss Virtual ──
    try:
        from app.strategy.virtual_sl_recovery import calculate_slv
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        snap_for_slv = MARKET_SNAPSHOT_CACHE.get(symbol, levels or {})
        slv_data = calculate_slv(
            entry_price = price,
            side        = side,
            symbol      = symbol,
            snap        = snap_for_slv,
            market_type = 'crypto_futures',
        )
        slv_price = slv_data['slv_price']
        
        # Calcular Hard Stop inicial para auditoría
        from app.strategy.virtual_sl_recovery import calculate_hard_stop_pips
        slv_hs_pips = calculate_hard_stop_pips(symbol, 'crypto_futures', snap_for_slv)
        
        log_info(MODULE, f'SLVM [{symbol}]: SLV={slv_price:.6f} (HS: {slv_hs_pips:.1f} pips, {slv_data["source"]})')
    except Exception as slv_e:
        log_warning(MODULE, f'SLVM calc error for {symbol}: {slv_e}')
        slv_price = None
        slv_hs_pips = None

    # ── CALCULAR TAMAÑO DINÁMICO DE POSICIÓN BASADO EN RIESGO Y CAPITAL CONFIGURADO ──
    try:
        from app.core.position_sizing import calculate_position_size
        is_forex = any(x in symbol for x in ['EUR', 'GBP', 'JPY', 'XAU', 'XAG'])
        m_type = 'forex_futures' if is_forex else 'crypto_futures'
        
        sizing_res = calculate_position_size(
            symbol=symbol,
            entry_price=price,
            sl_price=sl_final,
            market_type=m_type,
            trade_number=1, # T1 inicial
            regime=regime.get('category', 'riesgo_medio') if isinstance(regime, dict) else 'riesgo_medio',
            supabase=supabase
        )
        if sizing_res and sizing_res.get('quantity', 0) > 0:
            size = sizing_res['quantity']
            log_info(MODULE, f"📏 Dynamic Sizing exitoso para {symbol}: size={size} (notional={sizing_res['nocional']} USD)")
    except Exception as sizing_e:
        log_warning(MODULE, f"Error calculando tamaño dinámico en _execute_paper_open_unlocked: {sizing_e}. Usando size original: {size}")

    # Determinar si el modo es Paper o Live
    is_paper = bool(BOT_STATE.config_cache.get("paper_trading", False))
    trade_mode = "paper" if is_paper else "live"
    live_exchange_order_id = None
    execution_fill_price = price
    executed_size = size

    if not is_paper:
        try:
            from app.execution.binance_connector import get_client, get_futures_symbol_info_cached, round_step_size
            client = get_client()
            sym_clean = symbol.replace("/", "").upper()
            info = get_futures_symbol_info_cached(client, sym_clean)
            step_size = info.get('step_size') or 0.001
            min_qty = info.get('min_qty') or step_size
            executed_size = round_step_size(size, step_size)
            if executed_size < min_qty and size > 0:
                executed_size = min_qty
            if executed_size <= 0:
                log_error(MODULE, f"Live sizing too small for {sym_clean}: size={size}, step={step_size}")
                return None

            binance_side = 'BUY' if side.lower() in ('long', 'buy') else 'SELL'
            pos_side = 'LONG' if side.lower() in ('long', 'buy') else 'SHORT'

            order_res = client.futures_create_order(
                symbol=sym_clean,
                side=binance_side,
                type='MARKET',
                quantity=executed_size,
                positionSide=pos_side
            )
            live_exchange_order_id = str(order_res.get('orderId', ''))
            fills = order_res.get('fills', [])
            if fills:
                execution_fill_price = sum(float(f['price']) * float(f['qty']) for f in fills) / sum(float(f['qty']) for f in fills)
            elif order_res.get('avgPrice') and float(order_res.get('avgPrice')) > 0:
                execution_fill_price = float(order_res.get('avgPrice'))
            else:
                execution_fill_price = price

            log_info(MODULE, f"⚡ [BINANCE FUTURES LIVE ORDER FILLED] {sym_clean} {pos_side} qty={executed_size} avgPx={execution_fill_price} orderId={live_exchange_order_id}")
        except Exception as live_err:
            err_msg = str(live_err)
            if "-2019" in err_msg or "Margin is insufficient" in err_msg:
                log_warning(MODULE, f"⚠️ [BINANCE MARGIN INSUFFICIENT] {symbol}: Margen insuficiente en Binance Futures ({err_msg}). Apertura omitida.")
            else:
                log_error(MODULE, f"❌ Error placing live Binance Futures order for {symbol}: {live_err}")
            return None

    # Dashboard log (orders table)
    order_db_uuid = None
    try:
        ord_res = supabase.table('orders').insert({
            'symbol': symbol,
            'side': 'BUY' if side.lower() == 'long' else 'SELL',
            'order_type': 'MARKET',
            'quantity': executed_size,
            'limit_price': execution_fill_price,
            'entry_price': execution_fill_price,
            'stop_loss_price': sl_dict['sl_price'],
            'take_profit_price': tp_full,
            'status': 'open',
            'is_paper': is_paper,
            'binance_order_id': live_exchange_order_id,
            'rule_code': rule_code
        }).execute()
        if ord_res and ord_res.data:
            order_db_uuid = ord_res.data[0].get('id')
    except Exception as e:
        log_warning(MODULE, f"Failed to log order to orders table: {e}")

    # Persistir
    data = {
        'symbol':           symbol,
        'side':             side.upper(),
        'entry_price':      round(execution_fill_price, 8),
        'avg_entry_price':  round(execution_fill_price, 8),
        'current_price':    round(execution_fill_price, 8),
        'size':             round(executed_size, 8),
        'stop_loss':        round(sl_final, 8),
        'take_profit':      round(tp_full, 8),
        'sl_price':         round(sl_final, 8),
        'tp_partial_price': round(tp_partial, 8),
        'tp_full_price':    round(tp_full, 8),
        'status':           'open',
        'regime_entry':     regime.get('category', 'riesgo_medio'),
        'rule_code':        rule_code,
        'rule_entry':       rule_code,
        'velocity_entry':   vel_config.get('velocity', 'unknown'),
        'opened_at':        datetime.now(timezone.utc).isoformat(),
        'mode':             trade_mode,
        'order_id':         order_db_uuid,
        'sl_exchange_order_id': live_exchange_order_id,
        # ── SLVM Fields ──
        'slv_price':        slv_price,
        'slv_hard_stop_pips': slv_hs_pips if slv_price else None,
        'recovery_mode':    False,
        'recovery_cycles':  0,
    }

    # ═══════════════════════════════════════════════════════════════
    # ATOMIC LIMIT RE-CHECK — LAST LINE OF DEFENSE BEFORE INSERT
    # Even though _execute_paper_open checked under lock, re-verify
    # because candle_execution or other workers may have inserted.
    # ═══════════════════════════════════════════════════════════════
    try:
        max_sym_recheck = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 3))
        recheck_variants = crypto_symbol_match_variants(symbol)
        recheck_res = supabase.table('positions').select('id', count='exact') \
            .in_('symbol', recheck_variants).eq('status', 'open').execute()
        
        recheck_count = recheck_res.count if recheck_res.count is not None else 0
        if recheck_res.data:
            recheck_count = max(recheck_count, len(recheck_res.data))
            
        if recheck_count >= max_sym_recheck:
            log_warning(MODULE, f"🚫 ATOMIC_RECHECK_BLOCKED: {symbol} has {recheck_count} open (limit {max_sym_recheck}). INSERT rejected.")
            return None
        
        log_info(MODULE, f"✅ ATOMIC_RECHECK_OK: {symbol} count is {recheck_count}. Proceeding with insert.")
    except Exception as rc_e:
        log_error(MODULE, f"ATOMIC re-check failed for {symbol}: {rc_e}. BLOCKING for safety.")
        return None
    # ═══════════════════════════════════════════════════════════════

    res = supabase.table('positions').insert(data).execute()
    new_pos = res.data[0] if res.data else None
    if new_pos:
        # Key by pos_id to support multiple positions per symbol
        BOT_STATE.positions[new_pos.get('id', symbol)] = new_pos
        sm.on_position_opened(symbol, side, new_pos)

    log_info(MODULE, f"🚀 [{trade_mode.upper()} OPEN] [{symbol}] {side.upper()} at ${execution_fill_price:,.2f} (SL: ${data['sl_price']:,.2f}, TP: ${data['tp_full_price']:,.2f})")
    return new_pos

async def _execute_paper_partial_close(pos, price, supabase):
    """Ejecuta cierre parcial simulado (50% del capital)."""
    symbol = pos['symbol']
    entry = float(pos.get('entry_price') or 0)
    side = (pos.get('side') or '').lower()
    
    is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF')) or pos.get('market_type') == 'forex_futures'
    table_name = 'forex_positions' if is_forex else 'positions'
    
    partial_qty = float(pos.get('size') or pos.get('lots') or 0) * 0.5
    from app.core.pnl_calculator import calculate_pnl
    partial_pnl_usd, partial_pnl_pct = calculate_pnl(pos.get('market_type') or ('forex' if is_forex else 'crypto'), side, entry, price, partial_qty, symbol, supabase)
    pnl_pct = partial_pnl_pct
    # Check UUID formatting to avoid database validation crashes
    import uuid
    is_uuid = False
    pos_id = pos.get('id')
    if pos_id:
        try:
            uuid.UUID(str(pos_id))
            is_uuid = True
        except ValueError:
            is_uuid = False

    db_key_name = 'id'
    db_record_id = pos_id
    if is_forex and not is_uuid:
        db_key_name = 'ctrader_order_id'
        db_record_id = pos.get('ctrader_order_id') or pos_id
    
    size_key = 'lots' if is_forex else 'size'
    original_size = float(pos.get(size_key) or pos.get('lots') or pos.get('size') or 0)
    
    # Update Position
    supabase.table(table_name).update({
        'partial_closed': True,
        'partial_close_price': price,
        'current_price': price,
        'partial_close_usd': round(partial_pnl_usd, 4),
        size_key: original_size - partial_qty
    }).eq(db_key_name, db_record_id).execute()

    # 🛡️ Si es una posición de Crypto LIVE, enviar orden de cierre parcial real a Binance Futures
    if not is_forex and pos.get('mode') == 'live':
        try:
            from app.execution.binance_connector import get_client, get_futures_symbol_info_cached, round_step_size
            client = get_client()
            sym_clean = symbol.replace("/", "").upper()
            info = get_futures_symbol_info_cached(client, sym_clean)
            step_size = info.get('step_size') or 0.001
            p_close_qty = round_step_size(partial_qty, step_size)
            close_side = 'SELL' if side in ('long', 'buy') else 'BUY'
            pos_side = 'LONG' if side in ('long', 'buy') else 'SHORT'
            if p_close_qty > 0:
                p_order = client.futures_create_order(
                    symbol=sym_clean,
                    side=close_side,
                    type='MARKET',
                    quantity=p_close_qty,
                    positionSide=pos_side
                )
                log_info(MODULE, f"⚡ [BINANCE FUTURES LIVE PARTIAL CLOSE] {sym_clean} {pos_side} qty={p_close_qty} orderId={p_order.get('orderId')}")
        except Exception as p_close_err:
            log_error(MODULE, f"❌ Error enviando cierre parcial Binance Futures para {symbol}: {p_close_err}")
    
    # 2. Persistir en paper_trades (Log de actividad parcial)
    p_rule_code = pos.get('rule_code') or pos.get('rule_entry') or "Cc-Partial"
    
    supabase.table('paper_trades').insert({
        'symbol':       symbol,
        'side':         pos['side'],
        'entry_price':  entry,
        'exit_price':   price,
        'total_pnl_usd': round(partial_pnl_usd, 4),
        'total_pnl_pct': round(pnl_pct, 4),
        'close_reason': 'partial_tp',
        'closed_at':    datetime.now(timezone.utc).isoformat(),
        'mode':         'paper',
        'rule_code':    p_rule_code[:10]
    }).execute()
    
    log_info(MODULE, f"✅ PARTIAL CLOSE [{symbol}] at ${price:,.2f} | PnL: ${partial_pnl_usd:.2f}")
    
    # ── REGISTRAR PN EN CAPITAL ACUMULADO (Interés Compuesto) ──
    try:
        from app.core.capital_manager import register_realized_pnl
        # Determinar mercado (heuristicamente por símbolo)
        market = 'forex' if any(x in symbol for x in ['EUR', 'GBP', 'JPY', 'XAU']) else 'crypto'
        register_realized_pnl(market, partial_pnl_usd)
    except Exception as cap_e:
        log_warning(MODULE, f"Error actualizando capital acumulado en partial close: {cap_e}")

async def _execute_paper_close(pos, price, reason, supabase, snap=None):
    """Cierra la posición completamente en Paper Trading."""
    symbol = pos['symbol']
    entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or 0)
    side = (pos.get('side') or '').lower()
    qty = float(pos.get('size') or pos.get('lots') or 0)
    
    is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF')) or pos.get('market_type') == 'forex_futures'
    table_name = 'forex_positions' if is_forex else 'positions'
    market_type = 'forex_futures' if is_forex else 'crypto_futures'
    
    # Check UUID formatting to avoid database validation crashes
    import uuid
    is_uuid = False
    pos_id = pos.get('id')
    if pos_id:
        try:
            uuid.UUID(str(pos_id))
            is_uuid = True
        except ValueError:
            is_uuid = False

    db_key_name = 'id'
    db_record_id = pos_id
    if is_forex and not is_uuid:
        db_key_name = 'ctrader_order_id'
        db_record_id = pos.get('ctrader_order_id') or pos_id
    
    from app.core.pnl_calculator import calculate_pnl
    pnl_usd, pnl_pct = calculate_pnl(pos.get('market_type') or ('forex' if is_forex else 'crypto'), side, entry, price, qty, symbol, supabase)

    # Si hubo cierre parcial previo, sumar sus USD
    partial_pnl = pos.get('partial_pnl_usd')
    total_pnl = pnl_usd + (float(partial_pnl) if partial_pnl is not None else 0.0)

    # ── SMART ANTI-LOSS GUARD v2.0 ──
    # Evalúa la tendencia macro (EMA20 vs EMA50) antes de permitir un cierre en pérdida.
    # Solo bloquea el cierre si la tendencia sigue favorable (pullback temporal).
    # Si la tendencia se rompió (EMA20 < EMA50 para LONGs), permite el cierre.
    from app.strategy.smart_loss_guard import should_block_close
    guard_result = should_block_close(
        snap=snap,
        side=side,
        reason=reason,
        total_pnl=total_pnl,
        market_type=market_type,
        symbol=symbol,
    )

    if guard_result['block']:
        # Tendencia sana: bloquear cierre y activar EREP
        # Estrategia: sl_price=0 para dejar que la caída ocurra sin cerrar,
        # esperar 5 minutos al rebote, y cerrar DESPUÉS de la recuperación.
        log_warning(MODULE,
            f"SMART GUARD: Protegiendo {symbol} ({reason}) PnL=${total_pnl:.4f}. "
            f"{guard_result['reason']}"
        )
        try:
            # Columnas comunes (existen en ambas tablas)
            guard_update = {
                'erep_active': True,
                'erep_phase': 2,
                'erep_p1_price': entry,
                'erep_q1': qty,
                'erep_market_type': market_type,
                'erep_cycles_elapsed': 0,
                'erep_activated_at': datetime.now(timezone.utc).isoformat(),
                'sl_price': 0,
            }
            # Columnas exclusivas de crypto (NO existen en forex_positions)
            if not is_forex:
                guard_update['sl_type'] = 'erep_recovery_wait'
                guard_update['stop_loss'] = 0
                guard_update['sl_dynamic_price'] = 0

            supabase.table(table_name).update(guard_update).eq(db_key_name, db_record_id).execute()

            # Actualizar BOT_STATE local
            if pos_id in BOT_STATE.positions:
                BOT_STATE.positions[pos_id].update(guard_update)
        except Exception as upd_e:
            log_warning(MODULE, f"Error actualizando Smart Guard para {symbol}: {upd_e}")
        return False

    # ── CANDLE MOMENTUM GUARD (Protección Central de Ganancias en Tendencia) ──
    if total_pnl > 0 and reason not in ('emergency_sl', 'sl_hit', 'sl_hit_fx', 'sl_hit_fx_hard', 'liquidation', 'weekend_close', 'KILL_SWITCH', 'MANUAL', 'MANUAL_CLOSE'):
        try:
            from app.core.memory_store import MEMORY_STORE
            from app.strategy.candle_momentum_guard import should_allow_exit
            df_15m_g = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
            df_5m_g = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
            allow_exit_mom, mom_reason = should_allow_exit(
                position=pos,
                current_price=price,
                df_15m=df_15m_g,
                df_5m=df_5m_g,
                exit_rule_id=reason,
                market_type=market_type,
                snap=snap
            )
            if not allow_exit_mom:
                log_warning(MODULE, f"MOMENTUM GUARD bloquea cierre de {symbol} ({reason}) PnL=${total_pnl:.4f}: {mom_reason}")
                return False
        except Exception as mom_e:
            log_warning(MODULE, f"Error evaluando Candle Momentum Guard en _execute_paper_close para {symbol}: {mom_e}")

    # ── Cerrar posición en la tabla correcta con columnas válidas ──
    if is_forex:
        pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
        is_buy = side in ('long', 'buy')
        pips_calc = ((price - entry) / pip_sz if is_buy else (entry - price) / pip_sz) if (price > 0 and entry > 0 and pip_sz > 0) else 0.0
        close_update = {
            'status': 'closed',
            'close_reason': reason[:20],
            'current_price': price,
            'closed_at': datetime.now(timezone.utc).isoformat(),
            'pnl_usd': round(total_pnl, 2),
            'pnl_pips': round(pips_calc, 1),
        }
    else:
        close_update = {
            'status': 'closed',
            'close_reason': reason[:20],
            'current_price': price,
            'closed_at': datetime.now(timezone.utc).isoformat(),
            'realized_pnl': round(total_pnl, 4),
            'realized_pnl_pct': round(pnl_pct, 4),
        }

    log_info(MODULE, f"Cerrando {symbol} ({reason}) en tabla {table_name}: PnL=${total_pnl:.4f} ({pnl_pct:.2f}%)")
    
    # 🛡️ Si es una posición de Forex LIVE con ID cTrader, enviar orden de cierre real a IC Markets / cTrader
    if is_forex and pos.get('mode') == 'live' and pos.get('ctrader_pos_id'):
        try:
            ctrader_pid = pos.get('ctrader_pos_id')
            lots_clean = round(abs(float(pos.get('lots') or pos.get('size') or 0.01)), 2)
            close_vol = int(round(lots_clean * 10_000_000)) if symbol != 'XAUUSD' else int(round(lots_clean * 10_000))
            
            from app.core.safety_manager import get_worker
            fw = get_worker('forex_worker')
            if fw and hasattr(fw, 'close_position'):
                fw.close_position(ctrader_pid, close_vol, symbol=symbol, reason=reason)
                log_info(MODULE, f"[CTRADER LIVE CLOSE] Enviada orden de cierre a cTrader para {symbol} (posId {ctrader_pid}) volumen {close_vol}")
        except Exception as live_close_e:
            log_error(MODULE, f"Error enviando cierre cTrader para {symbol}: {live_close_e}")

    # 🛡️ Si es una posición de Crypto LIVE, enviar orden de cierre real a Binance Futures
    if not is_forex and pos.get('mode') in ('live', 'real'):
        try:
            from app.execution.binance_connector import get_client, get_futures_symbol_info_cached, round_step_size
            client = get_client()
            sym_clean = symbol.replace("/", "").upper()
            info = get_futures_symbol_info_cached(client, sym_clean)
            step_size = info.get('step_size') or 0.001
            close_qty = round_step_size(qty, step_size)
            close_side = 'SELL' if side in ('long', 'buy') else 'BUY'
            pos_side = 'LONG' if side in ('long', 'buy') else 'SHORT'
            
            # Consultar saldo/posición real en Binance para evitar rechazos por reduceOnly
            actual_amt = 0.0
            try:
                acc_info = client.futures_account()
                matching_pos = next((p for p in acc_info.get('positions', []) if p.get('symbol') == sym_clean and p.get('positionSide') in (pos_side, 'BOTH') and abs(float(p.get('positionAmt') or 0)) > 0), None)
                if matching_pos:
                    actual_amt = abs(float(matching_pos.get('positionAmt') or 0))
            except Exception as acc_err:
                log_debug(MODULE, f"No se pudo consultar futures_account para {sym_clean}: {acc_err}")
                actual_amt = close_qty

            if actual_amt <= 0:
                log_info(MODULE, f"ℹ️ [BINANCE FUTURES] Posición {sym_clean} {pos_side} ya estaba cerrada o liquidada en el exchange (amt=0). Sincronizando DB.")
            else:
                real_close_qty = round_step_size(actual_amt, step_size) if actual_amt > 0 else close_qty
                if real_close_qty > 0:
                    close_res = client.futures_create_order(
                        symbol=sym_clean,
                        side=close_side,
                        type='MARKET',
                        quantity=real_close_qty,
                        positionSide=pos_side if matching_pos and matching_pos.get('positionSide') == pos_side else 'BOTH'
                    )
                    log_info(MODULE, f"⚡ [BINANCE FUTURES LIVE CLOSE] {sym_clean} {pos_side} qty={real_close_qty} orderId={close_res.get('orderId')}")
            
            # Cancelar cualquier orden limit/stop huérfana de este símbolo
            try:
                client.futures_cancel_all_open_orders(symbol=sym_clean)
            except Exception:
                pass
        except Exception as live_close_err:
            err_msg = str(live_close_err)
            if '-2022' in err_msg or 'ReduceOnly' in err_msg:
                log_info(MODULE, f"ℹ️ [BINANCE FUTURES] Posición {symbol} ya no tenía saldo abierto para reducir en Binance: {err_msg}")
            else:
                log_error(MODULE, f"❌ Error enviando cierre Binance Futures para {symbol}: {live_close_err}")

    supabase.table(table_name).update(close_update).eq(db_key_name, db_record_id).execute()
    
    # Check if there are other open positions for this symbol
    open_pos = supabase.table(table_name).select('id').eq('symbol', symbol).eq('status', 'open').execute()
    all_closed = len(open_pos.data) == 0 if open_pos.data else True
    sm.on_position_closed(symbol, reason, all_closed=all_closed)
    
    from app.strategy.dynamic_sl_manager import cancel_all_sl_orders
    await cancel_all_sl_orders(
        symbol=symbol,
        position=pos,
        supabase=supabase,
        reason=reason
    )

    p_rule_code = pos.get('rule_code') or pos.get('rule_entry') or "Cc-Manual"
    # Enriquecer close_reason con sl_type para análisis post-deploy
    detailed_reason = reason
    sl_type = pos.get('sl_type', '')
    if reason.startswith('sl_') and sl_type and sl_type not in reason:
        detailed_reason = f"{reason}_{sl_type}"
    
    supabase.table('paper_trades').insert({
        'symbol': symbol,
        'side': pos['side'],
        'entry_price': entry,
        'exit_price': price,
        'total_pnl_usd': round(total_pnl, 4),
        'total_pnl_pct': round(pnl_pct, 4),
        'close_reason': detailed_reason[:30],
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'paper',
        'rule_code': p_rule_code[:10]
    }).execute()
    
    # ── REGISTRAR PN EN CAPITAL ACUMULADO (Interés Compuesto) ──
    try:
        from app.core.capital_manager import register_realized_pnl
        # Determinar mercado (heuristicamente por símbolo)
        market = 'forex' if any(x in symbol for x in ['EUR', 'GBP', 'JPY', 'XAU']) else 'crypto'
        register_realized_pnl(market, total_pnl)
    except Exception as cap_e:
        log_warning(MODULE, f"Error actualizando capital acumulado: {cap_e}")

    # ── CANCELAR ÓRDENES HUÉRFANAS ──
    # Al cerrar la posición, cancelar todas las pending_orders y actualizar orders
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        # 1. Cancelar pending_orders pendientes para este símbolo
        supabase.table('pending_orders').update({
            'status': 'cancelled',
            'cancelled_at': now_iso,
            'updated_at': now_iso
        }).eq('symbol', symbol).eq('status', 'pending').execute()
        
        # 2. Actualizar orders asociados al cierre (marcar como cerrados)
        close_status = 'sl_hit' if reason == 'sl' else ('tp_hit' if 'tp' in reason else 'closed')
        supabase.table('orders').update({
            'status': close_status,
            'closed_at': now_iso
        }).eq('symbol', symbol).eq('status', 'open').execute()
        
        log_info(MODULE, f"🧹 Órdenes pendientes canceladas para {symbol} (razón: {reason})")
    except Exception as cancel_e:
        log_warning(MODULE, f"Error cancelando órdenes huérfanas de {symbol}: {cancel_e}")

    # Remove from BOT_STATE
    if pos_id:
        BOT_STATE.positions.pop(pos_id, None)
    else:
        # Fallback for symbol-only entries
        BOT_STATE.positions.pop(symbol, None)

    # Register SL cooldown if closed by any SL mechanism (Corrección #2)
    sl_reasons = ('sl', 'backstop', 'dynamic_sl', 'time_sl', 'stop_loss')
    if any(r in reason.lower() for r in sl_reasons):
        register_sl_event(symbol, side)

    log_info(MODULE, f"🏁 FULL CLOSE [{symbol}] ({reason}) at ${price:,.2f} | Total PnL: ${total_pnl:.2f}")


async def _handle_unexpected_close(
    symbol, position, real_data,
    supabase, telegram_bot
):
    """
    La posición fue cerrada por Binance sin que el bot lo supiera.
    Puede ser: liquidación, SL ejecutado, TP ejecutado, o cierre manual.
    """
    # Determinar razón probable
    entry_price   = float(position.get('avg_entry', 0))
    liq_price     = float(real_data.get('liquidationPrice', 0))

    reason = 'unknown'
    # In Futures, if liq price was hit, it's a liquidation.
    # Note: liquidationPrice is where it WAS at last check or current.
    # If closed now, we check if it was close to liq.
    if liq_price > 0:
         # Rough heuristic: if it closed without bot intervention and we have liq price, 
         # it might be liquidation. But specifically for binance, 
         # usually we check if it was hit.
         reason = 'liquidation'
    elif position.get('sl_price'):
        reason = 'sl_or_tp_hit'

    # Calcular PnL aproximado para registro de capital
    entry_p = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    qty = float(position.get('size') or 0)
    # Intentar obtener precio actual del ticker o snapshot
    current_p = entry_p
    try:
        ticker = await provider.get_ticker(symbol)
        current_p = float(ticker['price'])
    except:
        pass
    
    pnl_usd = (current_p - entry_p) * qty if position.get('side', 'long').lower() in ['long', 'buy'] else (entry_p - current_p) * qty

    # Actualizar Supabase
    pos_id = position.get('id')
    update_fields = {
        'status': 'closed', # Cambiado de is_open: False a status: closed para consistencia
        'close_reason': reason,
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'realized_pnl': round(pnl_usd, 4),
        'current_price': current_p
    }

    if pos_id:
        supabase.table('positions').update(update_fields).eq('id', pos_id).execute()
        BOT_STATE.positions.pop(pos_id, None)
    else:
        supabase.table('positions').update(update_fields).eq('symbol', symbol).eq('status', 'open').execute()
        BOT_STATE.positions.pop(symbol, None)

    # ── REGISTRAR PN EN CAPITAL ACUMULADO ──
    try:
        from app.core.capital_manager import register_realized_pnl
        register_realized_pnl('crypto', pnl_usd)
    except Exception as cap_e:
        log_warning(MODULE, f"Error actualizando capital acumulado en unexpected close: {cap_e}")

    # Alerta Telegram
    from app.workers.alerts_service import send_telegram_message
    emoji = "💥" if reason == 'liquidation' else "📌"
    if asyncio.iscoroutinefunction(send_telegram_message):
        await send_telegram_message(
            f"{emoji} POSICIÓN CERRADA POR BINANCE [{symbol}]\n"
            f"Razón detectada: {reason.upper()}\n"
            f"Precio entrada: ${entry_price:,.2f}\n"
            f"Verificar historial en Binance para PnL exacto."
        )
    else:
        send_telegram_message(
            f"{emoji} POSICIÓN CERRADA POR BINANCE [{symbol}]\n"
            f"Razón detectada: {reason.upper()}\n"
            f"Precio entrada: ${entry_price:,.2f}\n"
            f"Verificar historial en Binance para PnL exacto."
        )

    log_warning(MODULE,
        f"Posición {symbol} cerrada externamente: {reason}")
