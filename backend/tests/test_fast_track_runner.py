import unittest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from app.stocks.fast_track_runner_engine import (
    evaluate_fast_track_entry,
    evaluate_fast_track_exits,
    evaluate_fast_track_reentry,
    calculate_fast_track_delta
)


class TestFastTrackRunnerEngine(unittest.TestCase):

    def setUp(self):
        # Generar datos sintéticos de 5m (20 velas)
        times_5m = [datetime(2026, 10, 13, 9, 30) + timedelta(minutes=5 * i) for i in range(25)]
        self.df_5m = pd.DataFrame({
            'open': [2.00 + 0.1 * i for i in range(25)],
            'high': [2.20 + 0.12 * i for i in range(25)],
            'low': [1.95 + 0.09 * i for i in range(25)],
            'close': [2.15 + 0.11 * i for i in range(25)],
            'volume': [600_000 + 10_000 * i for i in range(25)]
        }, index=times_5m)

        # Generar datos sintéticos de 15m (15 velas)
        times_15m = [datetime(2026, 10, 13, 9, 30) + timedelta(minutes=15 * i) for i in range(15)]
        self.df_15m = pd.DataFrame({
            'open': [2.00 + 0.3 * i for i in range(15)],
            'high': [2.50 + 0.35 * i for i in range(15)],
            'low': [1.90 + 0.28 * i for i in range(15)],
            'close': [2.40 + 0.33 * i for i in range(15)],
            'volume': [1_200_000 for _ in range(15)]
        }, index=times_15m)

        # Generar datos sintéticos de 1H (5 velas)
        times_1h = [datetime(2026, 10, 13, 9, 30) + timedelta(hours=i) for i in range(5)]
        self.df_1h = pd.DataFrame({
            'open': [2.00, 5.37, 8.20, 6.26, 4.00],
            'high': [5.62, 9.50, 8.20, 6.50, 4.20],
            'low': [1.99, 3.75, 5.66, 3.45, 3.40],
            'close': [5.37, 8.20, 6.26, 3.56, 3.50],
            'volume': [5_000_000 for _ in range(5)]
        }, index=times_1h)

    def test_01_evaluate_fast_track_entry(self):
        """Punto A: Entrada al Open con Gap moderado (+25%) y volumen fuerte."""
        res = evaluate_fast_track_entry(
            ticker="JBDI",
            df_5m=self.df_5m,
            df_15m=self.df_15m,
            df_1h=self.df_1h,
            df_1d=pd.DataFrame({'close': [2.00] * 5}), # IPO Joven
            gap_pct=25.0
        )
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['rule_code'], 'FT_RUNNER_BUY')
        self.assertEqual(res['position_tranche_pct'], 0.30)
        self.assertGreater(res['initial_stop_loss'], 0.0)

    def test_02_15m_climax_wick_exit(self):
        """Punto B.2.e: Clímax 15m con vela mayor a 9 previas y mecha superior >= 10% fuera de BB."""
        # Modificar la última vela de 15m para simular el pico de JBDI a $9.50
        df_climax_15m = self.df_15m.copy()
        df_climax_15m.iloc[-1] = {
            'open': 6.30,
            'high': 9.50,
            'low': 5.32,
            'close': 8.36, # Mecha superior: (9.50 - 8.36) = 1.14 / (9.50 - 5.32) = 27.2%
            'volume': 3_500_000
        }

        pos = {
            'ticker': 'JBDI',
            'entry_price': 2.41,
            'shares': 650,
            'stop_loss': 3.50
        }

        res = evaluate_fast_track_exits(
            position=pos,
            df_5m=self.df_5m,
            df_15m=df_climax_15m,
            df_1h=self.df_1h,
            current_price=8.50
        )
        self.assertTrue(res['should_exit'])
        self.assertEqual(res['action'], 'PARTIAL_SELL_40')
        self.assertEqual(res['pct_to_sell'], 40)
        self.assertEqual(res['shares_to_sell'], 260)
        self.assertEqual(res['rule_code'], 'FT_PARTIAL_SELL')

    def test_03_trailing_stop_update_and_hit(self):
        """Punto B.2.a: Trailing stop dinámico por pendiente ascendente de EMA9."""
        pos = {
            'ticker': 'JBDI',
            'entry_price': 2.41,
            'shares': 390,
            'stop_loss': 4.50
        }

        # 1. Comprobar actualización ascendente del SL
        res_update = evaluate_fast_track_exits(
            position=pos,
            df_5m=self.df_5m,
            df_15m=self.df_15m,
            df_1h=self.df_1h,
            current_price=6.80
        )
        self.assertTrue(res_update['should_update_sl'])
        self.assertGreater(res_update['new_stop_loss'], pos['stop_loss'])

        # 2. Comprobar ejecución cuando el precio cae y perfora el SL actualizado
        pos_with_sl = dict(pos)
        pos_with_sl['stop_loss'] = 6.40
        res_hit = evaluate_fast_track_exits(
            position=pos_with_sl,
            df_5m=self.df_5m,
            df_15m=self.df_15m,
            df_1h=self.df_1h,
            current_price=6.30
        )
        self.assertTrue(res_hit['should_exit'])
        self.assertEqual(res_hit['action'], 'FULL_EXIT')
        self.assertEqual(res_hit['rule_code'], 'FT_TRAILING_STOP_HIT')

    def test_04_pyramiding_reentry(self):
        """Punto C: Recompra inteligente en pullback 5m a EMA9 con estructura alcista 15m/1H."""
        pos = {
            'ticker': 'JBDI',
            'avg_price': 2.41,
            'shares': 300,
            'reentry_count': 0
        }

        # Simular vela de 5m que toca EMA9_5m
        df_reentry_5m = self.df_5m.copy()
        c = df_reentry_5m['close']
        ema9 = float(c.ewm(span=9, adjust=False).mean().iloc[-2])
        df_reentry_5m.iloc[-1] = {
            'open': ema9 + 0.10,
            'high': ema9 + 0.15,
            'low': ema9 - 0.02, # Toca soporte EMA9
            'close': ema9 + 0.02,
            'volume': 800_000
        }
        # DataFrame 1H con estructura de mínimos crecientes (10:20 ET en JBDI)
        df_1h_growing = pd.DataFrame({
            'open': [2.00, 3.50, 4.50],
            'high': [3.50, 5.00, 6.00],
            'low': [1.99, 3.20, 4.20], # 4.20 > 3.20 (creciente)
            'close': [3.40, 4.80, 5.80],
            'volume': [3_000_000 for _ in range(3)]
        })

        res = evaluate_fast_track_reentry(
            position=pos,
            df_5m=df_reentry_5m,
            df_15m=self.df_15m,
            df_1h=df_1h_growing,
            current_price=float(df_reentry_5m['close'].iloc[-1])
        )
        self.assertTrue(res['should_reenter'])
        self.assertEqual(res['rule_code'], 'FT_REENTRY_BUY')
        self.assertEqual(res['tranche_pct'], 0.35)
        # El stop global debe ser al menos Break-Even (>= avg_price)
        self.assertGreaterEqual(res['new_global_sl'], pos['avg_price'])

    def test_05_anti_distribution_candado(self):
        """Punto C: Candado anti-distribución bloquea recompras tras un clímax reciente (< 45m)."""
        pos = {
            'ticker': 'JBDI',
            'avg_price': 2.41,
            'shares': 300,
            'reentry_count': 0
        }

        # Clímax ocurrió hace 15 minutos
        recent_climax_time = datetime.now(timezone.utc) - timedelta(minutes=15)

        res = evaluate_fast_track_reentry(
            position=pos,
            df_5m=self.df_5m,
            df_15m=self.df_15m,
            df_1h=self.df_1h,
            current_price=6.00,
            last_climax_exit_time=recent_climax_time
        )
        # Debe ser bloqueada por riesgo de falso dip en fase de dumping
        self.assertFalse(res['should_reenter'])
        self.assertIn("Candado Anti-Distribución", res['reason'])


if __name__ == '__main__':
    unittest.main()
