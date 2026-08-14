"""
Unit tests for CENTINELA State Machine & Arbitrage.
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.halcon_centinela.state_machine import PositionStateTracker, CentinelaState
from app.halcon_centinela.arbitrage import arbitrate_close_signal


def test_state_transitions():
    tracker = PositionStateTracker()
    pos_id = "pos_test_123"

    # Default state is NEUTRAL
    assert tracker.get_state(pos_id) == CentinelaState.NEUTRAL

    # Score crosses 30 (> 25) -> VIGILANCIA
    s1 = tracker.transition(pos_id, score_final=-30.0, direction='long', squeeze_active=False, close_threshold=60.0, partial_range=(25.0, 60.0))
    assert s1 == CentinelaState.VIGILANCIA

    # Score reaches -65 (>= 60) without squeeze -> CIERRE_TOTAL
    s2 = tracker.transition(pos_id, score_final=-65.0, direction='long', squeeze_active=False, close_threshold=60.0, partial_range=(25.0, 60.0))
    assert s2 == CentinelaState.CIERRE_TOTAL


def test_cooldown():
    tracker = PositionStateTracker()
    pos_id = "pos_cooldown_test"

    # Not in cooldown initially
    assert tracker.is_in_cooldown(pos_id, cooldown_seconds=120) == False

    # Register close action
    tracker.register_close_action(pos_id, "CIERRE_PARCIAL")

    # Now in cooldown
    assert tracker.is_in_cooldown(pos_id, cooldown_seconds=120) == True


def test_arbitrage_logic():
    tracker = PositionStateTracker()
    
    # Position with EREP active should be blocked from CENTINELA close
    pos_erep = {'id': 'p1', 'erep_active': True}
    res = arbitrate_close_signal('CIERRE_TOTAL', pos_erep, tracker)
    assert res['execute'] == False
    assert res['blocked_by'] == 'EREP'

    # Normal position should execute
    pos_normal = {'id': 'p2', 'erep_active': False, 'recovery_mode': False}
    res_normal = arbitrate_close_signal('CIERRE_TOTAL', pos_normal, tracker)
    assert res_normal['execute'] == True
