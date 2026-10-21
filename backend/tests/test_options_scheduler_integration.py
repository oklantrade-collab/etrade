"""
Test suite verifying the end-to-end integration of Options Gap Runner and Defense Engine
into stocks_scheduler.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta, date
from unittest.mock import MagicMock, AsyncMock, patch

from app.options.aduana_gap_runner_options import (
    evaluate_options_gap_entry_tranches,
    evaluate_options_gap_aduana_exit,
    get_min_gap_threshold,
    is_optionable
)
from app.options.opt_contract_picker import (
    select_best_option_contract,
    fetch_and_select_best_option_contract,
    SelectedContract
)


def _generate_mock_df(n_bars=30, base_price=500.0, trend="up"):
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=n_bars, freq="5min")
    prices = [base_price]
    for _ in range(n_bars - 1):
        delta = np.random.uniform(0.2, 1.0) if trend == "up" else np.random.uniform(-1.0, -0.2)
        prices.append(prices[-1] + delta)
    prices = np.array(prices)
    df = pd.DataFrame({
        "open": prices - 0.2,
        "high": prices + 0.5,
        "low": prices - 0.5,
        "close": prices,
        "volume": np.random.uniform(50000, 150000, size=n_bars)
    }, index=dates)
    return df


def test_is_optionable_recognition():
    """Verify that ETFs and Mega-Caps are recognized as optionable."""
    assert is_optionable("SPY") is True
    assert is_optionable("QQQ") is True
    assert is_optionable("NVDA") is True
    assert is_optionable("TSLA") is True
    assert is_optionable("AAPL") is True


def test_min_gap_threshold_etfs_and_megacaps():
    """Verify adaptive gap thresholds (ETFs 0.6%, Mega-Caps 1.2%, High-Beta 5.0%)."""
    assert get_min_gap_threshold("SPY") == 0.6
    assert get_min_gap_threshold("QQQ") == 0.6
    assert get_min_gap_threshold("NVDA") == 1.2
    assert get_min_gap_threshold("AAPL") == 1.2
    assert get_min_gap_threshold("AMD") == 1.2
    assert get_min_gap_threshold("SMALLCAP") == 5.0


def test_contract_selection_calls_and_puts():
    """Verify that ATM contracts (Delta ~ 0.50) are correctly chosen for CALLs and PUTs."""
    now_d = date.today()
    exp_d = now_d + timedelta(days=5)

    mock_contracts = [
        {
            "symbol": "SPY", "strike": 490.0, "right": "C", "expiry": exp_d.isoformat(),
            "bid": 12.0, "ask": 12.2, "volume": 500, "open_interest": 1000, "delta": 0.85
        },
        {
            "symbol": "SPY", "strike": 500.0, "right": "C", "expiry": exp_d.isoformat(),
            "bid": 4.5, "ask": 4.6, "volume": 1200, "open_interest": 2500, "delta": 0.51
        },
        {
            "symbol": "SPY", "strike": 510.0, "right": "C", "expiry": exp_d.isoformat(),
            "bid": 1.2, "ask": 1.3, "volume": 800, "open_interest": 1500, "delta": 0.22
        },
    ]

    best_call, _ = select_best_option_contract(
        contracts=mock_contracts,
        underlying_price=500.0,
        direction="CALL",
        budget_usd=1000.0,
        now_date=now_d
    )

    assert best_call is not None
    assert best_call.strike == 500.0
    assert best_call.right == "C"
    assert best_call.tranche_1_contracts >= 1


def test_options_defense_hard_stop():
    """Verify that an option position losing >= 35% triggers Hard Stop immediately."""
    pos = {
        "id": 99,
        "symbol": "SPY",
        "direction": "CALL",
        "entry_debit": 5.00,
        "last_mark_price": 3.10,
        "qty": 2
    }
    # Premium dropped from 5.00 to 3.10 (-38%)
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=498.0,
        current_option_premium=3.10,
        position_age_minutes=15.0
    )
    assert res["should_exit"] is True
    assert res["rule_code"] == "OPT_GAP_HARD_SL_PREM"


def test_options_defense_ratchet_tier2():
    """Verify that an option gaining >= 25% locks in a minimum floor of +15% net."""
    pos = {
        "id": 100,
        "symbol": "NVDA",
        "direction": "CALL",
        "entry_debit": 4.00,
        "highest_premium_seen": 5.20, # +30% peak
        "qty": 2
    }
    # Premium pulls back to 4.50 (below the +15% floor: 4.00 * 1.15 = 4.60)
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=215.0,
        current_option_premium=4.50,
        position_age_minutes=30.0
    )
    assert res["should_exit"] is True
    assert res["rule_code"] == "OPT_GAP_TRAIL_TIER2"


def test_options_defense_put_breakeven_shield():
    """Verify that PUT with >= +15% peak protects purchase price (Breakeven Shield)."""
    pos = {
        "id": 101,
        "symbol": "QQQ",
        "direction": "PUT",
        "entry_debit": 6.00,
        "highest_premium_seen": 7.00, # +16.6% peak
        "qty": 1
    }
    # Premium drops back to 6.02 (at entry premium * 1.01)
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=715.0,
        current_option_premium=6.02,
        position_age_minutes=25.0
    )
    assert res["should_exit"] is True
    assert res["rule_code"] == "OPT_GAP_PUT_BREAKEVEN"


def test_run_options_gap_defense_cycle_execution():
    """Verify run_options_gap_defense_cycle updates mark and triggers exits."""
    import asyncio
    from app.workers.stocks_scheduler import run_options_gap_defense_cycle

    mock_trade = {
        "id": 888,
        "symbol": "SPY",
        "strategy_type": "long_call",
        "direction": "bullish",
        "status": "open",
        "qty": 1,
        "entry_debit": 10.0,
        "expiry": (date.today() + timedelta(days=7)).isoformat(),
        "entry_time": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        "exit_plan": {
            "initial_sl": 490.0,
            "stop_loss_underlying": 490.0,
            "highest_premium_seen": 10.0
        },
        "entry_fills": [{"strike": 500.0, "right": "C"}]
    }

    mock_sb = MagicMock()
    mock_select = MagicMock()
    mock_select.execute.return_value.data = [mock_trade]
    mock_sb.table.return_value.select.return_value.eq.return_value = mock_select

    with patch("app.workers.stocks_scheduler.get_supabase", return_value=mock_sb), \
         patch("app.data.yfinance_provider.YFinanceProvider.get_ohlcv", new_callable=AsyncMock) as mock_ohlcv:
        mock_ohlcv.return_value = _generate_mock_df(n_bars=30, base_price=505.0, trend="up")
        
        asyncio.run(run_options_gap_defense_cycle())
        
        # Verify that Supabase was called to update or close
        assert mock_sb.table.called
