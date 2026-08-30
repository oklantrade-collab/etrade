import pytest
import pandas as pd
import numpy as np
from app.strategy.capital_protection import evaluate_fkr_kinetic_trailing, ProtectionState


class TestFKRKineticTrailing:
    def setup_method(self):
        dates = pd.date_range(start="2026-08-26 10:00", periods=20, freq="15min")
        closes = [1.3500 + i * 0.0005 for i in range(20)]
        self.df_15m = pd.DataFrame({
            'open_time': dates,
            'open': [c - 0.0002 for c in closes],
            'high': [c + 0.0005 for c in closes],
            'low': [c - 0.0003 for c in closes],
            'close': closes,
            'volume': [1000] * 20
        })
        self.df_15m['uma2_ema'] = self.df_15m['close'].ewm(span=9, adjust=False).mean()
        self.df_15m['ema2'] = self.df_15m['close'].ewm(span=9, adjust=False).mean()

    def test_fkr_breakeven_lock_at_5_pips(self):
        state = ProtectionState(
            position_id="test_fkr_1",
            symbol="GBPUSD",
            side="long",
            entry_price=1.35000,
            current_sl=1.34800,
            original_sl=1.34800,
            market_type="forex_futures",
            rule_code="Aa61",
            lots=0.01
        )
        
        res = evaluate_fkr_kinetic_trailing(state, current_price=1.35060, df_15m=self.df_15m)
        assert res['action'] == 'update_sl'
        assert res['new_level'] == 1
        assert res['new_sl'] == pytest.approx(1.35010, abs=1e-5)
        assert 'fkr_breakeven_lock' in res['reason']

    def test_fkr_ema9_trailing_at_10_pips(self):
        state = ProtectionState(
            position_id="test_fkr_2",
            symbol="GBPUSD",
            side="long",
            entry_price=1.35000,
            current_sl=1.35010,
            original_sl=1.34800,
            market_type="forex_futures",
            rule_code="Aa61",
            lots=0.01
        )
        
        ema9_val = float(self.df_15m['ema2'].iloc[-1])
        res = evaluate_fkr_kinetic_trailing(state, current_price=1.35120, df_15m=self.df_15m)
        assert res['action'] == 'update_sl'
        assert res['new_level'] == 2
        assert res['new_sl'] == pytest.approx(max(1.35020, ema9_val), abs=1e-5)
        assert 'fkr_ema9_15m_trail' in res['reason']

    def test_fkr_zone_traversal_upper5_target(self):
        state = ProtectionState(
            position_id="test_fkr_3",
            symbol="GBPUSD",
            side="long",
            entry_price=1.35000,
            current_sl=1.35050,
            original_sl=1.34800,
            market_type="forex_futures",
            rule_code="Aa61",
            lots=0.01
        )
        
        snap = {'upper_5': 1.35140, 'lower_5': 1.34800}
        res = evaluate_fkr_kinetic_trailing(state, current_price=1.35150, df_15m=self.df_15m, snap=snap)
        assert res['action'] == 'close_market'
        assert 'fkr_zone_traversal_upper5_tp' in res['reason']
        assert res['pips'] >= 12.0

    def test_fkr_giveback_guard_retention(self):
        state = ProtectionState(
            position_id="test_fkr_4",
            symbol="GBPUSD",
            side="long",
            entry_price=1.35000,
            current_sl=1.35050,
            original_sl=1.34800,
            market_type="forex_futures",
            rule_code="Aa61",
            lots=0.01
        )
        
        res = evaluate_fkr_kinetic_trailing(state, current_price=1.35210, df_15m=self.df_15m, pnl_pico=3.50)
        assert res['action'] == 'close_market'
        assert 'fkr_giveback_guard_30pct' in res['reason']
