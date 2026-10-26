import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from app.stocks.aduana_gap_runner_engine import evaluate_gap_runner_entry_tranches


def _build_5m_df(bars, start_time="2026-10-23 13:35:00"):
    idx = pd.date_range(start_time, periods=len(bars), freq="5min", tz="UTC")
    return pd.DataFrame(bars, index=idx)


def test_buy_stop_blocks_when_high_below_open_plus_1pct():
    """
    Si la acción abre a $10.00 y el máximo alcanzado es $10.05 (< $10.10 Open + 1%),
    el filtro BUY STOP bloquea la entrada.
    """
    df_5m = _build_5m_df([
        {"open": 10.00, "high": 10.04, "low": 9.98, "close": 10.02, "volume": 50000},
        {"open": 10.02, "high": 10.05, "low": 10.01, "close": 10.04, "volume": 60000},
    ])
    res = evaluate_gap_runner_entry_tranches(
        ticker="TRAP",
        df_5m=df_5m,
        df_15m=None,
        df_1h=None,
        gap_pct=12.0,
        config={"skip_time_window_check": True}
    )
    assert res["should_enter"] is False
    assert "Filtro BUY STOP (Open + 1%)" in res["reason"]
    assert res["trigger_price"] == 10.10


def test_buy_stop_allows_when_high_reaches_open_plus_1pct():
    """
    Si la acción abre a $10.00 y supera $10.10 (+1%), con vela 1 verde y sobre VWAP,
    autoriza la entrada con order_type='stop' y trigger_price=10.10.
    """
    df_5m = _build_5m_df([
        {"open": 10.00, "high": 10.15, "low": 9.98, "close": 10.12, "volume": 80000},
        {"open": 10.12, "high": 10.25, "low": 10.10, "close": 10.22, "volume": 95000},
    ])
    res = evaluate_gap_runner_entry_tranches(
        ticker="RUNNER",
        df_5m=df_5m,
        df_15m=None,
        df_1h=None,
        gap_pct=15.0,
        config={"skip_time_window_check": True}
    )
    assert res["should_enter"] is True
    assert res["order_type"] == "stop"
    assert res["trigger_price"] == 10.10
    assert res["open_day"] == 10.00
    assert res["rule_code"] == "GAP_TRANCHE_1"


def test_vwap_filter_blocks_price_below_vwap():
    """
    Filtro Maestro VWAP: bloquea cualquier compra si el precio actual cae bajo VWAP.
    """
    df_5m = _build_5m_df([
        {"open": 10.00, "high": 10.50, "low": 10.00, "close": 10.40, "volume": 200000},
        {"open": 10.40, "high": 10.42, "low": 9.70, "close": 9.80, "volume": 50000},
    ])
    res = evaluate_gap_runner_entry_tranches(
        ticker="DUMP",
        df_5m=df_5m,
        df_15m=None,
        df_1h=None,
        gap_pct=14.0,
        config={"skip_time_window_check": True}
    )
    assert res["should_enter"] is False
    assert "Filtro Maestro VWAP" in res["reason"]


def test_orb_filter_blocks_giant_gap_red_candle1():
    """
    Filtro ORB en Gaps > 30%: si la primera vela es roja de descarga y no se ha recuperado
    el ORB High, bloquea la compra.
    """
    df_5m = _build_5m_df([
        {"open": 10.00, "high": 10.30, "low": 9.10, "close": 9.20, "volume": 300000},
        {"open": 9.20, "high": 9.60, "low": 9.15, "close": 9.55, "volume": 100000},
        {"open": 9.55, "high": 9.95, "low": 9.50, "close": 9.90, "volume": 120000},
    ])
    res = evaluate_gap_runner_entry_tranches(
        ticker="GAPCRAP",
        df_5m=df_5m,
        df_15m=None,
        df_1h=None,
        gap_pct=35.0,
        config={"skip_time_window_check": True, "skip_vwap_check": True}
    )
    assert res["should_enter"] is False
    assert "Filtro ORB Gaps > 30%" in res["reason"]


@patch("app.stocks.stocks_order_executor.get_supabase")
@patch("app.stocks.stocks_order_executor.is_ib_bridge_alive", return_value=True)
@patch("app.stocks.stocks_order_executor._send_telegram_sync")
def test_place_stop_order_creates_stp_payload(mock_tg, mock_ib_alive, mock_get_sb):
    """
    Verifica que place_stop_order registre una orden con order_type='stop' y trigger_price=Open*1.01
    en estado 'pending' cuando el puente IBKR APOLO está activo.
    """
    from app.stocks.stocks_order_executor import place_stop_order

    mock_sb = MagicMock()
    mock_get_sb.return_value = mock_sb

    # Mock config & open positions
    mock_cfg_res = MagicMock()
    mock_cfg_res.data = [{"total_capital": 3000, "max_pct_per_trade": 0.25, "max_total_risk_pct": 0.80, "paper_trading": True}]
    mock_pos_res = MagicMock()
    mock_pos_res.data = []

    def table_side_effect(name):
        t = MagicMock()
        if name == "stocks_config":
            t.select.return_value.limit.return_value.execute.return_value = mock_cfg_res
        elif name == "stocks_positions":
            t.select.return_value.eq.return_value.execute.return_value = mock_pos_res
        elif name == "stocks_orders":
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "ord-123"}])
        return t

    mock_sb.table.side_effect = table_side_effect

    res = place_stop_order(
        ticker="AIOK",
        direction="buy",
        rule_code="GAP_TRANCHE_1",
        context={"price": 5.61, "day_open_price": 5.55},
        rule={"group_name": "OPEN_GAP_RUNNER"}
    )

    assert res["success"] is True
    assert res["order_type"] == "stop"
    assert res["trigger_price"] == 5.61  # round(5.55 * 1.01, 2) = 5.61
    assert res["ib_routed"] is True
