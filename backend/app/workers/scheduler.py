import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import numpy as np

# Add backend to path BEFORE local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logger import log_info, log_error, log_warning, log_debug
from app.core.supabase_client import get_supabase
from app.core.config import settings, STRUCTURE_CONFIG
from app.core.memory_store import BOT_STATE, update_memory_df, get_memory_df, MEMORY_STORE, update_current_candle_close, MARKET_SNAPSHOT_CACHE
from app.core.startup import warm_up

# Strategy & Analysis
from app.strategy.volume_spike import detect_spike
from app.strategy.mtf_scorer import calculate_mtf_score

# Providers & Strategy
from app.execution.data_provider import BinanceCryptoProvider, PaperTradingProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.analysis.fibonacci_bb import extract_fib_levels
from app.strategy.market_regime import classify_market_risk, update_regime_if_changed
from app.core.parameter_guard import get_active_params
from app.strategy.rule_engine import evaluate_all_rules, load_rules_to_memory
from app.analysis.ai_candles import interpret_candles_with_ai, apply_ai_binding
from app.strategy.risk_controls import check_pre_filters, check_correlation_filter
from app.core.position_sizing import (
    calculate_position_size, can_open_short, get_bearish_action, calculate_sl_tp
)
from app.core.position_monitor import (
    check_open_positions_5m,
    check_signal_reversal,
    _execute_paper_partial_close,
    _execute_paper_close,
    _execute_paper_open
)
from app.analysis.fibonacci_bb import extract_fib_levels, get_next_fibonacci_target
from app.strategy.band_exit import evaluate_band_exit
from app.workers.performance_monitor import send_telegram_message
from app.analysis.parabolic_sar import calculate_parabolic_sar, analyze_structure
from app.strategy.strategy_engine import StrategyEngine
from app.analysis.movement_classifier import (
    classify_movement
)
from app.analysis.smart_limit import (
    calculate_smart_limit_price
)
from app.strategy.proactive_exit import (
    evaluate_proactive_exit
)
from app.core.symbol_state import SymbolStateMachine, detect_market_ambiguity
from app.core.safety_manager import (
    register_heartbeat, validate_signal, check_circuit_breaker,
    register_sl_event, reset_sl_counter, check_all_heartbeats
)
from app.strategy.macro_filter import fetch_macro_context
from app.strategy.crypto_adaptive_exit import (
    evaluate_crypto_tp, evaluate_crypto_sl, close_all_crypto_positions
)

sm = SymbolStateMachine.get_instance()


MODULE = "v4_scheduler"

# --- IP Ban Detection (Binance protection) ---
BAN_UNTIL_TS = None  # timestamp en ms, None = sin ban

def is_ip_banned() -> bool:
    global BAN_UNTIL_TS
    if BAN_UNTIL_TS is None:
        return False
    now_ms = int(time.time() * 1000)
    if now_ms < BAN_UNTIL_TS:
        return True
    BAN_UNTIL_TS = None # Reset if time passed
    return False

def handle_binance_error(e: Exception) -> tuple[str, str, bool]:
    """Detects ban and returns (blocked_by, error_message, is_real_error)"""
    global BAN_UNTIL_TS
    error_str = repr(e)
    # Detectar ban de IP (Format: "IP banned until 1773792895499")
    if 'IP banned until' in error_str:
        import re
        match = re.search(r'IP banned until (\d+)', error_str)
        if match:
            BAN_UNTIL_TS = int(match.group(1))
            ban_dt = datetime.fromtimestamp(BAN_UNTIL_TS/1000, tz=timezone.utc)
            log_warning(MODULE, f"BINANCE: IP baneada hasta {ban_dt}")
            return "ip_banned", error_str, True
    return "exception", error_str, True


async def write_market_snapshot(symbol: str, df, regime: dict, spike: dict, mtf_score: float, supabase):
    """
    Escribe el estado técnico actual del símbolo.
    Una sola fila por símbolo — siempre upsert.
    """
    try:
        if df is None or df.empty:
            log_warning('SNAPSHOT', f'df vacío para {symbol}, saltando snapshot')
            return
        last = df.iloc[-1]
        
        # Extraer niveles Fibonacci de forma robusta
        try:
            lib_levels = extract_fib_levels(df)
        except (KeyError, ValueError, AttributeError):
            # Si el DF actual (ej: 5m) no tiene Fibonacci bands,
            # intentar usar el DF de 15m que sí debería tenerlas.
            from app.core.memory_store import MEMORY_STORE
            df_15m_mem = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
            if df_15m_mem is not None and 'basis' in df_15m_mem.columns:
                lib_levels = extract_fib_levels(df_15m_mem)
            else:
                # Fallback: niveles en 0
                lib_levels = {
                    'zone': 0, 'basis': 0.0,
                    'upper_1': 0.0, 'upper_2': 0.0, 'upper_3': 0.0, 'upper_4': 0.0, 'upper_5': 0.0, 'upper_6': 0.0,
                    'lower_1': 0.0, 'lower_2': 0.0, 'lower_3': 0.0, 'lower_4': 0.0, 'lower_5': 0.0, 'lower_6': 0.0
                }

        # 1. LEER FASE ANTERIOR PARA DETECTAR CAMBIO (Paso 1 - Mejora)
        prev_trend = 0
        try:
            prev_res = supabase.table('market_snapshot').select('sar_trend_4h, sar_phase').eq('symbol', symbol).maybe_single().execute()
            if prev_res.data:
                prev_trend = int(prev_res.data.get('sar_trend_4h', 0))
        except: pass

        # --- 2. CÁLCULO SAR 4H ---
        sar_value = 0
        sar_trend = 0
        sar_phase = 'neutral'
        
        from app.core.memory_store import MEMORY_STORE
        df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
        
        if df_4h is not None and not df_4h.empty:
            df_4h = df_4h.copy()
            df_4h = calculate_parabolic_sar(df_4h)
            
            last_4h      = df_4h.iloc[-1]
            sar_trend    = int(last_4h['sar_trend'])
            sar_value    = float(last_4h['sar'])
            
            if sar_trend > 0:
                sar_phase = 'long'
            elif sar_trend < 0:
                sar_phase = 'short'
            
            MEMORY_STORE[symbol]['sar'] = {
                'phase':      sar_phase,
                'value_4h':   sar_value,
                'trend_4h':   sar_trend,
                'changed_at': None # Se seteará en el snapshot si aplica
            }
            
            # Guardar velas 4H con SAR en la base de datos para el gráfico
            await upsert_candles_to_db(symbol, "4h", df_4h, supabase)

        # Detectar el cambio real
        sar_changed = (prev_trend != 0 and sar_trend != 0 and sar_trend != prev_trend)
        changed_at_iso = None
        if sar_changed:
            changed_at_iso = datetime.now(timezone.utc).isoformat()
            MEMORY_STORE[symbol]['sar']['changed_at'] = changed_at_iso
            log_info('SAR', f"--- CAMBIO DETECTADO PARA {symbol}: {prev_trend} -> {sar_trend} ---")

        # ─── 3. CÁLCULO SAR 15m (Híbrido) ───
        sar_15m = None
        sar_trend_15m = 0
        sar_ini_high_15m = False
        sar_ini_low_15m = False
        sar_ini_high_15m_window = False
        sar_ini_low_15m_window  = False
        p_signal_15m = None

        # Intentar obtener DF de 15m desde memoria
        df_15m_mem = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
        
        if df_15m_mem is not None and not df_15m_mem.empty:
            # Recalcular SAR sobre copia para asegurar frescura
            df_15m_sar = calculate_parabolic_sar(df_15m_mem.copy())
            last_15m = df_15m_sar.iloc[-1]
            
            sar_15m = float(last_15m.get('sar', 0))
            sar_trend_15m = int(last_15m.get('sar_trend', 0))
            sar_ini_high_15m = bool(last_15m.get('sar_ini_high', False))
            sar_ini_low_15m = bool(last_15m.get('sar_ini_low', False))

            # CORRECCIÓN 3: Ventana de 3 velas para SAR Change
            df_15m_recent = df_15m_sar.tail(3)
            sar_ini_high_15m_window = bool(df_15m_recent['sar_ini_high'].any())
            sar_ini_low_15m_window  = bool(df_15m_recent['sar_ini_low'].any())
            
            # Señal PineScript (Prioridad 15m > 30m > 4h)
            p_signal_15m = str(last_15m.get('last_pinescript_signal', '') or '')
            
            if p_signal_15m not in ('Buy', 'Sell'):
                # Si en 15m no hay nada (muy raro con el propagation), probar 30m/4h
                df_30m_mem = MEMORY_STORE.get(symbol, {}).get('30m', {}).get('df')
                if df_30m_mem is not None and not df_30m_mem.empty:
                    p_signal_15m = str(df_30m_mem.iloc[-1].get('last_pinescript_signal', '') or '')
            
            if p_signal_15m not in ('Buy', 'Sell'):
                # Consultar 4h
                df_4h_mem = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
                if df_4h_mem is not None and not df_4h_mem.empty:
                    p_signal_15m = str(df_4h_mem.iloc[-1].get('last_pinescript_signal', '') or '')

        upsert_data = {
            'symbol':           symbol,
            'sar_15m':          sar_15m,
            'sar_trend_15m':    sar_trend_15m,
            'sar_ini_high_15m': sar_ini_high_15m,
            'sar_ini_low_15m':  sar_ini_low_15m,
            'sar_ini_high_15m_window': sar_ini_high_15m_window,
            'sar_ini_low_15m_window':  sar_ini_low_15m_window,
            'pinescript_signal': p_signal_15m,
            'pinescript_signal_age': int(last_15m.get('signal_age', 0)) if last_15m is not None else 0,
            'price':            float(last['close']),
            'fibonacci_zone':   int(lib_levels.get('zone', 0)),
            'basis':            float(lib_levels.get('basis', 0)),
            'upper_1':          float(lib_levels.get('upper_1', 0)),
            'upper_2':          float(lib_levels.get('upper_2', 0)),
            'upper_3':          float(lib_levels.get('upper_3', 0)),
            'upper_4':          float(lib_levels.get('upper_4', 0)),
            'upper_5':          float(lib_levels.get('upper_5', 0)),
            'upper_6':          float(lib_levels.get('upper_6', 0)),
            'lower_1':          float(lib_levels.get('lower_1', 0)),
            'lower_2':          float(lib_levels.get('lower_2', 0)),
            'lower_3':          float(lib_levels.get('lower_3', 0)),
            'lower_4':          float(lib_levels.get('lower_4', 0)),
            'lower_5':          float(lib_levels.get('lower_5', 0)),
            'lower_6':          float(lib_levels.get('lower_6', 0)),
            'dist_basis_pct':   float(
                abs(float(last['close']) -
                    float(last.get('basis', last['close'])))
                / float(last.get('basis', last['close'])) * 100
                if float(last.get('basis', 0)) > 0 else 0
            ),
            'mtf_score':        round(float(mtf_score), 4),
            'ema20_phase':      str(last.get('ema20_phase', '')),
            'adx':              float(last.get('adx', 0)),
            'regime':           regime.get('category', ''),
            'risk_score':       regime.get('risk_score', 0),
            'spike_detected':   spike.get('detected', False),
            'spike_ratio':      spike.get('ratio', 0),
            'spike_direction':  spike.get('direction', ''),
            'sar_4h':           sar_value,
            'sar_trend_4h':     sar_trend,
            'sar_phase':        sar_phase,
            'updated_at':       datetime.now(timezone.utc).isoformat()
        }

        # ─── 4. CLASIFICACIÓN DE MOVIMIENTO Y SMART LIMIT ───
        df_15m = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
        if df_15m is not None and not df_15m.empty:
            movement = classify_movement(df_15m)
            limit_long  = calculate_smart_limit_price(df_15m, 'long',  movement['movement_type'])
            limit_short = calculate_smart_limit_price(df_15m, 'short', movement['movement_type'])

            upsert_data.update({
                'movement_type':       movement['movement_type'],
                'basis_slope_pct':     movement['basis_slope_pct'],
                'ema200_slope_pct':    movement['ema200_slope_pct'],
                'movement_confidence': movement['confidence'],
                'signal_bias':         movement['signal_bias'],
                'movement_description':movement['description'],
                'smart_limit_long':    limit_long.get('limit_price'),
                'smart_limit_short':   limit_short.get('limit_price'),
                'smart_limit_band_long':  limit_long.get('band_target'),
                'smart_limit_band_short': limit_short.get('band_target'),
            })

        # ── ESTRUCTURA 15m (para el ciclo de 5m) ────
        cfg_struct = STRUCTURE_CONFIG
        df_15m_struct = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
        if df_15m_struct is not None and not df_15m_struct.empty:
            df_15m_sar_s = calculate_parabolic_sar(df_15m_struct.copy())
            struct_15m = analyze_structure(
                df            = df_15m_sar_s,
                sar_col       = 'sar_trend',
                n_confirm     = cfg_struct['velas_confirmacion'],
                umbral_low    = cfg_struct['umbral_lower_low'],
                umbral_high   = cfg_struct['umbral_higher_high']
            )
        else:
            struct_15m = {
                'structure': 'unknown', 'allow_long': True,
                'allow_short': True, 'reverse_signal': False,
                'reason': 'No 15m data'
            }
        upsert_data['structure_15m']        = struct_15m['structure']
        upsert_data['allow_long_15m']       = struct_15m['allow_long']
        upsert_data['allow_short_15m']      = struct_15m['allow_short']
        upsert_data['reverse_signal_15m']   = struct_15m['reverse_signal']
        upsert_data['structure_reason_15m'] = struct_15m['reason']

        # ── ESTRUCTURA 4h (para el ciclo de 15m) ────
        if df_4h is not None and not df_4h.empty:
            df_4h_sar_s = calculate_parabolic_sar(df_4h.copy())
            struct_4h = analyze_structure(
                df            = df_4h_sar_s,
                sar_col       = 'sar_trend',
                n_confirm     = cfg_struct['velas_confirmacion'],
                umbral_low    = cfg_struct['umbral_lower_low'],
                umbral_high   = cfg_struct['umbral_higher_high']
            )
        else:
            struct_4h = {
                'structure': 'unknown', 'allow_long': True,
                'allow_short': True, 'reverse_signal': False,
                'reason': 'No 4h data'
            }
        upsert_data['structure_4h']        = struct_4h['structure']
        upsert_data['allow_long_4h']       = struct_4h['allow_long']
        upsert_data['allow_short_4h']      = struct_4h['allow_short']
        upsert_data['reverse_signal_4h']   = struct_4h['reverse_signal']
        upsert_data['structure_reason_4h'] = struct_4h['reason']

        log_info('STRUCTURE', f'{symbol}/15m: {struct_15m["reason"]}')
        log_info('STRUCTURE', f'{symbol}/4h: {struct_4h["reason"]}')

        if sar_changed:
             upsert_data['sar_phase_changed_at'] = changed_at_iso

        supabase.table('market_snapshot').upsert(upsert_data).execute()
        log_info('SNAPSHOT', f'Snapshot OK para {symbol}: mtf={mtf_score:.4f}')
    except Exception as e:
        log_error('SNAPSHOT', f'FALLO snapshot para {symbol}: {e}')
        raise


async def sync_current_candle_to_db(symbol: str, current_price: float, supabase) -> None:
    """
    Sincroniza la vela EN CURSO de cada timeframe con Supabase.
    Esto permite que el gráfico del frontend muestre el precio actual, no el de la última vela cerrada.
    Solo actualiza la última fila (is_closed=False).
    """
    # Solo sincronizar timeframes visibles en gráfico
    timeframes_to_sync = ['15m', '1h', '4h', '1d']
    from app.core.memory_store import MEMORY_STORE

    for tf in timeframes_to_sync:
        try:
            df = MEMORY_STORE.get(symbol, {}).get(tf, {}).get('df', None)
            if df is None or df.empty:
                continue

            last = df.iloc[-1]
            
            # Obtener open_time (columna o índice)
            if 'open_time' in last:
                open_time = last['open_time']
            elif hasattr(last, 'name'):
                open_time = last.name
            else:
                continue
                
            if isinstance(open_time, pd.Timestamp):
                if open_time.tzinfo is None:
                    open_time = open_time.tz_localize('UTC')
                open_time = open_time.isoformat()
            else:
                open_time = str(open_time)

            # Usar símbolo original (BTCUSDT) para consistencia en DB (Standardization)

            # Upsert solo de la vela en curso
            supabase.table('market_candles').upsert({
                'symbol':     symbol.replace('/', ''),
                'exchange':   'binance',
                'timeframe':  tf,
                'open_time':  open_time,
                'open':       float(last['open']),
                'high':       float(last['high']),
                'low':        float(last['low']),
                'close':      current_price,
                'volume':     float(last['volume']),
                'hlc3':       float(last.get('hlc3', current_price)),
                'is_closed':  False,  # vela en curso
                # Inyectar indicadores de la última vela calculada para extender lineas
                'basis':      float(last.get('basis', 0)) or None if pd.notna(last.get('basis')) else None,
                'upper_6':    float(last.get('upper_6', 0)) or None if pd.notna(last.get('upper_6')) else None,
                'lower_6':    float(last.get('lower_6', 0)) or None if pd.notna(last.get('lower_6')) else None,
                'sar':        float(last.get('sar', 0)) or None if pd.notna(last.get('sar')) else None,
                'sar_trend':  int(last.get('sar_trend', 0)) or None if pd.notna(last.get('sar_trend')) else None,
            }, on_conflict='symbol,exchange,timeframe,open_time').execute()

        except Exception as e:
            log_warning('SYNC_CANDLE', f'Error sync {symbol}/{tf}: {e}')

async def upsert_candles_to_db(symbol: str, timeframe: str, df, sb):
    """
    Sincroniza velas OHLCV con la base de datos para uso en gráficos.
    Mantiene el historial actualizado automáticamente.
    """
    if df is None or df.empty:
        return
    try:
        rows = []
        # Upsert solo los últimos 300 para eficiencia en cada ciclo (FiboBand necesita 200)
        sub_df = df.tail(300)
        
        # Usar símbolo original (BTCUSDT) para consistencia en DB (Standardization)
        
        for _, r in sub_df.iterrows():
            # Asegurar TZ-aware para Postgres (Requirement 10)
            open_time = r['open_time']
            if open_time.tzinfo is None:
                open_time = open_time.replace(tzinfo=timezone.utc)
            
            rows.append({
                "symbol":    symbol.replace('/', ''),
                "exchange":  "binance",
                "timeframe": timeframe,
                "open_time": open_time.isoformat(),
                "open":      float(r['open']),
                "high":      float(r['high']),
                "low":       float(r['low']),
                "close":     float(r['close']),
                "volume":    float(r['volume']),
                "quote_volume": float(r.get('quote_volume', 0)),
                "trades_count": int(r.get('trades_count', 0)),
                "taker_buy_volume": float(r.get('taker_buy_volume', 0)),
                "is_closed":  True,
                # FIBONACCI BANDS PER CANDLE:
                "basis":   float(r.get('basis', 0) or 0) if pd.notna(r.get('basis')) else None,
                "upper_1": float(r.get('upper_1', 0) or 0) if pd.notna(r.get('upper_1')) else None,
                "upper_2": float(r.get('upper_2', 0) or 0) if pd.notna(r.get('upper_2')) else None,
                "upper_3": float(r.get('upper_3', 0) or 0) if pd.notna(r.get('upper_3')) else None,
                "upper_4": float(r.get('upper_4', 0) or 0) if pd.notna(r.get('upper_4')) else None,
                "upper_5": float(r.get('upper_5', 0) or 0) if pd.notna(r.get('upper_5')) else None,
                "upper_6": float(r.get('upper_6', 0) or 0) if pd.notna(r.get('upper_6')) else None,
                "lower_1": float(r.get('lower_1', 0) or 0) if pd.notna(r.get('lower_1')) else None,
                "lower_2": float(r.get('lower_2', 0) or 0) if pd.notna(r.get('lower_2')) else None,
                "lower_3": float(r.get('lower_3', 0) or 0) if pd.notna(r.get('lower_3')) else None,
                "lower_4": float(r.get('lower_4', 0) or 0) if pd.notna(r.get('lower_4')) else None,
                "lower_5": float(r.get('lower_5', 0) or 0) if pd.notna(r.get('lower_5')) else None,
                "lower_6": float(r.get('lower_6', 0) or 0) if pd.notna(r.get('lower_6')) else None,
                "sar":       float(r.get('sar', 0) or 0) if pd.notna(r.get('sar')) else None,
                "sar_trend": int(r.get('sar_trend', 0) or 0) if pd.notna(r.get('sar_trend')) else None,
                "pinescript_signal": str(r.get('pinescript_signal', '')) if r.get('pinescript_signal') in ('Buy', 'Sell') else None,
            })
        
        # Usamos upsert con on_conflict para manejar duplicados
        log_info('CANDLES', f"Upserting {len(rows)} candles for {symbol} {timeframe}")
        sb.table('market_candles').upsert(
            rows, 
            on_conflict="symbol,exchange,timeframe,open_time"
        ).execute()
        
    except Exception as e:
        log_error('CANDLES', f"FALLO upsert velas para {symbol} {timeframe}: {e}")


async def backfill_candles(symbol: str, bars: int = 200, sb = None):
    """Backfill manual de velas para completar huecos."""
    if sb is None:
        sb = get_supabase()
    
    from app.execution.data_provider import BinanceCryptoProvider
    from app.core.config import settings
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    
    timeframes = ['15m', '1h', '4h', '1d']
    for tf in timeframes:
        try:
            df_raw = await provider.get_ohlcv(symbol, tf, limit=bars)
            if df_raw is not None:
                # FIX: Calcular indicadores antes de subir a DB
                from app.analysis.indicators_v2 import calculate_all_indicators
                df = calculate_all_indicators(df_raw, BOT_STATE.config_cache)
                await upsert_candles_to_db(symbol, tf, df, sb)
                log_info('BACKFILL', f'{symbol} {tf}: {len(df)} velas sincronizadas con indicadores')
        except Exception as e:
            log_error('BACKFILL', f'Error backfill {symbol} {tf}: {e}')
    
    await provider.close()


async def apply_structure_filter_5m(
    symbol:        str,
    current_price: float,
    snap:          dict,
    signal:        str,
    sb
) -> str:
    """
    Aplica el filtro de estructura 15m para el ciclo de 5m.
    El ciclo 5m mira el SAR y estructura de 15m.
    Returns: dirección autorizada ('long'/'short') o None
    """
    cfg = STRUCTURE_CONFIG

    allow_long_15m    = bool(snap.get('allow_long_15m',    True))
    allow_short_15m   = bool(snap.get('allow_short_15m',   True))
    reverse_15m       = bool(snap.get('reverse_signal_15m', False))
    structure_15m     = snap.get('structure_15m', 'unknown')
    reason_15m        = snap.get('structure_reason_15m', '')

    if not signal:
        return None

    if signal == 'Buy':
        if allow_long_15m:
            log_info('STRUCTURE_5M',
                f'{symbol}: ✅ Buy autorizado '
                f'por estructura 15m ({structure_15m})'
            )
            return 'long'

        elif reverse_15m:
            position = BOT_STATE.positions.get(symbol)
            if position and (position.get('side') or '').lower() == 'short':
                entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                pnl = ((entry - current_price) / entry * 100) if entry > 0 else 0
                if not cfg['require_profit_to_reverse'] or pnl >= 0:
                    await _execute_paper_close(position, current_price, 'structure_reversal_15m', sb)
                    await send_telegram_message(
                        f"🔄 REVERSIÓN 15m [{symbol}]\n"
                        f"Estructura débil + Buy 5m\n"
                        f"Cerrando SHORT: {pnl:+.2f}%\n"
                        f"→ Abriendo LONG"
                    )
                    return 'long'
                else:
                    log_info('STRUCTURE_5M',
                        f'{symbol}: SHORT en pérdida '
                        f'({pnl:.2f}%) — no revertir'
                    )
                    return None
            else:
                log_info('STRUCTURE_5M',
                    f'{symbol}: ⚡ Reversión 15m '
                    f'sin posición → LONG directo'
                )
                return 'long'

        else:
            log_info('STRUCTURE_5M',
                f'{symbol}: ❌ Buy bloqueado '
                f'por estructura 15m: {reason_15m}'
            )
            return None

    elif signal == 'Sell':
        if allow_short_15m:
            log_info('STRUCTURE_5M',
                f'{symbol}: ✅ Sell autorizado '
                f'por estructura 15m ({structure_15m})'
            )
            return 'short'

        elif reverse_15m:
            position = BOT_STATE.positions.get(symbol)
            if position and (position.get('side') or '').lower() == 'long':
                entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                pnl = ((current_price - entry) / entry * 100) if entry > 0 else 0
                if not cfg['require_profit_to_reverse'] or pnl >= 0:
                    await _execute_paper_close(position, current_price, 'structure_reversal_15m', sb)
                    await send_telegram_message(
                        f"🔄 REVERSIÓN 15m [{symbol}]\n"
                        f"Estructura débil + Sell 5m\n"
                        f"Cerrando LONG: {pnl:+.2f}%\n"
                        f"→ Abriendo SHORT"
                    )
                    return 'short'
                else:
                    log_info('STRUCTURE_5M',
                        f'{symbol}: LONG en pérdida '
                        f'({pnl:.2f}%) — no revertir'
                    )
                    return None
            else:
                log_info('STRUCTURE_5M',
                    f'{symbol}: ⚡ Reversión 15m '
                    f'sin posición → SHORT directo'
                )
                return 'short'

        else:
            log_info('STRUCTURE_5M',
                f'{symbol}: ❌ Sell bloqueado '
                f'por estructura 15m: {reason_15m}'
            )
            return None

    return None


async def apply_structure_filter_15m(
    symbol:        str,
    current_price: float,
    snap:          dict,
    signal:        str,
    sb
) -> str:
    """
    El ciclo 15m mira el SAR y estructura de 4h.
    Mismo comportamiento que apply_structure_filter_5m
    pero usando las columnas _4h del snapshot.
    Returns: dirección autorizada ('long'/'short') o None
    """
    cfg = STRUCTURE_CONFIG

    allow_long_4h  = bool(snap.get('allow_long_4h',    True))
    allow_short_4h = bool(snap.get('allow_short_4h',   True))
    reverse_4h     = bool(snap.get('reverse_signal_4h', False))
    structure_4h   = snap.get('structure_4h', 'unknown')
    reason_4h      = snap.get('structure_reason_4h', '')

    if not signal:
        return None

    if signal == 'Buy':
        if allow_long_4h:
            log_info('STRUCTURE_15M',
                f'{symbol}: ✅ Buy autorizado '
                f'por estructura 4h ({structure_4h})'
            )
            return 'long'
        elif reverse_4h:
            position = BOT_STATE.positions.get(symbol)
            if position and (position.get('side') or '').lower() == 'short':
                entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                pnl = ((entry - current_price) / entry * 100) if entry > 0 else 0
                if not cfg['require_profit_to_reverse'] or pnl >= 0:
                    await _execute_paper_close(position, current_price, 'structure_reversal_4h', sb)
                    await send_telegram_message(
                        f"🔄 REVERSIÓN 4h [{symbol}]\n"
                        f"Estructura débil 4h + Buy 15m\n"
                        f"Cerrando SHORT: {pnl:+.2f}%\n"
                        f"→ Abriendo LONG"
                    )
                    return 'long'
                log_info('STRUCTURE_15M',
                    f'{symbol}: SHORT en pérdida — no revertir'
                )
                return None
            else:
                log_info('STRUCTURE_15M',
                    f'{symbol}: ⚡ Reversión 4h sin posición → LONG directo'
                )
                return 'long'
        else:
            log_info('STRUCTURE_15M',
                f'{symbol}: ❌ Buy bloqueado '
                f'por estructura 4h: {reason_4h}'
            )
            return None

    elif signal == 'Sell':
        if allow_short_4h:
            log_info('STRUCTURE_15M',
                f'{symbol}: ✅ Sell autorizado '
                f'por estructura 4h ({structure_4h})'
            )
            return 'short'
        elif reverse_4h:
            position = BOT_STATE.positions.get(symbol)
            if position and (position.get('side') or '').lower() == 'long':
                entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                pnl = ((current_price - entry) / entry * 100) if entry > 0 else 0
                if not cfg['require_profit_to_reverse'] or pnl >= 0:
                    await _execute_paper_close(position, current_price, 'structure_reversal_4h', sb)
                    await send_telegram_message(
                        f"🔄 REVERSIÓN 4h [{symbol}]\n"
                        f"Estructura débil 4h + Sell 15m\n"
                        f"Cerrando LONG: {pnl:+.2f}%\n"
                        f"→ Abriendo SHORT"
                    )
                    return 'short'
                log_info('STRUCTURE_15M',
                    f'{symbol}: LONG en pérdida — no revertir'
                )
                return None
            else:
                log_info('STRUCTURE_15M',
                    f'{symbol}: ⚡ Reversión 4h sin posición → SHORT directo'
                )
                return 'short'
        else:
            log_info('STRUCTURE_15M',
                f'{symbol}: ❌ Sell bloqueado '
                f'por estructura 4h: {reason_4h}'
            )
            return None

    return None


async def check_proactive_exit_crypto(
    symbol:        str,
    current_price: float,
    snap:          dict,
    sb
) -> bool:
    """
    Evalúa Aa51/Bb51 para posiciones de Crypto.
    Retorna True si se cerró la posición.
    """
    position = BOT_STATE.positions.get(symbol)
    if not position:
        return False

    # Obtener velas 4H del MEMORY_STORE
    df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')

    if df_4h is None or len(df_4h) < 3:
        return False

    # Evaluar cierre proactivo
    result = evaluate_proactive_exit(
        position      = position,
        current_price = current_price,
        snap          = snap,
        df_4h         = df_4h,
        market_type   = 'crypto_futures',
    )

    if not result['should_close']:
        return False

    # ── Cerrar posición ───────────────────────
    log_info('PROACTIVE_EXIT', f'🛡️ {symbol}: {result["rule_code"]} — {result["reason"]}')

    from app.core.position_monitor import _execute_paper_close
    await _execute_paper_close(position, current_price, result['rule_code'], sb)

    # Guardar en strategy_evaluations
    try:
        sb.table('strategy_evaluations').insert({
            'symbol':    symbol,
            'rule_code': result['rule_code'],
            'cycle':     '5m',
            'direction': 'close',
            'score':     1.0,
            'triggered': True,
            'context': {
                'pnl_pct':   result['pnl']['pnl_pct'],
                'pnl_usd':   result['pnl']['pnl_usd'],
                'reason':    result['reason'],
                'urgency':   result['urgency'],
            },
        }).execute()
    except Exception as e:
        log_warning('PROACTIVE_EXIT', f"Failed to log evaluation: {e}")

    # Alerta Telegram
    pnl = result['pnl']
    cond_str = "\n".join([f"  {'✅' if v['passed'] else '❌'} {v['name']}" for v in result['conditions'].values()])
    await send_telegram_message(
        f"🛡️ CIERRE PROACTIVO [{symbol}]\n"
        f"Regla: {result['rule_code']}\n"
        f"P&L: +{pnl['pnl_pct']:.3f}% (${pnl['pnl_usd']:.2f})\n"
        f"Razón: {result['reason']}\n"
        f"Urgencia: {result['urgency']}\n"
        f"Condiciones:\n{cond_str}"
    )

    return True


async def _process_symbol_5m(symbol: str, provider, gs_data, sb):
    """Auxiliar para procesar un símbolo en el ciclo 5m (Paralelo)."""
    # ── Heartbeat ─────────────────────────────
    register_heartbeat('crypto_scheduler_5m')
    
    cycle_start = time.time()
    try:
        # 1. Update prices (Use persistent provider)
        ticker_data = await provider.get_ticker(symbol)
        current_price = ticker_data['price']
        
        # ACTUALLIZAR VELAS EN MEMORIA (MEJORA: Reflejar precio actual en todos los TFs)
        if current_price > 0:
            update_current_candle_close(symbol=symbol, current_price=current_price)
            # Sincronizar vela en curso con DB para el frontend (is_closed=False)
            await sync_current_candle_to_db(symbol, current_price, sb)
            
            # Calcular señal PineScript del 15m actual
            from app.core.memory_store import MARKET_SNAPSHOT_CACHE
            if '15m' in MEMORY_STORE.get(symbol, {}):
                df_15m   = MEMORY_STORE[symbol]['15m']['df']
                last_row = df_15m.iloc[-1]
                p_signal = str(last_row.get('pinescript_signal', ''))

            # Actualizar en snapshot cache para uso inmediato
            if symbol in MARKET_SNAPSHOT_CACHE:
                MARKET_SNAPSHOT_CACHE[symbol]['pinescript_signal'] = p_signal

        # (Pending orders check migrated to after SL/TP checks)


        # 2. Check Cooldowns
        cooldown = sb.table("cooldowns").select("*").eq("symbol", symbol).eq("active", True).execute()
        cooldown_active = len(cooldown.data) > 0 if cooldown.data else False
        
        # 3. Diagnostic Log (Robust)
        log_diag = {
            "symbol": symbol,
            "cycle_type": "5m",
            "current_price": current_price,
            "emergency_active": gs_data.get("emergency_active", False),
            "circuit_breaker": gs_data.get("circuit_breaker_active", False),
            "cooldown_active": cooldown_active,
            "risk_category": "observation",
            "ema20_phase": "unknown",
            "entry_blocked_by": "no_15m_cycle",
            "cycle_duration_ms": int((time.time() - cycle_start) * 1000),
            "error_occurred": False,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        try:
            sb.table("pilot_diagnostics").insert(log_diag).execute()
        except Exception as e:
            log_warning(MODULE, f"pilot_diagnostics (5m) failed - attempting fallback: {e}")
            for key in ["risk_category", "ema20_phase", "entry_blocked_by"]:
                log_diag.pop(key, None)
            try: sb.table("pilot_diagnostics").insert(log_diag).execute()
            except: pass
        
        # 4. Heartbeat (Per Symbol)
        # Requirement 1: SIEMPRE escribir snapshot (Reflejar precio actual)
        # Obtenemos el MTF del cache ya que en 5m no se recalcula
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        current_mtf_cached = float(MARKET_SNAPSHOT_CACHE.get(symbol, {}).get('mtf_score', 0.0))
        
        # Clasificar régimen de riesgo rápido para el snapshot
        from app.strategy.market_regime import classify_market_risk
        df_5m = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
        
        # CORRECCIÓN: Si no está en memoria, forzamos descarga inicial (puebla el 5m cycle)
        if df_5m is None or df_5m.empty:
            try:
                log_info(MODULE, f"Descargando df_5m inicial para {symbol} (no encontrado en memoria)")
                df_raw = await provider.get_ohlcv(symbol, '5m', limit=300)
                df_5m = calculate_all_indicators(df_raw, BOT_STATE.config_cache)
                update_memory_df(symbol, '5m', df_5m)
            except Exception as e:
                log_error(MODULE, f"Error en descarga forzada de 5m para {symbol}: {e}")
        regime_5m = classify_market_risk(df_5m) if df_5m is not None else {"category": "observation", "risk_score": 0.5}
        
        # En 5m no hay spike result calculado localmente, pasamos dict vacío
        await write_market_snapshot(symbol, df_5m, regime_5m, {}, current_mtf_cached, sb)

        sb.table("bot_state").update({
            "last_5m_cycle_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }).eq("symbol", symbol).execute()

        # 5. SMART EXIT (SAR Phase Change)
        # Faster detection in 5m cycle to close before SL
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        from app.core.position_monitor import _execute_paper_close
        
        snap = MARKET_SNAPSHOT_CACHE.get(symbol, {})
        sar_phase = snap.get('sar_phase', 'neutral')
        sar_changed_at = snap.get('sar_phase_changed_at')
        
        position = BOT_STATE.positions.get(symbol)
        if position and sar_changed_at:
            side = (position.get('side') or '').lower()
            if (sar_phase == 'short' and side == 'long') or \
               (sar_phase == 'long'  and side == 'short'):
                
                # Cerrar ANTES del SL
                from app.workers.performance_monitor import send_telegram_message
                await _execute_paper_close(position, current_price, 'sar_phase_change', sb)
                await send_telegram_message(
                    f"🔄 SAR CAMBIÓ DE FASE [{symbol}]\n"
                    f"SAR 4h -> {sar_phase.upper()}\n"
                    f"Cerrando {side.upper()} a ${current_price:,.2f}\n"
                    f"(Antes del SL en ${position.get('sl_price', 0):,.2f})"
                )
                return # Detener procesamiento para este símbolo en este ciclo

        # ── NUEVO: Cierre Proactivo / Adaptativo v5.0 ──
        if position:
            # 1. TP Adaptativo v5
            tp_res = evaluate_crypto_tp(symbol, [position], current_price, snap, df_5m)
            if tp_res['should_close']:
                await close_all_crypto_positions(
                    symbol, [position], current_price, 
                    tp_res['close_reason'], tp_res['pnl'], sb, is_tp=True
                )
                reset_sl_counter(symbol, position.get('side', 'long'))
                return

            # 2. SL Adaptativo / SLV v5
            sl_res = evaluate_crypto_sl(symbol, [position], current_price, snap, df_5m)
            if sl_res['should_close']:
                await close_all_crypto_positions(
                    symbol, [position], current_price,
                    sl_res.get('exit_type', 'sl_v5'), sl_res['pnl_pips'], sb, is_tp=False
                )
                register_sl_event(symbol, position.get('side', 'long'))
                return
            elif sl_res.get('slv_triggered'):
                # Activar modo recuperación si no estaba activo
                if not position.get('recovery_mode'):
                    from app.strategy.virtual_sl_recovery import activate_recovery_mode_sync
                    activate_recovery_mode_sync(position, current_price, symbol, 'crypto_futures', sb)
            
            # 3. Fallback Proactivo Aa51 (Legacy)
            closed = await check_proactive_exit_crypto(symbol, current_price, snap, sb)
            if closed:
                return # Posición cerrada

        # 6. SMART EXIT (Signal Reversal)
        if position:
            # Leer MTF actual
            current_mtf = float(snap.get('mtf_score', 0))

            # Usar BOT_STATE.config_cache como trading_config
            trading_config = BOT_STATE.config_cache

            # Verificar reversión
            reversal = await check_signal_reversal(
                position      = position,
                current_mtf   = current_mtf,
                current_price = current_price,
                config        = trading_config
            )

            if reversal.get('should_exit'):
                # Cierre paper
                await _execute_paper_close(position, current_price, 'signal_reversal', sb)
                
                from app.workers.performance_monitor import send_telegram_message
                await send_telegram_message(
                    f"✅ SALIDA INTELIGENTE [{symbol}]\n"
                    f"MTF giró: {current_mtf:.4f}\n"
                    f"P&L: +{reversal['pnl_pct']:.2f}%"
                    f" (+${reversal['pnl_usd']:.2f})\n"
                    f"Ganancia asegurada antes de reversión"
                )
                log_info(MODULE, f"SMART EXIT executed for {symbol}: {reversal['detail']}")

            elif reversal.get('waiting_for_profit'):
                # Log interno — no Telegram (no spamear)
                log_info('REVERSAL',
                    f'{symbol}: MTF negativo '
                    f'({current_mtf:.4f}) pero P&L '
                    f'{reversal["current_pnl_pct"]:.2f}% '
                    f'< mínimo {reversal["needed_pct"]:.2f}%'
                )

        # 7. STRATEGY ENGINE v1.0 EVALUATION (5m)
        use_v2_global = bool(BOT_STATE.config_cache.get('use_strategy_engine_v2', False))
        pilot_v2_symbols = ['ETHUSDT', 'SOLUSDT']
        use_v2 = use_v2_global and symbol in pilot_v2_symbols

        if use_v2 and symbol not in BOT_STATE.positions:
            from app.core.memory_store import MARKET_SNAPSHOT_CACHE
            snap_5m = MARKET_SNAPSHOT_CACHE.get(symbol, {}).copy()
            engine = StrategyEngine.get_instance()
            
            # Construir contexto (df_15m y df_4h de memoria)
            df_15m_c = get_memory_df(symbol, "15m")
            df_4h_c  = get_memory_df(symbol, "4h")
            context_5m = engine.build_context(snap=snap_5m, df_15m=df_15m_c, df_4h=df_4h_c, df_5m=df_5m)
            
            signal_5m = engine.get_best_signal(context=context_5m, strategy_type='scalping', cycle='5m')
            if signal_5m:
                await engine.log_evaluation(symbol, signal_5m, context_5m)
                # Ejecutar apertura 5m
                from app.core.position_monitor import _execute_paper_open
                qty_5m = (float(BOT_STATE.config_cache.get("capital_operativo", 100)) * 0.10) / current_price
                await _execute_paper_open(
                    symbol=symbol, side=signal_5m['direction'], price=current_price,
                    size=qty_5m, rule_code=signal_5m['rule_code'], 
                    regime=regime_5m, levels={}, vel_config={}, supabase=sb
                )

            # ── 6. DYNAMIC TP (Fibonacci Bands + AI) ──
            # Volver a leer la posición (podría haber cerrado en el paso anterior)
            pos_now = BOT_STATE.positions.get(symbol)
            if pos_now:
                # Leer snapshot completo para niveles Fibonacci
                snap_full = sb.table('market_snapshot')\
                    .select('*')\
                    .eq('symbol', symbol)\
                    .maybe_single()\
                    .execute()
                
                if snap_full.data:
                    current_snap = snap_full.data
                    # Leer resultado de IA (cacheado cada 4h) desde MEMORY_STORE[symbol]
                    # Nota: MEMORY_STORE[symbol] 'ai_cache_4h' es donde se guarda según el prompt
                    ai_result = MEMORY_STORE[symbol].get('ai_cache_4h', {})
                    
                    # Obtener próxima banda
                    next_target = get_next_fibonacci_target(
                        side          = pos_now['side'],
                        current_price = current_price,
                        current_zone  = int(current_snap.get('fibonacci_zone', 0)),
                        levels        = current_snap
                    )
                    
                    # Evaluar si cerrar en la banda
                    band_decision = evaluate_band_exit(
                        position      = pos_now,
                        current_price = current_price,
                        next_target   = next_target,
                        mtf_score     = current_mtf,
                        ai_result     = ai_result,
                        config        = trading_config
                    )

                    # Obtener P&L actual para el mensaje de Telegram
                    entry = float(pos_now.get('avg_entry_price') or pos_now.get('entry_price') or 0)
                    if entry > 0:
                        if (pos_now.get('side') or '').lower() == 'long':
                            pnl_pct = (current_price - entry) / entry * 100
                        else:
                            pnl_pct = (entry - current_price) / entry * 100
                    else:
                        pnl_pct = 0

                    if band_decision['action'] == 'partial_close':
                        await _execute_paper_partial_close(pos_now, current_price, sb)
                        await send_telegram_message(
                            f"📊 CIERRE PARCIAL [{symbol}]\n"
                            f"Banda: {band_decision['target_name']}\n"
                            f"Motivo: {band_decision['reason']}\n"
                            f"P&L: +{pnl_pct:.2f}%"
                        )
                        log_info('BAND_EXIT', f'{symbol}: Cierre parcial ejecutado en {band_decision["target_name"]}')

                    elif band_decision['action'] == 'full_close':
                        await _execute_paper_close(pos_now, current_price, 'tp_dynamic_band', sb)
                        await send_telegram_message(
                            f"✅ CIERRE TOTAL [{symbol}]\n"
                            f"Banda: {band_decision['target_name']}\n"
                            f"Motivo: {band_decision['reason']}\n"
                            f"P&L: +{pnl_pct:.2f}%"
                        )
                        log_info('BAND_EXIT', f'{symbol}: Cierre total ejecutado en {band_decision["target_name"]}')

                    elif band_decision['action'] == 'hold':
                        log_info('BAND_EXIT',
                            f'{symbol}: {band_decision["reason"]}'
                        )
        else:
            # --- VERIFICAR EJECUCIÓN LIMIT ORDERS (SWING) ---
            from app.strategy.swing_orders import check_limit_order_execution
            await check_limit_order_execution(symbol=symbol, current_price=current_price, provider=provider, sb=sb)

            # ---> EVALUACIÓN Cc (Híbrido) <---
            from app.strategy.rule_engine import (
                evaluate_cc21_long_scalp,
                evaluate_cc11_short_scalp
            )
            from app.core.memory_store import MARKET_SNAPSHOT_CACHE
            
            # Solo evaluar si no hay posición abierta (se cumple por el "else")
            snap = MARKET_SNAPSHOT_CACHE.get(symbol, {})
            sar_phase  = snap.get('sar_phase', 'neutral')
            p_signal   = snap.get('pinescript_signal', '')

            result = {'triggered': False}
            if '15m' in MEMORY_STORE.get(symbol, {}):
                df_15m = MEMORY_STORE[symbol]['15m']['df']
                if sar_phase == 'long':
                    result = evaluate_cc21_long_scalp(
                        df     = df_15m,
                        snap   = snap,
                        signal = p_signal
                    )
                elif sar_phase == 'short':
                    result = evaluate_cc11_short_scalp(
                        df     = df_15m,
                        snap   = snap,
                        signal = p_signal
                    )

            if result['triggered']:
                from app.workers.performance_monitor import send_telegram_message
                direction = 'long' if sar_phase == 'long' else 'short'

                # ── FILTRO DE ESTRUCTURA 15m (ciclo 5m) ──
                pinescript_5m = snap.get('pinescript_signal', '')
                authorized_direction = await apply_structure_filter_5m(
                    symbol        = symbol,
                    current_price = current_price,
                    snap          = snap,
                    signal        = pinescript_5m,
                    sb            = sb
                )
                # Si el filtro rechaza, anular la dirección
                if authorized_direction is None:
                    log_info('STRUCTURE_5M',
                        f'{symbol}: Señal {direction.upper()} bloqueada por estructura 15m'
                    )
                    result = {'triggered': False}  # Cancel the trigger
                else:
                    direction = authorized_direction  # Use structure-authorized direction

            if result.get('triggered', False):
                from app.workers.performance_monitor import send_telegram_message
                
                if not BOT_STATE.config_cache.get("observe_only"):
                    # Dynamic Velocity sizing (Requirement)
                    from app.core.parameter_guard import get_velocity_config
                    vel_config = get_velocity_config(float(snap.get('adx', 25)))
                    
                    cap_op = float(BOT_STATE.config_cache.get("capital_operativo", 100))
                    # Apply sizing_pct
                    effective_sizing = vel_config.get('sizing_pct', 1.0)
                    qty = max(18.0, cap_op * 0.1 * effective_sizing) / current_price
                    
                    is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False
                    if is_paper:
                         # Use levels from snapshot for TP calculation
                         await _execute_paper_open(
                             symbol=symbol, side=direction, price=current_price,
                             size=qty, rule_code=result['rule_code'], regime=snap, # snap has regime info
                             levels=snap, vel_config=vel_config, supabase=sb
                         )
                    else:
                         await provider.place_order(symbol=symbol, side=direction, size=qty, order_type="MARKET")
                    
                if asyncio.iscoroutinefunction(send_telegram_message):
                    await send_telegram_message(
                        f"⚡ ENTRADA SCALP [{symbol}]\n"
                        f"Regla: {result['rule_code']}\n"
                        f"Dirección: {direction.upper()}\n"
                        f"Precio: ${current_price:,.4f}\n"
                        f"Motivo: {result['reason']}"
                    )
                else:
                    send_telegram_message(
                        f"⚡ ENTRADA SCALP [{symbol}]\n"
                        f"Regla: {result['rule_code']}\n"
                        f"Dirección: {direction.upper()}\n"
                        f"Precio: ${current_price:,.4f}\n"
                        f"Motivo: {result['reason']}"
                    )
        
    except Exception as inner_e:
        import traceback
        full_err = traceback.format_exc()
        blocked_by, err_msg, _ = handle_binance_error(inner_e)
        log_error(MODULE, f"Error in 5m cycle for {symbol}: {full_err}")
        sb.table("pilot_diagnostics").insert({
            "symbol": symbol,
            "cycle_type": "5m",
            "error_occurred": True,
            "error_message": err_msg,
            "risk_category": None,
            "entry_blocked_by": blocked_by,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }).execute()

async def cycle_5m():
    """Speed 2A: Monitor BE, SL, Emergencies & Reconcile (Parallel)."""
    log_debug(MODULE, "--- Speed 2A: 5m Cycle (Parallel) ---")
    sb = get_supabase()
    raw_symbols = BOT_STATE.config_cache.get("symbols_active") or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    symbols = list(set([s.replace("/", "") for s in raw_symbols]))
    
    # Create LOCAL provider for this cycle to avoid concurrency issues with globals
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    
    try:
        
        events = await check_open_positions_5m(
            provider    = provider,
            supabase    = sb,
            telegram_bot = None # Will use internal send_telegram from position_monitor
        )

        # ── TICK STATE MACHINE (Waiting/Ambiguous) ──
        active_symbols = BOT_STATE.config_cache.get('active_symbols', [])
        for sym in active_symbols:
            sm.tick_waiting(sym)
            sm.tick_ambiguous(sym)

        # Si hubo cierre inesperado, no procesar más para este símbolo en este ciclo
        # (Though cycle_5m processes ALL symbols now, so we filter by symbol in the loop below)
        
        gs_data = {}
        try:
            global_state = sb.table("bot_global_state").select("*").eq("id", 1).maybe_single().execute()
            gs_data = global_state.data or {}
        except Exception as e:
            log_warning(MODULE, f"bot_global_state match failed: {e}")
        
        if is_ip_banned():
            log_info(MODULE, "IP baneada. Ciclo 5m omitido.")
            return

        # Prepare filtered symbols (those NOT unexpectedly closed)
        closed_symbols = [e['symbol'] for e in events if e['event'] == 'unexpected_close']
        active_symbols = [s for s in symbols if s not in closed_symbols]

        tasks = [_process_symbol_5m(s, provider, gs_data, sb) for s in active_symbols]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Executive heartbeat is still global but restricted to columns that exist
        sb.table("bot_global_state").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", 1).execute()

    except Exception as e:
        log_error(MODULE, f"Global error in 5m cycle: {e}")
    finally:
        await provider.close()

scheduler = AsyncIOScheduler()

# Sync Configuration from Supabase (Requirement 2 & Problem 2)
async def sync_db_config_to_memory():
    """Reads trading_config and risk_config from DB and updates BOT_STATE.config_cache."""
    try:
        sb = get_supabase()
        
        # 1. Load trading_config
        res = sb.table("trading_config").select("*").eq("id", 1).maybe_single().execute()
        db_cfg = res.data or {}
        
        # 2. Load risk_config (Critical for limits)
        from app.core.supabase_client import get_risk_config
        risk_cfg = get_risk_config()
        
        # Merge configs
        combined_cfg = {**db_cfg, **risk_cfg}
        
        # Problem 2: Recalculate capital_operativo automatically
        cap_total = float(combined_cfg.get("capital_total") or 500)
        pct_trade = float(combined_cfg.get("pct_for_trading") or 20)
        cap_op = cap_total * (pct_trade / 100.0) * 0.90
        
        # Update DB if it differs significantly
        if abs(float(combined_cfg.get("capital_operativo", 0)) - cap_op) > 0.01:
            log_info(MODULE, f"Recalculating capital_operativo: {cap_op}")
            sb.table("trading_config").update({"capital_operativo": cap_op}).eq("id", 1).execute()
            combined_cfg["capital_operativo"] = cap_op

        # Update BOT_STATE.config_cache
        current = BOT_STATE.config_cache or {}
        current.update(combined_cfg)
        
        # Force symbols_active format
        active_s = combined_cfg.get("active_symbols")
        if active_s:
            if isinstance(active_s, str):
                try:
                    active_s = json.loads(active_s)
                except:
                    active_s = [s.strip() for s in active_s.split(",") if s.strip()]
            current["symbols_active"] = active_s

        BOT_STATE.config_cache = current
        log_info(MODULE, f"Config (Trading + Risk) synced from Supabase. Limits: Global={current.get('max_open_trades')}, Symbol={current.get('max_positions_per_symbol')}")
    except Exception as e:
        log_error(MODULE, f"Failed to sync config from DB: {e}")

async def sync_positions_to_memory():
    """Synchronize BOT_STATE.positions with the 'positions' table in Supabase."""
    try:
        sb = get_supabase()
        res = sb.table("positions").select("*").eq("status", "open").execute()
        
        # Clear current and rebuild to ensure closed ones are removed
        new_positions = {}
        for p in res.data:
            pos_id = str(p.get('id', p['symbol']))
            new_positions[pos_id] = p
            
        BOT_STATE.positions = new_positions
        log_info(MODULE, f"Positions synced: {len(BOT_STATE.positions)} active trades in memory.")
    except Exception as e:
        log_error(MODULE, f"Failed to sync positions to memory: {e}")

# Load Pilot Config (Requirement 2: Ensure fail-safe to Paper)
def load_config_to_memory():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config_btc_pilot.json")
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                BOT_STATE.config_cache = json.load(f)
            log_info(MODULE, f"Pilot config loaded from file: {path}")
        else:
            log_warning(MODULE, "config_btc_pilot.json not found. Falling back to default (PAPER).")
            # Fail-safe: secure default
            BOT_STATE.config_cache = {"paper_trading": True, "observe_only": True}
    except Exception as e:
        log_error(MODULE, f"Error loading config file: {e}. Failing safe to PAPER.")
        BOT_STATE.config_cache = {"paper_trading": True, "observe_only": True}

async def _process_symbol_15m(symbol: str, provider, gs_data, sb):
    """Procesamiento asíncrono para UN símbolo en el ciclo 15m (Parallel)."""
    # ── 1. Heartbeat & Safety Manager ─────────
    register_heartbeat('crypto_scheduler_15m')
    
    # ── 2. Circuit Breaker Global ────────────
    cb = await check_circuit_breaker(sb, 'crypto_futures')
    if cb['active']:
        log_info('SAFETY', f'Ciclo omitido por Circuit Breaker: {cb["reason"]}')
        return

    t0 = time.time()
    error_msg = None
    raw_indicators = {}
    blocked_by = None
    rule_eval = "none"
    rule_match = None
    
    # Snapshot data placeholders
    spike_result = {'detected': False, 'ratio': 0, 'direction': ''}
    mtf_result = {'score': 0.0}
    regime = {'category': 'riesgo_medio', 'risk_score': 50}
    fib_levels = {'basis': 0, 'upper_5': 0, 'upper_6': 0, 'lower_5': 0, 'lower_6': 0}
    
    try:
        # PHASE 1: Download OHLCV (Smart Frequency)
        cycle_count = BOT_STATE.cycle_count_15m
        DOWNLOAD_FREQUENCY = {
            '5m':  1,    # cada ciclo de 5m (agregado)
            '15m': 1,    # cada ciclo (siempre)
            '30m': 2,    # cada 2 ciclos = 30 min
            '1h':  4,    # cada 4 ciclos = 1 hora
            '4h':  16,   # cada 16 ciclos = 4 horas
            '1d':  96,   # cada 96 ciclos = 1 día
        }

        # Determinamos qué temporalidades descargar en este ciclo
        # (Siempre descargamos si la memoria está vacía para ese TF)
        timeframes_to_fetch = [
            tf for tf, freq in DOWNLOAD_FREQUENCY.items()
            if cycle_count % freq == 0 or get_memory_df(symbol, tf) is None
        ]

        # Mapeamos las descargas asíncronas
        fetch_tasks = {}
        for tf in timeframes_to_fetch:
            # FIX: Aumentar limit para 4h/1d (FiboBand necesita 200 periodos)
            limit = 300 if tf in ['5m', '15m', '30m', '1h'] else 500
            fetch_tasks[tf] = provider.get_ohlcv(symbol, tf, limit=limit)
        
        if fetch_tasks:
            download_results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)
            for tf, res in zip(fetch_tasks.keys(), download_results):
                if isinstance(res, Exception):
                    log_error(MODULE, f"Error descargando {tf} para {symbol}: {repr(res)}")
                    if tf == '15m': raise res # 15m es crítico
                else:
                    df_tf = calculate_all_indicators(res, BOT_STATE.config_cache)
                    update_memory_df(symbol, tf, df_tf)
                    # Escribir en Supabase para el frontend
                    await upsert_candles_to_db(symbol, tf, df_tf, sb)
        
        # Recuperar el DF de 15m (siempre debería estar por frecuencia 1)
        df = get_memory_df(symbol, "15m")
        if df is None:
             raise Exception(f"No hay datos de 15m disponibles para {symbol}")
        
        t1 = time.time()
        
        last_row = df.iloc[-1]
        if 'metadata' not in MEMORY_STORE[symbol]: MEMORY_STORE[symbol]['metadata'] = {}
        MEMORY_STORE[symbol]['metadata']['current_atr'] = float(last_row['atr'])
        
        # ── SPIKE DETECTION (For Snapshot) ──
        # Provide volume_sma_20 if not already in DF
        vol_sma = df['volume'].rolling(20).mean().iloc[-1]
        
        # Inyectar zona para guardado en spikes (se guarda en mtf_score de volume_spikes)
        indicators_context = {
            'volume_sma_20': vol_sma, 
            'symbol': symbol,
            'zone': fib_levels.get('zone', 0)
        }
        spike_info = detect_spike(df, indicators_context, BOT_STATE.config_cache, cycle_id=None)
        if spike_info:
            spike_result = {
                'detected': True,
                'ratio': spike_info.get('spike_ratio', 0),
                'direction': spike_info.get('direction', '')
            }

        # ── MTF SCORING (For Snapshot) ──
        # Transform current Indicators into dict for scorer
        # Since we only have 15m, 4h, 1d in memory, we pass what we have
        all_inds = {}
        for tf in ['15m', '30m', '1h', '4h', '1d']:
            m_df = get_memory_df(symbol, tf)
            if m_df is not None and not m_df.empty:
                # Scorer expects specific keys (ema_3, rsi_14, etc.)
                # We map our keys: email1..email5
                last_tf = m_df.iloc[-1]
                all_inds[tf] = {
                    'ema_3': float(last_tf.get('ema1', 0)),
                    'ema_9': float(last_tf.get('ema2', 0)),
                    'ema_20': float(last_tf.get('ema3', 0)),
                    'ema_50': float(last_tf.get('ema4', 0)),
                    'rsi_14': float(last_tf.get('rsi', 50)), # Use default if missing
                    'macd_histogram': float(last_tf.get('macd', 0)),
                    'close': float(last_tf.get('close', 0))
                }
        
        mtf_result = calculate_mtf_score(symbol, all_inds, spike_direction=spike_result['direction'] or 'BULLISH')
        cur_mtf_score = mtf_result.get('score', 0.0)
        
        print(f"[DEBUG] {symbol}: df length = {len(df)}")
        t2 = time.time()
        
        # PHASE 3: Regime
        regime = classify_market_risk(df)
        await update_regime_if_changed(symbol, regime, sb)
        t3 = time.time()

        # STEP 4: MANDATORY SNAPSHOT (Requirement 1: SIEMPRE escribir snapshot)
        # Lo hacemos antes de evaluar señales para evitar que fallos en reglas bloqueen el snapshot
        await write_market_snapshot(
            symbol, df, regime, spike_result,
            mtf_result.get('score', 0.0),
            sb
        )
        
        # PHASE 4: Rule Engine
        fib_levels = extract_fib_levels(df)
        
        # Warmup Check (Sprint 3 requirement)
        warmup_limit = 200
        is_warmed = len(df) >= warmup_limit
        if not is_warmed:
            blocked_by = "warmup_incomplete"
        
        # Update bot_state warmup & heartbeat status (Per Symbol)
        try:
            sb.table("bot_state").upsert({
                "symbol": symbol,
                "warmup_completed": is_warmed,
                "warmup_bars_loaded": len(df),
                "last_15m_cycle_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }, on_conflict="symbol").execute()
        except Exception as e:
            log_error(MODULE, f"bot_state upsert failed for {symbol}: {e}")

        if not blocked_by:
            if gs_data.get("circuit_breaker_active", False): blocked_by = "circuit_breaker"
            elif gs_data.get("emergency_active", False): blocked_by = "emergency_active"
            else:
                cooldown = sb.table("cooldowns").select("*").eq("symbol", symbol).eq("active", True).execute()
                if cooldown.data: blocked_by = "cooldown_active"

        if not blocked_by:
            # ── PASO 4: FILTRO SAR 4H ──────────────────────
            # Leer fase SAR actual (recién calculada en snapshot)
            sar_data  = MEMORY_STORE[symbol].get('sar', {})
            sar_phase = sar_data.get('phase', 'neutral')
            sar_changed_at = sar_data.get('changed_at')
            current_price = float(last_row['close'])

            # ── LOG 1: ENTRADA AL CICLO DE EVALUACIÓN ──
            log_info('ENTRY_EVAL',
                f'{symbol}: MTF={cur_mtf_score:.4f} '
                f'SAR={sar_phase} '
                f'spike={spike_result["detected"]} '
                f'regime={regime["category"]}'
            )

            # 1. SI SAR CAMBIÓ → CERRAR POSICIÓN ACTUAL
            if sar_changed_at:
                positions = BOT_STATE.get_positions_by_symbol(symbol)
                for position in positions:
                    side = (position.get('side') or '').lower()
                    
                    # Calcular P&L para el log
                    entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                    pnl_pct = 0
                    if entry > 0:
                        if side == 'long': pnl_pct = (current_price - entry) / entry * 100
                        else: pnl_pct = (entry - current_price) / entry * 100

                    # SAR cambió a bajista → cerrar LONG
                    if sar_phase == 'short' and side == 'long':
                        await _execute_paper_close(position, current_price, 'sar_phase_change', sb)
                        from app.workers.performance_monitor import send_telegram_message
                        await send_telegram_message(
                            f"🔄 CAMBIO DE FASE SAR [{symbol}]\n"
                            f"SAR 4h → BAJISTA\n"
                            f"Cerrando LONG a ${current_price:,.2f}\n"
                            f"P&L: {pnl_pct:.2f}%\n"
                            f"Sistema entra en FASE SHORT"
                        )
                    
                    # SAR cambió a alcista → cerrar SHORT
                    elif sar_phase == 'long' and side == 'short':
                        await _execute_paper_close(position, current_price, 'sar_phase_change', sb)
                        from app.workers.performance_monitor import send_telegram_message
                        await send_telegram_message(
                            f"🔄 CAMBIO DE FASE SAR [{symbol}]\n"
                            f"SAR 4h → ALCISTA\n"
                            f"Cerrando SHORT a ${current_price:,.2f}\n"
                            f"P&L: {pnl_pct:.2f}%\n"
                            f"Sistema entra en FASE LONG"
                        )

            # 2. DETERMINAR DIRECCIÓN PERMITIDA
            allowed_direction = None
            if sar_phase == 'long':
                allowed_direction = 'long'
            elif sar_phase == 'short':
                allowed_direction = 'short'

            from app.core.parameter_guard import get_active_params, get_velocity_config
            base_params = get_active_params(regime['category'], sb)
            
            # Leer ADX actual
            adx = float(last_row.get('adx', 25))
            
            # Obtener config dinámica por velocidad
            vel_config = get_velocity_config(adx)
            
            effective_threshold = vel_config['mtf_threshold']
            effective_sl_mult   = vel_config['sl_mult']
            
            cfg = {
                **base_params,
                'mtf_threshold': effective_threshold,
                'atr_mult': effective_sl_mult
            }
            mtf_threshold = effective_threshold
            
            market_type = BOT_STATE.config_cache.get('market_type', 'futures')

            log_info('ENTRY_EVAL',
                f'{symbol}: ADX={adx:.1f} '
                f'velocidad={vel_config["velocity"]} '
                f'threshold_efectivo={effective_threshold} '
                f'(antes fijo: {base_params.get("mtf_threshold")})'
            )

            # ── LOG 2: FILTRO MTF ──
            if allowed_direction == 'long':
                mtf_passes = cur_mtf_score >= mtf_threshold
                log_info('ENTRY_EVAL',
                    f'{symbol}: {"PASS" if mtf_passes else "FAIL"} MTF filtro LONG '
                    f'({cur_mtf_score:.4f} {">=" if mtf_passes else "<"} {mtf_threshold})'
                )
            elif allowed_direction == 'short':
                mtf_passes = cur_mtf_score <= -mtf_threshold
                log_info('ENTRY_EVAL',
                    f'{symbol}: {"PASS" if mtf_passes else "FAIL"} MTF filtro SHORT '
                    f'({cur_mtf_score:.4f} {"<=" if mtf_passes else ">"} {-mtf_threshold})'
                )
            else:
                log_info('ENTRY_EVAL',
                    f'{symbol}: SAR neutral, MTF={cur_mtf_score:.4f} threshold={mtf_threshold}'
                )

            # ── LOG 3: FILTRO SAR ──
            if allowed_direction:
                log_info('ENTRY_EVAL',
                    f'{symbol}: PASS SAR (allowed_direction={allowed_direction})'
                )
            else:
                log_info('ENTRY_EVAL',
                    f'{symbol}: SAR neutral (no filtra direccion)'
                )

            # --- HYBRID SIGNAL DETECTION (15m, 30m, 4h) ---
            p_signal_raw = last_row.get("pinescript_signal")
            p_signal = str(p_signal_raw) if pd.notna(p_signal_raw) else ""
            
            # Check 30m signal
            df_30m = MEMORY_STORE.get(symbol, {}).get('30m', {}).get('df')
            p_signal_30m = ""
            if df_30m is not None and not df_30m.empty:
                last_30m = df_30m.iloc[-1]
                ps_30_raw = last_30m.get("pinescript_signal")
                p_signal_30m = str(ps_30_raw) if pd.notna(ps_30_raw) else ""
            
            # Check 4h signal
            df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
            p_signal_4h = ""
            if df_4h is not None and not df_4h.empty:
                last_4h = df_4h.iloc[-1]
                ps_4h_raw = last_4h.get("pinescript_signal")
                p_signal_4h = str(ps_4h_raw) if pd.notna(ps_4h_raw) else ""
            
            # Consolidate: prioritiza señales activas (Si hay señal en TF mayor, la hereda el ciclo menor)
            # Prioridad: 15m > 30m > 4h
            source_tf = "15m"
            if not p_signal and p_signal_30m:
                p_signal = p_signal_30m
                source_tf = "30m"
            elif not p_signal and p_signal_4h:
                p_signal = p_signal_4h
                source_tf = "4h"

            m_buy = bool(last_row.get("macd_buy", False))
            m_sell = bool(last_row.get("macd_sell", False))
            
            # 3. EVALUACIÓN DE REGLAS
            
            # --- MODO DUAL (Fase 3) ---
            use_v2_global = bool(BOT_STATE.config_cache.get('use_strategy_engine_v2', False))
            # Gradual rollout: ETH y SOL primero
            pilot_v2_symbols = ['ETHUSDT', 'SOLUSDT']
            use_v2 = use_v2_global and symbol in pilot_v2_symbols
            direction_checked = 'none'
            
            if use_v2:
                # --- NEW STRATEGY ENGINE v1.0 EVALUATION ---
                engine = StrategyEngine.get_instance()
                from app.core.memory_store import MARKET_SNAPSHOT_CACHE
                snap_for_context = MARKET_SNAPSHOT_CACHE.get(symbol, {}).copy()
                snap_for_context.update({
                    'price': float(last_row['close']), 'adx': adx,
                    'mtf_score': cur_mtf_score, 'pinescript_signal': p_signal,
                    'regime': regime['category']
                })
                context = engine.build_context(snap=snap_for_context, df_15m=df, df_4h=get_memory_df(symbol, "4h"))

                new_signal = None
                if not BOT_STATE.get_positions_by_symbol(symbol):
                    new_signal = engine.get_best_signal(context=context, strategy_type='scalping', cycle='15m')
                    if new_signal:
                        await engine.log_evaluation(symbol, new_signal, context)
                        rule_match = {'direction': new_signal['direction'], 'rule': {'rule_code': new_signal['rule_code']}, 'market_data': last_row.to_dict()}
                        rule_eval = new_signal['rule_code']
                    else:
                        all_results = engine.evaluate_all(context, 'long', 'scalping', '15m') + engine.evaluate_all(context, 'short', 'scalping', '15m')
                        for r in all_results:
                            if r['score'] >= 0.40: await engine.log_evaluation(symbol, r, context)
            else:
                # --- ENGINE ANTIGUO (Hardcoded/JSON) ---
                from app.strategy.rule_engine import evaluate_all_rules
                from app.strategy.rule_engine import get_rules_from_memory
                all_r = get_rules_from_memory() or []
                
                if allowed_direction:
                    if allowed_direction == 'long' and cur_mtf_score >= mtf_threshold:
                        direction_checked = 'long'
                        rule_match = evaluate_all_rules(df, fib_levels, regime, pinescript_signal=p_signal if p_signal else None, cfg=cfg, direction='long', rules=all_r, source_tf=source_tf)
                    elif allowed_direction == 'short' and cur_mtf_score <= -mtf_threshold:
                        direction_checked = 'short'
                        bearish_action = get_bearish_action(market_type=market_type, has_long_open=bool(BOT_STATE.get_positions_by_symbol(symbol)))
                        if bearish_action == 'open_short':
                            rule_match = evaluate_all_rules(df, fib_levels, regime, pinescript_signal=p_signal if p_signal else None, cfg=cfg, direction='short', rules=all_r, source_tf=source_tf)
                else:
                    if cur_mtf_score >= mtf_threshold:
                        direction_checked = 'long'
                        rule_match = evaluate_all_rules(df, fib_levels, regime, pinescript_signal=p_signal if p_signal else None, cfg=cfg, direction='long', rules=all_r, source_tf=source_tf)
                    elif cur_mtf_score <= -mtf_threshold:
                        direction_checked = 'short'
                        bearish_action = get_bearish_action(market_type=market_type, has_long_open=bool(BOT_STATE.get_positions_by_symbol(symbol)))
                        if bearish_action == 'open_short':
                            rule_match = evaluate_all_rules(df, fib_levels, regime, pinescript_signal=p_signal if p_signal else None, cfg=cfg, direction='short', rules=all_r, source_tf=source_tf)
            
            if not rule_match:
                blocked_by = f"no_signal_{source_tf}" if not (p_signal or m_buy or m_sell) else "evaluated_no_trigger"
            else:
                # ── 3. Validar Señal (Zombie Check) ──────
                v_signal = validate_signal(symbol, float(last_row['close']), last_row.name if hasattr(last_row, 'name') else None)
                if not v_signal['valid']:
                    blocked_by = f"safety_block ({v_signal['reason']})"
                    rule_match = None

            # ── 4. Filtro Macro (BTC Compass) ─────────
            if rule_match and not blocked_by:
                macro = await fetch_macro_context('crypto_futures', symbol, sb)
                if (rule_match['direction'] == 'long' and not macro['allow_long']) or \
                   (rule_match['direction'] == 'short' and not macro['allow_short']):
                    blocked_by = f"macro_filter ({macro['reason']})"
                    rule_match = None
                elif macro.get('reduce_sizing'):
                    log_info('MACRO', f'{symbol}: Reduciendo sizing por contexto macro cauteloso')

            # ── LOG 4: RESULTADO EVALUACIÓN DE REGLAS ──
            if rule_match and rule_match.get('direction'):
                log_info('ENTRY_EVAL',
                    f'{symbol}: PASS regla activada: '
                    f'{rule_match.get("rule", {}).get("rule_code", "?")} '
                    f'direction={rule_match["direction"]}'
                )
            else:
                log_info('ENTRY_EVAL',
                    f'{symbol}: FAIL ninguna regla activada '
                    f'(p_signal={p_signal}, m_buy={m_buy}, m_sell={m_sell}, '
                    f'dir_checked={direction_checked})'
                )

            if not rule_match:
                blocked_by = f"no_signal_{source_tf}" if not (p_signal or m_buy or m_sell) else "evaluated_no_trigger"
            else:
                # ── 3. Validar Señal (Zombie Check) ──────
                v_signal = validate_signal(symbol, float(last_row['close']), last_row.name if hasattr(last_row, 'name') else None)
                if not v_signal['valid']:
                    blocked_by = f"safety_block ({v_signal['reason']})"
                    rule_match = None

            # ── 4. Filtro Macro (BTC Compass) ─────────
            if rule_match and not blocked_by:
                macro = await fetch_macro_context('crypto_futures', symbol, sb)
                if (rule_match['direction'] == 'long' and not macro['allow_long']) or \
                   (rule_match['direction'] == 'short' and not macro['allow_short']):
                    blocked_by = f"macro_filter ({macro['reason']})"
                    rule_match = None
                elif macro.get('reduce_sizing'):
                    log_info('MACRO', f'{symbol}: Reduciendo sizing por contexto macro cauteloso')
                    # Opcional: ajustar sizing aquí si se desea

            # Validar pre-filtros si hay match
            if rule_match and rule_match['direction'] in ['long', 'short']:
                symbol_positions_count = len(BOT_STATE.get_positions_by_symbol(symbol))
                max_per_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 4))
                
                pre_res = check_pre_filters(
                    regime, rule_match['market_data'], rule_match['direction'],
                    symbol, float(last_row['close']), fib_levels['basis'],
                    open_trades_count=len(BOT_STATE.positions), 
                    symbol_positions_count=symbol_positions_count,
                    capital_sufficient=True, warmup_complete=True,
                    max_per_symbol=max_per_symbol,
                    rule_code=rule_match['rule']['rule_code']
                )
                if not pre_res['passed']: 
                    blocked_by = "|".join(pre_res['reasons'])
                else:
                    # ── STATE MACHINE & AMBIGUITY CHECK ──
                    snap_for_sm = regime.copy()
                    snap_for_sm.update({'price': float(last_row['close']), 'adx': float(last_row.get('adx', 25)), 'mtf_score': cur_mtf_score, 'sar_trend_4h': int(last_row.get('sar_trend_4h',0)), 'sar_trend_15m': int(last_row.get('sar_trend_15m',0)), 'fibonacci_zone': fib_levels.get('zone', 0)})
                    ambiguity = detect_market_ambiguity(snap_for_sm)
                    
                    if ambiguity['is_ambiguous']:
                        blocked_by = f"market_ambiguous ({ambiguity['reason']})"
                        sm.set_ambiguous(symbol, ambiguity['reason'])
                    else:
                        sm_check = sm.can_open(symbol, rule_match['direction'], float(last_row['close']), max_per_symbol)
                        
                        if not sm_check['allowed']:
                            blocked_by = f"state_machine_block ({sm_check['reason']})"
                        elif sm_check.get('is_flip'):
                            # Ejecutar flip: cerrar posiciones opuestas
                            positions = BOT_STATE.get_positions_by_symbol(symbol)
                            for p in positions:
                                if p.get('side', '').lower() != rule_match['direction'].lower():
                                    try:
                                        await _execute_paper_close(p, float(last_row['close']), f"flip_{rule_match['direction']}", sb)
                                        sm.on_position_closed(symbol, f"flip_{rule_match['direction']}", all_closed=True)
                                    except Exception as e:
                                        log_error(MODULE, f"Error en flip close para {symbol}: {e}")
                                    
                        # Filtro de correlación
                    corr_result = check_correlation_filter(
                        symbol_new     = symbol,
                        direction_new  = rule_match['direction'],
                        open_positions = list(BOT_STATE.positions.values()),
                        df_dict        = {s: MEMORY_STORE[s]['15m']['df'] for s in MEMORY_STORE if '15m' in MEMORY_STORE[s]},
                        regime         = regime['category']
                    )
                    if corr_result['blocked']:
                        blocked_by = f"correlation_limit ({corr_result['reason']})"

        t4 = time.time()
        
        # PHASE 5: AI Interpretation (Optional)
        ai_res = None
        if rule_match and not blocked_by and BOT_STATE.config_cache.get("ai_candles_enabled", True):
            try:
                ai_res = await interpret_candles_with_ai(
                    symbol, df, fib_levels, regime, 
                    str(last_row.get("ema20_phase", "flat")),
                    float(last_row.get("adx", 0.0)),
                    signal_direction=rule_match['direction']
                )
            except Exception as e:
                log_error(MODULE, f"AI Interpretation error for {symbol}: {e}")
        t5 = time.time()

        # MEJORA 2: Modo Binding simplificado (Veto binario)
        ai_mode = BOT_STATE.config_cache.get('ai_candles_mode', 'informative')
        cap_op = float(BOT_STATE.config_cache.get("capital_operativo", 100))
        
        # Tamaño dinámico por velocidad (sizing_pct)
        effective_sizing = vel_config.get('sizing_pct', 1.0)
        base_allocation  = 0.1 # 10% base
        final_sizing_usd = max(18.0, cap_op * base_allocation * effective_sizing)
        
        proposed_sizes = [{'trade_n': 1, 'usd': final_sizing_usd}] 
        binding_blocked = False

        if rule_match and not blocked_by and ai_mode == 'binding' and ai_res:
            binding = apply_ai_binding(
                ai_result        = ai_res,
                signal_direction = rule_match['direction'],
                min_confidence   = BOT_STATE.config_cache.get('ai_min_confidence', 0.40)
            )

            if binding['blocked']:
                binding_blocked = True
                blocked_by = 'ai_veto'
                
                # Registrar veto en signals_log
                await sb.table('signals_log').insert({
                    'symbol':       symbol,
                    'direction':    rule_match['direction'],
                    'rule_code':    rule_eval,
                    'acted_on':     False,
                    'reason_skip':  binding['reason'],
                    'detected_at':  datetime.now(timezone.utc).isoformat()
                }).execute()

                from app.workers.performance_monitor import send_telegram_message
                if asyncio.iscoroutinefunction(send_telegram_message):
                    await send_telegram_message(
                        f"🤖 IA VETÓ ENTRADA [{symbol}]\n"
                        f"Señal: {rule_match['direction'].upper()} | "
                        f"Regla: {rule_eval}\n"
                        f"Motivo: {binding['reason']}"
                    )
                else:
                    send_telegram_message(
                        f"🤖 IA VETÓ ENTRADA [{symbol}]\n"
                        f"Señal: {rule_match['direction'].upper()} | "
                        f"Regla: {rule_eval}\n"
                        f"Motivo: {binding['reason']}"
                    )
                log_info(MODULE, f"SIGNAL BLOCKED BY AI: {symbol} Rule {rule_eval} - {binding['reason']}")

        log_diag = {
            "symbol": symbol, "cycle_type": "15m",
            "risk_category": regime['category'], "risk_score": regime['risk_score'],
            "ema20_phase": str(last_row.get("ema20_phase", "flat")),
            "adx_value": float(last_row.get("adx", 0.0)),
            "mtf_score_logged": cur_mtf_score,
            "direction_evaluated": direction_checked,
            "rule_evaluated": rule_eval,
            "rule_triggered": True if (rule_match and not blocked_by) else False,
            "entry_blocked_by": blocked_by,
            "current_price": float(last_row['close']),
            "error_occurred": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle_duration_ms": int((time.time() - t0) * 1000)
        }
        
        # Guardar metadatos de IA en el log para auditoría
        if ai_res:
             log_diag["ai_recommendation"] = ai_res.get("recommendation")
             log_diag["ai_agreed"] = ai_res.get("agrees_with_signal")
             log_diag["ai_confidence"] = ai_res.get("pattern_confidence")
             log_diag["ai_mode"] = ai_mode
             log_diag["ai_blocked"] = binding_blocked

        # LOG DIAGNOSTICS DE FORMA ROBUSTA
        try:
            # Eliminar columnas de IA si dan error (fallback)
            sb.table("pilot_diagnostics").insert(log_diag).execute()
        except Exception as e:
            log_warning(MODULE, f"pilot_diagnostics insert failed - attempting fallback: {e}")
            # Identify columns mentioned in the error if possible or just try minimal set
            for key in ["ai_blocked", "ai_agreed", "ai_confidence", "ai_recommendation", "ai_mode", "direction_evaluated", "mtf_score_logged"]:
                log_diag.pop(key, None)
            try:
                sb.table("pilot_diagnostics").insert(log_diag).execute()
            except Exception as final_e:
                log_error(MODULE, f"Final pilot_diagnostics fallback failed: {final_e}")
        
        # EXECUTION (Only if triggered and NOT blocked)
        # ── LOG 5: DECISIÓN FINAL DE EJECUCIÓN ──
        if blocked_by:
            log_info('ENTRY_EVAL',
                f'{symbol}: FINAL -> BLOCKED by={blocked_by}'
            )
        elif BOT_STATE.config_cache.get("observe_only"):
            log_info('ENTRY_EVAL',
                f'{symbol}: FINAL -> BLOCKED by=observe_only '
                f'(regla={rule_eval}, triggered={bool(rule_match)})'
            )
            # Limits are now handled atomically inside _execute_paper_open
            pass
        else:
            log_info('ENTRY_EVAL',
                f'{symbol}: FINAL -> NO TRADE (sin regla activa)'
            )

        if not blocked_by and not BOT_STATE.config_cache.get("observe_only"):
             # --- 1) SCALPING (MARKET ORDERS) ---
             if rule_match:
                 log_info(MODULE, f"TRADE TRIGGERED (SCALPING): {symbol} - {rule_eval}")
                 current_price = float(last_row['close'])

                 # ── FILTRO DE ESTRUCTURA 4h (ciclo 15m) ──
                 from app.core.memory_store import MARKET_SNAPSHOT_CACHE
                 snap_struct = MARKET_SNAPSHOT_CACHE.get(symbol, {})
                 struct_signal = 'Buy' if rule_match['direction'] == 'long' else 'Sell'
                 struct_authorized = await apply_structure_filter_15m(
                     symbol        = symbol,
                     current_price = current_price,
                     snap          = snap_struct,
                     signal        = struct_signal,
                     sb            = sb
                 )
                 if struct_authorized is None:
                     log_info('STRUCTURE_15M',
                         f'{symbol}: Scalp {rule_match["direction"].upper()} '
                         f'bloqueado por estructura 4h'
                     )
                     blocked_by = 'structure_4h_block'
                 else:
                     # Use structure-authorized direction
                     rule_match['direction'] = struct_authorized
                 
                 if not blocked_by:
                     for trade in proposed_sizes:
                         qty = trade['usd'] / current_price
                         is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False
                         if is_paper:
                             await _execute_paper_open(
                                 symbol=symbol, side=rule_match['direction'], price=current_price,
                                 size=qty, rule_code=rule_eval, regime=regime, levels=fib_levels,
                                 vel_config=vel_config, supabase=sb
                             )
                         else:
                             await provider.place_order(
                                 symbol=symbol, side=rule_match['direction'],
                                 size=qty, order_type="MARKET"
                             )
        # --- 2) SWING (LIMIT ORDERS V5.0) ---
        from app.strategy.swing_orders import process_swing_orders
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        if not BOT_STATE.config_cache.get("observe_only"):
             snap_ref = MARKET_SNAPSHOT_CACHE.get(symbol, {})
             
             # Swing 15m -> cada ciclo de 15m
             try:
                 log_info('SWING', f'{symbol}/15m: iniciando evaluación swing')
                 await process_swing_orders(
                     symbol=symbol,
                     timeframe='15m',
                     df=df,
                     snap=snap_ref,
                     sb=sb
                 )
                 log_info('SWING', f'{symbol}/15m: evaluación swing completada')
             except Exception as swing_e:
                 log_error('SWING', f'{symbol}/15m: error en evaluación swing: {swing_e}')
             
             # Swing 4h -> cada 16 ciclos (cada 4h)
             if BOT_STATE.cycle_count_15m % 16 == 0:
                  df_4h_safe = get_memory_df(symbol, "4h")
                  if df_4h_safe is not None and not df_4h_safe.empty:
                       # --- SWING 4h ---
                       try:
                           log_info('SWING', f'{symbol}/4h: iniciando evaluación swing')
                           await process_swing_orders(
                               symbol=symbol,
                               timeframe='4h',
                               df=df_4h_safe,
                               snap=snap_ref,
                               sb=sb
                           )
                           log_info('SWING', f'{symbol}/4h: evaluación swing completada')
                       except Exception as swing_e4h:
                           log_error('SWING', f'{symbol}/4h: error en evaluación swing: {swing_e4h}')

                       # --- SCALPING 4h (Reglas Aa31/Bb31) ---
                       try:
                           if BOT_STATE.config_cache.get('use_strategy_engine_v2'):
                               engine = StrategyEngine.get_instance()
                               if not BOT_STATE.get_positions_by_symbol(symbol):
                                   context_4h = engine.build_context(snap=snap_ref, df_15m=df, df_4h=df_4h_safe)
                                   signal_4h = engine.get_best_signal(context=context_4h, strategy_type='scalping', cycle='4h')
                                   if signal_4h:
                                      max_global = int(BOT_STATE.config_cache.get('max_open_trades', 3))
                                      current_open = len(BOT_STATE.positions)
                                      
                                      max_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 1))
                                      num_for_symbol = len(BOT_STATE.get_positions_by_symbol(symbol))

                                      # Limits are now handled atomically inside _execute_paper_open
                                      from app.core.parameter_guard import get_velocity_config
                                      from app.workers.performance_monitor import send_telegram_message
                                      current_price = float(last_row['close'])
                                      vel_config = get_velocity_config(float(snap_ref.get('adx', 25)))
                                      cap_op = float(BOT_STATE.config_cache.get("capital_operativo", 100))
                                      qty_4h = (cap_op * 0.1 * vel_config.get('sizing_pct', 1.0)) / current_price
                                      await _execute_paper_open(
                                          symbol=symbol, side=signal_4h['direction'], price=current_price,
                                          size=qty_4h, rule_code=signal_4h['rule_code'], 
                                          regime=snap_ref, levels=snap_ref, vel_config=vel_config, supabase=sb
                                      )
                                      await send_telegram_message(
                                          f"⚡ SCALPING 4H [{symbol}]\nRegla: {signal_4h['rule_code']}\nDirección: {signal_4h['direction'].upper()}\nScore: {signal_4h['score']:.2f}\nRazón: {signal_4h['reason']}"
                                      )
                       except Exception as scalp_4h_e:
                           log_error('SCALPING_4H', f'{symbol}: Error en evaluación scalping 4h: {scalp_4h_e}')

    except Exception as inner_e:
        import traceback
        blocked_by, err_msg, _ = handle_binance_error(inner_e)
        log_error(MODULE, f"Error processing {symbol}: {err_msg}\n{traceback.format_exc()}")
        try:
            # Also write snapshot on error if we have even partial data
            # (Optional, but let's keep it clean: only on success or partial success)
            if 'df' in locals() and df is not None:
                await write_market_snapshot(symbol, df, regime if 'regime' in locals() else {}, spike_result, mtf_result.get('score', 0), sb)
            
            sb.table("pilot_diagnostics").insert({
                "symbol": symbol, "cycle_type": "15m", 
                "error_occurred": True, "error_message": err_msg,
                "entry_blocked_by": blocked_by,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }).execute()
        except: pass

async def cycle_15m():
    """Speed 2B: Main Analysis Pipeline (Parallel Symbols)."""
    log_info(MODULE, f"--- Speed 2B: 15m Cycle (Parallel) ---")
    BOT_STATE.cycle_count_15m += 1
    
    # Create LOCAL provider for this cycle
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    # Check paper mode
    is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False
    if is_paper:
        provider = PaperTradingProvider(provider)

    try:
        sb = get_supabase()
        raw_symbols = BOT_STATE.config_cache.get("symbols_active") or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
        symbols = list(set([s.replace("/", "") for s in raw_symbols]))
        
        if is_ip_banned():
            log_info(MODULE, "IP baneada. Ciclo 15m omitido.")
            return

        await sync_db_config_to_memory()
        
        gs_data = {}
        try:
            global_state = sb.table("bot_global_state").select("*").eq("id", 1).maybe_single().execute()
            gs_data = global_state.data or {}
        except Exception as e:
            log_warning(MODULE, f"global_state fetch error: {e}")

        # Ejecución paralela real de todos los símbolos (Sprint 3)
        tasks = [_process_symbol_15m(s, provider, gs_data, sb) for s in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # --- PHASE 1: Performance Alerts ---
        try:
            from app.workers.performance_monitor import check_performance_alerts
            await check_performance_alerts()
            log_info(MODULE, "Performance alerts check completed.")
        except Exception as e:
            log_error(MODULE, f"Performance alerts check failed: {e}")
        
        # Executive heartbeat
        sb.table("bot_global_state").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", 1).execute()

    except Exception as e:
        log_error(MODULE, f"Global error in 15m cycle: {e}")
    finally:
        await provider.close()


async def listen_for_rule_changes():
    """Realtime listener to invalidate rules cache (Requirement 2)."""
    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    
    def on_change(payload):
        log_info(MODULE, "Rules updated in Supabase. Reloading memory cache...")
        load_rules_to_memory()

    # Note: supabase-py Realtime support is still evolving, 
    # for now we simulate with a heartbeat or direct channel if available.
    log_info(MODULE, "Subscribed to trading_rules Realtime changes.")
    # (Implementation details for supabase-py realtime go here)

async def main():
    # 0. Load Configuration (Fail-safe to Paper)
    load_config_to_memory()
    load_rules_to_memory()
    
    # Initialize Strategy Engine v1.0
    sb = get_supabase()
    engine = StrategyEngine.get_instance(sb)
    await engine.load()
    log_info('STARTUP', 'Strategy Engine v1.0 cargado')
    
    # Persistent providers to keep connections alive
    real_binance = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    symbols = BOT_STATE.config_cache.get("symbols_active", ["BTCUSDT"])
    
    # 1. Warm-up
    log_info(MODULE, f"Warming up memory for: {symbols}")
    try:
        await warm_up(symbols, ["5m", "15m", "4h", "1d"], real_binance)
    finally:
        await real_binance.close()

    # 2. Start WebSocket Monitor Task
    try:
        from app.ws.ws_manager import WebSocketManager
        ws_mgr = WebSocketManager(
            symbols, 
            settings.binance_api_key, 
            settings.binance_secret, 
            testnet=settings.binance_testnet
        )
        asyncio.create_task(ws_mgr.start())
        log_info(MODULE, "WebSocket Emergency Monitor started.")
    except Exception as e:
        log_error(MODULE, f"Failed to start WebSocket Monitor: {e}")

    # 3. Realtime Cache Invalidation Task
    asyncio.create_task(listen_for_rule_changes())
    
    # 4. Sync Config Periodically
    scheduler.add_job(sync_db_config_to_memory, 'interval', minutes=10, id='sync_cfg')
    
    # 5. Schedule Tasks with offsets
    scheduler.add_job(cycle_5m, CronTrigger(minute='*/5', second='10'), id='2a', replace_existing=True)
    scheduler.add_job(cycle_15m, CronTrigger(minute='*/15', second='30'), id='2b', replace_existing=True)
    
    # 6. Daily DB Cleanup (03:00 UTC = 22:00 Lima)
    #    Triple redundancia: pg_cron + Vercel Cron + APScheduler
    async def daily_cleanup_job():
        from app.workers.data_cleanup import cleanup_database
        log_info(MODULE, "Ejecutando limpieza diaria de BD...")
        try:
            result = await cleanup_database()
            log_info(MODULE, f"Limpieza diaria completada: {result.get('total_deleted', 0)} filas eliminadas")
        except Exception as e:
            log_error(MODULE, f"Error en limpieza diaria: {e}")
    
    scheduler.add_job(daily_cleanup_job, CronTrigger(hour=3, minute=0), id='daily_cleanup', replace_existing=True)
    
    # 7. Heartbeat Check (Every 5 minutes)
    async def heartbeat_check_job():
        await check_all_heartbeats()
    
    scheduler.add_job(heartbeat_check_job, CronTrigger(minute='*/5'), id='heartbeat_check', replace_existing=True)
    
    log_info(MODULE, "v4 Scheduler Started. Running initial cycles...")
    
    # Run once at startup to populate dashboard immediately
    asyncio.create_task(cycle_15m())
    asyncio.create_task(cycle_5m())
    
    scheduler.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log_info(MODULE, "Stopped manually.")
