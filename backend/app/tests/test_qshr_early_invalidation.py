import pytest
import pandas as pd
import numpy as np
from app.strategy.quantum_squeeze_hedge import evaluate_qshr_hedge_signal
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult

def _make_df_5m_bullish_surge():
    # 25 candles with flat/compressed history then explosive surge at the end
    opens = [158.50] * 24 + [158.55]
    closes = [158.51] * 24 + [158.85]
    highs = [158.53] * 24 + [158.90]
    lows = [158.49] * 24 + [158.54]
    vols = [1000] * 24 + [4000]

    df = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': vols
    })
    df['ema_3'] = df['close'].ewm(span=3, adjust=False).mean()
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    return df

def _make_df_15m():
    prices = [158.00 + i * 0.05 for i in range(30)]
    df = pd.DataFrame({
        'open': [p - 0.02 for p in prices],
        'high': [p + 0.05 for p in prices],
        'low': [p - 0.03 for p in prices],
        'close': prices,
        'volume': [5000 + i * 200 for i in range(30)]
    })
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    return df

def test_qshr_early_invalidation_short():
    """Verifica que un SHORT activo se corte de inmediato y gire a LONG con volumen asimétrico ante impulso alcista violento."""
    df_5m = _make_df_5m_bullish_surge()
    df_15m = _make_df_15m()
    active_short = {
        'id': 'pos_test_short',
        'symbol': 'USDJPY',
        'side': 'short',
        'entry_price': 158.60,
        'lots': 0.01,
        'status': 'open'
    }

    res = evaluate_qshr_hedge_signal(
        symbol='USDJPY',
        df_5m=df_5m,
        df_15m=df_15m,
        active_position=active_short,
        market_type='forex_futures'
    )

    assert res is not None, "Debe emitir una señal de salida"
    assert res['action'] == 'close_and_flip_long', f"Se esperaba close_and_flip_long, se obtuvo {res.get('action')}"
    assert res['flip_side'] == 'long'
    assert res['flip_lots'] >= 0.02, f"Se esperaba volumen asimétrico >= 0.02, se obtuvo {res.get('flip_lots')}"
    assert res['rule_code'] == 'Bb33_QSHR_EARLY_EXIT'
    assert 'Cut & Flip' in res['reason']

def test_aduana_same_side_drawdown_guard():
    """Verifica que AduanaValidator bloquee un segundo SHORT si el existente tiene Drawdown >= 5 pips."""
    aduana = AduanaValidator()
    
    # Existing SHORT entered at 158.50, current price is 159.20 (drawdown = 70 pips)
    market_data = {
        'price': 159.20,
        'df_15m': _make_df_15m(),
        'open_symbols': ['USDJPY'],
        'max_active_symbols': 3,
        'current_symbol_positions': 1,
        'max_positions_per_symbol': 3,
        'active_positions': [{
            'symbol': 'USDJPY',
            'side': 'short',
            'entry_price': 158.50,
            'status': 'open'
        }]
    }

    res = aduana.validate(
        symbol='USDJPY',
        side='short',
        order_type='MARKET',
        market_data=market_data,
        strategy='BBHOT'
    )

    assert res.approved is False, "Aduana debe bloquear la re-entrada SHORT en drawdown"
    assert res.rule_triggered == 'SAME_SIDE_DRAWDOWN_BLOCKED'
    assert 'Drawdown' in res.reason
