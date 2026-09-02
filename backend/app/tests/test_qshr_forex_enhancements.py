import unittest
import os
import sys
import pandas as pd
import numpy as np

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.strategy.quantum_squeeze_hedge import (
    evaluate_fib_band_virtual_sl,
    get_fib_buffer_pct,
    calculate_15m_fibonacci_levels
)


class TestFibBufferPct(unittest.TestCase):
    """Tests para la calibración de buffer porcentual por activo."""

    def test_crypto_buffer(self):
        self.assertEqual(get_fib_buffer_pct('BTCUSDT'), 0.0020)
        self.assertEqual(get_fib_buffer_pct('ETHUSDT'), 0.0020)
        self.assertEqual(get_fib_buffer_pct('SOLUSDT'), 0.0020)

    def test_gold_buffer(self):
        self.assertEqual(get_fib_buffer_pct('XAUUSD'), 0.0012)

    def test_jpy_buffer(self):
        self.assertEqual(get_fib_buffer_pct('USDJPY'), 0.0010)

    def test_gbp_buffer(self):
        self.assertEqual(get_fib_buffer_pct('GBPUSD'), 0.0010)

    def test_standard_forex_buffer(self):
        self.assertEqual(get_fib_buffer_pct('EURUSD'), 0.0008)
        self.assertEqual(get_fib_buffer_pct('AUDUSD'), 0.0008)


class TestVirtualFibSL(unittest.TestCase):
    """Tests para el Stop Loss Virtual anclado a Bandas de Fibonacci."""

    def setUp(self):
        """Crear DataFrames de 15m con datos suficientes para calcular indicadores."""
        np.random.seed(42)
        dates_15m = pd.date_range('2026-08-19 04:00', periods=30, freq='15min')

        # Escenario EURUSD: Precio base ~1.1000, final ~1.1037
        prices_eur = [1.0950 + i * 0.0003 for i in range(30)]
        self.df_15m_eur = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 0.0002 for p in prices_eur],
            'high': [p + 0.0005 for p in prices_eur],
            'low': [p - 0.0004 for p in prices_eur],
            'close': prices_eur,
            'volume': [5000 + i * 100 for i in range(30)]
        })

        # Escenario GBPUSD: Precio base ~1.2650, final ~1.2766
        prices_gbp = [1.2650 + i * 0.0004 for i in range(30)]
        self.df_15m_gbp = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 0.0003 for p in prices_gbp],
            'high': [p + 0.0008 for p in prices_gbp],
            'low': [p - 0.0005 for p in prices_gbp],
            'close': prices_gbp,
            'volume': [8000 + i * 150 for i in range(30)]
        })

        # Escenario BTCUSDT: Precio base ~60500, final ~61950
        prices_btc = [60500 + i * 50 for i in range(30)]
        self.df_15m_btc = pd.DataFrame({
            'time': dates_15m,
            'open': [p - 20 for p in prices_btc],
            'high': [p + 80 for p in prices_btc],
            'low': [p - 50 for p in prices_btc],
            'close': prices_btc,
            'volume': [100 + i * 10 for i in range(30)]
        })

    # ── LONG: SL Virtual se activa cuando el precio perfora la banda Fibonacci ──

    def test_long_sl_triggers_below_fib_floor_eurusd(self):
        """LONG EURUSD: Precio cae debajo de Fib Floor + buffer con cruce bajista EMA3 < EMA9 → cierre virtual."""
        # Crear serie con caída final para que EMA3 < EMA9
        df_down = self.df_15m_eur.copy()
        df_down['close'] = [1.1050 - i * 0.0003 for i in range(30)]
        entry_price = 1.1030
        levels = calculate_15m_fibonacci_levels(df_down, entry_price)
        fib_floor = levels['basis_15m']
        buffer = get_fib_buffer_pct('EURUSD')
        trigger_price = fib_floor * (1.0 - buffer) - 0.0005  # Debajo del SL virtual

        pos = {'side': 'long', 'entry_price': entry_price, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, df_down, trigger_price, 'EURUSD')

        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'close_virtual_fib_sl')
        self.assertEqual(result['rule_code'], 'Bb33_QSHR_FIB_VIRTUAL_SL')
        self.assertIn('Fib Floor', result['reason'])

    def test_long_no_trigger_when_ema3_above_ema9(self):
        """LONG EURUSD: Si EMA3 > EMA9 en 15m, el SL Virtual NUNCA se activa (momento alcista protegido)."""
        entry_price = 1.1030
        levels = calculate_15m_fibonacci_levels(self.df_15m_eur, entry_price)
        fib_floor = levels['basis_15m']
        buffer = get_fib_buffer_pct('EURUSD')
        trigger_price = fib_floor * (1.0 - buffer) - 0.0005

        pos = {'side': 'long', 'entry_price': entry_price, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, self.df_15m_eur, trigger_price, 'EURUSD')
        # Debe ser None porque self.df_15m_eur tiene EMA3 > EMA9
        self.assertIsNone(result)

    def test_long_no_trigger_above_fib_floor(self):
        """LONG EURUSD: Precio testea la banda pero no la perfora con buffer → no se activa."""
        df_down = self.df_15m_eur.copy()
        df_down['close'] = [1.1050 - i * 0.0003 for i in range(30)]
        entry_price = 1.1030
        levels = calculate_15m_fibonacci_levels(df_down, entry_price)
        fib_floor = levels['basis_15m']
        buffer = get_fib_buffer_pct('EURUSD')
        safe_price = fib_floor * (1.0 - buffer) + 0.0010  # Por encima del SL virtual pero menor que entry

        pos = {'side': 'long', 'entry_price': entry_price, 'lots': 0.05}
        if safe_price < entry_price:
            result = evaluate_fib_band_virtual_sl(pos, df_down, safe_price, 'EURUSD')
            self.assertIsNone(result)

    def test_long_no_trigger_when_in_profit(self):
        """LONG EURUSD: Si el precio está en ganancia, el SL Virtual no se evalúa."""
        pos = {'side': 'long', 'entry_price': 1.0900, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, self.df_15m_eur, 1.1050, 'EURUSD')
        self.assertIsNone(result)

    # ── SHORT: SL Virtual se activa cuando el precio perfora la banda Fibonacci ──

    def test_short_sl_triggers_above_fib_ceiling_gbpusd(self):
        """SHORT GBPUSD: Precio sube por encima de Fib Ceiling + buffer con EMA3 > EMA9 → cierre virtual."""
        entry_price = 1.2680  # Entry < lower_1 -> ceiling es basis
        levels = calculate_15m_fibonacci_levels(self.df_15m_gbp, entry_price)
        fib_ceiling = levels['basis_15m']
        buffer = get_fib_buffer_pct('GBPUSD')
        trigger_price = fib_ceiling * (1.0 + buffer) + 0.0010  # Por encima de ceiling + buffer

        pos = {'side': 'short', 'entry_price': entry_price, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, self.df_15m_gbp, trigger_price, 'GBPUSD')

        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'close_virtual_fib_sl')
        self.assertEqual(result['rule_code'], 'Bb33_QSHR_FIB_VIRTUAL_SL')
        self.assertIn('Fib Ceiling', result['reason'])

    def test_short_no_trigger_when_ema3_below_ema9(self):
        """SHORT GBPUSD: Si EMA3 < EMA9 en 15m, el SL Virtual NUNCA se activa (momento bajista protegido)."""
        df_down = self.df_15m_gbp.copy()
        df_down['close'] = [1.2800 - i * 0.0004 for i in range(30)]
        entry_price = 1.2680
        levels = calculate_15m_fibonacci_levels(df_down, entry_price)
        fib_ceiling = levels['basis_15m']
        buffer = get_fib_buffer_pct('GBPUSD')
        trigger_price = fib_ceiling * (1.0 + buffer) + 0.0010

        pos = {'side': 'short', 'entry_price': entry_price, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, df_down, trigger_price, 'GBPUSD')
        self.assertIsNone(result)

    def test_short_no_trigger_when_in_profit(self):
        """SHORT GBPUSD: Si el precio está en ganancia (debajo del entry), no se activa."""
        pos = {'side': 'short', 'entry_price': 1.2900, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, self.df_15m_gbp, 1.2700, 'GBPUSD')
        self.assertIsNone(result)

    # ── CRYPTO: Funciona igual con BTC ──

    def test_long_sl_triggers_btcusdt(self):
        """LONG BTC: Precio cae debajo de Fib Floor + buffer crypto con EMA3 < EMA9 → cierre virtual."""
        df_down = self.df_15m_btc.copy()
        df_down['close'] = [62000 - i * 50 for i in range(30)]
        entry_price = 61800  # Entry > upper_1 -> floor es basis
        levels = calculate_15m_fibonacci_levels(df_down, entry_price)
        fib_floor = levels['basis_15m']
        buffer = get_fib_buffer_pct('BTCUSDT')
        trigger_price = fib_floor * (1.0 - buffer) - 50  # Bien debajo del SL virtual

        pos = {'side': 'long', 'entry_price': entry_price, 'lots': 0.01}
        result = evaluate_fib_band_virtual_sl(pos, df_down, trigger_price, 'BTCUSDT')

        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'close_virtual_fib_sl')

    def test_short_sl_triggers_btcusdt(self):
        """SHORT BTC: Precio sube por encima de Fib Ceiling + buffer crypto con EMA3 > EMA9 → cierre virtual."""
        entry_price = 60800  # Entry < lower_1 -> ceiling es basis
        levels = calculate_15m_fibonacci_levels(self.df_15m_btc, entry_price)
        fib_ceiling = levels['basis_15m']
        buffer = get_fib_buffer_pct('BTCUSDT')
        trigger_price = fib_ceiling * (1.0 + buffer) + 50

        pos = {'side': 'short', 'entry_price': entry_price, 'lots': 0.01}
        result = evaluate_fib_band_virtual_sl(pos, self.df_15m_btc, trigger_price, 'BTCUSDT')

        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'close_virtual_fib_sl')

    # ── Edge cases ──

    def test_returns_none_with_no_position(self):
        result = evaluate_fib_band_virtual_sl(None, self.df_15m_eur, 1.1000, 'EURUSD')
        self.assertIsNone(result)

    def test_returns_none_with_insufficient_data(self):
        small_df = self.df_15m_eur.head(5)
        pos = {'side': 'long', 'entry_price': 1.1000, 'lots': 0.05}
        result = evaluate_fib_band_virtual_sl(pos, small_df, 1.0800, 'EURUSD')
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
