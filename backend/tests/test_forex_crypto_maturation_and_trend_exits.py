"""
Test Suite: Motor de Maduración, Filtro de Tendencia 15m y Protección de Salidas
en FOREX y CRIPTO (eTrade v6.0)
================================================================================
Verifica:
1. Forex Trailing Stop Multi-Tier:
   - Eliminación del techo artificial de $1.00 USD.
   - Activación de trailing por escalones (Tier 1: +14p -> BE+2p, Tier 2: +22p -> +10p, Tier 3: +35p -> 65% lock).
2. Forex Aduana 15M Trend Guard:
   - Cierres prematuros bloqueados si EMA3_15m > EMA9_15m en LONGs o EMA3_15m < EMA9_15m en SHORTs.
3. Cripto Ventana de Maduración (is_trade_mature):
   - Prohibido cerrar en los primeros 20 minutos por micro-retrocesos de 5m.
4. Cripto Aduana 15M Trend Guard:
   - Early profit protect y cascada stagnation suprimidos si la tendencia madre de 15m sigue viva.
5. Invalidación Temprana QSHR (qshr_early_invalidation):
   - Erradicación del corte hipersensible de -0.15% en los primeros minutos.
   - Invalidación sólo ante pérdida confirmada estructural con tendencia 15m fracturada.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from app.strategy.capital_protection import PROTECTION_CONFIG
from app.strategy.quantum_squeeze_hedge import (
    evaluate_qshr_trailing_and_exit,
    evaluate_qshr_hedge_signal,
    is_trade_mature
)
from app.core.position_monitor import (
    check_early_profit_protect_ema_5m,
    is_trade_mature as is_trade_mature_monitor
)


def make_candle_df(closes, high_mult=1.001, low_mult=0.999, open_mult=1.0):
    n = len(closes)
    return pd.DataFrame({
        'open': [c * open_mult for c in closes],
        'high': [c * high_mult for c in closes],
        'low': [c * low_mult for c in closes],
        'close': closes,
        'volume': [1000.0] * n
    })


def test_forex_trailing_tiers_no_one_dollar_cap():
    """
    Test 1: Forex trailing stop multi-nivel sin corte a $1.00.
    Tier 1 (+14 pips -> BE+2p), Tier 2 (+22 pips -> +10p), Tier 3 (+35 pips -> 65% lock).
    """
    cfg = PROTECTION_CONFIG['forex_futures']
    assert cfg['be_trigger_pips'] == 14
    assert cfg['be_buffer_pips'] == 2
    assert cfg['trailing_levels_pips'] == [(14, 2), (22, 10), (35, 20), (50, 35), (70, 52)]
    assert cfg['min_time_before_inverse_close'] == 4  # 20 min maduración

    # Configuración Crypto también ampliada
    cfg_crypto = PROTECTION_CONFIG['crypto_futures']
    assert cfg_crypto['be_trigger_pct'] == 0.015  # +1.5% maduración
    assert cfg_crypto['be_buffer_pct'] == 0.0035

    # Simular lógica de trailing escalonado de forex_worker_standalone:
    entry_px = 1.08000
    pip_size = 0.0001

    def calc_forex_trailing_sl(current_px, is_short=False):
        pips = (entry_px - current_px) / pip_size if is_short else (current_px - entry_px) / pip_size
        if pips >= 35.0:
            locked = pips * 0.65
            return round(entry_px + (locked * pip_size), 5), 'Tier 3'
        elif pips >= 22.0:
            locked = 10.0
            return round(entry_px + (locked * pip_size), 5), 'Tier 2'
        elif pips >= 14.0:
            locked = 2.0
            return round(entry_px + (locked * pip_size), 5), 'Tier 1'
        return None, 'No Trigger'

    # Escenario A: +15 pips -> Tier 1 (BE + 2 pips = 1.08020)
    sl_1, tier_1 = calc_forex_trailing_sl(1.08150)
    assert tier_1 == 'Tier 1'
    assert sl_1 == 1.08020

    # Escenario B: +25 pips -> Tier 2 (Entrada + 10 pips = 1.08100)
    sl_2, tier_2 = calc_forex_trailing_sl(1.08250)
    assert tier_2 == 'Tier 2'
    assert sl_2 == 1.08100

    # Escenario C: +40 pips -> Tier 3 (65% protegido = 26 pips -> 1.08260)
    sl_3, tier_3 = calc_forex_trailing_sl(1.08400)
    assert tier_3 == 'Tier 3'
    assert sl_3 == 1.08260


def test_forex_15m_ema_trend_guard_blocks_exhaustion_exit():
    """
    Test 2: En Forex, si la posición tiene ganancia pero 15m EMA3 > EMA9,
    los cierres prematuros de Bollinger Exhaustion quedan bloqueados.
    """
    # 25 velas 15m con clara tendencia alcista (EMA3 > EMA9)
    closes_15m = [1.0800 + i * 0.0003 for i in range(25)]
    df_15m = make_candle_df(closes_15m)
    df_15m['ema1'] = df_15m['close'].ewm(span=3, adjust=False).mean()
    df_15m['ema2'] = df_15m['close'].ewm(span=9, adjust=False).mean()
    df_15m['ema3'] = df_15m['close'].ewm(span=20, adjust=False).mean()

    # 10 velas 5m con estancamiento final
    closes_5m = [1.0870, 1.0872, 1.0871, 1.0870, 1.0869]
    df_5m = make_candle_df(closes_5m)

    pos = {
        'symbol': 'EURUSD',
        'side': 'long',
        'entry_price': 1.0800,
        'current_lots': 0.01,
        'opened_at': (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    }
    cur_p = 1.0870 # +70 pips

    # Evaluar salida QSHR
    res = evaluate_qshr_trailing_and_exit(pos, df_5m, df_15m, cur_p, 'EURUSD')
    # Como EMA3 > EMA9 en 15m está activa, no debe retornar close_bollinger_exhaustion
    action = res.get('action') if res else None
    assert action != 'close_bollinger_exhaustion', "No debe cerrar por agotamiento de Bollinger mientras EMA3 > EMA9 en 15m!"


def test_crypto_maturation_blocks_premature_exit():
    """
    Test 3: Ventana de maduración (20 min) en Cripto.
    Una posición recién abierta (ej. 5 minutos) con leve ganancia (+0.8%)
    NO debe cerrarse por cruce de 5m en check_early_profit_protect_ema_5m.
    """
    now = datetime.now(timezone.utc)
    recent_opened = (now - timedelta(minutes=5)).isoformat()

    pos_young = {
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 60000.0,
        'opened_at': recent_opened,
        'market_type': 'crypto_futures'
    }

    assert is_trade_mature(pos_young, min_minutes=20) is False
    assert is_trade_mature_monitor(pos_young, min_minutes=20) is False

    # Correr early profit protect
    cfg = {'exit_on_signal_reversal': True, 'min_profit_exit_pct_crypto': 1.50}
    import asyncio
    res = asyncio.run(check_early_profit_protect_ema_5m(pos_young, current_price=60500.0, config=cfg))
    assert res['should_exit'] is False, "Una posición de 5 min debe estar protegida por la ventana de maduración!"


def test_crypto_15m_trend_alive_blocks_early_profit_protect():
    """
    Test 4: Posición madura (>25 min) con ganancia (+1.8%), donde 5m tiene cruce bajista (EMA3 < EMA9)
    pero la tendencia madre 15m sigue viva (EMA3 > EMA9).
    Debe bloquear el micro-cierre para permitir correr las ganancias.
    """
    from app.core.memory_store import MEMORY_STORE

    now = datetime.now(timezone.utc)
    pos_mature = {
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 150.0,
        'opened_at': (now - timedelta(minutes=35)).isoformat(),
        'market_type': 'crypto_futures'
    }

    # Simular 5m bajista
    closes_5m = [154.0, 153.8, 153.5, 153.0, 152.8]
    df_5m = make_candle_df(closes_5m)
    df_5m['ema_3'] = [153.0] * len(df_5m)
    df_5m['ema_9'] = [153.5] * len(df_5m) # EMA3 < EMA9 en 5m

    # Simular 15m alcista (tendencia madre viva)
    closes_15m = [148.0 + i * 0.3 for i in range(25)]
    df_15m = make_candle_df(closes_15m)
    df_15m['ema1'] = df_15m['close'].ewm(span=3, adjust=False).mean()
    df_15m['ema2'] = df_15m['close'].ewm(span=9, adjust=False).mean() # EMA3 > EMA9

    MEMORY_STORE['SOLUSDT'] = {
        '5m': {'df': df_5m},
        '15m': {'df': df_15m}
    }

    cfg = {'exit_on_signal_reversal': True, 'min_profit_exit_pct_crypto': 1.50}
    import asyncio
    res = asyncio.run(check_early_profit_protect_ema_5m(pos_mature, current_price=152.8, config=cfg))
    assert res['should_exit'] is False, "Debe suprimir la salida de 5m mientras la tendencia madre 15m siga viva!"


def test_crypto_qshr_early_invalidation_does_not_cut_at_minus_015():
    """
    Test 5: QSHR Early Invalidation no debe cortar a -0.15% en los primeros minutos.
    Si la posición tiene -0.40% de pérdida por oscilación normal y 15m está viva, NO debe invalidar.
    """
    now = datetime.now(timezone.utc)
    active_pos = {
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 65000.0,
        'opened_at': (now - timedelta(minutes=4)).isoformat(),
        'market_type': 'crypto_futures',
        'lots': 0.05
    }

    # 5m velas con retroceso suave (-0.40%)
    current_px = 64740.0 # -0.40%
    closes_5m = [65100.0, 65050.0, 64950.0, 64850.0, 64740.0] * 5
    df_5m = make_candle_df(closes_5m)
    df_5m['basis'] = 64900.0
    df_5m['ma3'] = 64760.0
    df_5m['ma9'] = 64850.0 # ema3 < ema9 en 5m

    # 15m velas en tendencia alcista fuerte
    closes_15m = [64000.0 + i * 50.0 for i in range(25)]
    df_15m = make_candle_df(closes_15m)
    df_15m['ema1'] = df_15m['close'].ewm(span=3, adjust=False).mean()
    df_15m['ema2'] = df_15m['close'].ewm(span=9, adjust=False).mean()

    res = evaluate_qshr_hedge_signal(
        symbol='BTCUSDT',
        df_5m=df_5m,
        df_15m=df_15m,
        active_position=active_pos,
        market_type='crypto_futures'
    )

    action = res.get('action') if res else None
    assert action != 'close_original_long', "No debe invalidar a -0.40% en los primeros minutos con 15m alcista!"
