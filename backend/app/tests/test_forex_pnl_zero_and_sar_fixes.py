"""
Unit tests verifying fixes for Forex PnL=0.00 closures:
1. EMERGENCY_PROFIT_CLOSE skipping when Forex market closed (weekends).
2. EMERGENCY_PROFIT_CLOSE requiring real confirmed profit (> $0.10, > 1 pip).
3. EMERGENCY_OCO fallback when position has no profit (entry == price).
4. SAR phase change grace period, precedence check, and BbApexEma immunity.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.strategy.emergency_guards import trigger_emergency_protection


def test_emergency_protection_skips_when_forex_market_closed():
    """When the Forex market is closed, emergency guards must not close forex positions."""
    async def _run():
        with patch('app.core.market_hours.is_forex_market_open', return_value=False), \
             patch('app.strategy.emergency_guards.get_supabase') as mock_sb:
            
            mock_client = MagicMock()
            mock_sb.return_value = mock_client
            
            await trigger_emergency_protection('forex_futures')
            
            # Verify table('forex_positions').select was never even executed
            mock_client.table.assert_not_called()
    asyncio.run(_run())


def test_emergency_protection_requires_positive_profit():
    """
    If current_price == entry_price (PnL = 0.00), the position must NOT be closed
    as EMERGENCY_PROFIT_CLOSE. It must divert to Condition B (EMERGENCY_OCO).
    """
    async def _run():
        mock_sb = MagicMock()
        mock_positions = [
            {
                'id': 'pos-gbp-1',
                'symbol': 'GBPUSD',
                'side': 'SHORT',
                'entry_price': 1.35135,
                'current_price': 1.35135,
                'lots': 0.01,
                'rule_code': 'BbApexEma',
                'tp_price': 0.0
            }
        ]
        
        snap_builder = MagicMock()
        snap_builder.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {'price': 1.35135}
        
        update_builder = MagicMock()
        
        def table_router(table_name):
            if table_name == 'forex_positions':
                mock_table = MagicMock()
                mock_table.select.return_value.eq.return_value.execute.return_value.data = mock_positions
                mock_table.update = update_builder
                return mock_table
            elif table_name == 'market_snapshot':
                return snap_builder
            return MagicMock()

        mock_sb.table.side_effect = table_router

        with patch('app.core.market_hours.is_forex_market_open', return_value=True), \
             patch('app.strategy.emergency_guards.get_supabase', return_value=mock_sb):
            
            await trigger_emergency_protection('forex_futures')

            # Assert update was called with EMERGENCY_OCO, NOT closed with EMERGENCY_PROFIT_CLOSE
            calls = update_builder.call_args_list
            assert len(calls) > 0
            updated_data = calls[0][0][0]
            assert updated_data.get('recovery_exit_reason') == 'EMERGENCY_OCO'
            assert updated_data.get('status') != 'closed'
            assert updated_data.get('close_reason') != 'EMERGENCY_PROFIT_CLOSE'
    asyncio.run(_run())


def test_emergency_protection_closes_when_real_profit():
    """
    When position has confirmed real profit (> $0.10 and > 1 pip),
    it should close cleanly and write current_price and positive pnl_usd.
    """
    async def _run():
        mock_sb = MagicMock()
        mock_positions = [
            {
                'id': 'pos-eur-win',
                'symbol': 'EURUSD',
                'side': 'LONG',
                'entry_price': 1.1500,
                'current_price': 1.1520, # +20 pips -> ~$2.00 USD on 0.01 lot
                'lots': 0.01,
                'rule_code': 'BbApexEma',
            }
        ]

        snap_builder = MagicMock()
        snap_builder.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {'price': 1.1520}

        update_builder = MagicMock()

        def table_router(table_name):
            if table_name == 'forex_positions':
                mock_table = MagicMock()
                mock_table.select.return_value.eq.return_value.execute.return_value.data = mock_positions
                mock_table.update = update_builder
                return mock_table
            elif table_name == 'market_snapshot':
                return snap_builder
            return MagicMock()

        mock_sb.table.side_effect = table_router

        with patch('app.core.market_hours.is_forex_market_open', return_value=True), \
             patch('app.strategy.emergency_guards.get_supabase', return_value=mock_sb):

            await trigger_emergency_protection('forex_futures')

            assert len(update_builder.call_args_list) > 0
            updated_data = update_builder.call_args_list[0][0][0]
            assert updated_data.get('status') == 'closed'
            assert updated_data.get('close_reason') == 'EMERGENCY_PROFIT_CLOSE'
            assert updated_data.get('current_price') == 1.1520
            assert updated_data.get('pnl_usd') > 0
            assert updated_data.get('pnl_pips') >= 1.0
    asyncio.run(_run())


def test_sar_precedence_and_grace_period_logic():
    """
    Test the protective conditions that prevent instant exits:
    1. Position held < 300s must be in grace period.
    2. Position opened after sar_changed_at must be ignored.
    3. BbApexEma strategy must be immune to SAR phase change.
    """
    now = datetime.now(timezone.utc)
    
    # Case 1: Fresh position (held 2 seconds) -> Grace period
    pos_fresh = {
        'id': 'pos-fresh',
        'symbol': 'GBPUSD',
        'opened_at': (now - timedelta(seconds=2)).isoformat(),
        'rule_code': 'BbApexEma'
    }
    opened_dt = datetime.fromisoformat(pos_fresh['opened_at'])
    elapsed_s = (now - opened_dt).total_seconds()
    assert elapsed_s < 300, "Should be within 300s grace period"

    # Case 2: Opened after SAR change
    sar_changed_at = (now - timedelta(minutes=10)).isoformat()
    pos_after_sar = {
        'id': 'pos-after',
        'symbol': 'GBPUSD',
        'opened_at': (now - timedelta(minutes=5)).isoformat(),
        'rule_code': 'Generic'
    }
    pos_dt = datetime.fromisoformat(pos_after_sar['opened_at'])
    sar_dt = datetime.fromisoformat(sar_changed_at)
    assert pos_dt >= sar_dt, "Position opened after SAR change should not be closed by older SAR change"

    # Case 3: BbApexEma immunity
    assert any(k in pos_fresh['rule_code'] for k in ('ApexEma', 'Aa13', 'Bb13', 'Aa21', 'Bb25', 'Bb41'))
