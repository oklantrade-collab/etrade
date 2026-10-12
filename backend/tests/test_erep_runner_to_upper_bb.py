"""
Test Suite: EREP P3 Runner to Upper Bollinger Band guided by EMA3
==================================================================
Valida:
1. Retención de Runner en P3 cuando EMA3 es positiva (prohibido cerrar en P3).
2. Retención de Runner en SHORT cuando EMA3 es negativa hacia Lower BB.
3. Cierre completo (TP Clímax) al alcanzar la Banda Superior de Bollinger.
4. Cierre completo (TP Clímax) en SHORT al alcanzar la Banda Inferior de Bollinger.
5. Cierre por agotamiento si EMA3 gira en contra por encima de P3.
6. Cierre estándar en P3 si EMA3 es plana o desfavorable al momento del cruce.
7. Disparo de EREP P2 en rebote institucional EMA9 / EMA20 de 1h/4h.
8. Bloqueo preventivo de Aa12 si en 1h la EMA3 tiene pendiente negativa.
"""

import unittest
import pandas as pd
import numpy as np

from app.strategy.erep_recovery_engine import (
    evaluate_erep_entry_trigger,
    evaluate_erep_exit_trigger,
)
from app.strategy.erep_manager import (
    evaluate_erep_phase,
    detect_p2_entry_signal,
)
from app.strategy.rule_engine import (
    evaluate_rule_conditions,
    DEFAULT_RULES,
)


class TestEREPRunnerToUpperBB(unittest.TestCase):

    def setUp(self):
        # 15m DataFrame alcista: EMA3 creciente
        closes_bull = [100.0, 100.2, 100.5, 101.0, 101.8, 102.5]
        self.df_15m_bull = pd.DataFrame({
            'open': [99.8, 100.0, 100.2, 100.6, 101.2, 101.9],
            'high': [100.2, 100.4, 100.8, 101.3, 102.0, 102.8],
            'low': [99.7, 99.9, 100.1, 100.5, 101.0, 101.8],
            'close': closes_bull,
            'upper_band': [105.0] * 6,
            'lower_band': [95.0] * 6,
            'volume': [1000] * 6,
        })
        self.df_15m_bull['ema3'] = self.df_15m_bull['close'].ewm(span=3, adjust=False).mean()
        self.df_15m_bull['ema9'] = self.df_15m_bull['close'].ewm(span=9, adjust=False).mean()

        # 15m DataFrame bajista: EMA3 decreciente
        closes_bear = [102.5, 101.8, 101.0, 100.5, 100.2, 99.5]
        self.df_15m_bear = pd.DataFrame({
            'open': [102.8, 102.0, 101.3, 100.8, 100.4, 100.0],
            'high': [103.0, 102.2, 101.5, 101.0, 100.5, 100.1],
            'low': [102.2, 101.5, 100.8, 100.2, 99.8, 99.2],
            'close': closes_bear,
            'upper_band': [105.0] * 6,
            'lower_band': [95.0] * 6,
            'volume': [1000] * 6,
        })
        self.df_15m_bear['ema3'] = self.df_15m_bear['close'].ewm(span=3, adjust=False).mean()
        self.df_15m_bear['ema9'] = self.df_15m_bear['close'].ewm(span=9, adjust=False).mean()

    def test_erep_p3_runner_retention_when_ema3_positive_long(self):
        """
        Al tocar P3 en LONG, si EMA3 tiene pendiente positiva y Upper BB no ha sido tocada,
        PROHIBIDO cerrar en P3. Retener Runner hacia Upper BB y blindar SL a P3 (+buffer).
        """
        pos = {
            'id': 'pos-ada-1',
            'symbol': 'ADAUSDT',
            'side': 'long',
            'entry_price': 0.2507,
            'erep_active': True,
            'erep_phase': 3,
            'erep_p2_price': 0.2450,
            'erep_p3_avg': 0.2480,
            'upper_bb': 0.2600,
        }
        current_price = 0.2485  # Cruza P3 al alza (0.2485 >= 0.2480)

        res = evaluate_erep_exit_trigger(
            position_p1=pos,
            current_price=current_price,
            symbol='ADAUSDT',
            df_15m=self.df_15m_bull,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'hold_erep_runner_to_upper_bb')
        self.assertEqual(res['rule_code'], 'Bb33_EREP_RUNNER_UPPER_BB')
        self.assertGreaterEqual(res['new_sl'], pos['erep_p3_avg'])
        self.assertEqual(res['target_tp'], 0.2600)

        # Validar en evaluate_erep_phase (mismo comportamiento de holding)
        snap = {'upper_band': 0.2600, 'lower_band': 0.2400}
        phase_res = evaluate_erep_phase(
            position=pos,
            current_price=current_price,
            snap=snap,
            df_15m=self.df_15m_bull,
            market_type='crypto_futures',
        )
        self.assertEqual(phase_res['action'], 'hold_runner_to_bb')
        self.assertGreaterEqual(phase_res['new_sl'], pos['erep_p3_avg'])

    def test_erep_p3_runner_retention_when_ema3_negative_short(self):
        """
        Al tocar P3 en SHORT, si EMA3 tiene pendiente negativa,
        retener Runner hacia Lower BB y blindar SL a P3 (-buffer).
        """
        pos = {
            'id': 'pos-eur-short',
            'symbol': 'EURUSD',
            'side': 'short',
            'entry_price': 1.0850,
            'erep_active': True,
            'erep_phase': 3,
            'erep_p2_price': 1.0920,
            'erep_p3_avg': 1.0880,
            'lower_bb': 1.0780,
        }
        current_price = 1.0875  # Cruza P3 a la baja (1.0875 <= 1.0880)

        res = evaluate_erep_exit_trigger(
            position_p1=pos,
            current_price=current_price,
            symbol='EURUSD',
            df_15m=self.df_15m_bear,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'hold_erep_runner_to_lower_bb')
        self.assertEqual(res['rule_code'], 'Bb33_EREP_RUNNER_LOWER_BB')
        self.assertLessEqual(res['new_sl'], pos['erep_p3_avg'])
        self.assertEqual(res['target_tp'], 1.0780)

    def test_erep_p3_exit_at_upper_bollinger_band_long(self):
        """
        Si el precio alcanza la Banda Superior de Bollinger, tomar ganancia completa (TP Clímax).
        """
        pos = {
            'id': 'pos-ada-1',
            'symbol': 'ADAUSDT',
            'side': 'long',
            'entry_price': 0.2507,
            'erep_active': True,
            'erep_phase': 3,
            'erep_p3_avg': 0.2480,
            'upper_bb': 0.2600,
        }
        current_price = 0.2605  # Toca Upper BB

        res = evaluate_erep_exit_trigger(
            position_p1=pos,
            current_price=current_price,
            symbol='ADAUSDT',
            df_15m=self.df_15m_bull,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'close_erep_cluster')
        self.assertEqual(res['rule_code'], 'Bb33_EREP_CLUSTER_EXIT_UPPER_BB')

        # También verificar en evaluate_erep_phase
        snap = {'upper_band': 0.2600, 'lower_band': 0.2400}
        phase_res = evaluate_erep_phase(
            position=pos,
            current_price=current_price,
            snap=snap,
            df_15m=self.df_15m_bull,
            market_type='crypto_futures',
        )
        self.assertEqual(phase_res['action'], 'close_all')
        self.assertEqual(phase_res['close_type'], 'tp_upper_bb_runner')

    def test_erep_p3_exit_at_lower_bollinger_band_short(self):
        """
        Si el precio alcanza la Banda Inferior de Bollinger en SHORT, tomar ganancia completa.
        """
        pos = {
            'id': 'pos-eur-short',
            'symbol': 'EURUSD',
            'side': 'short',
            'entry_price': 1.0850,
            'erep_active': True,
            'erep_phase': 3,
            'erep_p3_avg': 1.0880,
            'lower_bb': 1.0780,
        }
        current_price = 1.0775  # Toca Lower BB

        res = evaluate_erep_exit_trigger(
            position_p1=pos,
            current_price=current_price,
            symbol='EURUSD',
            df_15m=self.df_15m_bear,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'close_erep_cluster')
        self.assertEqual(res['rule_code'], 'Bb33_EREP_CLUSTER_EXIT_LOWER_BB')

    def test_erep_p3_exhaustion_exit_when_ema3_turns_adverse(self):
        """
        Si la posición estaba en modo Runner y la EMA3 gira en contra por encima de P3,
        cerrar por agotamiento de momentum protegiendo la ganancia acumulada.
        """
        pos = {
            'id': 'pos-ada-runner',
            'symbol': 'ADAUSDT',
            'side': 'long',
            'entry_price': 0.2507,
            'erep_active': True,
            'erep_phase': 3,
            'erep_p3_avg': 0.2480,
            'erep_runner_active': True,
            'upper_bb': 0.2650,
        }
        current_price = 0.2530  # Por encima de P3, pero la vela giró a la baja (df_15m_bear)

        res = evaluate_erep_exit_trigger(
            position_p1=pos,
            current_price=current_price,
            symbol='ADAUSDT',
            df_15m=self.df_15m_bear,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'close_erep_cluster')
        self.assertEqual(res['rule_code'], 'Bb33_EREP_CLUSTER_EXIT_EXHAUSTION')

    def test_erep_p3_exit_standard_when_no_momentum_or_flat(self):
        """
        Si al cruzar P3 la EMA no es favorable o no hay datos de momentum,
        cerrar en Breakeven como salvaguarda estándar.
        """
        pos = {
            'id': 'pos-gbp-1',
            'symbol': 'GBPUSD',
            'side': 'short',
            'entry_price': 1.34847,
            'erep_active': True,
            'erep_phase': 3,
            'erep_p3_avg': 1.35900,
        }
        current_price = 1.35850  # Cruza P3 sin df

        res = evaluate_erep_exit_trigger(
            position_p1=pos,
            current_price=current_price,
            symbol='GBPUSD',
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'close_erep_cluster')
        self.assertEqual(res['rule_code'], 'Bb33_EREP_CLUSTER_EXIT')

    def test_erep_entry_trigger_on_ema9_4h_support(self):
        """
        Validar que EREP P2 se dispare en rebote institucional EMA9 de 4h cuando el drawdown >= 0.40%.
        """
        pos = {
            'id': 'pos-ada-knife',
            'symbol': 'ADAUSDT',
            'side': 'long',
            'entry_price': 0.2507,
            'size': 299,
        }
        current_price = 0.2494  # Drawdown = (0.2507 - 0.2494)/0.2507 = 0.52% >= 0.40%

        # df_5m con micro-rebote radar (ema3 actual >= anterior)
        df_5m = pd.DataFrame({
            'open': [0.2493, 0.2492, 0.2493],
            'high': [0.2495, 0.2494, 0.2496],
            'low': [0.2491, 0.2490, 0.2492],
            'close': [0.2493, 0.2492, 0.2495],
            'volume': [1000, 1500, 2000],
        })

        df_15m = pd.DataFrame({
            'open': [0.2505, 0.2500, 0.2495],
            'high': [0.2506, 0.2501, 0.2497],
            'low': [0.2498, 0.2493, 0.2490],
            'close': [0.2500, 0.2495, 0.2494],
            'volume': [5000, 6000, 8000],
        })

        df_4h = pd.DataFrame({
            'close': [0.2480, 0.2485, 0.2490, 0.2492, 0.2494] * 4,
        })

        snap = {
            'symbol': 'ADAUSDT',
            'ema9_4h': 0.2494,
            'ema20_4h': 0.2456,
        }

        res = evaluate_erep_entry_trigger(
            position=pos,
            df_5m=df_5m,
            df_15m=df_15m,
            current_price=current_price,
            snap=snap,
            market_type='crypto_futures',
            df_4h=df_4h,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'execute_erep_p2')
        self.assertEqual(res['side'], 'long')
        self.assertEqual(res['target_band'], 'EMA9_4H')

    def test_aa12_prevents_entry_when_1h_ema3_negative(self):
        """
        Validar que la regla de entrada Aa12 esté BLOQUEADA si en 1h la EMA3 tiene pendiente negativa.
        """
        aa12_rule = next((r for r in DEFAULT_RULES if r.get('rule_code') == 'Aa12'), None)
        self.assertIsNotNone(aa12_rule)

        # Caso A: 1h con EMA3 negativa (cuchillo cayendo como en ADAUSDT)
        market_data_knife = {
            'price_touched_lower_5_6': True,
            'reversal_confirmation_long': True,
            'bb_lower_slope_positive': True,
            'ema3_slope_1h_positive': False,  # ❌ 1h EMA3 descendente
        }
        res_blocked = evaluate_rule_conditions(aa12_rule, market_data_knife)
        self.assertFalse(res_blocked, "Aa12 no debe entrar si 1h EMA3 tiene pendiente negativa.")

        # Caso B: 1h con EMA3 positiva (rebote sano confirmado en 1h)
        market_data_safe = {
            'price_touched_lower_5_6': True,
            'reversal_confirmation_long': True,
            'bb_lower_slope_positive': True,
            'ema3_slope_1h_positive': True,   # ✅ 1h EMA3 ascendente
        }
        res_allowed = evaluate_rule_conditions(aa12_rule, market_data_safe)
        self.assertTrue(res_allowed, "Aa12 debe entrar cuando 1h EMA3 confirma soporte alcista.")


if __name__ == '__main__':
    unittest.main()
