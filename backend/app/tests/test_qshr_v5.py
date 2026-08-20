import unittest
import pandas as pd
import numpy as np
from app.strategy.quantum_squeeze_hedge import (
    calculate_5m_velocity,
    calculate_sipv_indicator,
    detect_bollinger_squeeze_expansion,
    detect_squeeze_pinch_charging,
    calculate_asymmetric_hedge_lots,
    scan_squeeze_opportunities,
    evaluate_qshr_trailing_and_exit,
    evaluate_qshr_hedge_signal,
    get_qshr_hud_status
)
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult

class TestQSHRv5(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        dates_5m = pd.date_range('2026-08-19 06:00', periods=30, freq='5min')
        prices = [1.3500 + i*0.0002 for i in range(25)] + [1.3550, 1.3560, 1.3580, 1.3610, 1.3650]
        self.df_5m = pd.DataFrame({
            'time': dates_5m,
            'open': [p - 0.0001 for p in prices],
            'high': [p + 0.0003 for p in prices],
            'low': [p - 0.0002 for p in prices],
            'close': prices,
            'volume': [1000 + i*50 for i in range(25)] + [3000, 4500, 6000, 8000, 12000]
        })
        self.df_5m['basis'] = self.df_5m['close'].rolling(20).mean()
        std = self.df_5m['close'].rolling(20).std()
        self.df_5m['upper_1'] = self.df_5m['basis'] + 2.0 * std
        self.df_5m['lower_1'] = self.df_5m['basis'] - 2.0 * std

        dates_15m = pd.date_range('2026-08-19 04:00', periods=25, freq='15min')
        prices_15m = [1.3480 + i*0.0005 for i in range(25)]
        self.df_15m = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 0.0003 for p in prices_15m],
            'high': [p + 0.0008 for p in prices_15m],
            'low': [p - 0.0004 for p in prices_15m],
            'close': prices_15m,
            'volume': [5000 + i*200 for i in range(20)] + [15000, 25000, 35000, 45000, 60000]
        })

    def test_velocity_5m(self):
        vel = calculate_5m_velocity(self.df_5m)
        self.assertIn('v_5m_score', vel)
        self.assertTrue(vel['v_5m_score'] > 0)
        self.assertEqual(vel['direction'], 'BULLISH_SURGE')

    def test_sipv_15m(self):
        sipv = calculate_sipv_indicator(self.df_15m)
        self.assertIn('sipv_score', sipv)
        self.assertIn('vol_ratio_15m', sipv)

    def test_detect_squeeze_expansion(self):
        sq = detect_bollinger_squeeze_expansion(self.df_5m)
        self.assertIn('is_expanding', sq)
        self.assertIn('bandwidth_ratio', sq)

    def test_detect_squeeze_pinch_charging(self):
        pinch = detect_squeeze_pinch_charging(self.df_5m)
        self.assertIn('is_charging', pinch)
        self.assertIn('pinch_ratio', pinch)

    def test_calculate_asymmetric_hedge_lots(self):
        # 0.01 base lots con V_5m >= 3.0 -> escala a 0.02 (2x / 1.5x)
        lots_1 = calculate_asymmetric_hedge_lots(0.01, 3.2)
        self.assertEqual(lots_1, 0.02)
        # 0.04 base lots con V_5m >= 3.0 -> 0.06 (1.5x)
        lots_2 = calculate_asymmetric_hedge_lots(0.04, 3.2)
        self.assertEqual(lots_2, 0.06)

    def test_scale_out_partial_exit(self):
        # Posición de 0.04 lots con salida SIPV Climax -> cierra 0.02 y deja 0.02
        pos = {'symbol': 'GBPUSD', 'side': 'long', 'lots': 0.04, 'entry_price': 1.3500}
        res = evaluate_qshr_trailing_and_exit(pos, self.df_5m, self.df_15m, 1.3650, 'GBPUSD')
        self.assertIsNotNone(res)
        if res and res.get('action') == 'partial_close_market_active_sipv':
            self.assertEqual(res['close_lots'], 0.02)
            self.assertEqual(res['remaining_lots'], 0.02)

    def test_qshr_hud_status(self):
        hud = get_qshr_hud_status('GBPUSD', self.df_5m, self.df_15m, {'side': 'long', 'lots': 0.02})
        self.assertIn('state_label', hud)
        self.assertIn('color', hud)

    def test_aduana_max_active_symbols(self):
        aduana = AduanaValidator()
        market_data = {
            'df_15m': self.df_15m,
            'df_5m': self.df_5m,
            'squeeze_velocity': 3.2,
            'open_symbols': ['GBPUSD'],
            'max_active_symbols': 1
        }
        res = aduana.validate(
            symbol='EURUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_DIRECT_LONG'
        )
        self.assertFalse(res.approved)
        self.assertEqual(res.rule_triggered, 'MAX_ACTIVE_SYMBOLS_REACHED')

    def test_aduana_qshr_override(self):
        aduana = AduanaValidator()
        market_data = {
            'df_15m': self.df_15m,
            'df_5m': self.df_5m,
            'squeeze_velocity': 3.2,
            'open_symbols': ['GBPUSD'],
            'max_active_symbols': 2
        }
        res = aduana.validate(
            symbol='GBPUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_DIRECT_LONG'
        )
        self.assertTrue(res.approved)
        self.assertEqual(res.rule_triggered, 'QSHR_SQUEEZE_OVERRIDE')

if __name__ == '__main__':
    unittest.main()
