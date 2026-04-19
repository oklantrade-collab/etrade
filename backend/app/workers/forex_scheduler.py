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
            df = calculate_all_indicators(df, BOT_STATE.config_cache)
            update_memory_df(symbol, tf, df)
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
            sar_trend = int(last_4h['sar_trend'])
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
            sar_trend_15m = int(last_15m.get('sar_trend', 0))
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

        upsert_data = {
            'symbol':            symbol,
            'price':             float(last['close']),
            'fibonacci_zone':    int(fib_levels.get('zone', 0)),
            'basis':             float(fib_levels.get('basis', 0)),
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
            'pinescript_signal_age': int(last_15m.get('signal_age', 0)) if last_15m is not None else 0,
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
            'updated_at':            datetime.now(timezone.utc).isoformat(),
        }

        if sar_changed:
            upsert_data['sar_phase_changed_at'] = changed_at_iso

        sb.table('market_snapshot').upsert(upsert_data).execute()
        log_info('SNAPSHOT_FX', f'Snapshot OK: {symbol} mtf={mtf_score:.4f}')

    except Exception as e:
        log_error('SNAPSHOT_FX', f'FALLO snapshot {symbol}: {e}')


# ══════════════════════════════════════════════════
#  CANDLE UPSERT (Forex)
# ══════════════════════════════════════════════════

async def upsert_forex_candles(symbol: str, timeframe: str, df: pd.DataFrame, sb):
    """Sindronizar velas Forex con market_candles."""
    if df is None or df.empty:
        return
    try:
        rows = []
        sub_df = df.tail(300)

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
                'volume':    float(r.get('volume', 0)),
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

def calculate_forex_lot_size(
    symbol: str,
    capital_usd: float,
    risk_pct: float,
    sl_pips: float,
    leverage: int = 100,
) -> dict:
    """
    Calcula tamano de lote Forex basado en riesgo.
    formula: lots = risk_usd / (sl_pips * pip_value)
    """
    pip_size = PIP_SIZES.get(symbol, 0.0001)
    risk_usd = capital_usd * (risk_pct / 100.0)

    # Pip value para 1 lote estandar (100,000 unidades)
    pip_value = pip_size * 100_000

    if sl_pips > 0 and pip_value > 0:
        lots = risk_usd / (sl_pips * pip_value)
    else:
        lots = LOT_CONFIG['micro_lot']

    # Redondear al step mas cercano
    step = LOT_CONFIG['lot_step']
    lots = max(LOT_CONFIG['min_lot'], round(lots / step) * step)

    return {
        'lotes': round(lots, 2),
        'risk_usd': round(risk_usd, 2),
        'pip_value': pip_value,
        'pip_size': pip_size,
    }


def calculate_forex_sl_tp(
    symbol: str,
    direction: str,
    entry_price: float,
    sl_pips: float = 30,
    tp_pips: float = 60,
) -> dict:
    """
    Calcula SL/TP en precio a partir de pips.
    """
    pip_size = PIP_SIZES.get(symbol, 0.0001)

    if direction == 'long':
        sl_price = entry_price - (sl_pips * pip_size)
        tp_price = entry_price + (tp_pips * pip_size)
    else:
        sl_price = entry_price + (sl_pips * pip_size)
        tp_price = entry_price - (tp_pips * pip_size)

    return {
        'sl_price': round(sl_price, 5),
        'tp_price': round(tp_price, 5),
        'sl_pips': sl_pips,
        'tp_pips': tp_pips,
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
    rule_code = signal['rule_code']

    # Leer config de trading
    try:
        cfg_res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
        cfg = cfg_res.data or {}
    except:
        cfg = {}

    capital = float(cfg.get('capital_total', 1000))
    risk_pct = FOREX_RISK_CONFIG['max_risk_per_trade'] * 100  # 1%
    sl_pips = FOREX_RISK_CONFIG['sl_pips_default']
    tp_pips = sl_pips * FOREX_RISK_CONFIG['tp_rr_ratio']

    # Calcular lot size
    sizing = calculate_forex_lot_size(
        symbol=symbol,
        capital_usd=capital,
        risk_pct=risk_pct,
        sl_pips=sl_pips,
    )

    # Calcular SL/TP
    levels = calculate_forex_sl_tp(
        symbol=symbol,
        direction=direction,
        entry_price=price,
        sl_pips=sl_pips,
        tp_pips=tp_pips,
    )

    # Paper trading check
    is_paper = cfg.get('paper_trading', True) is not False

    if is_paper:
        # Paper trading: simular orden
        order = {
            'order_id': f'PAPER-FX-{int(time.time())}',
            'symbol': symbol,
            'side': direction,
            'quantity': sizing['lotes'],
            'price': price,
            'status': 'filled',
        }
        log_info(MODULE, f"[PAPER] Orden Forex: {direction.upper()} {sizing['lotes']} lotes {symbol} @ {price:.5f}")
    else:
        # Live trading: enviar a cTrader
        order = await provider.place_order(
            symbol=symbol,
            side='buy' if direction == 'long' else 'sell',
            order_type='market',
            quantity=sizing['lotes'],
            sl_price=levels['sl_price'],
            tp_price=levels['tp_price'],
        )

    if 'error' in order:
        log_error(MODULE, f"Error abriendo posicion: {order['error']}")
        return

    # Registrar en Supabase
    try:
        sb.table('positions').insert({
            'symbol':           symbol,
            'side':             direction,
            'avg_entry_price':  price,
            'size':             sizing['lotes'],
            'sl_price':         levels['sl_price'],
            'tp_partial_price': levels['tp_price'],
            'rule_code':        rule_code,
            'status':           'open',
            'mode':             'paper' if is_paper else 'live',
            'market_type':      'forex_futures',
            'external_id':      order.get('order_id'),
            'opened_at':        datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log_error(MODULE, f"Error registrando posicion en DB: {e}")

    # Registrar en BOT_STATE
    BOT_STATE.positions[symbol] = {
        'symbol': symbol,
        'side': direction,
        'avg_entry_price': price,
        'size': sizing['lotes'],
        'sl_price': levels['sl_price'],
        'tp_partial_price': levels['tp_price'],
        'rule_code': rule_code,
        'status': 'open',
        'market_type': 'forex_futures',
    }

    # Telegram
    side_emoji = 'LONG' if direction == 'long' else 'SHORT'
    await send_telegram_message(
        f"FOREX {side_emoji} [{symbol}]\n"
        f"Regla: {rule_code} | Score: {signal.get('score', 0):.2f}\n"
        f"Entrada: {price:.5f}\n"
        f"SL: {levels['sl_price']:.5f} (-{sl_pips} pips)\n"
        f"TP: {levels['tp_price']:.5f} (+{tp_pips:.0f} pips)\n"
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

        # 4. Smart Exit: SAR Phase Change
        snap = MARKET_SNAPSHOT_CACHE.get(symbol, {})
        sar_data = MEMORY_STORE.get(symbol, {}).get('sar', {})
        sar_phase = sar_data.get('phase', 'neutral')
        sar_changed_at = sar_data.get('changed_at')

        position = BOT_STATE.positions.get(symbol)
        if position and sar_changed_at:
            side = (position.get('side') or '').lower()
            if (sar_phase == 'short' and side == 'long') or \
               (sar_phase == 'long' and side == 'short'):

                await _execute_paper_close(position, current_price, 'sar_phase_change_fx', sb)
                entry = float(position.get('avg_entry_price', 0))
                if entry > 0:
                    if side == 'long':
                        pnl_pips = (current_price - entry) / PIP_SIZES.get(symbol, 0.0001)
                    else:
                        pnl_pips = (entry - current_price) / PIP_SIZES.get(symbol, 0.0001)
                else:
                    pnl_pips = 0

                await send_telegram_message(
                    f"FOREX SAR REVERSAL [{symbol}]\n"
                    f"SAR 4h -> {sar_phase.upper()}\n"
                    f"Cerrando {side.upper()}: {pnl_pips:+.1f} pips\n"
                    f"Precio: {current_price:.5f}"
                )
                return

        # 5. Smart Exit: Signal Reversal
        if position:
            current_mtf = float(snap.get('mtf_score', 0))
            trading_config = BOT_STATE.config_cache

            reversal = await check_signal_reversal(
                position=position,
                current_mtf=current_mtf,
                current_price=current_price,
                config=trading_config,
            )

            if reversal.get('should_exit'):
                await _execute_paper_close(position, current_price, 'signal_reversal_fx', sb)
                await send_telegram_message(
                    f"FOREX SALIDA INTELIGENTE [{symbol}]\n"
                    f"MTF giro: {current_mtf:.4f}\n"
                    f"PnL: {reversal.get('pnl_pct', 0):+.2f}%"
                )

        # 6. SL/TP check (manual for Forex since paper mode)
        if position:
            sl = float(position.get('sl_price', 0))
            tp = float(position.get('tp_partial_price', 0))
            side = (position.get('side') or '').lower()

            if sl > 0:
                if (side == 'long' and current_price <= sl) or \
                   (side == 'short' and current_price >= sl):
                    await _execute_paper_close(position, current_price, 'sl_hit_fx', sb)
                    await send_telegram_message(
                        f"FOREX SL HIT [{symbol}]\n"
                        f"Precio: {current_price:.5f}\n"
                        f"SL: {sl:.5f}"
                    )
                    return

            if tp > 0:
                if (side == 'long' and current_price >= tp) or \
                   (side == 'short' and current_price <= tp):
                    await _execute_paper_close(position, current_price, 'tp_hit_fx', sb)
                    await send_telegram_message(
                        f"FOREX TP HIT [{symbol}]\n"
                        f"Precio: {current_price:.5f}\n"
                        f"TP: {tp:.5f}"
                    )
                    return

        # 7. Heartbeat
        try:
            sb.table('bot_state').upsert({
                'symbol': symbol,
                'last_5m_cycle_at': datetime.now(timezone.utc).isoformat(),
                'last_updated': datetime.now(timezone.utc).isoformat(),
            }, on_conflict='symbol').execute()
        except:
            pass

    except Exception as e:
        log_error(MODULE, f"5m cycle error {symbol}: {e}")


async def forex_cycle_5m():
    """Ciclo 5m Forex: Gestion de posiciones y smart exits."""
    global _forex_provider
    log_debug(MODULE, "--- Forex 5m Cycle ---")

    sb = get_supabase()
    symbols = FOREX_SYMBOLS

    provider = _forex_provider
    if not provider or not provider._connected:
        log_warning(MODULE, "Provider Forex desconectado. Omitiendo ciclo 5m.")
        return

    try:
        tasks = [_forex_process_symbol_5m(s, provider, sb) for s in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        log_error(MODULE, f"Error global forex 5m: {e}")


# ══════════════════════════════════════════════════
#  CYCLE 15m — Full Analysis (Forex)
# ══════════════════════════════════════════════════

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
        fetch_tasks = {}
        for tf in timeframes_to_fetch:
            limit = 300 if tf in ['5m', '15m', '30m', '1h'] else 500
            fetch_tasks[tf] = provider.get_ohlcv(symbol, tf, limit=limit)

        if fetch_tasks:
            results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)
            for tf, res in zip(fetch_tasks.keys(), results):
                if isinstance(res, Exception):
                    log_warning(MODULE, f"Error descargando {tf} para {symbol}: {res}")
                    if tf == '15m':
                        raise res
                elif res is not None and not res.empty:
                    df_tf = calculate_all_indicators(res, BOT_STATE.config_cache)
                    update_memory_df(symbol, tf, df_tf)
                    await upsert_forex_candles(symbol, tf, df_tf, sb)

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

        # Solo evaluar si no hay posicion abierta
        if symbol not in BOT_STATE.positions:
            signal = engine.get_best_signal(context=context, strategy_type='scalping', cycle='15m')

            if signal:
                await engine.log_evaluation(symbol, signal, context)

                # Verificar limites de posicion
                max_global = int(BOT_STATE.config_cache.get('max_open_trades', 3))
                current_open = len([s for s in BOT_STATE.positions if BOT_STATE.positions[s].get('status') == 'open'])
                max_per_pair = FOREX_RISK_CONFIG['max_positions_per_pair']
                has_open = symbol in BOT_STATE.positions

                if current_open >= max_global:
                    log_info('POSITION_LIMIT_FX', f'{symbol}: Limite GLOBAL {max_global} alcanzado')
                elif has_open:
                    log_info('POSITION_LIMIT_FX', f'{symbol}: Ya tiene posicion abierta')
                else:
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
                    if symbol not in BOT_STATE.positions:
                        context_4h = engine.build_context(snap=snap, df_15m=df, df_4h=df_4h_safe)
                        signal_4h = engine.get_best_signal(context=context_4h, strategy_type='scalping', cycle='4h')
                        if signal_4h:
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
    global _forex_provider, _forex_cycle_count
    _forex_cycle_count += 1

    log_info(MODULE, f"--- Forex 15m Cycle #{_forex_cycle_count} ---")

    sb = get_supabase()
    symbols = FOREX_SYMBOLS

    provider = _forex_provider
    if not provider or not provider._connected:
        log_warning(MODULE, "Provider Forex desconectado. Omitiendo ciclo 15m.")
        return

    try:
        # Sync config
        try:
            res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
            if res.data:
                BOT_STATE.config_cache.update(res.data)
        except:
            pass

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

        for tf in ['5m','15m','1h','4h','1d']:
            try:
                df = await provider.get_ohlcv(
                    symbol, tf, limit=300
                )
                if df is not None and \
                   not df.empty:
                    df = fibonacci_bollinger(df)
                    df = calculate_all_indicators(df, BOT_STATE.config_cache)
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
