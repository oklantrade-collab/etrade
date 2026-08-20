import unittest
import pandas as pd
import numpy as np
from app.strategy.quantum_squeeze_hedge import (
    calculate_5m_velocity,
    calculate_sipv_indicator,
    detect_bollinger_squeeze_expansion,
    calculate_cluster_stop_loss,
    evaluate_cluster_exit,
    evaluate_qshr_hedge_signal
)
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult

class TestQSHRBooster(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        dates_5m = pd.date_range('2026-08-19 06:00', periods=30, freq='5min')
        prices_up = [1.3500 + i*0.0002 for i in range(25)] + [1.3550, 1.3560, 1.3580, 1.3610, 1.3650]
        self.df_5m_bull = pd.DataFrame({
            'time': dates_5m,
            'open': [p - 0.0001 for p in prices_up],
            'high': [p + 0.0003 for p in prices_up],
            'low': [p - 0.0002 for p in prices_up],
            'close': prices_up,
            'volume': [1000 + i*50 for i in range(25)] + [3000, 4500, 6000, 8000, 12000]
        })
        self.df_5m_bull['basis'] = self.df_5m_bull['close'].rolling(20).mean()
        std = self.df_5m_bull['close'].rolling(20).std()
        self.df_5m_bull['upper_1'] = self.df_5m_bull['basis'] + 2.0 * std
        self.df_5m_bull['lower_1'] = self.df_5m_bull['basis'] - 2.0 * std

        prices_down = [1.3650 - i*0.0002 for i in range(25)] + [1.3600, 1.3590, 1.3570, 1.3540, 1.3500]
        self.df_5m_bear = pd.DataFrame({
            'time': dates_5m,
            'open': [p + 0.0001 for p in prices_down],
            'high': [p + 0.0002 for p in prices_down],
            'low': [p - 0.0003 for p in prices_down],
            'close': prices_down,
            'volume': [1000 + i*50 for i in range(25)] + [3000, 4500, 6000, 8000, 12000]
        })
        self.df_5m_bear['basis'] = self.df_5m_bear['close'].rolling(20).mean()
        std_bear = self.df_5m_bear['close'].rolling(20).std()
        self.df_5m_bear['upper_1'] = self.df_5m_bear['basis'] + 2.0 * std_bear
        self.df_5m_bear['lower_1'] = self.df_5m_bear['basis'] - 2.0 * std_bear

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

    def test_booster_long_detection(self):
        # Ya existe una posición LONG y ocurre un Breakout Alcista
        pos_long = {'id': 'pos-1', 'symbol': 'GBPUSD', 'side': 'long', 'lots': 0.01}
        res = evaluate_qshr_hedge_signal('GBPUSD', self.df_5m_bull, self.df_15m, active_position=pos_long)
        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'open_booster_long')
        self.assertEqual(res['rule_code'], 'Bb33_QSHR_BOOSTER_LONG')
        self.assertTrue(res['velocity'] >= 2.5)

    def test_booster_short_detection(self):
        # Ya existe una posición SHORT y ocurre un Breakout Bajista
        pos_short = {'id': 'pos-2', 'symbol': 'GBPUSD', 'side': 'short', 'lots': 0.01}
        res = evaluate_qshr_hedge_signal('GBPUSD', self.df_5m_bear, self.df_15m, active_position=pos_short)
        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'open_booster_short')
        self.assertEqual(res['rule_code'], 'Bb33_QSHR_BOOSTER_SHORT')

    def test_cluster_stop_loss_calculation(self):
        last_candle = self.df_5m_bull.iloc[-1]
        sl_long = calculate_cluster_stop_loss('GBPUSD', last_candle, 'long', buffer_pips=2.0)
        self.assertTrue(sl_long < float(last_candle['low']))

    def test_cluster_take_profit_sipv_15m(self):
        positions = [
            {'id': 'p-1', 'symbol': 'GBPUSD', 'side': 'long', 'lots': 0.01},
            {'id': 'p-2', 'symbol': 'GBPUSD', 'side': 'long', 'lots': 0.02}
        ]
        # Al tocar sobre-extensión alcista con clímax SIPV
        res = evaluate_cluster_exit('GBPUSD', positions, self.df_5m_bull, self.df_15m, 1.3650)
        self.assertIsNotNone(res)
        if res:
            self.assertEqual(res['action'], 'cluster_take_profit')
            self.assertEqual(len(res['position_ids']), 2)

    def test_aduana_booster_approval_and_max_positions_limit(self):
        aduana = AduanaValidator()
        
        # Caso 1: Límite no alcanzado (1 posición abierta / max 3) -> APROBADO
        market_data_ok = {
            'df_15m': self.df_15m,
            'df_5m': self.df_5m_bull,
            'squeeze_velocity': 3.2,
            'current_symbol_positions': 1,
            'max_positions_per_symbol': 3
        }
        res_ok = aduana.validate(
            symbol='GBPUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data_ok,
            strategy='Bb33_QSHR_BOOSTER_LONG'
        )
        self.assertTrue(res_ok.approved)
        self.assertEqual(res_ok.rule_triggered, 'QSHR_BOOSTER_APPROVED')

        # Caso 2: Límite alcanzado (3 posiciones abiertas / max 3) -> RECHAZADO
        market_data_limit = {
            'df_15m': self.df_15m,
            'df_5m': self.df_5m_bull,
            'squeeze_velocity': 3.2,
            'current_symbol_positions': 3,
            'max_positions_per_symbol': 3
        }
        res_limit = aduana.validate(
            symbol='GBPUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data_limit,
            strategy='Bb33_QSHR_BOOSTER_LONG'
        )
        self.assertFalse(res_limit.approved)
        self.assertEqual(res_limit.rule_triggered, 'MAX_POSITIONS_PER_SYMBOL_REACHED')

if __name__ == '__main__':
    unittest.main()
