"""
Test Suite: Data Integrity, Broker Freshness, Symmetric Pullback Guard & Emergency Bracket Failsafe
===================================================================================================
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from app.rebote_aduana.aduana_validator import AduanaValidator
from app.core.safety_manager import calculate_emergency_bracket


def create_sample_df(count=30, base_price=100.0, trend='neutral', is_stale=False):
    """Genera DataFrame sintético con timestamps y EMAs."""
    now = datetime.now(timezone.utc)
    if is_stale:
        # Última vela debe tener al menos 30 minutos de antigüedad
        start_time = now - timedelta(minutes=30 + (count * 5))
    else:
        start_time = now - timedelta(minutes=count * 5)

    timestamps = [start_time + timedelta(minutes=i * 5) for i in range(count)]
    
    if trend == 'bullish':
        closes = [base_price + (i * 0.5) for i in range(count)]
    elif trend == 'bearish':
        closes = [base_price - (i * 0.5) for i in range(count)]
    else:
        closes = [base_price + (np.sin(i) * 0.5) for i in range(count)]

    opens = [c - 0.1 for c in closes]
    highs = [max(o, c) + 0.2 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.2 for o, c in zip(opens, closes)]
    volumes = [1000.0 for _ in range(count)]

    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    # Calcular EMAs
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ema2'] = df['ema_9']
    df['ema3'] = df['ema_20']
    df['ema9'] = df['ema_9']
    df['ema20'] = df['ema_20']
    return df


def test_aduana_candle_integrity_stale_data():
    """Velas con antigüedad superior a 15m en 5m deben ser bloqueadas por STALE_CANDLE_DATA_BLOCKED."""
    df_stale = create_sample_df(count=30, base_price=100.0, is_stale=True)
    aduana = AduanaValidator()
    
    market_data = {
        'df_5m': df_stale,
        'df_15m': df_stale,
        'price': 100.0,
        'squeeze_velocity': 3.0
    }
    
    res = aduana.validate(
        symbol='SOLUSDT',
        side='SHORT',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_DIRECT_SHORT'
    )
    
    assert not res.approved
    assert res.rule_triggered == 'STALE_CANDLE_DATA_BLOCKED'


def test_aduana_candle_integrity_nan_values():
    """Velas con valores NaN recientes deben ser bloqueadas por CANDLE_DATA_CORRUPTED."""
    df_nan = create_sample_df(count=30, base_price=100.0, is_stale=False)
    df_nan.loc[df_nan.index[-1], 'close'] = np.nan
    aduana = AduanaValidator()
    
    market_data = {
        'df_5m': df_nan,
        'price': 100.0,
        'squeeze_velocity': 3.0
    }
    
    res = aduana.validate(
        symbol='SOLUSDT',
        side='SHORT',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_DIRECT_SHORT'
    )
    
    assert not res.approved
    assert res.rule_triggered == 'CANDLE_DATA_CORRUPTED'


def test_aduana_price_discrepancy():
    """Discrepancia de precio > 0.40% entre vela y Ticker del Broker debe ser bloqueada."""
    df = create_sample_df(count=30, base_price=100.0, is_stale=False)
    aduana = AduanaValidator()
    
    # Vela en 100.0 pero Broker Ticker en 104.17 (desfase de 4.17%)
    market_data = {
        'df_5m': df,
        'price': 100.0,
        'broker_ticker_price': 104.17
    }
    
    res = aduana.validate(
        symbol='SOLUSDT',
        side='SHORT',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_DIRECT_SHORT'
    )
    
    assert not res.approved
    assert res.rule_triggered == 'PRICE_DISCREPANCY_BLOCKED'


def test_aduana_symmetric_pullback_guard():
    """Validar que órdenes sobre-extendidas sin pullback a EMA9 sean rechazadas."""
    # SHORT en tendencia bajista muy sobre-extendido sin haber tocado EMA9
    df_15m = create_sample_df(count=30, base_price=100.0, trend='bearish')
    last_idx = df_15m.index[-1]
    df_15m.loc[last_idx, 'close'] = 85.0
    df_15m.loc[last_idx, 'high'] = 85.2
    df_15m.loc[last_idx, 'ema9'] = 90.0 # High (85.2) < EMA9 (90.0)
    
    aduana = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'price': 85.0,
        'squeeze_velocity': 3.0
    }
    
    # 1. SHORT sobre-extendido
    res_short = aduana.validate(
        symbol='SOLUSDT',
        side='SHORT',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_DIRECT_SHORT'
    )
    assert not res_short.approved
    assert res_short.rule_triggered == 'NO_PULLBACK_OVEREXTENDED'

    # 2. LONG sobre-extendido en tendencia alcista
    df_long = create_sample_df(count=30, base_price=100.0, trend='bullish')
    l_idx = df_long.index[-1]
    df_long.loc[l_idx, 'close'] = 115.0
    df_long.loc[l_idx, 'low'] = 114.8
    df_long.loc[l_idx, 'ema9'] = 110.0 # Low (114.8) > EMA9 (110.0)
    
    market_data_long = {
        'df_15m': df_long,
        'price': 115.0,
        'squeeze_velocity': 3.0
    }
    res_long = aduana.validate(
        symbol='SOLUSDT',
        side='LONG',
        order_type='MARKET',
        market_data=market_data_long,
        strategy='Bb33_QSHR_DIRECT_LONG'
    )
    assert not res_long.approved
    assert res_long.rule_triggered == 'NO_PULLBACK_OVEREXTENDED'


def test_calculate_emergency_bracket_guaranteed_rr():
    """Comprobar que el Guardián de Emergencia calcule brackets con RR > 1.0 para Crypto y Forex."""
    # 1. Crypto SHORT (SOLUSDT)
    b_crypto_short = calculate_emergency_bracket(
        entry_price=100.0,
        side='SHORT',
        symbol='SOLUSDT',
        market_type='crypto_futures',
        min_rr=1.25,
        sl_distance_pct=0.02
    )
    assert b_crypto_short['sl_price'] > 100.0 # SL por encima en SHORT
    assert b_crypto_short['tp_price'] < 100.0 # TP por debajo en SHORT
    assert b_crypto_short['rr_ratio'] >= 1.25 # Ratio > 1.0 garantizado

    # 2. Crypto LONG (BTCUSDT)
    b_crypto_long = calculate_emergency_bracket(
        entry_price=60000.0,
        side='LONG',
        symbol='BTCUSDT',
        market_type='crypto_futures',
        min_rr=1.25,
        sl_distance_pct=0.015
    )
    assert b_crypto_long['sl_price'] < 60000.0 # SL por debajo en LONG
    assert b_crypto_long['tp_price'] > 60000.0 # TP por encima en LONG
    assert b_crypto_long['rr_ratio'] >= 1.25

    # 3. Forex SHORT (EURUSD)
    b_forex_short = calculate_emergency_bracket(
        entry_price=1.08500,
        side='SHORT',
        symbol='EURUSD',
        market_type='forex_futures',
        min_rr=1.5,
        sl_distance_pips=20.0
    )
    assert b_forex_short['sl_price'] > 1.08500
    assert b_forex_short['tp_price'] < 1.08500
    assert b_forex_short['rr_ratio'] >= 1.5

    # 4. Forex LONG (GBPUSD)
    b_forex_long = calculate_emergency_bracket(
        entry_price=1.27000,
        side='LONG',
        symbol='GBPUSD',
        market_type='forex_futures',
        min_rr=1.5,
        sl_distance_pips=20.0
    )
    assert b_forex_long['sl_price'] < 1.27000
    assert b_forex_long['tp_price'] > 1.27000
    assert b_forex_long['rr_ratio'] >= 1.5
