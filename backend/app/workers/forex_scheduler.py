"""
eTrader — Forex Scheduler (IC Markets via cTrader)
====================================================
Scheduler para operaciones Forex replicando la arquitectura
del scheduler de Crypto.

Opera con los mismos ciclos:
    5m  → gestión de posiciones y smart exits
    15m → análisis completo, indicadores y señales
    4h  → swing trade y reglas Aa31/Bb31

Usa el mismo Strategy Engine v1.0 y las mismas reglas
Aa/Bb/Cc/Dd. Solo cambia el proveedor de datos (CTrader
en lugar de Binance).
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logger import log_info, log_error, log_warning, log_debug
from app.core.supabase_client import get_supabase
from app.core.config import settings, STRUCTURE_CONFIG
from app.core.memory_store import (
    BOT_STATE, update_memory_df, get_memory_df, MEMORY_STORE,
    update_current_candle_close, MARKET_SNAPSHOT_CACHE
)

# Analysis & Indicators
from app.analysis.indicators_v2 import calculate_all_indicators
from app.analysis.fibonacci_bb import fibonacci_bollinger, extract_fib_levels, get_next_fibonacci_target
from app.analysis.parabolic_sar import calculate_parabolic_sar, analyze_structure
from app.strategy.volume_spike import detect_spike
from app.strategy.mtf_scorer import calculate_mtf_score
from app.strategy.market_regime import classify_market_risk, update_regime_if_changed

# Strategy Engine
from app.strategy.strategy_engine import StrategyEngine
from app.core.symbol_state import SymbolStateMachine

sm = SymbolStateMachine.get_instance()

# Position management
from app.core.position_sizing import calculate_position_size, can_open_short, calculate_sl_tp
from app.core.position_monitor import (
    _execute_paper_close,
    _execute_paper_partial_close,
    _execute_paper_open,
    check_signal_reversal,
)
from app.strategy.band_exit import evaluate_band_exit

# Alerts
from app.workers.alerts_service import send_telegram_message
from app.workers.performance_monitor import check_performance_alerts
from app.strategy.macro_filter import check_usd_exposure_filter

# Forex config
from app.config.forex_config import (
    FOREX_SYMBOLS, FOREX_TIMEFRAMES, PIP_SIZES,
    LOT_CONFIG, FOREX_RISK_CONFIG, CTRADER_CONFIG
)

# Provider
from app.execution.provider_factory import create_provider
from app.execution.providers.ctrader_provider import CTraderProtobufProvider

MODULE = "forex_scheduler"

# ── State ──────────────────────────────────────────
_forex_provider: Optional[CTraderProtobufProvider] = None
_forex_cycle_count = 0


# ══════════════════════════════════════════════════
#  WARM-UP (Phase 0)
# ══════════════════════════════════════════════════

async def warm_up_forex(symbols: list, timeframes: list, provider: CTraderProtobufProvider):
    """
    Precalentar MEMORY_STORE con datos Forex de IC Markets.
    Descarga velas historicas + calcula todos los indicadores.
    """
    log_info(MODULE, f"Precalentando Forex: {len(symbols)} simbolos x {len(timeframes)} TFs")
    start = datetime.now()

    tasks = []
    for symbol in symbols:
        for tf in timeframes:
            tasks.append(_warm_up_forex_symbol_tf(symbol, tf, provider))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            log_error(MODULE, f"Error en warm-up: {r}")

    elapsed = (datetime.now() - start).total_seconds()
    log_info(MODULE, f"Precalentamiento Forex completado: {elapsed:.1f}s")


async def _warm_up_forex_symbol_tf(symbol: str, tf: str, provider: CTraderProtobufProvider):
    """Descargar y procesar un symbol/tf."""
    try:
        df = await provider.get_ohlcv(symbol, tf, limit=300)
        if df is not None and not df.empty:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, calculate_all_indicators, df, BOT_STATE.config_cache)
            update_memory_df(symbol, tf, df)
            
            # Rehidratar caché en memoria (Evita base de datos pero soluciona el reinicio)
            if tf == '15m':
                last_row = df.iloc[-1]
                MARKET_SNAPSHOT_CACHE.setdefault(symbol, {}).update({
                    'price': float(last_row['close']),
                    'ema_3': float(last_row.get('ema1', 0) if last_row.get('ema1') is not None else 0),
                    'ema_9': float(last_row.get('ema2', 0) if last_row.get('ema2') is not None else 0),
                    'ema_20': float(last_row.get('ema3', 0) if last_row.get('ema3') is not None else 0),
                    'ema_50': float(last_row.get('ema4', 0) if last_row.get('ema4') is not None else 0),
                    'rsi_14': float(last_row.get('rsi1', 0) if last_row.get('rsi1') is not None else 0),
                    'atr': float(last_row.get('atr', 0) if last_row.get('atr') is not None else 0),
                    'adx': float(last_row.get('adx', 0) if last_row.get('adx') is not None else 0),
                    'macd_histogram': float(last_row.get('macd_hist', 0) if last_row.get('macd_hist') is not None else 0),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                
            log_info(MODULE, f"  {symbol}/{tf}: {len(df)} velas cargadas")
        else:
            log_warning(MODULE, f"  {symbol}/{tf}: sin datos")
    except Exception as e:
        log_error(MODULE, f"  Error warm-up {symbol}/{tf}: {e}")


# ══════════════════════════════════════════════════
#  MARKET SNAPSHOT (Forex)
# ══════════════════════════════════════════════════

async def write_forex_snapshot(
    symbol: str,
    df: pd.DataFrame,
    regime: dict,
    spike: dict,
    mtf_score: float,
    sb
):
    """
    Escribe el snapshot de mercado Forex en Supabase.
    Replica la logica de write_market_snapshot del scheduler crypto.
    """
    try:
        if df is None or df.empty:
            return
            
        import math
        def safe_int_nan(val, default=0):
            if val is None: return default
            import pandas as pd
            if pd.isna(val) or (isinstance(val, float) and math.isnan(val)): return default
            try: return int(float(val))
            except: return default

        last = df.iloc[-1]

        # Extraer niveles Fibonacci
        try:
            fib_levels = extract_fib_levels(df)
        except (KeyError, ValueError, AttributeError):
            df_15m_mem = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
            if df_15m_mem is not None and 'basis' in df_15m_mem.columns:
                fib_levels = extract_fib_levels(df_15m_mem)
            else:
                fib_levels = {
                    'zone': 0, 'basis': 0.0,
                    'upper_1': 0.0, 'upper_2': 0.0, 'upper_3': 0.0,
                    'upper_4': 0.0, 'upper_5': 0.0, 'upper_6': 0.0,
                    'lower_1': 0.0, 'lower_2': 0.0, 'lower_3': 0.0,
                    'lower_4': 0.0, 'lower_5': 0.0, 'lower_6': 0.0,
                }

        # SAR 4H
        sar_value = 0
        sar_trend = 0
        sar_phase = 'neutral'
        prev_trend = 0

        # Leer fase anterior
        try:
            prev_res = sb.table('market_snapshot').select('sar_trend_4h').eq('symbol', symbol).maybe_single().execute()
            if prev_res.data:
                prev_trend = int(prev_res.data.get('sar_trend_4h', 0))
        except:
            pass

        df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
        if df_4h is not None and not df_4h.empty:
            df_4h_sar = calculate_parabolic_sar(df_4h.copy())
            last_4h = df_4h_sar.iloc[-1]
            sar_trend = safe_int_nan(last_4h.get('sar_trend'))
            sar_value = float(last_4h['sar'])

            if sar_trend > 0:
                sar_phase = 'long'
            elif sar_trend < 0:
                sar_phase = 'short'

            MEMORY_STORE[symbol]['sar'] = {
                'phase': sar_phase,
                'value_4h': sar_value,
                'trend_4h': sar_trend,
                'changed_at': None,
            }

        sar_changed = (prev_trend != 0 and sar_trend != 0 and sar_trend != prev_trend)
        changed_at_iso = None
        if sar_changed:
            changed_at_iso = datetime.now(timezone.utc).isoformat()
            MEMORY_STORE[symbol]['sar']['changed_at'] = changed_at_iso
            log_info('SAR_FOREX', f"CAMBIO SAR {symbol}: {prev_trend} -> {sar_trend}")

        # SAR 15m
        sar_15m = None
        sar_trend_15m = 0
        sar_ini_high_15m = False
        sar_ini_low_15m = False
        p_signal_15m = None

        df_15m_mem = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
        last_15m = None
        if df_15m_mem is not None and not df_15m_mem.empty:
            df_15m_sar = calculate_parabolic_sar(df_15m_mem.copy())
            last_15m = df_15m_sar.iloc[-1]
            sar_15m = float(last_15m.get('sar', 0))
            sar_trend_15m = safe_int_nan(last_15m.get('sar_trend', 0))
            sar_ini_high_15m = bool(last_15m.get('sar_ini_high', False))
            sar_ini_low_15m = bool(last_15m.get('sar_ini_low', False))
            p_signal_15m = str(last_15m.get('last_pinescript_signal', '') or '')

        # Estructura 15m
        cfg_struct = STRUCTURE_CONFIG
        if df_15m_mem is not None and not df_15m_mem.empty:
            df_15m_sar_s = calculate_parabolic_sar(df_15m_mem.copy())
            struct_15m = analyze_structure(
                df=df_15m_sar_s,
                sar_col='sar_trend',
                n_confirm=cfg_struct['velas_confirmacion'],
                umbral_low=cfg_struct['umbral_lower_low'],
                umbral_high=cfg_struct['umbral_higher_high'],
            )
        else:
            struct_15m = {
                'structure': 'unknown', 'allow_long': True,
                'allow_short': True, 'reverse_signal': False,
                'reason': 'No 15m data',
            }

        # Estructura 4h
        if df_4h is not None and not df_4h.empty:
            df_4h_sar_s = calculate_parabolic_sar(df_4h.copy())
            struct_4h = analyze_structure(
                df=df_4h_sar_s,
                sar_col='sar_trend',
                n_confirm=cfg_struct['velas_confirmacion'],
                umbral_low=cfg_struct['umbral_lower_low'],
                umbral_high=cfg_struct['umbral_higher_high'],
            )
        else:
            struct_4h = {
                'structure': 'unknown', 'allow_long': True,
                'allow_short': True, 'reverse_signal': False,
                'reason': 'No 4h data',
            }

        import pandas as pd
        def _si(val):
            return 0 if pd.isna(val) else int(float(val))

        upsert_data = {
            'symbol':            symbol,
            'price':             float(last['close']),
            'fibonacci_zone':    _si(fib_levels.get('zone', 0)),
            'basis':             float(fib_levels.get('basis') or last.get('close', 0)),
            'upper_1':           float(fib_levels.get('upper_1', 0)),
            'upper_2':           float(fib_levels.get('upper_2', 0)),
            'upper_3':           float(fib_levels.get('upper_3', 0)),
            'upper_4':           float(fib_levels.get('upper_4', 0)),
            'upper_5':           float(fib_levels.get('upper_5', 0)),
            'upper_6':           float(fib_levels.get('upper_6', 0)),
            'lower_1':           float(fib_levels.get('lower_1', 0)),
            'lower_2':           float(fib_levels.get('lower_2', 0)),
            'lower_3':           float(fib_levels.get('lower_3', 0)),
            'lower_4':           float(fib_levels.get('lower_4', 0)),
            'lower_5':           float(fib_levels.get('lower_5', 0)),
            'lower_6':           float(fib_levels.get('lower_6', 0)),
            'dist_basis_pct':    float(
                abs(float(last['close']) - float(last.get('basis', last['close'])))
                / float(last.get('basis', last['close'])) * 100
                if float(last.get('basis', 0)) > 0 else 0
            ),
            'mtf_score':         round(float(mtf_score), 4),
            'ema20_phase':       str(last.get('ema20_phase', '')),
            'adx':               float(last.get('adx', 0)),
            'atr':               float(last.get('atr', 0)),
            'regime':            regime.get('category', ''),
            'risk_score':        regime.get('risk_score', 0),
            'spike_detected':    spike.get('detected', False),
            'spike_ratio':       spike.get('ratio', 0),
            'spike_direction':   spike.get('direction', ''),
            'sar_4h':            sar_value,
            'sar_trend_4h':      sar_trend,
            'sar_phase':         sar_phase,
            'sar_15m':           sar_15m,
            'sar_trend_15m':     sar_trend_15m,
            'sar_ini_high_15m':  sar_ini_high_15m,
            'sar_ini_low_15m':   sar_ini_low_15m,
            'pinescript_signal': p_signal_15m,
            'pinescript_signal_age': safe_int_nan(last_15m.get('signal_age', 0)) if last_15m is not None else 0,
            # Estructura
            'structure_15m':         struct_15m['structure'],
            'allow_long_15m':        struct_15m['allow_long'],
            'allow_short_15m':       struct_15m['allow_short'],
            'reverse_signal_15m':    struct_15m['reverse_signal'],
            'structure_reason_15m':  struct_15m['reason'],
            'structure_4h':          struct_4h['structure'],
            'allow_long_4h':         struct_4h['allow_long'],
            'allow_short_4h':        struct_4h['allow_short'],
            'reverse_signal_4h':     struct_4h['reverse_signal'],
            'structure_reason_4h':   struct_4h['reason'],
            'bb_expanding':          bool(last.get('bb_expanding', False)),
            'updated_at':            datetime.now(timezone.utc).isoformat(),
        }

        # Extraer indicadores para el caché en memoria (no están en la tabla DB)
        close_p = float(last.get('close', 0))
        e3 = float(last.get('ema1') or last.get('ema3') or last.get('ema_3') or close_p)
        e9 = float(last.get('ema2') or last.get('ema9') or last.get('ema_9') or close_p)
        e20 = float(last.get('ema3') or last.get('ema20') or last.get('ema_20') or close_p)
        upsert_data['ema3'] = e3
        upsert_data['ema9'] = e9
        upsert_data['ema20'] = e20
        upsert_data['ema_3'] = e3
        upsert_data['ema_9'] = e9
        upsert_data['ema_20'] = e20
        upsert_data['ema_50'] = float(last.get('ema4', last.get('ema_50', close_p)))
        upsert_data['rsi_14'] = float(last.get('rsi_14', last.get('rsi', 50)))
        upsert_data['macd_histogram'] = float(last.get('macd_histogram', last.get('macd', 0)))
        
        df_5m = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
        if df_5m is not None and not df_5m.empty:
            last_5m = df_5m.iloc[-1]
            upsert_data['ema3_5m'] = float(last_5m.get('ema1', last_5m.get('ema_3', 0)))
            upsert_data['ema9_5m'] = float(last_5m.get('ema2', last_5m.get('ema_9', 0)))
            upsert_data['ema20_5m'] = float(last_5m.get('ema3', last_5m.get('ema_20', 0)))
            
            # Injecting 5m raw metrics for Cooldown Bypass in Forex
            upsert_data['raw_metrics_5m'] = {
                'rsi': float(last_5m.get('rsi1', last_5m.get('rsi', 50))),
                'low': float(last_5m.get('low', 0)),
                'high': float(last_5m.get('high', 0)),
                'open': float(last_5m.get('open', 0)),
                'close': float(last_5m.get('close', 0)),
                'lower_5': float(last_5m.get('lower_5', 0)),
                'lower_6': float(last_5m.get('lower_6', 0)),
                'upper_5': float(last_5m.get('upper_5', 0)),
                'upper_6': float(last_5m.get('upper_6', 0)),
                'bb_lower': float(last_5m.get('bb_lower', last_5m.get('lower_2', 0))),
                'bb_upper': float(last_5m.get('bb_upper', last_5m.get('upper_2', 0)))
            }

        # Calcular Bollinger Bands estándar (20, 2)
        try:
            rolling_mean = df['close'].rolling(20).mean()
            rolling_std = df['close'].rolling(20).std()
            upsert_data['bb_upper'] = float(rolling_mean.iloc[-1] + 2 * rolling_std.iloc[-1])
            upsert_data['bb_lower'] = float(rolling_mean.iloc[-1] - 2 * rolling_std.iloc[-1])
        except Exception:
            upsert_data['bb_upper'] = 0.0
            upsert_data['bb_lower'] = 0.0

        # Para compatibilidad con algunos scripts que leen 'rsi_14_prev'
        try:
            if len(df) >= 2:
                prev_row = df.iloc[-2]
                upsert_data['rsi_14_prev'] = float(prev_row.get('rsi_14', prev_row.get('rsi', 50)))
        except:
            pass

        # Preparar datos para base de datos (excluyendo campos solo de caché)
        db_data = upsert_data.copy()
        for k in ['ema3', 'ema9', 'ema20', 'ema_3', 'ema_9', 'ema_20', 'ema_50', 'rsi_14', 'rsi_14_prev', 'macd_histogram', 'bb_upper', 'bb_lower', 'ema3_5m', 'ema9_5m', 'ema20_5m', 'raw_metrics_5m']:
            db_data.pop(k, None)

        if sar_changed:
            db_data['sar_phase_changed_at'] = changed_at_iso

        import math
        clean_db_data = {}
        for k, v in db_data.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean_db_data[k] = None
            else:
                clean_db_data[k] = v

        sb.table('market_snapshot').upsert(clean_db_data).execute()
        
        # Actualizar caché en memoria completo (incluyendo indicadores rápidos)
        MARKET_SNAPSHOT_CACHE[symbol] = upsert_data
        log_info('SNAPSHOT_FX', f'Snapshot OK: {symbol} mtf={mtf_score:.4f}')

    except Exception as e:
        log_error('SNAPSHOT_FX', f'FALLO snapshot {symbol}: {e}')


# ══════════════════════════════════════════════════
#  CANDLE UPSERT (Forex)
# ══════════════════════════════════════════════════

async def upsert_forex_candles(symbol: str, timeframe: str, df: pd.DataFrame, sb):
    """Sindronizar velas Forex con market_candles. THROTTLE: cada 60 min."""
    if df is None or df.empty:
        return

    # THROTTLE: Solo upsertear a Supabase cada 60 minutos para reducir egress
    import time as _time
    if not hasattr(upsert_forex_candles, '_last'):
        upsert_forex_candles._last = {}
    _key = f"{symbol}_{timeframe}"
    _now = _time.time()
    if _key in upsert_forex_candles._last and (_now - upsert_forex_candles._last[_key]) < 3600:
        return  # Skip — datos ya están en MEMORY_STORE (RAM)
    upsert_forex_candles._last[_key] = _now

    try:
        rows = []
        sub_df = df.tail(5)

        for idx, r in sub_df.iterrows():
            open_time = idx
            if hasattr(open_time, 'tzinfo') and open_time.tzinfo is None:
                open_time = open_time.tz_localize('UTC')
            if hasattr(open_time, 'isoformat'):
                open_time = open_time.isoformat()
            else:
                open_time = str(open_time)

            rows.append({
                'symbol':    symbol,
                'exchange':  'icmarkets',
                'timeframe': timeframe,
                'open_time': open_time,
                'open':      float(r['open']),
                'high':      float(r['high']),
                'low':       float(r['low']),
                'close':     float(r['close']),
                'volume':    float(r.get('volume') or 0),
                'is_closed': True,
                'basis':     float(r.get('basis', 0) or 0) if pd.notna(r.get('basis')) else None,
                'upper_6':   float(r.get('upper_6', 0) or 0) if pd.notna(r.get('upper_6')) else None,
                'lower_6':   float(r.get('lower_6', 0) or 0) if pd.notna(r.get('lower_6')) else None,
                'sar':       float(r.get('sar', 0) or 0) if pd.notna(r.get('sar')) else None,
                'sar_trend': int(r.get('sar_trend', 0) or 0) if pd.notna(r.get('sar_trend')) else None,
                'pinescript_signal': str(r.get('pinescript_signal', ''))
                    if r.get('pinescript_signal') in ('Buy', 'Sell') else None,
            })

        if rows:
            sb.table('market_candles').upsert(
                rows,
                on_conflict='symbol,exchange,timeframe,open_time'
            ).execute()
            log_info('CANDLES_FX', f"Upsert {len(rows)} velas {symbol}/{timeframe}")

    except Exception as e:
        log_error('CANDLES_FX', f"Error upsert {symbol}/{timeframe}: {e}")


# ══════════════════════════════════════════════════
#  FOREX POSITION OPENING
# ══════════════════════════════════════════════════

# ── TP Dinámico con Fibonacci ─────────────────────
# Mínimo ratio Riesgo:Beneficio aceptable por símbolo
MIN_TP_RR_RATIO = {
    'EURUSD': 1.5,
    'GBPUSD': 1.5,
    'USDJPY': 1.5,
    'XAUUSD': 1.2,
}
# Porcentaje de la distancia a la banda para el TP (95% = no exigir toque exacto)
TP_BAND_PCT = 0.95
# Bandas Fibonacci a evaluar (de más cerca a más lejos)
TP_BANDS_LONG  = ['upper_1', 'upper_2', 'upper_3', 'upper_4', 'upper_5', 'upper_6']
TP_BANDS_SHORT = ['lower_1', 'lower_2', 'lower_3', 'lower_4', 'lower_5', 'lower_6']


def _find_dynamic_tp(symbol, direction, entry_price, sl_price, snap, pip_size, atr):
    """
    Busca la primera banda de Fibonacci cuya distancia al entry
    supere el mínimo de RR ratio respecto al SL.
    Si ninguna banda cumple, usa un TP fijo basado en sl_pips × min_rr.
    """
    min_rr = MIN_TP_RR_RATIO.get(symbol, 1.5)
    sl_distance_pips = abs(entry_price - sl_price) / pip_size
    min_tp_pips = sl_distance_pips * min_rr

    bands = TP_BANDS_LONG if direction == 'long' else TP_BANDS_SHORT

    for band_name in bands:
        band_price = float(snap.get(band_name) or 0)
        if band_price <= 0:
            continue

        # Distancia de la banda al entry (en pips)
        if direction == 'long':
            tp_distance_pips = (band_price - entry_price) / pip_size
        else:
            tp_distance_pips = (entry_price - band_price) / pip_size

        # La banda debe estar del lado correcto (ganancia positiva)
        if tp_distance_pips <= 0:
            continue

        # Usar el 95% de la distancia a la banda
        effective_tp_pips = tp_distance_pips * TP_BAND_PCT

        if effective_tp_pips >= min_tp_pips:
            # Calcular el precio TP al 95% de la banda
            if direction == 'long':
                tp_price = entry_price + (effective_tp_pips * pip_size)
            else:
                tp_price = entry_price - (effective_tp_pips * pip_size)

            rr_actual = effective_tp_pips / sl_distance_pips if sl_distance_pips > 0 else 0
            log_info(MODULE,
                f"TP DINÁMICO [{symbol}]: Banda {band_name} seleccionada. "
                f"SL={sl_distance_pips:.0f} pips, TP={effective_tp_pips:.0f} pips, "
                f"RR=1:{rr_actual:.1f}"
            )
            return tp_price

    # Fallback: si ninguna banda cumple, usar RR mínimo fijo
    fallback_tp_pips = sl_distance_pips * min_rr
    if direction == 'long':
        tp_fallback = entry_price + (fallback_tp_pips * pip_size)
    else:
        tp_fallback = entry_price - (fallback_tp_pips * pip_size)

    log_info(MODULE,
        f"TP DINÁMICO [{symbol}]: Ninguna banda cumple RR mínimo ({min_rr}). "
        f"Usando fallback: {fallback_tp_pips:.0f} pips (SL={sl_distance_pips:.0f} pips)"
    )
    return tp_fallback


def calculate_forex_sl_tp(
    symbol: str,
    direction: str,
    entry_price: float,
    snap: dict = None,
) -> dict:
    """
    Calcula SL/TP en precio usando bandas de Fibonacci.
    TP Dinámico: busca la primera banda que cumpla un RR mínimo.
    """
    pip_size = PIP_SIZES.get(symbol, 0.0001)
    
    if snap:
        u1 = float(snap.get('upper_1') or 0)
        l1 = float(snap.get('lower_1') or 0)
        atr = (u1 - l1) / 3.236 if (u1 > 0 and l1 > 0) else (20 * pip_size)
        
        # 1. Calcular el SL técnico (zona de invalidación) para el TP y RR
        if direction == 'long':
            sl_tech = float(snap.get('lower_6') or (entry_price - 50 * pip_size)) - (0.5 * atr)
        else:
            sl_tech = float(snap.get('upper_6') or (entry_price + 50 * pip_size)) + (0.5 * atr)
        
        # 2. Encontrar TP dinámico usando el SL técnico
        tp = _find_dynamic_tp(symbol, direction, entry_price, sl_tech, snap, pip_size, atr)
        
        # 3. Calcular el Hard Stop físico (sl) más amplio para actuar de emergencia
        if symbol in ('XAUUSD', 'XAU/USD'):
            min_sl_pips = 600
        elif symbol in ('USDJPY', 'USD/JPY'):
            min_sl_pips = 50
        elif symbol in ('GBPUSD', 'GBP/USD'):
            min_sl_pips = 35
        else:
            min_sl_pips = 30
            
        if direction == 'long':
            sl = float(snap.get('lower_6') or (entry_price - 50 * pip_size)) - (2.0 * atr)
            sl = min(sl, entry_price - (min_sl_pips * pip_size))
        else:
            sl = float(snap.get('upper_6') or (entry_price + 50 * pip_size)) + (2.0 * atr)
            sl = max(sl, entry_price + (min_sl_pips * pip_size))
    else:
        # Fallback si no hay snapshot
        sl_pips = FOREX_RISK_CONFIG['sl_pips_default']
        tp_pips = sl_pips * FOREX_RISK_CONFIG['tp_rr_ratio']
        if direction == 'long':
            sl, tp = entry_price - (sl_pips * pip_size), entry_price + (tp_pips * pip_size)
        else:
            sl, tp = entry_price + (sl_pips * pip_size), entry_price - (tp_pips * pip_size)

    return {
        'sl_price': round(sl, 6),
        'tp_price': round(tp, 6),
        'sl_pips': abs(entry_price - sl) / pip_size,
    }


def calculate_forex_lot_size(
    symbol: str,
    capital_usd: float,
    risk_pct: float,
    sl_pips: float,
    leverage: int = 100,
    price: float = 1.0,
    rsi: float = 50.0,
    bb_lower: float = 0.0,
    bb_upper: float = 0.0,
    side: str = 'long'
) -> dict:
    """
    Calcula tamano de lote Forex basado en LOTAJE BASE FIJO + MULTIPLICADOR 2X EXTREMO.
    - Lotaje Base Fijo: 0.05 lotes para divisas Forex, 0.01 lotes para XAUUSD/Oro.
    - Multiplicador 2x: 2.0 si price < bb_lower o rsi < 20 en LONG (o price > bb_upper o rsi > 80 en SHORT).
    """
    pip_size = PIP_SIZES.get(symbol, 0.0001)
    sym_upper = (symbol or '').upper()

    if 'XAU' in sym_upper or 'GOLD' in sym_upper:
        base_lots = 0.01
    else:
        base_lots = 0.05

    multiplier = 1.0
    dir_str = str(side).lower()
    if dir_str in ('long', 'buy'):
        if (bb_lower > 0 and price < bb_lower) or (rsi < 20):
            multiplier = 2.0
    else:
        if (bb_upper > 0 and price > bb_upper) or (rsi > 80):
            multiplier = 2.0

    lots = round(base_lots * multiplier, 2)
    pip_val_usd = 10.0 if 'JPY' not in sym_upper else (10.0 / (price if price > 0 else 1.0))
    risk_usd = lots * max(sl_pips, 10.0) * pip_val_usd

    return {
        'lotes': lots,
        'risk_usd': round(risk_usd, 2),
        'pip_value': pip_val_usd,
        'pip_size': pip_size,
    }


async def open_forex_position(
    symbol: str,
    signal: dict,
    price: float,
    provider: CTraderProtobufProvider,
    sb,
):
    """
    Abrir posicion Forex via cTrader.
    Replica la logica de _execute_paper_open para Crypto.
    """
    direction = signal['direction']
    rc_raw = signal.get('rule_code', '')
    if isinstance(rc_raw, dict):
        rule_code = str(rc_raw.get('code', rc_raw.get('name', str(rc_raw))))
    else:
        rule_code = str(rc_raw)

    # === GUARD: Servicio Forex suspendido desde Settings ===
    try:
        fx_enabled_res = sb.table('system_config').select('value').eq('key', 'forex_enabled').maybe_single().execute()
        if fx_enabled_res and fx_enabled_res.data:
            val = fx_enabled_res.data.get('value')
            if val is False or val == 'false' or val == False:
                log_warning(MODULE, f"⏸️ [FOREX SUSPENDIDO] {symbol} {direction.upper()} rechazado: Servicio Forex desactivado desde Settings.")
                return
    except Exception:
        pass  # Si falla la consulta, permitir operar por seguridad

    # === ESCUDO DE SEGURIDAD ESTRICTO ===
    from app.core.safety_manager import validate_signal
    snap = MARKET_SNAPSHOT_CACHE.get(symbol, {})
    v_signal = validate_signal(
        symbol=symbol,
        price=price,
        market_type='forex_futures',
        direction=direction,
        rule_code=rule_code,
        snap=snap
    )
    if not v_signal['valid']:
        log_warning(MODULE, f"❌ BLOQUEO DE SEGURIDAD [{symbol}]: Posición abortada. Motivo: {v_signal['reason']}")
        return
    # === CHECK CANTIDAD MÁXIMA DE MONEDAS ACTIVAS (FOREX) ===
    try:
        open_fx = sb.table('forex_positions').select('symbol').eq('status', 'open').execute().data or []
        active_fx_symbols = set(p['symbol'] for p in open_fx)
        
        tc_res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        tc_params = (tc_res.data.get('regime_params') if tc_res and tc_res.data else {}) or {}
        max_active_symbols_forex = int(tc_params.get('max_active_symbols_forex', 1))
        
        if symbol not in active_fx_symbols and len(active_fx_symbols) >= max_active_symbols_forex:
            log_warning(MODULE, f"⛔ SEÑAL RECHAZADA para {symbol}: Máximo de monedas activas en Forex alcanzado ({len(active_fx_symbols)}/{max_active_symbols_forex})")
            return
    except Exception as e:
        log_error(MODULE, f"Error en validación max_active_symbols_forex: {e}")
    # ========================================================

    # ═══════════════════════════════════════════════════
    # PASO 1.5 — Reversión de posiciones opuestas (Netting Forex)
    # ═══════════════════════════════════════════════════
    try:
        opposite_side = 'short' if direction.lower() == 'long' else 'long'
        opp_res = sb.table('forex_positions').select('*')\
            .eq('status', 'open')\
            .eq('symbol', symbol)\
            .execute()
        
        opp_positions = [p for p in (opp_res.data or []) if p.get('side', '').lower() == opposite_side]
        
        if opp_positions:
            total_value = 0.0
            total_pnl = 0.0
            for opp_pos in opp_positions:
                pos_entry = float(opp_pos.get('avg_entry_price') or opp_pos.get('entry_price') or 0)
                pos_size = float(opp_pos.get('size') or 1.0)
                p_side = (opp_pos.get('side') or '').upper()
                if pos_entry > 0:
                    pos_val = pos_entry * pos_size
                    if p_side in ['LONG', 'BUY']:
                        pos_pnl = (price - pos_entry) * pos_size
                    else:
                        pos_pnl = (pos_entry - price) * pos_size
                    total_value += pos_val
                    total_pnl += pos_pnl
            
            log_info(MODULE, f"{symbol}: Evaluando {len(opp_positions)} posiciones {opposite_side.upper()} para Selective Reversal Netting")
            from app.core.position_monitor import _execute_paper_close
            for opp_pos in opp_positions:
                try:
                    pos_entry = float(opp_pos.get('avg_entry_price') or opp_pos.get('entry_price') or 0)
                    pos_size = float(opp_pos.get('size') or 1.0)
                    p_side = (opp_pos.get('side') or '').upper()
                    
                    pos_pnl = 0.0
                    if pos_entry > 0:
                        if p_side in ['LONG', 'BUY']:
                            pos_pnl = (price - pos_entry) * pos_size
                        else:
                            pos_pnl = (pos_entry - price) * pos_size
                            
                    if pos_pnl > 0:
                        # Cerrar en DB
                        await _execute_paper_close(opp_pos, price, f'reversal_{direction.lower()}', sb)
                        
                        # Cerrar en cTrader si es LIVE
                        if opp_pos.get('mode') == 'live' and opp_pos.get('ctrader_order_id') and provider:
                            lots_abs = abs(float(opp_pos.get('lots') or opp_pos.get('size') or 0.01))
                            await provider.close_order(str(opp_pos['ctrader_order_id']), int(lots_abs * 100000))
                            
                        log_info(MODULE, f"{symbol}: [REVERSAL] Cerrada posición opuesta {opp_pos['id']} ({opposite_side.upper()}) con ganancia.")
                    else:
                        log_info(MODULE, f"🛡️ [HEDGE] {symbol}: Posición opuesta {opp_pos['id']} en pérdida. Manteniendo abierta y abriendo cobertura.")
                except Exception as rev_err:
                    log_error(MODULE, f"{symbol}: Error procesando reversión para posición {opp_pos.get('id')}: {rev_err}")
    except Exception as rev_outer_err:
        log_error(MODULE, f"{symbol}: Error en lógica de reversión Forex: {rev_outer_err}")
    # ═══════════════════════════════════════════════════

    # Leer config de trading
    try:
        cfg_res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
        cfg = cfg_res.data or {}
    except:
        cfg = {}

    capital_op_fallback = float(cfg.get('capital_operativo', cfg.get('capital_total', 1000)))
    capital = float(cfg.get('capital_forex_futures', capital_op_fallback))
    
    risk_pct = FOREX_RISK_CONFIG['max_risk_per_trade'] * 100  # 1% default
    try:
        rc_res = sb.table('risk_config').select('max_risk_per_trade_pct').limit(1).execute()
        if rc_res.data:
            risk_pct = float(rc_res.data[0].get('max_risk_per_trade_pct', 2.0))
        else:
            risk_pct = float(cfg.get('max_trade_loss_pct', 1.0))
    except Exception:
        risk_pct = float(cfg.get('max_trade_loss_pct', 1.0))

    # 1. Calcular SL/TP usando Fibonacci
    levels = calculate_forex_sl_tp(
        symbol=symbol,
        direction=direction,
        entry_price=price,
        snap=MARKET_SNAPSHOT_CACHE.get(symbol)
    )
    sl_pips = levels['sl_pips']

    # 2. Calcular lot size basado en riesgo real
    sizing = calculate_forex_lot_size(
        symbol=symbol,
        capital_usd=capital,
        risk_pct=risk_pct,
        sl_pips=sl_pips,
        price=price,
    )

    # ── NUEVO: Calcular precio LIMIT inteligente para 1ª Entrada ──
    existing_positions = BOT_STATE.get_positions_by_symbol(symbol)
    is_primary_entry = (len(existing_positions) == 0)
    
    limit_price = None
    if is_primary_entry:
        try:
            snap_data = MARKET_SNAPSHOT_CACHE.get(symbol, {})
            df_5m = get_memory_df(symbol, '5m')
            df_15m = get_memory_df(symbol, '15m')
            
            ema3_5m, ema9_5m, ema20_5m = price, price, price
            ema3_5m_prev = price
            if df_5m is not None and len(df_5m) >= 2:
                last_5m = df_5m.iloc[-1]
                prev_5m = df_5m.iloc[-2] if len(df_5m) >= 3 else last_5m
                c_series_5m = df_5m['close']
                ema3_series = c_series_5m.ewm(span=3, adjust=False).mean()
                ema3_5m = float(last_5m.get('ema1') or last_5m.get('ema_3') or ema3_series.iloc[-1])
                ema3_5m_prev = float(prev_5m.get('ema1') or prev_5m.get('ema_3') or ema3_series.iloc[-2])
                ema9_5m = float(last_5m.get('ema2') or last_5m.get('ema_9') or c_series_5m.ewm(span=9, adjust=False).mean().iloc[-1])
                ema20_5m = float(last_5m.get('ema3') or last_5m.get('ema_20') or c_series_5m.ewm(span=20, adjust=False).mean().iloc[-1])

            ema3_15m, ema9_15m, ema20_15m = price, price, price
            bb_upper, bb_lower, basis = 0, 0, price
            if df_15m is not None and len(df_15m) >= 2:
                last_15m = df_15m.iloc[-1]
                c_series_15m = df_15m['close']
                ema3_15m = float(last_15m.get('ema1') or last_15m.get('ema_3') or c_series_15m.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_15m = float(last_15m.get('ema2') or last_15m.get('ema_9') or c_series_15m.ewm(span=9, adjust=False).mean().iloc[-1])
                ema20_15m = float(last_15m.get('ema3') or last_15m.get('ema_20') or c_series_15m.ewm(span=20, adjust=False).mean().iloc[-1])
                bb_upper = float(last_15m.get('upper_2', 0) or 0)
                bb_lower = float(last_15m.get('lower_2', 0) or 0)
                basis = ema20_15m if ema20_15m > 0 else float(last_15m.get('basis', price) or price)
            
            is_long = direction.lower() in ('long', 'buy')
            ema3_is_ascending = (ema3_5m > ema3_5m_prev)
            ema3_is_descending = (ema3_5m < ema3_5m_prev)
            
            if is_long:
                if not ema3_is_ascending:
                    log_warning(MODULE, f"⛔ [EMA3 SLOPE REJECT] {symbol} LONG abortado: EMA3 de 5m NO está en modo ascendente (curr={ema3_5m:.5f} <= prev={ema3_5m_prev:.5f})")
                    return
                if ema3_5m > ema9_5m > ema20_5m:
                    limit_prices = [min(price, ema9_5m) if ema9_5m > 0 else price, ema20_5m]
                    regime_name = "Impulso Alcista 5m (Dual LIMIT EMA9+EMA20)"
                elif ema3_15m > ema9_15m:
                    ma_candidates = [m for m in (ema9_15m, ema20_15m) if 0 < m < price]
                    limit_prices = [max(ma_candidates) if ma_candidates else price]
                    regime_name = "Tendencia Alcista 15m (EMA9/20_15m)"
                else:
                    if bb_lower > 0 and basis > bb_lower:
                        limit_prices = [bb_lower + (0.05 * (basis - bb_lower))]
                    else:
                        limit_prices = [price * 0.998]
                    regime_name = "Pullback/Squeeze (95% BB Inferior 15m)"
            else:
                if not ema3_is_descending:
                    log_warning(MODULE, f"⛔ [EMA3 SLOPE REJECT] {symbol} SHORT abortado: EMA3 de 5m NO está en modo descendente (curr={ema3_5m:.5f} >= prev={ema3_5m_prev:.5f})")
                    return
                if ema3_5m < ema9_5m < ema20_5m:
                    limit_prices = [max(price, ema9_5m) if ema9_5m > 0 else price, ema20_5m]
                    regime_name = "Impulso Bajista 5m (Dual LIMIT EMA9+EMA20)"
                elif ema3_15m < ema9_15m:
                    ma_candidates = [m for m in (ema9_15m, ema20_15m) if m > price]
                    limit_prices = [min(ma_candidates) if ma_candidates else price]
                    regime_name = "Tendencia Bajista 15m (EMA9/20_15m)"
                else:
                    if bb_upper > 0 and bb_upper > basis:
                        limit_prices = [bb_upper - (0.05 * (bb_upper - basis))]
                    else:
                        limit_prices = [price * 1.002]
                    regime_name = "Repunte/Squeeze (95% BB Superior 15m)"
            
            if len(limit_prices) > 1:
                log_info(MODULE, f"🎯 [PRIMARY LIMIT DUAL] {symbol} {direction.upper()} | Régimen: {regime_name} | Price={price:.5f} -> Limit1={limit_prices[0]:.5f}, Limit2={limit_prices[1]:.5f}")
                limit_price = limit_prices # Pass list
            else:
                limit_price = limit_prices[0]
                log_info(MODULE, f"🎯 [PRIMARY LIMIT CALC 5M/15M] {symbol} {direction.upper()} | Régimen: {regime_name} | Price={price:.5f} -> LimitPrice={limit_price:.5f}")
        except Exception as lp_err:
            log_error(MODULE, f"Error calculando limit_price para {symbol}: {lp_err}")
            limit_price = None

    # Paper trading check
    is_paper = cfg.get('paper_trading', False) is not False

    limit_list = limit_price if isinstance(limit_price, list) else ([limit_price] if limit_price else [None])
    num_orders = len(limit_list)
    lots = sizing['lotes']
    
    # Opción A (Riesgo Dividido): Dividir el lotaje base entre las órdenes
    base_lots = [round(lots / num_orders, 2) for _ in range(num_orders)]
    diff = round(lots - sum(base_lots), 2)
    if diff != 0 and num_orders > 0:
        base_lots[0] = round(base_lots[0] + diff, 2)
        
    for idx, limit_px in enumerate(limit_list):
        order_lots = base_lots[idx]
        if order_lots < 0.01:
            order_lots = 0.01
            
        exec_px = limit_px if (is_primary_entry and limit_px) else price
        exec_type = 'LIMIT' if (is_primary_entry and limit_px) else 'MARKET'
        
        if is_paper:
            # Paper trading: simular orden
            order = {
                'order_id': int(time.time()) + idx,
                'symbol': symbol,
                'side': direction,
                'quantity': order_lots,
                'price': exec_px,
                'status': 'filled',
            }
            log_info(MODULE, f"[PAPER] Orden Forex {exec_type} ({idx+1}/{num_orders}): {direction.upper()} {order_lots} lotes {symbol} @ {exec_px:.5f}")
        else:
            # Live trading: enviar a cTrader
            order = await provider.place_order(
                symbol=symbol,
                side='buy' if direction == 'long' else 'sell',
                order_type=exec_type.lower(),
                quantity=order_lots,
                price=exec_px if exec_type == 'LIMIT' else None,
                sl_price=levels['sl_price'],
                tp_price=levels['tp_price'],
            )
            log_info(MODULE, f"[LIVE {exec_type}] ({idx+1}/{num_orders}) {direction.upper()} {order_lots} lotes {symbol} @ {exec_px:.5f}")
            
        if 'error' in order:
            log_error(MODULE, f"Error abriendo posicion ({idx+1}/{num_orders}): {order['error']}")
            return

        # 3. Calcular SLV y Hard Stop inicial
        from app.strategy.virtual_sl_recovery import calculate_slv, calculate_hard_stop_pips
        slv_data = calculate_slv(
            entry_price = exec_px,
            side        = direction,
            symbol      = symbol,
            snap        = MARKET_SNAPSHOT_CACHE.get(symbol, {}),
            market_type = 'forex_futures'
        )
        slv_price = slv_data['slv_price']
        slv_hs_pips = calculate_hard_stop_pips(symbol, 'forex_futures', MARKET_SNAPSHOT_CACHE.get(symbol, {}))

        # Registrar en Supabase
        order_status = 'pending_limit' if (is_primary_entry and limit_px and not is_paper) else 'open'
        try:
            sb.table('forex_positions').insert({
                'symbol':           str(symbol)[:20],
                'side':             str(direction)[:20],
                'entry_price':      exec_px,
                'lots':             order_lots,
                'sl_price':         levels['sl_price'],
                'slv_price':        slv_price,
                'slv_hard_stop_pips': slv_hs_pips,
                'tp_price':         levels['tp_price'],
                'rule_code':        str(rule_code)[:20],
                'status':           order_status,
                'mode':             'paper' if is_paper else 'live',
                'market_type':      'forex_futures',
                'ctrader_order_id': int(order.get('order_id')) if (order and order.get('order_id') and str(order.get('order_id')).isdigit()) else None,
                'opened_at':        datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log_error(MODULE, f"Error registrando posicion en DB: {e}")

        # Registrar en BOT_STATE
        pos_id = str(order.get('order_id', f'FX-{int(time.time()) + idx}'))
        BOT_STATE.positions[pos_id] = {
            'id': pos_id,
            'symbol': symbol,
            'side': direction,
            'avg_entry_price': exec_px,
            'size': order_lots,
            'sl_price': levels['sl_price'],
            'slv_price': slv_price,
            'slv_hard_stop_pips': slv_hs_pips,
        'market_type': 'forex_futures',
    }
    sm.on_position_opened(symbol, direction, BOT_STATE.positions[pos_id])

    # Telegram
    side_emoji = 'LONG' if direction == 'long' else 'SHORT'
    pip_size = PIP_SIZES.get(symbol, 0.0001)
    entry_target = limit_price if (is_primary_entry and limit_price) else price
    sl_pips = abs(entry_target - levels['sl_price']) / pip_size
    tp_pips = abs(levels['tp_price'] - entry_target) / pip_size
    rr_ratio = tp_pips / sl_pips if sl_pips > 0 else 0
    
    if order_status == 'pending_limit':
        msg_header = f"🎯 ORDEN LÍMITE PENDIENTE — FOREX {side_emoji} [{symbol}]"
        entry_lbl = f"Precio Límite: {limit_price:.5f} (Pendiente de ejecución en cTrader)"
    else:
        msg_header = f"⚡ POSICIÓN ABIERTA — FOREX {side_emoji} [{symbol}]"
        entry_lbl = f"Entrada: {price:.5f}"

    await send_telegram_message(
        f"{msg_header}\n"
        f"Regla: {rule_code} | Score: {signal.get('score', 0):.2f}\n"
        f"{entry_lbl}\n"
        f"SL: {levels['sl_price']:.5f} (-{sl_pips:.0f} pips)\n"
        f"TP: {levels['tp_price']:.5f} (+{tp_pips:.0f} pips) RR 1:{rr_ratio:.1f}\n"
        f"Lotes: {sizing['lotes']} | Riesgo: ${sizing['risk_usd']:.2f}"
    )


# ══════════════════════════════════════════════════
#  CYCLE 5m — Position Management (Forex)
# ══════════════════════════════════════════════════

async def _forex_process_symbol_5m(symbol: str, provider: CTraderProtobufProvider, sb):
    """Procesar un simbolo Forex en ciclo 5m."""
    try:
        # 1. Obtener precio actual
        current_price = await provider.get_current_price(symbol)
        if current_price <= 0:
            return

        # 2. Actualizar velas en memoria
        update_current_candle_close(symbol=symbol, current_price=current_price)

        # 3. Snapshot cache update
        MARKET_SNAPSHOT_CACHE[symbol] = MARKET_SNAPSHOT_CACHE.get(symbol, {})
        MARKET_SNAPSHOT_CACHE[symbol]['price'] = current_price

        # --- VERIFICAR EJECUCIÓN LIMIT ORDERS (SWING) ---
        try:
            from app.strategy.swing_orders import check_limit_order_execution
            await check_limit_order_execution(symbol=symbol, current_price=current_price, provider=provider, sb=sb)
        except Exception as limit_err:
            log_error(MODULE, f"Error verificando ejecución de orden límite swing para {symbol}: {limit_err}")

        # 4. Smart Exit: SAR Phase Change
        snap = MARKET_SNAPSHOT_CACHE.get(symbol, {})
        sar_data = MEMORY_STORE.get(symbol, {}).get('sar', {})
        sar_phase = sar_data.get('phase', 'neutral')
        sar_changed_at = sar_data.get('changed_at')

        positions = BOT_STATE.get_positions_by_symbol(symbol)
        for position in positions:
            # --- SLVM v2 (Recovery & Hard Stop) ---
            from app.strategy.virtual_sl_recovery import process_symbol_5m_with_slvm_v2
            slvm_res = await process_symbol_5m_with_slvm_v2(
                symbol        = symbol,
                current_price = current_price,
                snap          = snap,
                sb            = sb,
                market_type   = 'forex_futures',
                position      = position
            )
            
            if slvm_res and slvm_res.get('should_close'):
                await _execute_paper_close(position, current_price, slvm_res.get('exit_type', 'slvm_close_fx'), sb)
                continue
            
            # --- MARGIN CALL ALERT (Amenaza al Capital) ---
            entry_p_margin = float(position.get('entry_price') or position.get('avg_entry_price') or 0)
            if entry_p_margin > 0:
                is_long_margin = (position.get('side') or 'long').lower() in ['long', 'buy']
                qty_margin = float(position.get('size') or position.get('lots') or 0)
                # Aproximación USD (En Forex real se debería usar pip_value * pips, pero esto es aproximado)
                # Usaremos la misma lógica básica de pnl_pct y lo proyectamos si es posible, o pnl raw.
                if 'total_pnl_usd' in position:
                    upnl_usd_margin = float(position['total_pnl_usd'] or 0)
                else:
                    # Alternativa simple: usar el %
                    upnl_pct_margin = (current_price - entry_p_margin) / entry_p_margin * 100 if is_long_margin else (entry_p_margin - current_price) / entry_p_margin * 100
                    # Asumimos que margin_call_alert_pct ya lidia con el ratio sobre la cuenta. 
                    # Pero check_margin_call espera pnl_usd. Lo pasamos crudo.
                    from app.core.pnl_calculator import calculate_pnl
                    upnl_usd_margin, _ = calculate_pnl('forex', position.get('side', 'long'), entry_p_margin, current_price, qty_margin, symbol, sb)
                
                from app.core.position_monitor import check_margin_call_alert
                await check_margin_call_alert(
                    symbol  = symbol,
                    pnl_usd = upnl_usd_margin,
                    sb      = sb,
                    pos_id  = str(position.get('id', ''))
                )



            # 4.3 Guardia de Posición Fantasma cTrader (Live orders sin cTrader ID después de 300s / 5 min)
            if position.get('mode') == 'live' and not position.get('ctrader_pos_id'):
                opened_at_str = position.get('opened_at')
                if opened_at_str:
                    try:
                        opened_dt = datetime.fromisoformat(str(opened_at_str).replace('Z', '+00:00'))
                        elapsed_s = (datetime.now(timezone.utc) - opened_dt).total_seconds()
                        if elapsed_s > 300:
                            log_warning(MODULE, f"👻 [GHOST POSITION GUARD] Cierre automático de posición fantasma no confirmada en cTrader para {symbol} (id={position['id']}) tras {elapsed_s:.0f}s")
                            sb.table('forex_positions').update({
                                'status': 'closed',
                                'closed_at': datetime.now(timezone.utc).isoformat(),
                                'close_reason': 'ctrader_unconfirmed_ghost'
                            }).eq('id', position['id']).execute()
                            continue
                    except Exception as g_e:
                        log_error(MODULE, f"Error en Ghost Position Guard para {symbol}: {g_e}")

            # 4.5 SMART EXIT DELAYED (Rebote técnico tras SAR)
            pending_sar_closes = MEMORY_STORE.setdefault(symbol, {}).setdefault('pending_sar_closes', {})
            pos_id = str(position.get('id', ''))
            is_pending_sar = pending_sar_closes.get(pos_id, False)

            if is_pending_sar:
                rsi_15m = snap.get('rsi_15m', 50)
                side = (position.get('side') or '').lower()
                bounce_triggered = False
                
                if side == 'long' and rsi_15m >= 55:
                    bounce_triggered = True
                elif side == 'short' and rsi_15m <= 45:
                    bounce_triggered = True
                    
                if bounce_triggered:
                    # 🛡️ Protección de tendencia EMA3/EMA9 (15m)
                    _ema3 = float(snap.get('ema3', 0))
                    _ema9 = float(snap.get('ema9', 0))
                    _trend_protected = False
                    if _ema3 > 0 and _ema9 > 0:
                        if side == 'long' and _ema3 > _ema9:
                            _trend_protected = True
                        elif side == 'short' and _ema3 < _ema9:
                            _trend_protected = True
                    
                    if _trend_protected:
                        log_info(MODULE, f"🛡️ SAR_DELAYED evitado para {symbol} por protección de tendencia (EMA3 vs EMA9).")
                    else:
                        await _execute_paper_close(position, current_price, 'sar_phase_change_fx_delayed', sb)
                        await send_telegram_message(
                            f"🎯 FX SAR EXIT DELAYED EJECUTADO [{symbol}]\n"
                            f"Cerrando {side.upper()} tras rebote (RSI 15m: {rsi_15m:.1f})\n"
                            f"Precio: {current_price:.5f}"
                        )
                        pending_sar_closes.pop(pos_id, None)
                        continue # Sigue con la siguiente posicion

            # 4. Smart Exit: SAR Phase Change
            if sar_changed_at and not is_pending_sar:
                side = (position.get('side') or '').lower()
                if (sar_phase == 'short' and side == 'long') or \
                   (sar_phase == 'long' and side == 'short'):

                    entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                    pnl_pct = 0.0
                    pnl_pips = 0.0
                    if entry > 0:
                        if side == 'long':
                            pnl_pct = (current_price - entry) / entry * 100
                            pnl_pips = (current_price - entry) / PIP_SIZES.get(symbol, 0.0001)
                        else:
                            pnl_pct = (entry - current_price) / entry * 100
                            pnl_pips = (entry - current_price) / PIP_SIZES.get(symbol, 0.0001)

                    if pnl_pct >= -0.05:
                        # 🛡️ Protección de tendencia EMA3/EMA9 (15m)
                        _ema3 = float(snap.get('ema3', 0))
                        _ema9 = float(snap.get('ema9', 0))
                        _trend_protected = False
                        if _ema3 > 0 and _ema9 > 0:
                            if side == 'long' and _ema3 > _ema9:
                                _trend_protected = True
                            elif side == 'short' and _ema3 < _ema9:
                                _trend_protected = True
                        
                        if _trend_protected:
                            log_info(MODULE, f"🛡️ SAR_PHASE_CHANGE evitado para {symbol} por protección de tendencia (EMA3 vs EMA9).")
                        else:
                            await _execute_paper_close(position, current_price, 'sar_phase_change_fx', sb)
                            await send_telegram_message(
                                f"🔄 FOREX SAR REVERSAL [{symbol}]\n"
                                f"SAR 4h -> {sar_phase.upper()}\n"
                                f"Cerrando {side.upper()} (PNL: {pnl_pct:.2f}% | {pnl_pips:+.1f} pips)\n"
                                f"Precio: {current_price:.5f}"
                            )
                            pending_sar_closes.pop(pos_id, None)
                            continue # Sigue con la siguiente posicion
                    else:
                        pending_sar_closes[pos_id] = True
                        await send_telegram_message(
                            f"⏳ FX SAR REVERSAL (DELAYED) [{symbol}]\n"
                            f"Pérdida actual {pnl_pct:.2f}% < -0.05%.\n"
                            f"Esperando rebote técnico (RSI) para cerrar {side.upper()}."
                        )
                        # Sigue evaluando tp/sl normales
            # 5. Smart Exit: Signal Reversal
            current_mtf = float(snap.get('mtf_score', 0))
            trading_config = BOT_STATE.config_cache

            reversal = await check_signal_reversal(
                position=position,
                current_mtf=current_mtf,
                current_price=current_price,
                config=trading_config,
                snap=snap
            )

            if reversal.get('should_exit'):
                # 🛡️ Protección de tendencia EMA3/EMA9 (15m)
                side = (position.get('side') or '').lower()
                _ema3 = float(snap.get('ema3', 0))
                _ema9 = float(snap.get('ema9', 0))
                _trend_protected = False
                if _ema3 > 0 and _ema9 > 0:
                    if side == 'long' and _ema3 > _ema9:
                        _trend_protected = True
                    elif side == 'short' and _ema3 < _ema9:
                        _trend_protected = True
                
                if _trend_protected:
                    log_info(MODULE, f"🛡️ SIGNAL_REVERSAL evitado para {symbol} por protección de tendencia (EMA3 vs EMA9).")
                else:
                    await _execute_paper_close(position, current_price, 'signal_reversal_fx', sb)
                    await send_telegram_message(
                        f"FOREX SALIDA INTELIGENTE [{symbol}]\n"
                        f"MTF giro: {current_mtf:.4f}\n"
                        f"PnL: {reversal.get('pnl_pct', 0):+.2f}%"
                    )
                    continue

            elif reversal.get('should_modify_oco_breakeven'):
                target_tp = reversal['target_tp_price']
                rev_start_str = position.get('sl_activated_at')
                is_rev_be = position.get('sl_type') == 'reversal_be'
                
                now_utc = datetime.now(timezone.utc)
                if not rev_start_str or not is_rev_be:
                    try:
                        sb.table('forex_positions').update({
                            'tp_price': target_tp,
                            'sl_type': 'reversal_be',
                            'sl_activated_at': now_utc.isoformat(),
                            'sl_activation_reason': 'ema_reversal_exact_be'
                        }).eq('id', position['id']).execute()
                        position['tp_price'] = target_tp
                        position['sl_type'] = 'reversal_be'
                        position['sl_activated_at'] = now_utc.isoformat()
                        
                        log_info(MODULE, f"Forex Break-Even Modificado para {symbol} a TP={target_tp}")
                        await send_telegram_message(
                            f"🛡️ DEFENSA BREAK-EVEN FOREX [{symbol}]\n"
                            f"Reversión rápida 15m detectada.\n"
                            f"TP ajustado a {target_tp:.5f}.\n"
                            f"Inicia contador de 45m para cierre de emergencia."
                        )
                    except Exception as e:
                        log_error(MODULE, f"Error updating Forex TP to Break-Even for {symbol}: {e}")
                else:
                    try:
                        rev_dt = datetime.fromisoformat(rev_start_str.replace('Z', '+00:00'))
                        elapsed_min = (now_utc - rev_dt).total_seconds() / 60
                        if elapsed_min >= 45:
                            entry_p_rev = float(position.get('entry_price') or position.get('avg_entry_price') or 0)
                            loss_pct = 0
                            if entry_p_rev > 0:
                                side_check = (position.get('side') or '').lower()
                                if side_check in ('long', 'buy'):
                                    loss_pct = (entry_p_rev - current_price) / entry_p_rev * 100
                                else:
                                    loss_pct = (current_price - entry_p_rev) / entry_p_rev * 100
                            
                            if 0 <= loss_pct <= 0.50:
                                # 🛡️ Protección de tendencia EMA3/EMA9 (15m)
                                _ema3 = float(snap.get('ema3', 0))
                                _ema9 = float(snap.get('ema9', 0))
                                _trend_protected = False
                                if _ema3 > 0 and _ema9 > 0:
                                    if side_check in ('long', 'buy') and _ema3 > _ema9:
                                        _trend_protected = True
                                    elif side_check in ('short', 'sell') and _ema3 < _ema9:
                                        _trend_protected = True
                                
                                if _trend_protected:
                                    log_info(MODULE, f"🛡️ EMA_REVERSAL_TIMEOUT evitado para {symbol} por protección de tendencia (EMA3 vs EMA9).")
                                else:
                                    await _execute_paper_close(position, current_price, 'ema_reversal_timeout_market', sb)
                                    await send_telegram_message(
                                        f"⏳ CIERRE POR TIMEOUT DE REVERSIÓN FOREX [{symbol}]\n"
                                        f"Tiempo superado: {elapsed_min:.1f}m\n"
                                        f"Pérdida aceptada: -{loss_pct:.2f}%\n"
                                        f"Detalle: Cerrado por Market para evitar mayor caída (límite 0.5%)."
                                    )
                                    continue
                    except Exception as e:
                        log_error(MODULE, f"Error checking forex reversal timeout for {symbol}: {e}")

            # 6. SL/SLV/Recovery check (integrated virtual stop loss for paper mode)
            sl = float(position.get('sl_price', 0))
            tp = float(position.get('tp_price', position.get('tp_partial_price', 0)))
            side = (position.get('side') or '').lower()

            # 6a. Si ya está en recovery_mode, evaluar el modo recuperación
            if position.get('recovery_mode'):
                try:
                    from app.strategy.virtual_sl_recovery import evaluate_recovery_mode_v2
                    mr_result = evaluate_recovery_mode_v2(position, current_price, snap, symbol, 'forex_futures')
                    if mr_result['should_close']:
                        pip_size = PIP_SIZES.get(symbol, 0.0001)
                        entry = float(position.get('avg_entry_price', position.get('entry_price', 0)))
                        if side in ('long', 'buy'):
                            pnl_pips = (current_price - entry) / pip_size
                        else:
                            pnl_pips = (entry - current_price) / pip_size
                        exit_type = f"slv_v2_{mr_result['exit_type']}"
                        await _execute_paper_close(position, current_price, exit_type, sb)
                        await send_telegram_message(
                            f"🛡️ FOREX RECOVERY EXIT [{symbol}]\n"
                            f"{mr_result['exit_type']}: {mr_result.get('reason', '')}\n"
                            f"PnL: {pnl_pips:+.1f} pips"
                        )
                        continue
                except Exception as e:
                    log_error(MODULE, f"Error evaluating recovery mode for {symbol}: {e}")

            # 6b. Evaluar SL adaptativo / SLV trigger (ANTES del hard stop)
            if not position.get('recovery_mode'):
                try:
                    from app.strategy.forex_adaptive_exit import evaluate_forex_sl
                    sl_res = evaluate_forex_sl(symbol, [position], current_price, snap)

                    if sl_res.get('should_close'):
                        pips_est = sl_res.get('pnl_pips', -1.0)
                        if pips_est < 0:
                            # P&L negativo: desviar a Modo Recuperación Virtual en lugar de cerrar
                            log_info(MODULE, f"🛡️ [ANTI-LOSS SLV] {symbol}: SL adaptativo en pérdida ({pips_est:.1f} pips). Activando Recovery Mode.")
                            from app.strategy.virtual_sl_recovery import activate_recovery_mode_sync
                            activate_recovery_mode_sync(position, current_price, symbol, 'forex_futures', sb, 'forex_positions')
                            await send_telegram_message(
                                f"🛡️ FOREX RECOVERY ACTIVATED [{symbol}]\n"
                                f"SL adaptativo tocado en pérdida ({pips_est:.1f} pips)\n"
                                f"Modo Recuperación Virtual activado"
                            )
                        else:
                            await _execute_paper_close(position, current_price, sl_res.get('exit_type', 'sl_adaptive_fx'), sb)
                            await send_telegram_message(
                                f"📉 FOREX ADAPTIVE SL [{symbol}]\n"
                                f"Precio: {current_price:.5f}\n"
                                f"PnL: {pips_est:+.1f} pips"
                            )
                            continue

                    elif sl_res.get('slv_triggered'):
                        # SLV tocado: activar recovery_mode
                        log_info(MODULE, f"🛡️ [SLV TRIGGERED] {symbol}: Activando Recovery Mode")
                        from app.strategy.virtual_sl_recovery import activate_recovery_mode_sync
                        activate_recovery_mode_sync(position, current_price, symbol, 'forex_futures', sb, 'forex_positions')
                        await send_telegram_message(
                            f"🛡️ FOREX SLV TRIGGERED [{symbol}]\n"
                            f"Precio: {current_price:.5f}\n"
                            f"SLV: {position.get('slv_price', 'N/A')}\n"
                            f"Modo Recuperación activado"
                        )
                        # No cerramos, continuamos monitoreando
                except Exception as e:
                    log_error(MODULE, f"Error evaluating SLV for {symbol}: {e}")

            # 6b.5 Cierre Estructural por Cambio de Tendencia (Proactive EMA Exit v2.0 con Guardia Anti-Pérdidas y EREP)
            if not position.get('recovery_mode') and not position.get('erep_active'):
                try:
                    ema3_15m = float(snap.get('ema3', 0))
                    ema9_15m = float(snap.get('ema9', 0))
                    ema3_5m = float(snap.get('ema3_5m', 0))
                    ema9_5m = float(snap.get('ema9_5m', 0))

                    if ema3_15m > 0 and ema9_15m > 0 and ema3_5m > 0 and ema9_5m > 0:
                        is_structural_exit = False
                        
                        # Para operaciones LONG: Si la estructura 15m y 5m giran a bajista
                        if side == 'long':
                            if (ema3_15m < ema9_15m) and (ema3_5m < ema9_5m):
                                is_structural_exit = True
                                
                        # Para operaciones SHORT: Si la estructura 15m y 5m giran a alcista
                        elif side == 'short':
                            if (ema3_15m > ema9_15m) and (ema3_5m > ema9_5m):
                                is_structural_exit = True

                        if is_structural_exit:
                            entry_pr = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                            pip_sz = PIP_SIZES.get(symbol, 0.0001)
                            pips_est = ((current_price - entry_pr) / pip_sz) if side == 'long' else ((entry_pr - current_price) / pip_sz)
                            
                            # 🛡️ REGLA 1: Si la operación está en GANANCIA REAL (pips_est > 0), asegurar ganancia
                            if pips_est > 0:
                                await _execute_paper_close(position, current_price, 'structural_ema_exit', sb)
                                await send_telegram_message(
                                    f"🟢 FOREX STRUCTURAL PROFIT EXIT [{symbol}]\n"
                                    f"Giro de estructura capturando ganancia.\n"
                                    f"Precio: {current_price:.5f}\n"
                                    f"PnL: {pips_est:+.1f} pips"
                                )
                                continue
                            # 🛡️ REGLA 2: Si está en pérdida (pips_est <= 0), NO cerrar en pérdida. Enrutar a EREP Fase 1
                            else:
                                log_info(MODULE, f"🛡️ [STRUCTURAL EXIT GUARD] {symbol} cambió estructura pero está en pérdida ({pips_est:.1f} pips). Enrutando a EREP Fase 1...")
                                try:
                                    from app.strategy.erep_manager import execute_erep_action
                                    await execute_erep_action(
                                        action={'action': 'activate_erep', 'reason': 'structural_break_loss'},
                                        position=position,
                                        current_price=current_price,
                                        symbol=symbol,
                                        market_type='forex_futures',
                                        supabase=sb
                                    )
                                except Exception as erep_e:
                                    log_error(MODULE, f"Error enrutando {symbol} a EREP desde structural exit: {erep_e}")
                                continue
                except Exception as e:
                    log_error(MODULE, f"Error evaluating Structural Exit for {symbol}: {e}")

            # 6b.6 Apretar trailing a EMA3 cuando tendencia 15m se revierte (ganancia > 0)
            if not position.get('recovery_mode'):
                try:
                    ema3_15m = float(snap.get('ema3', 0))
                    ema9_15m = float(snap.get('ema9', 0))
                    entry_pr = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
                    
                    if ema3_15m > 0 and ema9_15m > 0 and entry_pr > 0:
                        # Calcular si estamos en ganancia
                        pip_size_local = PIP_SIZES.get(symbol, 0.0001)
                        pnl_pips_local = ((current_price - entry_pr) / pip_size_local) if side == 'long' else ((entry_pr - current_price) / pip_size_local)
                        
                        is_trend_against = False
                        new_sl_ema3 = 0
                        if side == 'long' and ema3_15m < ema9_15m:
                            is_trend_against = True
                            new_sl_ema3 = ema3_15m
                        elif side == 'short' and ema3_15m > ema9_15m:
                            is_trend_against = True
                            new_sl_ema3 = ema3_15m
                        
                        if is_trend_against and pnl_pips_local > 0 and new_sl_ema3 > 0:
                            current_sl = float(position.get('sl_price', 0))
                            # Solo apretar si el nuevo SL es mejor que el actual
                            should_tighten = False
                            if side == 'long' and (current_sl <= 0 or new_sl_ema3 > current_sl):
                                should_tighten = True
                            elif side == 'short' and (current_sl <= 0 or new_sl_ema3 < current_sl):
                                should_tighten = True
                            
                            if should_tighten:
                                try:
                                    sb.table('forex_positions').update({
                                        'sl_price': new_sl_ema3,
                                        'sl_type': 'ema3_trend_tighten',
                                        'sl_activation_reason': f'EMA3({ema3_15m:.5f}) < EMA9({ema9_15m:.5f}) con ganancia +{pnl_pips_local:.1f} pips'
                                    }).eq('id', position['id']).execute()
                                    position['sl_price'] = new_sl_ema3
                                    sl = new_sl_ema3
                                    log_info(MODULE, f"🎯 TRAILING TIGHTENED [{symbol}]: SL movido a EMA3={new_sl_ema3:.5f} (tendencia revertida, ganancia: +{pnl_pips_local:.1f} pips)")
                                    await send_telegram_message(
                                        f"🎯 TRAILING APRETADO [{symbol}]\n"
                                        f"Tendencia 15m revertida (EMA3 < EMA9)\n"
                                        f"SL movido a EMA3: {new_sl_ema3:.5f}\n"
                                        f"Ganancia actual: +{pnl_pips_local:.1f} pips"
                                    )
                                except Exception as e:
                                    log_error(MODULE, f"Error tightening trailing for {symbol}: {e}")
                except Exception as e:
                    log_error(MODULE, f"Error evaluating trailing tighten for {symbol}: {e}")

            # 6c. Hard Stop de emergencia absoluta (último recurso, solo si no está en recovery)
            if sl > 0 and not position.get('recovery_mode'):
                if (side == 'long' and current_price <= sl) or \
                   (side == 'short' and current_price >= sl):
                    
                    # 🛡️ Protección de tendencia: Evitar cierre en pérdida si el momento es favorable
                    ema3_15m = float(snap.get('ema3', 0))
                    ema9_15m = float(snap.get('ema9', 0))
                    
                    is_protected = False
                    if ema3_15m > 0 and ema9_15m > 0:
                        if side == 'long' and ema3_15m > ema9_15m:
                            is_protected = True
                        elif side == 'short' and ema3_15m < ema9_15m:
                            is_protected = True

                    if not is_protected:
                        await _execute_paper_close(position, current_price, 'sl_hit_fx_hard', sb)
                        await send_telegram_message(
                            f"🚨 FOREX HARD STOP [{symbol}]\n"
                            f"Precio: {current_price:.5f}\n"
                            f"Hard SL: {sl:.5f}\n"
                            f"⚠️ Emergencia: SLV no pudo recuperar"
                        )
                        continue
                    else:
                        log_info(MODULE, f"🛡️ SL_HIT_FX_HARD evitado para {symbol} por protección de tendencia (EMA3 vs EMA9).")

            if tp > 0:
                if (side == 'long' and current_price >= tp) or \
                   (side == 'short' and current_price <= tp):
                    await _execute_paper_close(position, current_price, 'tp_hit_fx', sb)
                    await send_telegram_message(
                        f"FOREX TP HIT [{symbol}]\n"
                        f"Precio: {current_price:.5f}\n"
                        f"TP: {tp:.5f}"
                    )
                    continue

        # 7. Heartbeat
        try:
            sb.table('bot_state').upsert({
                'symbol': symbol,
                'last_5m_cycle_at': datetime.now(timezone.utc).isoformat(),
                'last_updated': datetime.now(timezone.utc).isoformat(),
            }, on_conflict='symbol').execute()
        except:
            pass

        # 8. Evaluación de Entradas Primarias en Ciclo de 5m (Cruces de Momentum)
        await _evaluate_5m_primary_signals(symbol, provider, sb)

    except Exception as e:
        log_error(MODULE, f"5m cycle error {symbol}: {e}")


async def _evaluate_5m_primary_signals(symbol: str, provider: CTraderProtobufProvider, sb):
    """
    Evaluación de Entradas Primarias en el Ciclo de 5 Minutos.
    Garantiza que cruces de momentum (ej. EMA3 < EMA9 < EMA20 en 5m para SHORT a las 20:50)
    activen inmediatamente las órdenes LIMIT en EMA9_5m en la cima del movimiento.
    """
    try:
        # Guard: Servicio Forex suspendido desde Settings
        try:
            fx_en = sb.table('system_config').select('value').eq('key', 'forex_enabled').maybe_single().execute()
            if fx_en and fx_en.data:
                val = fx_en.data.get('value')
                if val is False or val == 'false' or val == False:
                    return
        except:
            pass

        df_5m = get_memory_df(symbol, '5m')
        if df_5m is None or len(df_5m) < 3:
            return
            
        last_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]
        c_series_5m = df_5m['close']
        
        current_price = float(last_5m['close'])
        ema3_series = c_series_5m.ewm(span=3, adjust=False).mean()
        ema9_series = c_series_5m.ewm(span=9, adjust=False).mean()
        ema20_series = c_series_5m.ewm(span=20, adjust=False).mean()

        ema3_5m = float(last_5m.get('ema1') or last_5m.get('ema_3') or ema3_series.iloc[-1])
        ema9_5m = float(last_5m.get('ema2') or last_5m.get('ema_9') or ema9_series.iloc[-1])
        ema20_5m = float(last_5m.get('ema3') or last_5m.get('ema_20') or ema20_series.iloc[-1])

        ema3_prev = float(prev_5m.get('ema1') or prev_5m.get('ema_3') or ema3_series.iloc[-2])
        ema9_prev = float(prev_5m.get('ema2') or prev_5m.get('ema_9') or ema9_series.iloc[-2])

        # Verificar cruce fresco de momentum en 5m
        is_fresh_long = (ema3_5m > ema9_5m > ema20_5m) and (ema3_prev <= ema9_prev or ema3_5m > ema3_prev)
        is_fresh_short = (ema3_5m < ema9_5m < ema20_5m) and (ema3_prev >= ema9_prev or ema3_5m < ema3_prev)

        if not (is_fresh_long or is_fresh_short):
            return

        direction = 'long' if is_fresh_long else 'short'
        rule_code = 'BbHot' if direction == 'short' else 'AaHot'

        # Verificar si ya existe posición abierta para este símbolo
        existing_positions = BOT_STATE.get_positions_by_symbol(symbol)
        if existing_positions:
            return

        signal = {
            'rule_code': rule_code,
            'direction': direction,
            'strategy_type': 'scalping',
            'cycle': '5m',
            'score': 0.85,
            'reason': f'5m Crossover {direction.upper()} (EMA3={ema3_5m:.5f}, EMA9={ema9_5m:.5f}, EMA20={ema20_5m:.5f})'
        }

        log_info(MODULE, f"⚡ [5M CROSSOVER TRIGGER] {symbol} {direction.upper()} en candle close 5m (EMA9_5m={ema9_5m:.5f})")
        await open_forex_position(
            symbol=symbol,
            signal=signal,
            price=current_price,
            provider=provider,
            sb=sb
        )
    except Exception as e:
        log_error(MODULE, f"Error en _evaluate_5m_primary_signals para {symbol}: {e}")


async def forex_cycle_5m():
    """Ciclo 5m Forex: Gestion de posiciones y smart exits."""
    from app.core.safety_manager import is_system_paused, check_db_circuit_breaker
    if check_db_circuit_breaker():
        return
    if is_system_paused():
        log_debug("FOREX_SCHEDULER", "Sistema pausado globalmente. Omitiendo ciclo 5m.")
        return

    from app.core.market_hours import is_forex_market_open
    if not is_forex_market_open():
        log_debug("FOREX_SCHEDULER", "Mercado Forex cerrado. Omitiendo ciclo 5m.")
        return

    global _forex_provider
    log_debug(MODULE, "--- Forex 5m Cycle ---")

    sb = get_supabase()
    symbols = FOREX_SYMBOLS

    provider = _forex_provider
    if not provider or not provider._connected:
        log_warning(MODULE, "Provider Forex desconectado. Intentando reconectar en segundo plano y omitiendo ciclo 5m.")
        asyncio.create_task(get_forex_provider())
        return

    try:
        # Sync positions to memory to enforce state limits
        try:
            from app.workers.scheduler import sync_positions_to_memory
            await sync_positions_to_memory()
        except Exception as e:
            log_error(MODULE, f"Error syncing positions in forex 5m: {e}")

        tasks = [_forex_process_symbol_5m(s, provider, sb) for s in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)

        # ── TICK STATE MACHINE (Waiting/Ambiguous) ──
        for sym in symbols:
            sm.tick_waiting(sym)
            sm.tick_ambiguous(sym)

        # ── SYNC BROKER BALANCE TO SUPABASE ──
        try:
            balance_info = await provider.get_account_balance()
            if balance_info and 'balance' in balance_info:
                current_params = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
                params = (current_params.data or {}).get('regime_params') or {}
                params['broker_balance_forex'] = balance_info['balance']
                sb.table('trading_config').update({'regime_params': params}).eq('id', 1).execute()
                log_debug(MODULE, f"Broker balance synced: ${balance_info['balance']:.2f}")
        except Exception as bal_err:
            log_debug(MODULE, f"Balance sync skip: {bal_err}")

    except Exception as e:
        log_error(MODULE, f"Error global forex 5m: {e}")


# ══════════════════════════════════════════════════
#  CYCLE 15m — Full Analysis (Forex)
# ══════════════════════════════════════════════════

from app.strategy.profit_capture import evaluate_profit_capture
from app.strategy.profit_ladder import evaluate_profit_ladder, check_basis_crossed
from app.core.position_monitor import _execute_paper_close, _execute_paper_partial_close

async def process_forex_profit_management_15m(
    symbol: str,
    position: dict,
    current_price: float,
    snap: dict,
    df_15m: pd.DataFrame,
    sb,
    provider
) -> bool:
    """
    Gestión de ganancias en ciclo 15m para Forex.
    Corre MÓDULO A (Profit Capture) y MÓDULO B (Profit Ladder).
    """
    side = str(position.get('side', 'long'))
    pos_id = position.get('id')
    market_type = 'forex_futures'

    # ── MÓDULO A: Profit Capture ───────────────
    result_a = evaluate_profit_capture(
        symbol, side, position, current_price,
        snap, df_15m, market_type
    )

    if result_a['action'] in ('close', 'flip'):
        log_info('PROFIT_FX', f'💰 PROFIT CAPTURE [{symbol}]: {result_a["reason"]}')
        
        await _execute_paper_close(
            position, current_price,
            f'profit_capture_fx_{"_".join(result_a["triggered_by"])}',
            sb
        )

        if result_a['action'] == 'flip' and result_a.get('flip_direction'):
            flip_dir = result_a['flip_direction']
            log_info('PROFIT_FX', f'🔄 FLIP [{symbol}]: {side} → {flip_dir.upper()}')
            
            signal_flip = {
                'direction': flip_dir,
                'rule_code': 'profit_flip_fx',
                'score': 1.0
            }
            await open_forex_position(
                symbol=symbol, signal=signal_flip,
                price=current_price, provider=provider, sb=sb
            )

        await send_telegram_message(
            f'{"🔄 FLIP" if result_a["action"]=="flip" else "💰 PROFIT CAPTURE"} [{symbol}]\n'
            f'{result_a["conditions_met"]}/3 condiciones\n'
            f'Señales: {", ".join(result_a["triggered_by"])}\n'
            f'PnL: +{result_a["pnl_pct"]:.2f}%'
        )
        return True

    # ── Actualizar cruce de BASIS ─────────────
    basis_check = check_basis_crossed(position, current_price, snap, df_15m)
    if basis_check['crossed'] and not position.get('basis_crossed'):
        from app.strategy.virtual_sl_recovery import get_db_key_and_record_id
        db_key_name, db_record_id = get_db_key_and_record_id(position, 'forex_positions')
        try:
            sb.table('forex_positions').update({
                'basis_crossed': True,
                'basis_crossed_at': datetime.now(timezone.utc).isoformat(),
            }).eq(db_key_name, db_record_id).execute()
        except Exception as e:
            log_error('PROFIT_FX', f"Error updating basis_crossed: {e}")
            
        position['basis_crossed'] = True
        log_info('PROFIT_FX', f'📊 BASIS CRUZADO [{symbol}]: {basis_check["reason"]}')

    # ── MÓDULO B: Profit Ladder ────────────────
    result_b = evaluate_profit_ladder(
        symbol, side, position, current_price,
        snap, df_15m, market_type
    )

    if result_b['action'] == 'close':
        log_info('PROFIT_FX', f'📉 PROFIT LADDER CLOSE [{symbol}]: {result_b["reason"]}')
        await _execute_paper_close(
            position, current_price,
            f'profit_ladder_fx_{result_b.get("triggered_by", "ema")}',
            sb
        )
        await send_telegram_message(
            f'📉 PROFIT LADDER [{symbol}]\n'
            f'{result_b["reason"]}\n'
            f'Banda: {result_b.get("current_band")}'
        )
        return True

    elif result_b['action'] == 'partial_close_50':
        log_info('PROFIT_FX', f'📉 PROFIT LADDER PARTIAL CLOSE 50% [{symbol}]: {result_b["reason"]}')
        await _execute_paper_partial_close(
            position, current_price, sb
        )
        await send_telegram_message(
            f'📉 PROFIT LADDER 50% [{symbol}]\n'
            f'{result_b["reason"]}\n'
            f'Banda: {result_b.get("current_band")}'
        )
        return True

    elif result_b['action'] == 'update_floor':
        from app.strategy.virtual_sl_recovery import get_db_key_and_record_id
        db_key_name, db_record_id = get_db_key_and_record_id(position, 'forex_positions')
        try:
            sb.table('forex_positions').update({
                'profit_floor_band': result_b['new_floor_band'],
                'profit_floor_price': result_b['new_floor_price'],
                'highest_band_reached': result_b['current_band'],
            }).eq(db_key_name, db_record_id).execute()
        except Exception as e:
            log_error('PROFIT_FX', f"Error updating profit floor: {e}")
            
        log_info('PROFIT_FX', f'⬆️ FLOOR ACTUALIZADO [{symbol}]: {result_b["reason"]}')
        position['profit_floor_band'] = result_b['new_floor_band']
        position['profit_floor_price'] = result_b['new_floor_price']
        position['highest_band_reached'] = result_b['current_band']

    return False

async def _forex_process_symbol_15m(symbol: str, provider: CTraderProtobufProvider, sb):
    """Procesamiento completo 15m para un simbolo Forex."""
    global _forex_cycle_count
    t0 = time.time()

    try:
        # PHASE 1: Download OHLCV (Smart Frequency)
        cycle_count = _forex_cycle_count
        DOWNLOAD_FREQUENCY = {
            '5m':  1,
            '15m': 1,
            '30m': 2,
            '1h':  4,
            '4h':  16,
            '1d':  96,
        }

        timeframes_to_fetch = [
            tf for tf, freq in DOWNLOAD_FREQUENCY.items()
            if cycle_count % freq == 0 or get_memory_df(symbol, tf) is None
        ]

        # Descargas paralelas
        if timeframes_to_fetch:
            for tf in timeframes_to_fetch:
                limit = 300 if tf in ['5m', '15m', '30m', '1h'] else 500
                try:
                    res = await provider.get_ohlcv(symbol, tf, limit=limit)
                    if res is not None and not res.empty:
                        loop = asyncio.get_running_loop()
                        df_tf = await loop.run_in_executor(None, calculate_all_indicators, res, BOT_STATE.config_cache)
                        update_memory_df(symbol, tf, df_tf)
                        await upsert_forex_candles(symbol, tf, df_tf, sb)
                except Exception as res_err:
                    log_warning(MODULE, f"Error descargando {tf} para {symbol}: {res_err}")
                    if tf == '15m':
                        raise res_err
                # Pequeña pausa para evitar rate limit de cTrader
                await asyncio.sleep(0.4)

        # Recuperar DF 15m
        df = get_memory_df(symbol, '15m')
        if df is None or df.empty:
            log_warning(MODULE, f"No hay datos 15m para {symbol}")
            return

        last_row = df.iloc[-1]
        current_price = float(last_row['close'])

        # Guardar ATR en metadata
        if 'metadata' not in MEMORY_STORE.get(symbol, {}):
            MEMORY_STORE[symbol]['metadata'] = {}
        MEMORY_STORE[symbol]['metadata']['current_atr'] = float(last_row.get('atr', 0))

        # PHASE 2: Spike + MTF
        vol_sma = df['volume'].rolling(20).mean().iloc[-1]
        spike_result = {'detected': False, 'ratio': 0, 'direction': ''}
        try:
            spike_info = detect_spike(df, {'volume_sma_20': vol_sma, 'symbol': symbol, 'zone': 0}, BOT_STATE.config_cache, cycle_id=None)
            if spike_info:
                spike_result = {
                    'detected': True,
                    'ratio': spike_info.get('spike_ratio', 0),
                    'direction': spike_info.get('direction', ''),
                }
        except:
            pass

        # MTF score
        all_inds = {}
        for tf in ['15m', '30m', '1h', '4h', '1d']:
            m_df = get_memory_df(symbol, tf)
            if m_df is not None and not m_df.empty:
                last_tf = m_df.iloc[-1]
                all_inds[tf] = {
                    'ema_3': float(last_tf.get('ema1', 0)),
                    'ema_9': float(last_tf.get('ema2', 0)),
                    'ema_20': float(last_tf.get('ema3', 0)),
                    'ema_50': float(last_tf.get('ema4', 0)),
                    'rsi_14': float(last_tf.get('rsi', 50)),
                    'macd_histogram': float(last_tf.get('macd', 0)),
                    'close': float(last_tf.get('close', 0)),
                }

        mtf_result = calculate_mtf_score(symbol, all_inds, spike_direction=spike_result['direction'] or 'BULLISH')
        cur_mtf_score = mtf_result.get('score', 0.0)

        # PHASE 3: Regime
        regime = classify_market_risk(df)
        await update_regime_if_changed(symbol, regime, sb)

        # PHASE 4: Snapshot
        await write_forex_snapshot(symbol, df, regime, spike_result, cur_mtf_score, sb)

        # ── INTEGRACIÓN MÓDULO A Y B (Gestión de Ganancias) ──
        positions = BOT_STATE.get_positions_by_symbol(symbol)
        snap_for_profit = MARKET_SNAPSHOT_CACHE.get(symbol, {})
        for position in list(positions):
            closed = await process_forex_profit_management_15m(
                symbol=symbol,
                position=position,
                current_price=current_price,
                snap=snap_for_profit,
                df_15m=df,
                sb=sb,
                provider=provider
            )
            if closed:
                pass # Already closed

        # PHASE 5: Strategy Engine Evaluation
        engine = StrategyEngine.get_instance()
        if not engine.loaded:
            await engine.load()

        snap = MARKET_SNAPSHOT_CACHE.get(symbol, {}).copy()
        snap.update({
            'price': current_price,
            'adx': float(last_row.get('adx', 25)),
            'mtf_score': cur_mtf_score,
            'pinescript_signal': str(last_row.get('last_pinescript_signal', '') or ''),
            'regime': regime['category'],
        })
        MARKET_SNAPSHOT_CACHE[symbol] = snap

        df_4h = get_memory_df(symbol, '4h')
        df_5m = get_memory_df(symbol, '5m')
        context = engine.build_context(snap=snap, df_15m=df, df_4h=df_4h, df_5m=df_5m)

        # ── STATE MACHINE & AMBIGUITY CHECK ──
        from app.core.symbol_state import detect_market_ambiguity
        snap_for_sm = snap.copy()
        
        def _si(val):
            import pandas as pd
            return 0 if pd.isna(val) else int(float(val))
            
        snap_for_sm.update({
            'sar_trend_4h': _si(last_row.get('sar_trend_4h')), 
            'sar_trend_15m': _si(last_row.get('sar_trend_15m')), 
            'fibonacci_zone': _si(last_row.get('fibonacci_zone'))
        })
        
        ambiguity = detect_market_ambiguity(snap_for_sm)
        
        if ambiguity['is_ambiguous']:
            log_info('AMBIGUOUS_FX', f"{symbol}: {ambiguity['reason']}")
            sm.set_ambiguous(symbol, ambiguity['reason'])
        else:
            signal = None
            dca_smart_used = False
            
            existing_positions = BOT_STATE.get_positions_by_symbol(symbol)
            if existing_positions:
                from app.strategy.smart_dca_5m import evaluate_smart_dca

                
                snap_15m = snap
                df_5m = get_memory_df(symbol, "5m")
                snap_5m = df_5m.iloc[-1].to_dict() if df_5m is not None and not df_5m.empty else {}
                
                is_long = existing_positions[0].get('side', '').lower() in ['long', 'buy']
                last_pos = sorted(existing_positions, key=lambda x: x.get('opened_at', ''), reverse=True)[0]
                last_entry = float(last_pos.get('entry_price') or last_pos.get('avg_entry_price') or current_price)
                
                price_improvement_pct = 0.002
                can_dca = False
                max_per_pair = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 4))
                
                if len(existing_positions) < max_per_pair:
                    if is_long and current_price <= last_entry * (1 - price_improvement_pct):
                        can_dca = True
                    elif not is_long and current_price >= last_entry * (1 + price_improvement_pct):
                        can_dca = True
                        
                if can_dca and snap_5m:
                    dca_res = evaluate_smart_dca(snap_15m, snap_5m, is_long)
                    if dca_res.get('should_dca'):
                        signal = {
                            'rule_code': dca_res['rule_code'],
                            'direction': 'long' if is_long else 'short',
                            'strategy_type': 'scalping',
                            'cycle': '5m',
                            'reason': dca_res['reason']
                        }
                        dca_smart_used = True

            if not dca_smart_used:
                normal_signal = engine.get_best_signal(context=context, strategy_type='scalping', cycle='15m')
                
                # --- FASE 5.5: V1 Engine Fallback (Crypto Logic para Aa23, Bb23, etc) ---
                if not normal_signal:
                    from app.strategy.rule_engine import evaluate_all_rules, get_rules_from_memory
                    from app.analysis.fibonacci_bb import extract_fib_levels
                    
                    all_v1_rules = get_rules_from_memory()
                    fib_levels = extract_fib_levels(df)
                    
                    df_5m = get_memory_df(symbol, "5m")
                    ema3_5m, ema9_5m, ema20_5m = 0, 0, 0
                    bb_upper_5m_opens, bb_lower_5m_opens = False, False
                    
                    if df_5m is not None and len(df_5m) >= 2:
                        c0 = df_5m.iloc[-1]
                        c1 = df_5m.iloc[-2]
                        ema3_5m = c0.get('ema1', c0.get('ema_3', 0))
                        ema9_5m = c0.get('ema2', c0.get('ema_9', 0))
                        ema20_5m = c0.get('ema3', c0.get('ema_20', 0))
                        
                        u0 = float(c0.get('upper_2', 0))
                        u1 = float(c1.get('upper_2', 0))
                        if u0 > 0 and u1 > 0: bb_upper_5m_opens = (u0 > u1)
                        
                        l0 = float(c0.get('lower_2', 0))
                        l1 = float(c1.get('lower_2', 0))
                        if l0 > 0 and l1 > 0: bb_lower_5m_opens = (l0 < l1)
                    
                    df.loc[df.index[-1], 'ema3_5m'] = ema3_5m
                    df.loc[df.index[-1], 'ema9_5m'] = ema9_5m
                    df.loc[df.index[-1], 'ema20_5m'] = ema20_5m
                    df.loc[df.index[-1], 'bb_upper_5m_opens'] = bb_upper_5m_opens
                    df.loc[df.index[-1], 'bb_lower_5m_opens'] = bb_lower_5m_opens
                    
                    v1_long = evaluate_all_rules(df, fib_levels, regime, pinescript_signal=str(last_row.get('last_pinescript_signal', '') or ''), cfg=BOT_STATE.config_cache, direction='long', rules=all_v1_rules, source_tf='15m', market_type='forex_futures')
                    v1_short = evaluate_all_rules(df, fib_levels, regime, pinescript_signal=str(last_row.get('last_pinescript_signal', '') or ''), cfg=BOT_STATE.config_cache, direction='short', rules=all_v1_rules, source_tf='15m', market_type='forex_futures')
                    
                    if v1_long:
                        rc_str = v1_long.get("rule", {}).get("rule_code", str(v1_long)) if isinstance(v1_long, dict) else str(v1_long)
                        normal_signal = {'rule_code': rc_str, 'direction': 'long', 'strategy_type': 'scalping', 'cycle': '15m'}
                    elif v1_short:
                        rc_str = v1_short.get("rule", {}).get("rule_code", str(v1_short)) if isinstance(v1_short, dict) else str(v1_short)
                        normal_signal = {'rule_code': rc_str, 'direction': 'short', 'strategy_type': 'scalping', 'cycle': '15m'}

                if normal_signal:
                    if not existing_positions:
                        signal = normal_signal
                    else:
                        is_long = existing_positions[0].get('side', '').lower() in ['long', 'buy']
                        is_signal_long = normal_signal['direction'] == 'long'
                        if is_long != is_signal_long:
                            signal = normal_signal # FLIP allowed


            if signal:
                await engine.log_evaluation(symbol, signal, context)

                max_global = int(BOT_STATE.config_cache.get('max_open_trades', 16))
                current_open = len(BOT_STATE.positions)
                max_per_pair = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 4))

                if current_open >= max_global:
                    log_info('POSITION_LIMIT_FX', f'{symbol}: Limite GLOBAL {max_global} alcanzado')
                else:
                    sm_check = sm.can_open(symbol, signal['direction'], current_price, max_per_pair)
                    
                    if not sm_check['allowed']:
                        log_info('STATE_MACHINE_FX', f"{symbol}: Bloqueado - {sm_check['reason']}")
                    else:
                        if sm_check.get('is_flip'):
                            log_info('FLIP_FX', f"{symbol}: FLIP {signal['direction']} - Evaluando posiciones opuestas")
                            existing_positions = BOT_STATE.get_positions_by_symbol(symbol)
                            for p in existing_positions:
                                if p.get('side', '').lower() != signal['direction'].lower():
                                    entry = float(p.get('avg_entry_price') or p.get('entry_price') or current_price)
                                    pnl_pct = 0.0
                                    if entry > 0:
                                        if p.get('side', '').lower() in ('long', 'buy'):
                                            pnl_pct = (current_price - entry) / entry * 100
                                        else:
                                            pnl_pct = (entry - current_price) / entry * 100
                                            
                                    if pnl_pct <= 0:
                                        log_info('FLIP_FX', f"[{symbol}] Flip omitido para esta posición: PNL {pnl_pct:.2f}% <= 0%. Se mantiene como Hedge.")
                                        continue

                                    try:
                                        from app.core.position_monitor import _execute_paper_close
                                        await _execute_paper_close(p, current_price, f"flip_{signal['direction']}_fx", sb)
                                        sm.on_position_closed(symbol, f"flip_{signal['direction']}_fx", all_closed=True)
                                    except Exception as e:
                                        log_error(MODULE, f"Error en flip close para {symbol}: {e}")
                                        
                        # ── RE-CHECK LIMIT POST-FLIP ──
                        current_pair_count = len([p for p in BOT_STATE.positions.values() if p['symbol'] == symbol and p.get('status') == 'open'])
                        if current_pair_count >= max_per_pair:
                            log_info('POSITION_LIMIT_FX', f"[{symbol}] Flip abortado u open excedido: {current_pair_count}/{max_per_pair} alcanzado.")
                        else:
                            # ── MEJORA C: Filtro Correlación USD ──
                            all_forex_pos = [p for p in BOT_STATE.positions.values() if p.get('market_type') == 'forex']
                            usd_check = check_usd_exposure_filter(symbol, signal['direction'], all_forex_pos)
                            if not usd_check['passed']:
                                log_info('USD_CORR_FX', f"{symbol}: {usd_check['reason']}")
                            else:
                                # Proceder a abrir
                                await open_forex_position(
                                    symbol=symbol,
                                    signal=signal,
                                    price=current_price,
                                    provider=provider,
                                    sb=sb,
                                )
            else:
                # Log near-misses
                all_results = (
                    engine.evaluate_all(context, 'long', 'scalping', '15m') +
                    engine.evaluate_all(context, 'short', 'scalping', '15m')
                )
                for r in all_results:
                    if r['score'] >= 0.40:
                        await engine.log_evaluation(symbol, r, context)

        # --- ESTRATEGIA CUSTOM APEX_EMA (SwingEma) para Forex ---
        try:
            from app.strategy.swing_orders import process_swing_ema_strategy
            await process_swing_ema_strategy(
                symbol=symbol,
                df_15m=df,
                snap=snap,
                sb=sb
            )
        except Exception as swing_ema_err:
            log_error(MODULE, f"{symbol}/15m swing ema error: {swing_ema_err}")

        # PHASE 6: Swing Orders (4h cycle = cada 16 ciclos)
        if _forex_cycle_count % 16 == 0:
            try:
                from app.strategy.swing_orders import process_swing_orders
                df_4h_safe = get_memory_df(symbol, '4h')
                if df_4h_safe is not None and not df_4h_safe.empty:
                    await process_swing_orders(
                        symbol=symbol,
                        timeframe='4h',
                        df=df_4h_safe,
                        snap=snap,
                        sb=sb,
                    )

                    # Scalping 4h (Aa31/Bb31)
                    existing_positions_4h = BOT_STATE.get_positions_by_symbol(symbol)
                    max_per_pair = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 4))
                    
                    if len(existing_positions_4h) < max_per_pair:
                        context_4h = engine.build_context(snap=snap, df_15m=df, df_4h=df_4h_safe)
                        signal_4h = engine.get_best_signal(context=context_4h, strategy_type='scalping', cycle='4h')
                        if signal_4h:
                            # ── PRICE IMPROVEMENT CHECK (DCA) ──
                            can_open = True
                            if existing_positions_4h:
                                last_pos = sorted(existing_positions_4h, key=lambda x: x.get('opened_at', ''), reverse=True)[0]
                                last_entry = float(last_pos.get('entry_price') or last_pos.get('avg_entry_price') or 0)
                                direction = signal_4h['direction']
                                
                                if direction == "long" and current_price >= last_entry:
                                    log_info('DCA_BLOCK_FX_4H', f'{symbol}: No mejora precio LONG ({current_price} >= {last_entry})')
                                    can_open = False
                                elif direction == "short" and current_price <= last_entry:
                                    log_info('DCA_BLOCK_FX_4H', f'{symbol}: No mejora precio SHORT ({current_price} <= {last_entry})')
                                    can_open = False
                            
                            if can_open:
                                # ── MEJORA C: Filtro Correlación USD (4h) ──
                                all_forex_pos_4h = [p for p in BOT_STATE.positions.values() if p.get('market_type') == 'forex']
                                usd_check_4h = check_usd_exposure_filter(symbol, signal_4h['direction'], all_forex_pos_4h)
                                if not usd_check_4h['passed']:
                                    log_info('USD_CORR_FX_4H', f"{symbol}: {usd_check_4h['reason']}")
                                else:
                                    await open_forex_position(
                                        symbol=symbol,
                                        signal=signal_4h,
                                        price=current_price,
                                        provider=provider,
                                        sb=sb,
                                    )
            except Exception as swing_e:
                log_error(MODULE, f'{symbol}/4h swing error: {swing_e}')

        elapsed = time.time() - t0
        log_info(MODULE, f'{symbol}/15m: ciclo completado ({elapsed:.1f}s)')

    except Exception as e:
        import traceback
        log_error(MODULE, f"Error {symbol}/15m: {e}\n{traceback.format_exc()}")


async def forex_cycle_15m():
    """Ciclo 15m Forex: Analisis completo + senales."""
    from app.core.safety_manager import is_system_paused, check_db_circuit_breaker
    if check_db_circuit_breaker():
        return
    if is_system_paused():
        log_info("FOREX_SCHEDULER", "Sistema pausado globalmente. Omitiendo ciclo 15m.")
        return

    from app.core.market_hours import is_forex_market_open
    if not is_forex_market_open():
        log_info("FOREX_SCHEDULER", "Mercado Forex cerrado. Omitiendo ciclo 15m.")
        return

    global _forex_provider, _forex_cycle_count
    _forex_cycle_count += 1

    log_info(MODULE, f"--- Forex 15m Cycle #{_forex_cycle_count} ---")

    sb = get_supabase()
    symbols = FOREX_SYMBOLS

    provider = _forex_provider
    if not provider or not provider._connected:
        log_warning(MODULE, "Provider Forex desconectado. Intentando reconectar en segundo plano y omitiendo ciclo 15m.")
        asyncio.create_task(get_forex_provider())
        return

    try:
        # Sync config
        try:
            res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
            if res.data:
                BOT_STATE.config_cache.update(res.data)
        except:
            pass

        # Sync positions to memory to enforce state limits
        try:
            from app.workers.scheduler import sync_positions_to_memory
            await sync_positions_to_memory()
        except Exception as e:
            log_error(MODULE, f"Error syncing positions in forex 15m: {e}")

        # Procesar todos los simbolos en paralelo
        tasks = [_forex_process_symbol_15m(s, provider, sb) for s in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Performance alerts
        try:
            await check_performance_alerts()
        except Exception as e:
            log_error(MODULE, f"Performance alerts error: {e}")

    except Exception as e:
        log_error(MODULE, f"Error global forex 15m: {e}")


# ══════════════════════════════════════════════════
#  INIT & MAIN
# ══════════════════════════════════════════════════

async def get_forex_provider():
    """
    Singleton del provider Forex.
    La conexión TCP se mantiene abierta.
    """
    global _forex_provider
    if _forex_provider is None or \
       not _forex_provider._authenticated:
        _forex_provider = create_provider(
            'forex_futures'
        )
        connected = await _forex_provider.connect()
        if not connected:
            raise Exception(
                'No se pudo conectar a cTrader'
            )
        # Subscribir a precios en tiempo real
        await _forex_provider.subscribe_prices(
            symbols  = FOREX_SYMBOLS,
            callback = _handle_forex_price
        )
        log_info('FOREX',
            f'Provider Protobuf inicializado: '
            f'{FOREX_SYMBOLS}'
        )
    return _forex_provider


def _handle_forex_price(symbol, mid, bid, ask):
    """
    Callback de precio en tiempo real.
    Actualiza MEMORY_STORE con el precio actual.
    Equivalente al WebSocket de Binance.
    """
    if symbol not in MEMORY_STORE:
        MEMORY_STORE[symbol] = {}
    MEMORY_STORE[symbol]['current_price'] = mid
    MEMORY_STORE[symbol]['bid']           = bid
    MEMORY_STORE[symbol]['ask']           = ask
    MEMORY_STORE[symbol]['last_tick']     = \
        datetime.now(timezone.utc)


async def init_forex_worker(supabase) -> Optional[CTraderProtobufProvider]:
    """
    Inicializar el worker de Forex con
    provider Protobuf.
    """
    try:
        provider = await get_forex_provider()
    except Exception as e:
        log_error(MODULE, f"Error inicializando provider Protobuf: {e}")
        return None

    log_info('FOREX_SCHEDULER',
        'Precalentando velas históricas...'
    )

    # Descargar historial para todos los símbolos
    for symbol in FOREX_SYMBOLS:
        MEMORY_STORE[symbol] = \
            MEMORY_STORE.get(symbol, {})

        for tf in ['5m','15m','30m','1h','4h','1d']:
            try:
                df = await provider.get_ohlcv(
                    symbol, tf, limit=300
                )
                if df is not None and \
                   not df.empty:
                    loop = asyncio.get_running_loop()
                    df = await loop.run_in_executor(None, calculate_all_indicators, df, BOT_STATE.config_cache)
                    df = calculate_parabolic_sar(df)

                    MEMORY_STORE[symbol][tf] = {
                        'df': df
                    }
                    log_info('FOREX',
                        f'{symbol}/{tf}: '
                        f'{len(df)} velas OK'
                    )
            except Exception as e:
                log_error('FOREX',
                    f'{symbol}/{tf}: {e}'
                )

    log_info('FOREX_SCHEDULER',
        '✅ Forex Protobuf Worker listo'
    )
    
    # Cargar Strategy Engine
    engine = StrategyEngine.get_instance(supabase)
    if not engine.loaded:
        await engine.load()
    log_info(MODULE, "Strategy Engine v1.0 cargado para Forex")

    return provider


async def main():
    """
    Entry point del Forex Scheduler.
    Ejecuta ciclos de 5m y 15m via APScheduler.
    """
    log_info(MODULE, "=== FOREX SCHEDULER STARTING ===")

    sb = get_supabase()
    provider = await init_forex_worker(sb)

    if not provider:
        log_error(MODULE, "ABORT: No se pudo inicializar el worker Forex.")
        return

    # Scheduler
    scheduler = AsyncIOScheduler()

    # 5m cycle: offset 20s para no colisionar con Crypto (que usa 10s)
    scheduler.add_job(
        forex_cycle_5m,
        CronTrigger(minute='*/5', second='20'),
        id='forex_5m',
        replace_existing=True,
    )

    # 15m cycle: offset 45s (Crypto usa 30s)
    scheduler.add_job(
        forex_cycle_15m,
        CronTrigger(minute='*/15', second='45'),
        id='forex_15m',
        replace_existing=True,
    )

    log_info(MODULE, "Scheduler Forex configurado. Ejecutando ciclo inicial...")

    # Correr ciclos iniciales
    asyncio.create_task(forex_cycle_15m())
    asyncio.create_task(forex_cycle_5m())

    scheduler.start()

    # Keep alive
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        log_info(MODULE, "Forex scheduler detenido.")
    finally:
        if _forex_provider:
            await _forex_provider.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log_info(MODULE, "Forex scheduler detenido manualmente.")
