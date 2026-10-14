"""
Test Suite: Blindaje de Stop Loss, EREP, Escudo de Tendencia EMA3>EMA9, Régimen 1H y Protección EOD.
Valida la prevención de desastres como JBDI (-52%) preservando al mismo tiempo la tolerancia a pullbacks sanos.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from app.strategy.erep_manager import evaluate_erep_phase
from app.stocks.stocks_adaptive_sl import evaluate_adaptive_sl, calculate_bounce_score


def create_mock_df(prices, timeframe='15m'):
    """Crea un DataFrame OHLCV sintético para pruebas."""
    n = len(prices)
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq='15min' if timeframe=='15m' else '1h')
    data = []
    for i, p in enumerate(prices):
        data.append({
            'open': p * 0.998,
            'high': p * 1.005,
            'low': p * 0.995,
            'close': p,
            'volume': 100000 + i * 1000
        })
    df = pd.DataFrame(data, index=dates)
    return df


def test_erep_cuts_at_panic_loss_threshold():
    """Valida que EREP nunca vuelva a bloquear el cierre en pérdida extrema y ejecute hard_panic_cut."""
    pos = {
        'id': 'test-pos-1',
        'ticker': 'JBDI',
        'side': 'long',
        'avg_entry_price': 10.0,
        'erep_p1_price': 10.0,
        'erep_phase': 2,
        'erep_cycles_elapsed': 2,
        'erep_max_loss_pct': 8.0,
        'shares': 100,
    }
    # Precio cayó a 9.10 (-9.0% > 8.0% de pánico)
    action = evaluate_erep_phase(
        position=pos,
        current_price=9.10,
        snap={},
        df_15m=None,
        market_type='stocks_spot'
    )
    assert action['action'] == 'close_all'
    assert action['close_type'] == 'hard_panic_cut'
    assert 'HARD PANIC CUT' in action['reason']


def test_erep_blocks_p2_when_1h_slope_is_flat_or_down():
    """Valida que EREP bloquee recompras P2 si la tendencia horaria está frenada o descendente."""
    pos = {
        'id': 'test-pos-2',
        'ticker': 'JBDI',
        'side': 'long',
        'avg_entry_price': 10.0,
        'erep_p1_price': 10.0,
        'erep_phase': 2,
        'erep_cycles_elapsed': 1,
        'erep_max_loss_pct': 8.0,
        'shares': 100,
    }
    # Serie de 1H descendente (10.5, 10.2, 9.8) -> slope_1h < 0
    df_1h_bearish = create_mock_df([10.5, 10.2, 9.8], timeframe='1h')
    
    action = evaluate_erep_phase(
        position=pos,
        current_price=9.80, # Pérdida de -2% (dentro de tolerancia EREP)
        snap={'rsi_14': 15}, # Sobreventa extrema que normalmente dispararía P2
        df_15m=create_mock_df([10.0, 9.9, 9.8]),
        df_1h=df_1h_bearish,
        market_type='stocks_spot'
    )
    # P2 debe estar bloqueado por Régimen Defensivo 1H
    assert action['action'] == 'wait_p2_signal'
    assert 'P2 bloqueado: EMA3 1H sin impulso alcista' in action['reason']


def test_trend_guard_protects_bullish_pullback():
    """Valida que un retroceso intradía moderado con EMA3 > EMA9 en 15m no sea expulsado por ruido."""
    # Serie 15m donde el precio retrocede levemente pero EMA3 > EMA9 sigue intacto
    prices = [10.0, 10.2, 10.4, 10.6, 10.8, 11.0, 10.9, 10.85]
    df_15m = create_mock_df(prices, timeframe='15m')
    
    score_res = calculate_bounce_score(
        ticker='AAPL',
        position={'entry_price': 11.0},
        current_price=10.85, # Drawdown de -1.36%
        snap={'lower_2': 10.80},
        df_15m=df_15m,
        config={'sl_wait_threshold': 8.0}
    )
    # Debe registrar trend_guard_15m alcista
    assert 'trend_guard_15m' in score_res['components']
    assert score_res['components']['trend_guard_15m']['status'] == 'bullish_intact'


def test_adaptive_sl_cuts_at_wait_threshold():
    """Valida que evaluate_adaptive_sl corte forzosamente cuando se supera el sl_wait_threshold (8%)."""
    pos = {
        'id': 'test-pos-4',
        'entry_price': 10.0,
        'shares': 100,
    }
    # Pérdida de -8.5% (supera sl_wait_threshold de 8%)
    res = evaluate_adaptive_sl(
        ticker='JBDI',
        position=pos,
        current_price=9.15,
        snap={},
        df_15m=None,
        config={'sl_close_threshold': 2.0, 'sl_wait_threshold': 8.0}
    )
    assert res['action'] == 'close_forced'
    assert res['zone'] == 'hard_stop'
