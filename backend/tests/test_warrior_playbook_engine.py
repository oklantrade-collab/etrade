"""
Unit test for Warrior Playbook Knowledge Engine (Ross Cameron Experiences).
"""
import pytest
from app.stocks.warrior_playbook_engine import warrior_playbook

def test_historical_session_retrieval():
    sessions = warrior_playbook.get_all_sessions()
    assert len(sessions) >= 1
    s72k = sessions[0]
    assert s72k["net_pnl"] == 72872.42
    assert len(s72k["trades"]) == 3
    
    tickers = [t["ticker"] for t in s72k["trades"]]
    assert "VWave" in tickers
    assert "SVRE" in tickers
    assert "GEM" in tickers
    
    # GEM trade details
    gem = next(t for t in s72k["trades"] if t["ticker"] == "GEM")
    assert gem["pnl"] == 46000.00
    assert gem["duration_seconds"] == 120
    assert len(gem["phases"]) == 6

def test_inference_200ma_overhead_block():
    # Context where price is at $8.90 and 200 MA is at $9.00 (within 2%)
    ctx = {
        "ticker": "TEST1",
        "price": 8.90,
        "vwap": 8.00,
        "sma_200": 9.00,
        "change_pct": 45.0
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "BLOCK_ENTRY"
    assert result.recommended_action == "BLOCK_MICRO_PULLBACK_200MA_RESISTANCE"
    assert "VWave" in result.historical_trade_ref

def test_inference_vwap_support_rebound():
    # Context where price is at $8.02 and VWAP is at $8.00
    ctx = {
        "ticker": "TEST2",
        "price": 8.02,
        "vwap": 8.00,
        "change_pct": 50.0
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "EXECUTE_ENTRY"
    assert result.recommended_action == "BUY_VWAP_SUPPORT"
    assert "VWave" in result.historical_trade_ref

def test_inference_gem_running_up_pyramid():
    # Context where ticker is up +230% with low float and tape acceleration
    ctx = {
        "ticker": "GEM_LIKE",
        "price": 3.75,
        "vwap": 2.50,
        "change_pct": 230.0,
        "float_shares": 4_000_000,
        "is_running_up": True,
        "tape_acceleration": True
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "SCALE_IN"
    assert result.recommended_action == "PYRAMID_SCALE_IN"
    assert "GEM" in result.historical_trade_ref

def test_inference_svre_consolidation_breakout():
    # Context where price is consolidating above VWAP with normal spread
    ctx = {
        "ticker": "SVRE_LIKE",
        "price": 6.95,
        "vwap": 6.80,
        "is_consolidating_above_vwap": True,
        "spread_pct": 0.4
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "EXECUTE_ENTRY"
    assert result.recommended_action == "ANTICIPATE_WHOLE_NUMBER_BREAKOUT"
    assert "SVRE" in result.historical_trade_ref

def test_inference_svre_wide_spread_warning():
    # Context where price is consolidating above VWAP but spread is 2.2%
    ctx = {
        "ticker": "SVRE_WIDE",
        "price": 6.95,
        "vwap": 6.80,
        "is_consolidating_above_vwap": True,
        "spread_pct": 2.2
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "SAFETY_GUARD"
    assert result.recommended_action == "WARN_DIP_SLIPPAGE_LIMIT_ONLY"
    assert "SVRE" in result.historical_trade_ref
