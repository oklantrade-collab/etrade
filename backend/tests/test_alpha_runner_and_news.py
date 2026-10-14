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
