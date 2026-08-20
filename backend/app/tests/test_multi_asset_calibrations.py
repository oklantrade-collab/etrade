import unittest
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from app.strategy.crypto_multi_asset_calibrations import (
    is_weekend_sniper_active,
    check_funding_rate_shield,
    evaluate_fast_short_hedge_crypto,
    calculate_notional_usd_sizing
)
from app.rebote_aduana.aduana_validator import AduanaValidator
from app.strategy.virtual_sl_recovery import calculate_hard_stop_pips

class TestMultiAssetCalibrations(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        dates = pd.date_range('2026-08-19 13:00', periods=25, freq='5min')
        prices = [64000 - i*50 for i in range(20)] + [63000, 62500, 61800, 61000, 60000]
        self.df_5m_dump = pd.DataFrame({
            'time': dates,
            'open': [p + 20 for p in prices],
            'high': [p + 30 for p in prices],
            'low': [p - 30 for p in prices],
            'close': prices,
            'volume': [1000 + i*500 for i in range(25)]
        })
        self.df_5m_dump['basis'] = self.df_5m_dump['close'].rolling(20).mean()
        std = self.df_5m_dump['close'].rolling(20).std()
        self.df_5m_dump['upper_1'] = self.df_5m_dump['basis'] + 2.0 * std
        self.df_5m_dump['lower_1'] = self.df_5m_dump['basis'] - 2.0 * std

    def test_xauusd_multi_atr_hard_stop(self):
        # XAUUSD debe tener un stop mínimo de 600 pips ($6.00 USD)
        snap = {'atr': 3.5}
        stop_pips = calculate_hard_stop_pips('XAUUSD', 'forex_futures', snap)
        self.assertGreaterEqual(stop_pips, 600.0)

    def test_crypto_weekend_sniper_detection(self):
        # Sábado a las 14:00 UTC -> Weekend Sniper ACTIVO
        dt_sat = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)
        self.assertTrue(is_weekend_sniper_active(dt_sat))

        # Domingo a las 18:00 UTC -> Weekend Sniper ACTIVO
        dt_sun = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)
        self.assertTrue(is_weekend_sniper_active(dt_sun))

        # Lunes a las 10:00 UTC -> Weekend Sniper INACTIVO
        dt_mon = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
        self.assertFalse(is_weekend_sniper_active(dt_mon))

    def test_crypto_funding_rate_shield(self):
        pos_long = {'id': 'pos-btc', 'symbol': 'BTCUSDT', 'side': 'LONG', 'size': 0.05}
        # 15:58 UTC (2 min antes del corte de las 16:00 UTC) con PnL +0.2% y funding +0.05%
        dt_pre_funding = datetime(2026, 8, 19, 15, 58, tzinfo=timezone.utc)
        res = check_funding_rate_shield('BTCUSDT', pos_long, 0.0020, 0.0005, dt_pre_funding)
        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'close_funding_shield')

    def test_crypto_fast_short_hedge(self):
        pos_long = {'id': 'pos-btc', 'symbol': 'BTCUSDT', 'side': 'LONG', 'size': 0.01}
        res = evaluate_fast_short_hedge_crypto(self.df_5m_dump, pos_long)
        self.assertIsNotNone(res)
        self.assertEqual(res['action'], 'open_fast_short_hedge')
        self.assertEqual(res['side'], 'short')

    def test_crypto_notional_usd_sizing(self):
        # BTC a $60,000 con $300 USD objetivo -> 0.005 BTC
        size_btc = calculate_notional_usd_sizing('BTCUSDT', 60000.0, target_notional_usd=300.0)
        self.assertEqual(size_btc, 0.005)

        # SOL a $75 con $300 USD objetivo -> 4.0 SOL
        size_sol = calculate_notional_usd_sizing('SOLUSDT', 75.0, target_notional_usd=300.0)
        self.assertEqual(size_sol, 4.0)

if __name__ == '__main__':
    unittest.main()
