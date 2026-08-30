import pytest
import pandas as pd
import numpy as np
from app.strategy.capital_protection import evaluate_rebote_kinetic_trailing, ProtectionState
from app.rebote_aduana.rebote_engine import ReboteEngine


def _create_sample_15m_df(price: float, basis: float, ema9: float, n: int = 15) -> pd.DataFrame:
    data = []
    for i in range(n):
        data.append({
            'open': price - 0.0005,
            'high': price + 0.0010,
            'low': price - 0.0010,
            'close': price,
            'ema2': ema9,
            'ema_9': ema9,
            'basis': basis,
            'ema3': basis,
            'upper_5': price + 0.0020,
            'lower_5': price - 0.0020,
            'volume': 100
        })
    return pd.DataFrame(data)


class TestReboteKineticTrailing:
    
    def test_rebote_breakeven_lock_at_5_pips(self):
        """Fase 1: Al alcanzar +5.0 pips, el SL debe bloquearse a Breakeven + 1.5 pips."""
        entry = 1.16500
        current_price = 1.16555 # +5.5 pips
        
        state = ProtectionState(
            position_id='reb_pos_1',
            symbol='EURUSD',
            side='long',
            entry_price=entry,
            current_sl=1.16350,
            original_sl=1.16350,
            market_type='forex_futures',
            rule_code='Dd11_15m',
            lots=0.01
        )
        
        df_15m = _create_sample_15m_df(price=current_price, basis=1.16700, ema9=1.16520)
        res = evaluate_rebote_kinetic_trailing(state, current_price, df_15m=df_15m)
        
        assert res['action'] == 'update_sl'
        assert res['new_sl'] == pytest.approx(entry + 0.00015, abs=1e-5) # +1.5 pips
        assert res['sl_type'] == 'breakeven'

    def test_rebote_ema9_trailing_and_profit_floor(self):
        """Fase 2: Al superar Basis o alcanzar +8.0 pips, activar EMA9 trailing con piso de ganancia."""
        entry = 1.16500
        current_price = 1.16590 # +9.0 pips
        ema9_val = 1.16560 # +6.0 pips
        
        state = ProtectionState(
            position_id='reb_pos_2',
            symbol='EURUSD',
            side='long',
            entry_price=entry,
            current_sl=1.16515,
            original_sl=1.16350,
            market_type='forex_futures',
            rule_code='Dd11_15m',
            lots=0.01
        )
        
        df_15m = _create_sample_15m_df(price=current_price, basis=1.16550, ema9=ema9_val)
        res = evaluate_rebote_kinetic_trailing(state, current_price, df_15m=df_15m)
        
        assert res['action'] == 'update_sl'
        assert res['new_sl'] == pytest.approx(ema9_val, abs=1e-5)
        assert res['sl_type'] == 'ema_trail'

    def test_rebote_zone_traversal_upper5_tp(self):
        """Fase 3: Al alcanzar +12.0 pips y tocar Upper_5, cerrar por Zone Traversal TP."""
        entry = 1.16500
        current_price = 1.16640 # +14.0 pips
        
        state = ProtectionState(
            position_id='reb_pos_3',
            symbol='EURUSD',
            side='long',
            entry_price=entry,
            current_sl=1.16560,
            original_sl=1.16350,
            market_type='forex_futures',
            rule_code='Dd11_15m',
            lots=0.01
        )
        
        snap = {'upper_5': 1.16630, 'lower_5': 1.16400}
        df_15m = _create_sample_15m_df(price=current_price, basis=1.16580, ema9=1.16600)
        res = evaluate_rebote_kinetic_trailing(state, current_price, df_15m=df_15m, snap=snap)
        
        assert res['action'] == 'close_market'
        assert 'rebote_zone_traversal_upper5_tp' in res['reason']
        assert res['pips'] == pytest.approx(14.0, abs=0.1)

    def test_rebote_giveback_guard_retention(self):
        """Giveback Guard: Asegurar el 70% del beneficio si el pico fue >= $2.50 y retrocede > 30%."""
        entry = 1.16500
        current_price = 1.16680 # +18.0 pips ($1.80) tras pico de $3.00 (30.0 pips)
        
        state = ProtectionState(
            position_id='reb_pos_4',
            symbol='EURUSD',
            side='long',
            entry_price=entry,
            current_sl=1.16560,
            original_sl=1.16350,
            market_type='forex_futures',
            rule_code='Dd11_15m',
            lots=0.01
        )
        
        df_15m = _create_sample_15m_df(price=current_price, basis=1.16580, ema9=1.16600)
        res = evaluate_rebote_kinetic_trailing(state, current_price, df_15m=df_15m, pnl_pico=3.00)
        
        assert res['action'] == 'close_market'
        assert 'rebote_giveback_guard_30pct' in res['reason']

    def test_rebote_engine_wick_rejection_filter(self):
        """ReboteEngine: Detecta mecha de absorción y rechaza caídas libres sin mecha."""
        engine = ReboteEngine()
        
        # Caso 1: Vela con mecha inferior del 40% (Absorción compradora) -> APROBADO
        df_wick_good = pd.DataFrame([{
            'open': 1.16550,
            'high': 1.16560,
            'low': 1.16500,
            'close': 1.16540 # rango=60, lower_wick=40 (66.6%)
        }, {
            'open': 1.16540,
            'high': 1.16570,
            'low': 1.16530,
            'close': 1.16560
        }])
        
        ok_long, reason_long = engine._check_wick_rejection(df_wick_good, df_wick_good, 'long')
        assert ok_long is True
        
        # Caso 2: Vela Marubozu bajista sin mecha (caída libre) -> RECHAZADO
        df_wick_bad = pd.DataFrame([{
            'open': 1.16600,
            'high': 1.16605,
            'low': 1.16500,
            'close': 1.16502 # rango=105, lower_wick=2 (1.9%)
        }, {
            'open': 1.16502,
            'high': 1.16505,
            'low': 1.16450,
            'close': 1.16452
        }])
        
        ok_bad, reason_bad = engine._check_wick_rejection(df_wick_bad, df_wick_bad, 'long')
        assert ok_bad is False
        assert 'Falling knife' in reason_bad
