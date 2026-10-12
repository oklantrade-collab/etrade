import os
import sys
import pytest
import pandas as pd
import numpy as np

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult
from app.strategy.quantum_squeeze_hedge import scan_squeeze_opportunities

def _build_test_dfs(trend='bullish', rsi_15m=68.0, rsi_5m=71.0, is_red_5m=False,
                    vol_boost_5m=False, close_under_ema3=False, is_rocket=False,
                    bandwidth_ratio=1.0, is_divergent=False):
    """
    Construye DataFrames sintéticos de 15m y 5m para pruebas controladas.
    """
    # 15m DataFrame (30 velas)
    dates_15m = pd.date_range('2026-09-17 00:00', periods=30, freq='15min')
    base_price = 100.0
    prices_15m = []
    
    for i in range(30):
        if trend == 'bullish':
            p = base_price + i * 0.4  # Fuerte tendencia alcista
        elif trend == 'bearish':
            p = base_price - i * 0.4  # Fuerte tendencia bajista
        else:
            p = base_price + np.sin(i / 3.0) * 0.2  # Neutral / Rango
        prices_15m.append(p)
        
    df_15m = pd.DataFrame({
        'timestamp': [int(d.timestamp() * 1000) for d in dates_15m],
        'open': [p - 0.1 for p in prices_15m],
        'high': [p + 0.3 for p in prices_15m],
        'low': [p - 0.2 for p in prices_15m],
        'close': prices_15m,
        'volume': [1000.0] * 30,
        'rsi': [rsi_15m] * 30,
        'atr': [0.5] * 30,
        'fibonacci_zone': [6.0 if trend == 'bullish' else (-6.0 if trend == 'bearish' else 0.0)] * 30,
        'upper_6': [prices_15m[-1] + 0.1] * 30,
        'lower_6': [prices_15m[-1] - 0.1] * 30
    })
    
    # 5m DataFrame (25 velas)
    dates_5m = pd.date_range('2026-09-17 06:00', periods=25, freq='5min')
    curr_px = prices_15m[-1]
    prices_5m = [curr_px - (25 - i) * 0.05 for i in range(24)]
    
    # Última vela de 5M configurable
    if is_rocket:
        last_open = curr_px
        last_high = curr_px + 2.5  # Vela gigante > 2.5x ATR
        last_low = curr_px - 0.1
        last_close = curr_px + 2.4
    elif is_red_5m:
        last_open = curr_px + 0.3
        last_high = curr_px + 0.4
        last_low = curr_px - 0.35
        last_close = curr_px - 0.3  # Cierre menor al open (roja) y bajo EMA3
    else:
        last_open = curr_px - 0.1
        last_high = curr_px + 0.3
        last_low = curr_px - 0.15
        last_close = curr_px + 0.2  # Cierre mayor al open (verde)
        
    prices_5m.append(last_close)
    volumes_5m = [500.0] * 24 + [1500.0 if vol_boost_5m else 400.0]
    
    df_5m = pd.DataFrame({
        'timestamp': [int(d.timestamp() * 1000) for d in dates_5m],
        'open': [p - 0.05 for p in prices_5m[:-1]] + [last_open],
        'high': [p + 0.15 for p in prices_5m[:-1]] + [last_high],
        'low': [p - 0.10 for p in prices_5m[:-1]] + [last_low],
        'close': prices_5m,
        'volume': volumes_5m,
        'rsi': [rsi_5m] * 25,
        'atr': [0.4] * 25,
        'fibonacci_zone': [6.0 if trend == 'bullish' else (-6.0 if trend == 'bearish' else 0.0)] * 25,
        'upper_6': [curr_px] * 25,
        'lower_6': [curr_px] * 25
    })
    
    return df_15m, df_5m


def test_solusdt_false_climax_short_blocked_by_aduana():
    """
    Caso SOLUSDT Real:
    Tendencia alcista (mtf=+0.55, SAR+), RSI 15m=68.3, RSI 5m=71.7.
    Bandas en expansión divergente, vela verde sin volumen vendedor.
    ADUANA debe bloquear la orden con éxito.
    """
    df_15m, df_5m = _build_test_dfs(
        trend='bullish',
        rsi_15m=68.3,
        rsi_5m=71.7,
        is_red_5m=False,
        vol_boost_5m=False,
        bandwidth_ratio=1.28,
        is_divergent=True
    )
    
    validator = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'df_5m': df_5m,
        'mtf_score': 0.55,
        'sar_trend': 'SAR+',
        'bandwidth_ratio': 1.28,
        'is_divergent': True,
        'is_test': True
    }
    
    res = validator.validate(
        symbol='SOLUSDT',
        side='short',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT'
    )
    
    assert res.approved is False
    assert res.rule_triggered in ('REJECT_CLIMAX_RSI_NOT_EXTREME', 'REJECT_CLIMAX_WALKING_THE_BANDS', 'REJECT_CLIMAX_NO_REVERSAL_CANDLE')


def test_solusdt_signal_generator_blocks_when_rsi_not_extreme():
    """
    En quantum_squeeze_hedge.py, si la macro 15m es alcista pero el RSI no alcanza
    sobrecompra extrema (>= 75 en 15m o >= 80 en 5m) o la vela no es roja bajo EMA3,
    no debe generarse la señal SHORT.
    """
    df_15m, df_5m = _build_test_dfs(
        trend='bullish',
        rsi_15m=68.3,
        rsi_5m=71.7,
        is_red_5m=False
    )
    
    sig = scan_squeeze_opportunities(
        symbol='SOLUSDT',
        df_5m=df_5m,
        df_15m=df_15m,
        market_type='crypto'
    )
    
    # No debe disparar Clímax Short en estas condiciones
    if sig:
        assert sig.get('rule_code') != 'Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT'


def test_genuine_climax_extreme_contra_trend_approved_with_45pct_sizing():
    """
    Clímax Extremo Genuino (SHORT):
    Macro alcista (mtf=+0.40), pero agotamiento parabólico real:
    RSI 15m=78.0, RSI 5m=82.0, vela roja bajo EMA3 con volumen vendedor institucional.
    ADUANA debe APROBAR la orden con sizing prudente del 45%.
    """
    df_15m, df_5m = _build_test_dfs(
        trend='bullish',
        rsi_15m=78.0,
        rsi_5m=82.0,
        is_red_5m=True,
        vol_boost_5m=True,
        bandwidth_ratio=1.05,
        is_divergent=False
    )
    
    validator = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'df_5m': df_5m,
        'mtf_score': 0.40,
        'sar_trend': 'SAR+',
        'bandwidth_ratio': 1.05,
        'is_divergent': False,
        'is_test': True
    }
    
    res = validator.validate(
        symbol='SOLUSDT',
        side='short',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT'
    )
    
    assert res.approved is True
    assert res.rule_triggered == 'QSHR_CLIMAX_EXTREME_CONTRA_TREND_APPROVED'
    assert res.detail.get('sizing_factor') == 0.45
    assert res.detail.get('contra_trend') is True


def test_genuine_climax_extreme_long_approved_with_45pct_sizing():
    """
    Clímax Extremo Genuino (LONG):
    Macro bajista (mtf=-0.45, SAR-), agotamiento parabólico en caída:
    RSI 15m=22.0, RSI 5m=18.0, vela verde sobre EMA3 con volumen comprador.
    ADUANA debe APROBAR con sizing del 45%.
    """
    df_15m, df_5m = _build_test_dfs(
        trend='bearish',
        rsi_15m=22.0,
        rsi_5m=18.0,
        is_red_5m=False,  # Cierre verde
        vol_boost_5m=True,
        bandwidth_ratio=1.05,
        is_divergent=False
    )
    
    validator = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'df_5m': df_5m,
        'mtf_score': -0.45,
        'sar_trend': 'SAR-',
        'bandwidth_ratio': 1.05,
        'is_divergent': False,
        'is_test': True
    }
    
    res = validator.validate(
        symbol='BTCUSDT',
        side='long',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_CLIMAX_5M_LOWER6_LONG'
    )
    
    assert res.approved is True
    assert res.rule_triggered == 'QSHR_CLIMAX_EXTREME_CONTRA_TREND_APPROVED'
    assert res.detail.get('sizing_factor') == 0.45


def test_climax_rocket_expansion_rejected():
    """
    Vela de expansión violenta (> 2.5x ATR):
    Movimiento explosivo por liquidación en masa.
    ADUANA debe rechazar la orden para evitar atrapar el cuchillo / cohete.
    """
    df_15m, df_5m = _build_test_dfs(
        trend='bullish',
        rsi_15m=79.0,
        rsi_5m=83.0,
        is_rocket=True
    )
    
    validator = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'df_5m': df_5m,
        'mtf_score': 0.35,
        'sar_trend': 'SAR+',
        'is_test': True
    }
    
    res = validator.validate(
        symbol='SOLUSDT',
        side='short',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT'
    )
    
    assert res.approved is False
    assert res.rule_triggered == 'REJECT_CLIMAX_ROCKET_EXPANSION'


def test_climax_in_neutral_market_approved_with_full_sizing():
    """
    Clímax en mercado neutral / no contra-tendencia:
    mtf=0.02 (rango), bandas estables.
    Debe aprobarse con sizing estándar (70% para 5M).
    """
    df_15m, df_5m = _build_test_dfs(
        trend='neutral',
        rsi_15m=55.0,
        rsi_5m=70.0,
        is_red_5m=True,
        vol_boost_5m=True
    )
    
    validator = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'df_5m': df_5m,
        'mtf_score': 0.02,
        'sar_trend': 'neutral',
        'is_test': True
    }
    
    res = validator.validate(
        symbol='ETHUSDT',
        side='short',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT'
    )
    
    assert res.approved is True
    assert res.rule_triggered == 'QSHR_CLIMAX_APPROVED'
    assert res.detail.get('sizing_factor') == 0.70
    assert res.detail.get('contra_trend') is False


def test_forex_climax_extreme_contra_trend():
    """
    Forex (EURUSD):
    Verifica que en Forex apliquen los umbrales adaptativos (RSI >= 72/78 para SHORT).
    """
    df_15m, df_5m = _build_test_dfs(
        trend='bullish',
        rsi_15m=73.5,
        rsi_5m=79.0,
        is_red_5m=True,
        vol_boost_5m=True
    )
    
    validator = AduanaValidator()
    market_data = {
        'df_15m': df_15m,
        'df_5m': df_5m,
        'mtf_score': 0.30,
        'sar_trend': 'SAR+',
        'is_test': True
    }
    
    res = validator.validate(
        symbol='EURUSD',
        side='short',
        order_type='MARKET',
        market_data=market_data,
        strategy='Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT'
    )
    
    assert res.approved is True
    assert res.rule_triggered == 'QSHR_CLIMAX_EXTREME_CONTRA_TREND_APPROVED'
    assert res.detail.get('sizing_factor') == 0.45
