"""
Unit tests verifying fixes for PnL=0.00, floating-point precision,
Cascada isolation, and non-QSHR early invalidation protection.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.execution.binance_connector import round_step_size, round_price
from app.execution.oco_builder import round_step_size as oco_round_step_size, round_price as oco_round_price
from app.cascada.cascada_manager import CascadaManager
from app.cascada.level_evaluator import check_rebote


def test_round_step_size_decimal_precision_exact():
    """
    Ensure round_step_size correctly rounds 0.74 with step 0.01 to 0.74,
    preventing the IEEE 754 bug where 0.74 % 0.01 resulted in 0.73.
    """
    test_cases = [
        (0.70, 0.01, 0.70),
        (0.71, 0.01, 0.71),
        (0.72, 0.01, 0.72),
        (0.73, 0.01, 0.73),
        (0.74, 0.01, 0.74),
        (0.75, 0.01, 0.75),
        (101.26, 0.01, 101.26),
        (0.001, 0.001, 0.001),
        (79006.4, 0.1, 79006.4),
    ]

    for qty, step, expected in test_cases:
        actual_binance = round_step_size(qty, step)
        actual_oco = oco_round_step_size(qty, step)
        assert actual_binance == expected, f"binance_connector: {qty} with step {step} expected {expected}, got {actual_binance}"
        assert actual_oco == expected, f"oco_builder: {qty} with step {step} expected {expected}, got {actual_oco}"


def test_round_price_decimal_precision():
    """Verify round_price exactness with Decimal."""
    assert round_price(101.26, 0.01) == 101.26
    assert oco_round_price(101.26, 0.01) == 101.26
    assert round_price(79008.635, 0.01) == 79008.63


def test_cascada_manager_ignores_climax_and_erep_positions():
    """
    CASCADA must strictly ignore positions belonging to CLIMAX, EREP, or QSHR,
    preventing premature closures like CASCADA_CERRAR_N2 at $0.00.
    """
    cm = CascadaManager.get_instance()

    climax_pos = {
        'id': 'pos_climax_sol',
        'symbol': 'SOLUSDT',
        'side': 'LONG',
        'rule_code': 'Bb33_QSHR_CLIMAX_5M_LOWER6_LONG',
        'status': 'open',
        'unrealized_pnl': 0.05
    }

    erep_pos = {
        'id': 'pos_erep_btc',
        'symbol': 'BTCUSDT',
        'side': 'SHORT',
        'rule_code': 'Bb33_QSHR_CLIMAX_UPPER6_SHORT',
        'erep_active': True,
        'status': 'open'
    }

    rebote_pos = {
        'id': 'pos_rebote_eur',
        'symbol': 'EURUSD',
        'side': 'LONG',
        'rule_code': 'BbReb_15m',
        'origen': 'REBOTE',
        'status': 'open',
        'unrealized_pnl': 1.50
    }

    assert cm.should_delegate_slv(climax_pos) is False
    assert cm.should_delegate_slv(erep_pos) is False
    assert cm.should_delegate_slv(rebote_pos) is True

    # When evaluate_all_cascade_positions is called, climax and erep must be filtered out
    results = cm.evaluate_all_cascade_positions([climax_pos, erep_pos], market_type='crypto')
    assert len(results) == 0, f"Expected 0 results for Climax/EREP, got {len(results)}"


def test_check_rebote_minimum_pnl_threshold():
    """
    check_rebote must reject exits when PnL is below the $0.20 threshold (e.g. $0.00 or $0.05),
    preventing micro-exits on noise.
    """
    snap = {
        'pendiente_EMA3': 'descending',
        'pendiente_EMA20': 'lateral',
        'slope_matrix': {'is_real_reversal': True}
    }

    # Case A: PnL is $0.05 (below $0.20 threshold) -> NOT rebote
    res_sub = check_rebote('long', snap, pnl_current=0.05, current_level=2)
    assert res_sub['is_rebote'] is False
    assert res_sub['reason'] == 'PNL_BELOW_MIN_THRESHOLD'

    # Case B: PnL is $0.00 -> NOT rebote
    res_zero = check_rebote('long', snap, pnl_current=0.00, current_level=2)
    assert res_zero['is_rebote'] is False

    # Case C: PnL is $1.50 (above $0.20 threshold) -> Rebote confirmed
    res_valid = check_rebote('long', snap, pnl_current=1.50, current_level=2)
    assert res_valid['is_rebote'] is True
    assert res_valid['reason'] == 'REAL_REVERSAL_CONFIRMED'
