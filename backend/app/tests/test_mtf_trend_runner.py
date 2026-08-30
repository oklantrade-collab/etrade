import sys
import os
import unittest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.strategy.profit_capture import evaluate_mtf_trend_guard


class TestMTFTrendRunner(unittest.TestCase):

    def setUp(self):
        """Crear series de velas sintéticas de 15m y 5m para pruebas cuantitativas."""
        np.random.seed(42)
        dates_15m = pd.date_range('2026-08-28 06:00', periods=25, freq='15min')
        dates_5m = pd.date_range('2026-08-28 09:00', periods=30, freq='5min')

        # ── 1. Escenario 15m Alcista Fuerte (LONG) ──
        prices_long_strong = [1.1000 + i * 0.0004 for i in range(25)]
        self.df_15m_long_strong = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 0.0002 for p in prices_long_strong],
            'high': [p + 0.0005 for p in prices_long_strong],
            'low': [p - 0.0003 for p in prices_long_strong],
            'close': prices_long_strong,
            'volume': [5000 + i * 100 for i in range(25)]
        })

        # ── 2. Escenario 15m Bajista Fuerte (SHORT) ──
        prices_short_strong = [1.1100 - i * 0.0004 for i in range(25)]
        self.df_15m_short_strong = pd.DataFrame({
            'time': dates_15m,
            'open': [p + 0.0002 for p in prices_short_strong],
            'high': [p + 0.0004 for p in prices_short_strong],
            'low': [p - 0.0005 for p in prices_short_strong],
            'close': prices_short_strong,
            'volume': [5000 + i * 100 for i in range(25)]
        })

        # ── 3. Escenario 15m con Pendiente Aplanada / Invertida ──
        prices_flat = [1.1000 + i * 0.0003 for i in range(20)] + [1.1060, 1.1058, 1.1055, 1.1050, 1.1045]
        self.df_15m_flat = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 0.0001 for p in prices_flat],
            'high': [p + 0.0003 for p in prices_flat],
            'low': [p - 0.0003 for p in prices_flat],
            'close': prices_flat,
            'volume': [5000 for _ in range(25)]
        })

        # ── 4. Escenario 5m con Quiebre Bajista (EMA3 < EMA9 y Precio < EMA20) ──
        prices_5m_breakdown = [1.1060 - i * 0.0003 for i in range(30)]
        self.df_5m_breakdown = pd.DataFrame({
            'time': dates_5m,
            'open': [p + 0.0001 for p in prices_5m_breakdown],
            'high': [p + 0.0002 for p in prices_5m_breakdown],
            'low': [p - 0.0003 for p in prices_5m_breakdown],
            'close': prices_5m_breakdown,
            'volume': [2000 for _ in range(30)]
        })

        # ── 5. Escenario 5m Sosteniendo EMA20 (Pullback Sano) ──
        prices_5m_holding = [1.1000 + i * 0.0002 for i in range(25)] + [1.1050, 1.1048, 1.1049, 1.1051, 1.1053]
        self.df_5m_holding = pd.DataFrame({
            'time': dates_5m,
            'open': [p - 0.0001 for p in prices_5m_holding],
            'high': [p + 0.0003 for p in prices_5m_holding],
            'low': [p - 0.0002 for p in prices_5m_holding],
            'close': prices_5m_holding,
            'volume': [2000 for _ in range(30)]
        })

    def test_1_long_blocks_exit_positive_slope(self):
        """1. LONG: evaluate_mtf_trend_guard bloquea la salida cuando EMA3_15m > EMA9_15m con pendiente positiva."""
        res = evaluate_mtf_trend_guard(
            side='long',
            df_15m=self.df_15m_long_strong,
            df_5m=self.df_5m_breakdown,
            current_price=1.1100,
            symbol='EURUSD',
            market_type='forex_futures',
            pnl_pips=5.0
        )
        self.assertTrue(res['should_block'])
        self.assertIn("Blindaje 15m LONG Activo", res['reason'])

    def test_2_short_blocks_exit_negative_slope(self):
        """2. SHORT: evaluate_mtf_trend_guard bloquea la salida cuando EMA3_15m < EMA9_15m con pendiente negativa."""
        res = evaluate_mtf_trend_guard(
            side='short',
            df_15m=self.df_15m_short_strong,
            df_5m=self.df_5m_holding,
            current_price=1.1000,
            symbol='EURUSD',
            market_type='forex_futures',
            pnl_pips=5.0
        )
        self.assertTrue(res['should_block'])
        self.assertIn("Blindaje 15m SHORT Activo", res['reason'])

    def test_3_long_allows_exit_flattened_slope_and_m5_reversal(self):
        """3. LONG: Autoriza la salida cuando la pendiente 15m se aplana Y en 5m EMA3 < EMA9 y Precio < EMA20."""
        res = evaluate_mtf_trend_guard(
            side='long',
            df_15m=self.df_15m_flat,
            df_5m=self.df_5m_breakdown,
            current_price=1.0970,  # Bajo EMA20 de 5m (que es ~1.1000)
            symbol='EURUSD',
            market_type='forex_futures',
            pnl_pips=4.0
        )
        self.assertFalse(res['should_block'])
        self.assertIn("Quiebre 5m LONG confirmado", res['reason'])

    def test_4_short_allows_exit_flattened_slope_and_m5_reversal(self):
        """4. SHORT: Autoriza la salida cuando la pendiente 15m se aplana Y en 5m EMA3 > EMA9 y Precio > EMA20."""
        prices_short_flat = [1.1100 - i * 0.0003 for i in range(20)] + [1.1040, 1.1042, 1.1045, 1.1048, 1.1050]
        df_15m_short_flat = pd.DataFrame({
            'time': pd.date_range('2026-08-28 06:00', periods=25, freq='15min'),
            'open': [p + 0.0001 for p in prices_short_flat],
            'high': [p + 0.0003 for p in prices_short_flat],
            'low': [p - 0.0003 for p in prices_short_flat],
            'close': prices_short_flat,
            'volume': [5000 for _ in range(25)]
        })
        res = evaluate_mtf_trend_guard(
            side='short',
            df_15m=df_15m_short_flat,
            df_5m=self.df_5m_holding,  # 5m subiendo
            current_price=1.1060,      # Sobre EMA20 de 5m
            symbol='EURUSD',
            market_type='forex_futures',
            pnl_pips=4.0
        )
        self.assertFalse(res['should_block'])
        self.assertIn("Quiebre 5m SHORT confirmado", res['reason'])

    def test_5_long_blocks_exit_flattened_slope_but_m5_holding(self):
        """5. LONG: Bloquea salida si la pendiente 15m se aplana pero la microestructura 5m sigue sobre EMA20."""
        res = evaluate_mtf_trend_guard(
            side='long',
            df_15m=self.df_15m_flat,
            df_5m=self.df_5m_holding,
            current_price=1.1055,  # Sobre EMA20 de 5m
            symbol='EURUSD',
            market_type='forex_futures',
            pnl_pips=5.5
        )
        self.assertTrue(res['should_block'])
        self.assertIn("Transición 5m LONG", res['reason'])

    def test_6_anti_giveback_triggers_at_safety_floor(self):
        """6. Anti-Giveback: Si la posición alcanzó +8 pips y retrocede a +3 pips, no bloquea y asegura salida."""
        res = evaluate_mtf_trend_guard(
            side='long',
            df_15m=self.df_15m_long_strong,
            df_5m=self.df_5m_holding,
            current_price=1.1030,
            symbol='EURUSD',
            market_type='forex_futures',
            pnl_pips=3.0,
            max_pnl_pips=8.5  # Superó los +8 pips previamente
        )
        self.assertFalse(res['should_block'])
        self.assertIn("Anti-Giveback Activado", res['reason'])

    def test_7_crypto_btc_works_identically(self):
        """7. Crypto: Funciona idénticamente con BTCUSDT evaluando porcentaje."""
        res = evaluate_mtf_trend_guard(
            side='long',
            df_15m=self.df_15m_long_strong,
            df_5m=self.df_5m_breakdown,
            current_price=62000,
            symbol='BTCUSDT',
            market_type='crypto_futures',
            pnl_pct=0.40
        )
        self.assertTrue(res['should_block'])


if __name__ == '__main__':
    unittest.main()
