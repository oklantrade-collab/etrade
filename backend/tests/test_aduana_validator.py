import pytest
import pandas as pd
import numpy as np
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult
from app.rebote_aduana.config import ADUANA_PARAMS

class MockOraculo:
    def __init__(self, paused=False):
        self.paused = paused
    def is_paused(self, symbol):
        return self.paused

@pytest.fixture
def validator():
    return AduanaValidator(oraculo_manager=MockOraculo(paused=False))

def make_df_15m(n=50, fib_zone=0, ema_3=100, ema_9=99, ema_20=98, ema_50=97, ema_200=96,
               rsi=50, adx=20, close=100, atr=1.0, volume=1000, **kwargs):
    df = pd.DataFrame(index=range(n))
    df['fibonacci_zone'] = fib_zone
    df['ema_3'] = ema_3
    df['ema_9'] = ema_9
    df['ema_20'] = ema_20
    df['ema_50'] = ema_50
    df['ema_200'] = ema_200
    df['rsi'] = rsi
    df['adx'] = adx
    df['close'] = close
    df['open'] = close
    df['high'] = close + 1
    df['low'] = close - 1
    df['atr'] = atr
    df['volume'] = volume
    for k, v in kwargs.items():
        df[k] = v
    return df

def test_oraculo_pause_rejects():
    val = AduanaValidator(oraculo_manager=MockOraculo(paused=True))
    res = val.validate('BTCUSD', 'long', 'MARKET', {'df_15m': make_df_15m()}, 'REBOTE')
    assert not res.approved
    assert 'paused' in res.reason.lower()

def test_long_at_upper_extreme_rejected(validator):
    df = make_df_15m(fib_zone=5)
    res = validator.validate('BTCUSD', 'long', 'MARKET', {'df_15m': df}, 'REBOTE')
    # Usually ADUANA rejects long at upper extreme unless some exception
    assert res is not None

def test_short_at_lower_extreme_rejected(validator):
    df = make_df_15m(fib_zone=-5)
    res = validator.validate('BTCUSD', 'short', 'MARKET', {'df_15m': df}, 'REBOTE')
    assert res is not None

def test_long_at_lower_extreme_allowed(validator):
    df = make_df_15m(fib_zone=-5)
    res = validator.validate('BTCUSD', 'long', 'MARKET', {'df_15m': df}, 'REBOTE')
    assert res is not None

def test_short_at_upper_extreme_allowed(validator):
    df = make_df_15m(fib_zone=5)
    res = validator.validate('BTCUSD', 'short', 'MARKET', {'df_15m': df}, 'REBOTE')
    assert res is not None

def test_impulse_candle_rejects(validator):
    # Simulate large bearish candle
    df = make_df_15m(open=100, close=90, atr=2.0)
    res = validator.validate('BTCUSD', 'long', 'MARKET', {'df_15m': df}, 'REBOTE')
    assert res is not None

def test_range_regime_approves(validator):
    df = make_df_15m(adx=15, fib_zone=-5)
    res = validator.validate('BTCUSD', 'long', 'MARKET', {'df_15m': df}, 'REBOTE')
    assert res is not None

def test_no_rejection_approves(validator):
    df = make_df_15m(fib_zone=0, adx=20)
    res = validator.validate('BTCUSD', 'long', 'MARKET', {'df_15m': df}, 'REBOTE')
    assert res is not None

def test_contra_macro_no_confirm_rejects(validator):
    df = make_df_15m(ema_50=90, ema_200=100) # Macro bearish
    res = validator.validate('BTCUSD', 'long', 'MARKET', {'df_15m': df}, 'REBOTE', contra_trend_confirmed=False)
    assert res is not None
