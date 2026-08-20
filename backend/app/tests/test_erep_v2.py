import unittest
import pandas as pd
import numpy as np
from app.strategy.erep_recovery_engine import (
    calculate_erep_p2_sizing,
    calculate_erep_weighted_breakeven,
    evaluate_erep_entry_trigger,
    evaluate_erep_exit_trigger
)
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult

class TestEREPv2(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        dates_5m = pd.date_range('2026-08-19 06:00', periods=30, freq='5min')
        prices_up = [1.3500 + i*0.0002 for i in range(25)] + [1.3550, 1.3560, 1.3580, 1.3610, 1.3625]
        self.df_5m_bull = pd.DataFrame({
            'time': dates_5m,
            'open': [p - 0.0001 for p in prices_up],
            'high': [p + 0.0003 for p in prices_up],
            'low': [p - 0.0002 for p in prices_up],
            'close': prices_up,
            'volume': [1000 + i*50 for i in range(25)] + [1500, 1800, 2000, 2200, 2500]
        })
        self.df_5m_bull['basis'] = self.df_5m_bull['close'].rolling(20).mean()
        std = self.df_5m_bull['close'].rolling(20).std()
        self.df_5m_bull['upper_1'] = self.df_5m_bull['basis'] + 2.0 * std
        self.df_5m_bull['lower_1'] = self.df_5m_bull['basis'] - 2.0 * std

        dates_15m = pd.date_range('2026-08-19 04:00', periods=25, freq='15min')
        prices_15m = [1.3520 + i*0.0004 for i in range(25)]
        self.df_15m = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 0.0003 for p in prices_15m],
            'high': [p + 0.0008 for p in prices_15m],
            'low': [p - 0.0004 for p in prices_15m],
            'close': prices_15m,
            'volume': [5000 + i*200 for i in range(20)] + [15000, 25000, 35000, 45000, 60000]
        })

    def test_erep_asymmetric_sizing(self):
        # 1. Distancia corta (< 25 pips) -> 1.0x (0.01)
        q2_low = calculate_erep_p2_sizing(0.01, 15.0)
        self.assertEqual(q2_low, 0.01)

        # 2. Distancia moderada (35 pips) -> 1.5x (0.02 para lote min 0.01)
        q2_med = calculate_erep_p2_sizing(0.01, 35.0)
        self.assertEqual(q2_med, 0.02)

        # 3. Distancia profunda (> 70 pips, caso GBPUSD 1.34847) -> 3.0x (0.03 lots)
        q2_deep = calculate_erep_p2_sizing(0.01, 110.0)
        self.assertEqual(q2_deep, 0.03)

    def test_erep_weighted_breakeven_p3(self):
        # P1 = 1.34847 (Q1 = 0.01), P2 = 1.36250 (Q2 = 0.03)
        # P3 esperado = (1.34847 * 0.01 + 1.36250 * 0.03) / 0.04 = 1.35899
        p3 = calculate_erep_weighted_breakeven(1.34847, 0.01, 1.36250, 0.03, 'GBPUSD')
        self.assertAlmostEqual(p3, 1.35899, places=5)

    def test_erep_entry_trigger_short_at_upper5(self):
        # Posición atrapada en 1.34847 (-110 pips de drawdown)
        pos = {
            'id': 'pos-1',
            'symbol': 'GBPUSD',
            'side': 'short',
            'lots': 0.01,
            'entry_price': 1.34847,
            'erep_p2_price': None
        }
        res = evaluate_erep_entry_trigger(pos, self.df_5m_bull, self.df_15m, 1.36250)
        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'execute_erep_p2')
        self.assertEqual(res['p2_size'], 0.03)
        self.assertAlmostEqual(res['p3_avg'], 1.35899, places=4)

    def test_erep_exit_trigger_at_p3(self):
        # Posición con P3 = 1.35900 activa
        pos = {
            'id': 'pos-1',
            'symbol': 'GBPUSD',
            'side': 'short',
            'lots': 0.01,
            'entry_price': 1.34847,
            'erep_p2_price': 1.36250,
            'erep_p3_avg': 1.35900
        }
        # Precio actual cruza a la baja a 1.35850 <= P3 (1.35900) -> DISPARO DE SALIDA
        res = evaluate_erep_exit_trigger(pos, 1.35850, 'GBPUSD')
        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'close_erep_cluster')

    def test_aduana_erep_approval_and_squeeze_blocking(self):
        aduana = AduanaValidator()

        # Caso 1: Velocidad normal (V_5m = 1.2 < 2.5) -> APROBADO
        market_data_ok = {
            'df_15m': self.df_15m,
            'df_5m': self.df_5m_bull,
            'squeeze_velocity': 1.2
        }
        res_ok = aduana.validate(
            symbol='GBPUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data_ok,
            strategy='Bb33_EREP_RECOVERY_P2'
        )
        self.assertTrue(res_ok.approved)
        self.assertEqual(res_ok.rule_triggered, 'EREP_P2_APPROVED')

        # Caso 2: Squeeze violento en contra (V_5m = 3.2 >= 2.5) -> BLOQUEO PREVENTIVO
        market_data_squeeze = {
            'df_15m': self.df_15m,
            'df_5m': self.df_5m_bull,
            'squeeze_velocity': 3.2
        }
        res_squeeze = aduana.validate(
            symbol='GBPUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data_squeeze,
            strategy='Bb33_EREP_RECOVERY_P2'
        )
        self.assertFalse(res_squeeze.approved)
        self.assertEqual(res_squeeze.rule_triggered, 'EREP_SQUEEZE_BLOCKED')

if __name__ == '__main__':
    unittest.main()
