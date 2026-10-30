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


# =====================================================================
# TESTS FOR COLD MARKET / RED INDICES SESSION ("Don't Make It Worse!")
# =====================================================================

def test_cold_market_session_retrieval():
    sessions = warrior_playbook.get_all_sessions()
    assert len(sessions) >= 2
    
    cold_sess = next((s for s in sessions if "Don't Make It Worse" in s["video_title"]), None)
    assert cold_sess is not None
    assert cold_sess["net_pnl"] < 0
    assert len(cold_sess["trades"]) == 3
    
    tickers = [t["ticker"] for t in cold_sess["trades"]]
    assert "PCLA" in tickers
    assert "NWE" in tickers
    assert "DAVI" in tickers

def test_cold_market_thickly_traded_block():
    ctx = {
        "ticker": "NCPL_LIKE",
        "price": 2.50,
        "vwap": 2.20,
        "change_pct": 80.0,
        "is_thickly_traded": True
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "BLOCK_ENTRY"
    assert result.recommended_action == "BLOCK_THICKLY_TRADED_TAPE"
    assert "NCPL" in result.historical_trade_ref

def test_cold_market_illiquid_reverse_split_block():
    ctx = {
        "ticker": "AXG_LIKE",
        "price": 4.10,
        "vwap": 4.00,
        "change_pct": 30.0,
        "is_reverse_split": True,
        "volume": 5000
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "BLOCK_ENTRY"
    assert result.recommended_action == "BLOCK_ILLIQUID_REVERSE_SPLIT"
    assert "AXG" in result.historical_trade_ref

def test_cold_market_red_tape_catalyst_block():
    ctx = {
        "ticker": "DAIC_LIKE",
        "price": 1.80,
        "vwap": 2.00,
        "has_positive_news": True,
        "candle_is_red": True
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "BLOCK_ENTRY"
    assert result.recommended_action == "BLOCK_RED_TAPE_CATALYST"
    assert "DAIC" in result.historical_trade_ref

def test_cold_market_topping_tail_cut():
    ctx = {
        "ticker": "PCLA_LIKE",
        "price": 3.05,
        "vwap": 3.10,
        "is_cold_market": True,
        "has_topping_tail": True
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "SAFETY_GUARD"
    assert result.recommended_action == "DEFENSIVE_CUT_TOPPING_TAIL"
    assert "PCLA" in result.historical_trade_ref

def test_cold_market_flat_top_squeeze_block():
    ctx = {
        "ticker": "NWE_LIKE",
        "price": 7.30,
        "vwap": 7.00,
        "is_cold_market": True,
        "is_flat_top_squeeze": True
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "BLOCK_ENTRY"
    assert result.recommended_action == "BLOCK_FLAT_TOP_BREAKOUT_IN_COLD_MARKET"
    assert "NWE" in result.historical_trade_ref

def test_cold_market_reduced_sizing_protocol():
    ctx = {
        "ticker": "COLD_ANY",
        "price": 5.00,
        "vwap": 4.90,
        "is_cold_market": True,
        "change_pct": 10.0
    }
    result = warrior_playbook.evaluate_live_opportunity(ctx)
    assert result.matched is True
    assert result.action_type == "SAFETY_GUARD"
    assert result.recommended_action == "APPLY_COLD_MARKET_REDUCED_SIZING"
    assert result.execution_params["position_size_multiplier"] == 0.30
    assert result.execution_params["max_daily_loss_limit"] == 1500.0
    assert "DAVI" in result.historical_trade_ref
