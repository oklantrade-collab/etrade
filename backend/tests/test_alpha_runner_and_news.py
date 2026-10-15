import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.stocks.news_catalyst_service import classify_headline, fetch_stock_news
from app.stocks.alpha_runner_scanner import calculate_semaphore_and_buying_force


def test_classify_headline_tier1_fda():
    res = classify_headline("FDA Approves Revolutionary Oncology Treatment")
    assert res["tier"] == "tier_1"
    assert res["tier_num"] == 1
    assert res["bonus"] == 25
    assert "FDA" in res["label"]


def test_classify_headline_tier1_patent():
    res = classify_headline("Company Wins Patent Lawsuit Settlement in Federal Court")
    assert res["tier"] == "tier_1"
    assert res["tier_num"] == 1
    assert res["bonus"] == 25
    assert "Patente" in res["label"]


def test_classify_headline_tier2_earnings():
    res = classify_headline("Q2 Financial Results Beat Wall Street Estimates and Guidance Raised")
    assert res["tier"] == "tier_2"
    assert res["tier_num"] == 2
    assert res["bonus"] == 15
    assert "Earnings" in res["label"]


def test_classify_headline_tier2_partnership():
    res = classify_headline("Enters into Strategic Partnership and Global Collaboration Agreement")
    assert res["tier"] == "tier_2"
    assert res["tier_num"] == 2
    assert res["bonus"] == 15
    assert "Alianza" in res["label"]


def test_classify_headline_tier3_upgrade():
    res = classify_headline("Top Analyst Upgrades Stock to Buy with Raised Price Target")
    assert res["tier"] == "tier_3"
    assert res["tier_num"] == 3
    assert res["bonus"] == 10
    assert "Upgrade" in res["label"]


def test_classify_headline_general():
    res = classify_headline("CEO speaks on daily market movements and macro trends")
    assert res["tier"] == "general"
    assert res["tier_num"] == 3
    assert res["bonus"] == 5


@patch("app.stocks.news_catalyst_service.yf.Search")
def test_fetch_stock_news_with_mocked_results(mock_search_cls):
    now_ts = int(datetime.now(timezone.utc).timestamp())
    mock_instance = MagicMock()
    mock_search_cls.return_value = mock_instance
    mock_instance.news = [
        {
            "title": "FDA Approves Revolutionary New Drug",
            "publisher": "PR Newswire",
            "link": "https://finance.yahoo.com/news/fda-approval-123.html",
            "providerPublishTime": now_ts
        },
        {
            "title": "General market morning note",
            "publisher": "MarketWatch",
            "link": "https://marketwatch.com/story/update-456.html",
            "providerPublishTime": now_ts
        }
    ]

    # Force a unique ticker not cached
    res = fetch_stock_news("MOCKTEST123")
    assert res["has_news"] is True
    assert res["bonus_points"] == 25
    assert res["catalyst_tier"] == 1
    assert len(res["articles"]) >= 1
    assert "FDA" in res["catalyst_badge"]


def test_semaphore_climax():
    # Price is right at the peak (<1.5% from High) with massive change (>20%)
    res = calculate_semaphore_and_buying_force(
        price=25.0,
        change_pct=25.0,
        day_high=25.1,
        day_low=19.0,
        open_price=20.0,
        volume=5000000,
        avg_volume=1000000,
        news_bonus=25
    )
    assert res["semaphore"] == "CLIMAX"
    assert "CLÍMAX (ESPERAR)" in res["semaphore_label"]
    assert res["rank_score"] > 0


def test_semaphore_pullback():
    # Price had a strong run (>8%) and is in a controlled pullback (1.5% to 7.5% below high)
    # High: 25.0, Price: 23.8 -> dist = (25-23.8)/23.8 * 100 = 5.04%
    res = calculate_semaphore_and_buying_force(
        price=23.8,
        change_pct=19.0,
        day_high=25.0,
        day_low=19.0,
        open_price=20.0,
        volume=5000000,
        avg_volume=1000000,
        news_bonus=25
    )
    assert res["semaphore"] == "PULLBACK"
    assert "PULLBACK COMPRABLE" in res["semaphore_label"]
    assert res["rank_score"] > 50


def test_semaphore_monitoring():
    # Price in ordinary range without overextension or pullback criteria
    res = calculate_semaphore_and_buying_force(
        price=10.2,
        change_pct=2.0,
        day_high=10.5,
        day_low=9.9,
        open_price=10.0,
        volume=1000000,
        avg_volume=1000000,
        news_bonus=0
    )
    assert res["semaphore"] == "MONITORING"
    assert "MONITOREO" in res["semaphore_label"]


def test_semaphore_descending_ema3_1h():
    # Price is up 60% on the day, but 1H EMA3 is flat/descending (slope <= 0)
    res = calculate_semaphore_and_buying_force(
        price=3.65,
        change_pct=64.9,
        day_high=4.15,
        day_low=2.20,
        open_price=2.25,
        volume=164000000,
        avg_volume=12000000,
        news_bonus=25,
        is_ema3_1h_ascending=False,
        ema3_slope_1h=-0.0476,
        delta_p_5m=-2.60
    )
    assert res["semaphore"] == "DESCENDING"
    assert "EMA3 1H DESCENDENTE" in res["semaphore_label"]
    assert res["semaphore_color"] == "#EF4444"
    # Buying force should be severely penalized
    assert res["buying_force_5m"] <= 35
    # Rank score should be heavily penalized by -45 pts
    assert res["rank_score"] <= 30.0


def test_semaphore_sipv_upper_rejection():
    # 1H candle has a large upper wick (>40% of range), showing distribution at highs
    res = calculate_semaphore_and_buying_force(
        price=24.0,
        change_pct=25.0,
        day_high=26.5,
        day_low=19.0,
        open_price=20.0,
        volume=5000000,
        avg_volume=1000000,
        news_bonus=25,
        is_ema3_1h_ascending=True,
        sipv_upper_rejection=True
    )
    assert res["semaphore"] == "CLIMAX"
    assert "RECHAZO SIPV" in res["semaphore_label"]
    assert res["semaphore_color"] == "#F59E0B"


def test_rule_engine_blocks_buy_when_ema3_1h_is_descending():
    from app.stocks.stocks_rule_engine import StocksRuleEngine
    re_instance = StocksRuleEngine.get_instance()
    
    rule = {
        "rule_code": "PRO_DIP_BUY",
        "direction": "buy",
        "order_type": "market"
    }
    # Context with descending EMA3 1H
    context = {
        "ticker": "GLND",
        "close": 3.65,
        "is_ema3_1h_ascending": False,
        "ema3_slope_1h": -0.0476,
        "ema_20_1d": 2.5,
        "ema_50_1d": 2.0,
        "ema_3_1d": 3.0,
        "ema_9_1d": 2.8,
        "ema_3": 3.6,
        "ema_9": 3.5,
        "ema_20": 3.4
    }
    eval_res = re_instance.evaluate_rule(rule, context)
    assert eval_res["triggered"] is False
    assert any("EMA3 1H Descendente" in f for f in eval_res["failures"])


def test_max_active_stocks_reading():
    from app.stocks.stocks_order_executor import _get_config
    
    with patch("app.stocks.stocks_order_executor.get_supabase") as mock_sb:
        # Mocking empty config -> default to 3
        mock_instance = MagicMock()
        mock_sb.return_value = mock_instance
        mock_instance.table().select().execute.return_value.data = []
        
        cfg = _get_config()
        assert cfg["max_positions"] == 3

        # Mocking custom max_active_stocks = '5'
        mock_instance.table().select().execute.return_value.data = [
            {"key": "max_active_stocks", "value": "5"}
        ]
        cfg = _get_config()
        assert cfg["max_positions"] == 5


def test_semaphore_below_ema9_no_pullback():
    # Caso BRR: +8.24% intradía, distancia al high dentro del rango de pullback (-2.8%),
    # EMA3 1H ascendente (+0.03), pero EMA3 1H (3.78) <= EMA9 1H (3.89)
    res = calculate_semaphore_and_buying_force(
        price=3.78,
        change_pct=8.24,
        day_high=3.89,
        day_low=3.40,
        open_price=3.50,
        volume=2500000,
        avg_volume=1000000,
        news_bonus=0,
        is_ema3_1h_ascending=True,
        ema3_slope_1h=0.03,
        is_ema3_above_ema9=False,
    )
    assert res["semaphore"] == "BELOW_EMA9"
    assert "BAJO EMA9 1H" in res["semaphore_label"]
    assert res["semaphore_color"] == "#94A3B8"
    # No recibe el bonus de pullback (+25 pts); setup_bonus es -10 pts
    assert res["rank_score"] <= 30.0


def test_rule_engine_blocks_buy_when_ema3_below_ema9():
    from app.stocks.stocks_rule_engine import StocksRuleEngine
    re_instance = StocksRuleEngine.get_instance()
    
    rule = {
        "rule_code": "PRO_DIP_BUY",
        "direction": "buy",
        "order_type": "market"
    }
    # Contexto con EMA3 <= EMA9 en 1H
    context = {
        "ticker": "BRR",
        "close": 3.78,
        "is_ema3_1h_ascending": True,
        "ema3_slope_1h": 0.03,
        "is_ema3_above_ema9": False,
        "ema3_1h_live": 3.78,
        "ema9_1h": 3.89,
        "ema_20_1d": 3.5,
        "ema_50_1d": 3.0,
        "ema_3_1d": 3.7,
        "ema_9_1d": 3.6,
        "ema_3": 3.78,
        "ema_9": 3.75,
        "ema_20": 3.70
    }
    eval_res = re_instance.evaluate_rule(rule, context)
    assert eval_res["triggered"] is False
    assert any("EMA3 <= EMA9 en 1H" in f for f in eval_res["failures"])


def test_semaphore_exhaustion_gap_above_25():
    res = calculate_semaphore_and_buying_force(
        price=36.5,
        change_pct=35.0,
        day_high=37.0,
        day_low=27.0,
        open_price=36.0,
        volume=5000000,
        avg_volume=500000,
        news_bonus=25,
        gap_pct=35.0,
        is_ema3_1h_ascending=True,
        is_ema3_above_ema9=True,
    )
    assert res["semaphore"] == "EXHAUSTION_GAP"
    assert "CLÍMAX GAP" in res["semaphore_label"]
    assert res["semaphore_color"] == "#F59E0B"
    assert "Anti-LQDA" in res["semaphore_tip"]


def test_semaphore_sweet_spot_continuation_under_25():
    res = calculate_semaphore_and_buying_force(
        price=11.3,
        change_pct=18.0,
        day_high=11.5,
        day_low=9.5,
        open_price=10.0,
        volume=4000000,
        avg_volume=800000,
        news_bonus=20,
        gap_pct=12.0,
        candle_1_green=True,
        plus_di_5m=26.0,
        minus_di_5m=12.0,
        adx_5m=22.0,
        open_ge_close=True,
        is_ema3_1h_ascending=True,
        is_ema3_above_ema9=True,
    )
    assert res["semaphore"] == "SWEET_SPOT"
    assert "SWEET SPOT" in res["semaphore_label"]
    assert res["semaphore_color"] == "#10B981"
    assert "3 tercios" in res["semaphore_tip"]
    assert res["rank_score"] >= 60.0


def test_rule_engine_blocks_exhaustion_gap_in_opening_window():
    from app.stocks.stocks_rule_engine import StocksRuleEngine
    re_instance = StocksRuleEngine.get_instance()
    
    rule = {
        "rule_code": "PRO_DIP_BUY",
        "direction": "buy",
        "order_type": "market"
    }
    context = {
        "ticker": "LQDA",
        "close": 36.5,
        "gap_pct": 35.0,
        "is_opening_window": True,
        "is_ema3_1h_ascending": True,
        "ema3_slope_1h": 0.05,
        "is_ema3_above_ema9": True,
        "ema_20_1d": 25.0,
        "ema_50_1d": 20.0,
        "ema_3_1d": 30.0,
        "ema_9_1d": 28.0,
        "ema_3": 36.0,
        "ema_9": 34.0,
        "ema_20": 30.0
    }
    eval_res = re_instance.evaluate_rule(rule, context)
    assert eval_res["triggered"] is False
    assert any("Gap Exhaustion Shield" in f for f in eval_res["failures"])


@patch("app.stocks.live_1h_candle_service.get_live_1h_candle_and_sipv", return_value={"is_ema3_1h_ascending": True, "is_ema3_above_ema9": True})
@patch("app.stocks.stocks_order_executor.get_supabase")
def test_order_executor_blocks_gap_exhaustion(mock_sb, mock_1h):
    from app.stocks.stocks_order_executor import execute_market_order
    mock_instance = MagicMock()
    mock_sb.return_value = mock_instance
    mock_instance.table().select().eq().order().limit().execute.return_value.data = []

    res = execute_market_order(
        ticker="LQDA",
        direction="buy",
        rule_code="PRO_BUY_MKT",
        context={
            "ticker": "LQDA",
            "price": 36.5,
            "gap_pct": 35.0,
            "is_opening_window": True,
            "now_dt": datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc),
        },
        rule={"rule_code": "PRO_BUY_MKT", "direction": "buy"}
    )
    assert res["success"] is False
    assert "Bloqueo Gap Exhaustion" in res["reason"]


@patch("app.stocks.diagnostic_validator.can_operate_pre_trade", return_value=(True, "OK", {}))
@patch("app.stocks.live_1h_candle_service.get_live_1h_candle_and_sipv", return_value={"is_ema3_1h_ascending": True, "is_ema3_above_ema9": True})
@patch("app.stocks.stocks_order_executor._get_config", return_value={"total_capital": 10000, "max_pct_per_trade": 0.1, "max_total_risk_pct": 0.5, "max_positions": 5, "paper_mode": True})
@patch("app.stocks.stocks_order_executor.get_supabase")
def test_order_executor_tranche_abort_on_red_candle(mock_sb, mock_cfg, mock_1h, mock_diag):
    from app.stocks.stocks_order_executor import execute_market_order
    mock_instance = MagicMock()
    mock_sb.return_value = mock_instance
    mock_instance.table().select().eq().order().limit().execute.return_value.data = []
    mock_instance.table().select().eq().execute.return_value.data = []

    res = execute_market_order(
        ticker="WFF",
        direction="buy",
        rule_code="SWEET_SPOT_BUY",
        context={
            "ticker": "WFF",
            "price": 10.0,
            "gap_pct": 12.0,
            "is_opening_window": False,
            "tranche_step": 2,
            "prev_candle_green": False,
            "open_ge_close": True,
            "now_dt": datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc),
        },
        rule={"rule_code": "SWEET_SPOT_BUY", "direction": "buy"}
    )
    assert res["success"] is False
    assert "Vela previa fue ROJA" in res["reason"]


@patch("app.stocks.diagnostic_validator.can_operate_pre_trade", return_value=(True, "OK", {}))
@patch("app.stocks.live_1h_candle_service.get_live_1h_candle_and_sipv", return_value={"is_ema3_1h_ascending": True, "is_ema3_above_ema9": True})
@patch("app.stocks.stocks_order_executor._get_config", return_value={"total_capital": 10000, "max_pct_per_trade": 0.1, "max_total_risk_pct": 0.5, "max_positions": 5, "paper_mode": True})
@patch("app.stocks.stocks_order_executor.get_supabase")
def test_order_executor_tranche_abort_on_down_gap(mock_sb, mock_cfg, mock_1h, mock_diag):
    from app.stocks.stocks_order_executor import execute_market_order
    mock_instance = MagicMock()
    mock_sb.return_value = mock_instance
    mock_instance.table().select().eq().order().limit().execute.return_value.data = []
    mock_instance.table().select().eq().execute.return_value.data = []

    res = execute_market_order(
        ticker="WFF",
        direction="buy",
        rule_code="SWEET_SPOT_BUY",
        context={
            "ticker": "WFF",
            "price": 10.0,
            "gap_pct": 12.0,
            "is_opening_window": False,
            "tranche_step": 2,
            "prev_candle_green": True,
            "open_ge_close": False,
            "now_dt": datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc),
        },
        rule={"rule_code": "SWEET_SPOT_BUY", "direction": "buy"}
    )
    assert res["success"] is False
    assert "Open < Close anterior" in res["reason"]


