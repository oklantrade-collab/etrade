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
    get_qshr_hud_status,
    calculate_hedge_sl
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

    def test_upper_wick_rejection(self):
        # Crear vela con mecha superior del 40% (rechazo en techo)
        df_wick = self.df_5m.copy()
        df_wick.iloc[-1, df_wick.columns.get_loc('high')] = 1.3750
        df_wick.iloc[-1, df_wick.columns.get_loc('close')] = 1.3650
        df_wick.iloc[-1, df_wick.columns.get_loc('open')] = 1.3600
        df_wick.iloc[-1, df_wick.columns.get_loc('low')] = 1.3590
        # High=1.3750, Close=1.3650, Open=1.3600, Low=1.3590 -> Range=0.0160, UpperWick=0.0100 (62.5%)
        res = scan_squeeze_opportunities('GBPUSD', df_wick, self.df_15m, 'forex_futures')
        # Debe ser rechazado por mecha superior excesiva o retornar None
        if res:
            self.assertNotEqual(res.get('action'), 'open_direct_long', "No debe abrir DIRECT_LONG con mecha superior de rechazo")

    def test_early_invalidation_cut_long(self):
        # Crear un escenario donde el LONG entró en 1.3650 y el precio cayó por debajo de basis (1.3550) con EMA3 < EMA9
        df_bearish_fall = self.df_5m.copy()
        df_bearish_fall.iloc[-1, df_bearish_fall.columns.get_loc('close')] = 1.3520
        df_bearish_fall.iloc[-1, df_bearish_fall.columns.get_loc('open')] = 1.3580
        df_bearish_fall['ma3'] = 1.3530
        df_bearish_fall['ma9'] = 1.3560
        df_bearish_fall['basis'] = 1.3550

        pos_long = {
            'id': 'pos-long-trap',
            'symbol': 'GBPUSD',
            'side': 'long',
            'entry_price': 1.3650,
            'lots': 0.01,
            'status': 'open'
        }
        res = evaluate_qshr_hedge_signal('GBPUSD', df_bearish_fall, self.df_15m, active_position=pos_long)
        self.assertIsNotNone(res)
        self.assertIn(res.get('action'), ('close_original_long', 'close_and_flip_short'), "Debe cortar la pérdida del LONG temprano ante ruptura fallida")

    def test_calculate_hedge_sl_crypto_buffer(self):
        # En BTCUSDT a 60,000, el buffer debe ser de al menos 0.8% (~480 USD) y no 0.0002
        candle_btc = pd.Series({
            'open': 59800.0,
            'high': 60500.0,
            'low': 59500.0,
            'close': 60000.0,
            'atr': 400.0
        })
        sl_long = calculate_hedge_sl(candle_btc, 'long', 'BTCUSDT')
        sl_dist = 60000.0 - sl_long
        self.assertGreater(sl_dist, 450.0, f"SL dist {sl_dist} debe ser mayor a 450 USD para tolerar ruido")
        self.assertLess(sl_long, 59500.0, "SL long debe estar debajo del low de la vela con buffer de seguridad")

if __name__ == '__main__':
    unittest.main()

