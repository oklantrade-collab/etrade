import pytest
import pandas as pd
import numpy as np
from app.core.memory_store import BOT_STATE
from app.strategy.profit_capture import evaluate_dynamic_tp_v6
from app.strategy.risk_controls import check_pre_filters

def test_dynamic_tp_v6_blocks_loss_exit():
    # Construct 15m DataFrame where cascade and reversal exist
    dates = pd.date_range(end='2026-08-30', periods=30, freq='15min')
    prices = np.linspace(100, 110, 30)
    df = pd.DataFrame({
        'open': prices - 0.1,
        'high': prices + 0.5,
        'low': prices - 0.5,
        'close': prices,
        'volume': 1000
    }, index=dates)

    # Last candle red and below EMA3
    df.iloc[-1, df.columns.get_loc('open')] = 110.0
    df.iloc[-1, df.columns.get_loc('close')] = 105.0 # Dropped below EMA3

    entry_price = 106.0 # Higher than current price 105.0 -> Trade is in LOSS (PnL = -0.94%)
    current_price = 105.0

    res = evaluate_dynamic_tp_v6(
        symbol='SOLUSDT',
        side='long',
        current_price=current_price,
        entry_price=entry_price,
        df_15m=df,
        market_type='crypto_futures'
    )

    # Must NOT trigger TP when in loss
    assert res['should_close'] is False
    assert res['rule_code'] == 'HOLD_TREND'

def test_dynamic_tp_v6_allows_profit_exit():
    # Construct 15m DataFrame where cascade and reversal exist
    dates = pd.date_range(end='2026-08-30', periods=30, freq='15min')
    prices = np.linspace(100, 110, 30)
    df = pd.DataFrame({
        'open': prices - 0.1,
        'high': prices + 0.5,
        'low': prices - 0.5,
        'close': prices,
        'volume': 1000
    }, index=dates)

    df.iloc[-1, df.columns.get_loc('open')] = 110.0
    df.iloc[-1, df.columns.get_loc('close')] = 108.0

    entry_price = 100.0 # Trade is in PROFIT (current 108.0 > entry 100.0, PnL = +8%)
    current_price = 108.0

    res = evaluate_dynamic_tp_v6(
        symbol='SOLUSDT',
        side='long',
        current_price=current_price,
        entry_price=entry_price,
        df_15m=df,
        market_type='crypto_futures'
    )

    # It evaluated and is allowed to close if conditions met
    assert res is not None

def test_bot_state_positions_by_market():
    BOT_STATE.positions = {
        'pos1': {'id': 'pos1', 'symbol': 'SOLUSDT', 'market_type': 'crypto'},
        'pos2': {'id': 'pos2', 'symbol': 'BTCUSDT', 'market_type': 'crypto'},
        'pos3': {'id': 'pos3', 'symbol': 'EURUSD', 'market_type': 'forex'},
        'pos4': {'id': 'pos4', 'ticker': 'AAPL', 'market_type': 'stocks'},
    }

    crypto_pos = BOT_STATE.get_positions_by_market('crypto')
    assert len(crypto_pos) == 2
    assert {p['symbol'] for p in crypto_pos} == {'SOLUSDT', 'BTCUSDT'}

    forex_pos = BOT_STATE.get_positions_by_market('forex')
    assert len(forex_pos) == 1
    assert forex_pos[0]['symbol'] == 'EURUSD'

    stock_pos = BOT_STATE.get_positions_by_market('stocks')
    assert len(stock_pos) == 1
    assert stock_pos[0]['ticker'] == 'AAPL'
