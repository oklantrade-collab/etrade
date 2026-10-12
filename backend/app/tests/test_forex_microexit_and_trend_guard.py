import unittest
import pandas as pd
import numpy as np
from app.strategy.quantum_squeeze_hedge import evaluate_qshr_trailing_and_exit
from app.strategy.bollinger_exhaustion import check_bollinger_exhaustion
from app.strategy.capital_protection import evaluate_volatile_trailing_v2, VOLATILE_TRAILING_CONFIG

class TestForexMicroexitAndTrendGuard(unittest.TestCase):
    def setUp(self):
        # 15m data
        dates_15m = pd.date_range('2026-09-15 08:00', periods=25, freq='15min')
        prices_15m_bull = [1.3500 + i*0.0003 for i in range(25)]
        self.df_15m_bull = pd.DataFrame({
            'open': [p - 0.0002 for p in prices_15m_bull],
            'high': [p + 0.0004 for p in prices_15m_bull],
            'low': [p - 0.0003 for p in prices_15m_bull],
            'close': prices_15m_bull,
            'volume': [1000 for _ in range(25)]
        }, index=dates_15m)
        self.df_15m_bull['ema3'] = self.df_15m_bull['close'].ewm(span=3, adjust=False).mean()
        self.df_15m_bull['ema9'] = self.df_15m_bull['close'].ewm(span=9, adjust=False).mean()
        self.df_15m_bull['basis_15m'] = self.df_15m_bull['close'].rolling(20).mean()
        std = self.df_15m_bull['close'].rolling(20).std()
        self.df_15m_bull['upper_band_15m'] = self.df_15m_bull['basis_15m'] + 2.0 * std
        self.df_15m_bull['lower_band_15m'] = self.df_15m_bull['basis_15m'] - 2.0 * std

        prices_15m_bear = [1.3600 - i*0.0003 for i in range(25)]
        self.df_15m_bear = pd.DataFrame({
            'open': [p + 0.0002 for p in prices_15m_bear],
            'high': [p + 0.0003 for p in prices_15m_bear],
            'low': [p - 0.0004 for p in prices_15m_bear],
            'close': prices_15m_bear,
            'volume': [1000 for _ in range(25)]
        }, index=dates_15m)
        self.df_15m_bear['ema3'] = self.df_15m_bear['close'].ewm(span=3, adjust=False).mean()
        self.df_15m_bear['ema9'] = self.df_15m_bear['close'].ewm(span=9, adjust=False).mean()
        self.df_15m_bear['basis_15m'] = self.df_15m_bear['close'].rolling(20).mean()
        std_bear = self.df_15m_bear['close'].rolling(20).std()
        self.df_15m_bear['upper_band_15m'] = self.df_15m_bear['basis_15m'] + 2.0 * std_bear
        self.df_15m_bear['lower_band_15m'] = self.df_15m_bear['basis_15m'] - 2.0 * std_bear

        # 5m data
        dates_5m = pd.date_range('2026-09-15 12:00', periods=10, freq='5min')
        self.df_5m = pd.DataFrame({
            'open': [1.3550, 1.3555, 1.3560, 1.3565, 1.3570, 1.3575, 1.3580, 1.3585, 1.3590, 1.3588],
            'high': [1.3555, 1.3560, 1.3565, 1.3570, 1.3575, 1.3580, 1.3585, 1.3590, 1.3595, 1.3592], # high decreasing on last
            'low':  [1.3545, 1.3550, 1.3555, 1.3560, 1.3565, 1.3570, 1.3575, 1.3580, 1.3585, 1.3580],
            'close':[1.3554, 1.3559, 1.3564, 1.3569, 1.3574, 1.3579, 1.3584, 1.3589, 1.3591, 1.3585],
            'volume':[500]*10
        }, index=dates_5m)

    def test_swing_strategy_immunity_in_qshr_exit(self):
        """Posiciones de estrategias Swing (BbApexEma, Bb41) no deben ser cerradas por QSHR."""
        pos_swing = {
            'id': 'pos-apex-1',
            'symbol': 'GBPUSD',
            'side': 'long',
            'lots': 0.01,
            'entry_price': 1.3500,
            'rule_code': 'BbApexEma'
        }
        res = evaluate_qshr_trailing_and_exit(pos_swing, self.df_5m, self.df_15m_bull, 1.3590, 'GBPUSD')
        self.assertIsNone(res, "Estrategias Swing como BbApexEma deben retornar None en evaluate_qshr_trailing_and_exit")

        pos_bb41 = {
            'id': 'pos-bb41-1',
            'symbol': 'EURUSD',
            'side': 'short',
            'lots': 0.01,
            'entry_price': 1.1550,
            'rule_code': 'Bb41_reversal'
        }
        res_bb41 = evaluate_qshr_trailing_and_exit(pos_bb41, self.df_5m, self.df_15m_bear, 1.1500, 'EURUSD')
        self.assertIsNone(res_bb41, "Estrategias Bb41 deben retornar None en evaluate_qshr_trailing_and_exit")

    def test_aduana_trend_guard_blocks_long_bollinger_exhaustion(self):
        """Si EMA3 > EMA9 en 15m, close_bollinger_exhaustion debe ser bloqueado en LONG."""
        pos_qshr = {
            'id': 'pos-qshr-1',
            'symbol': 'GBPUSD',
            'side': 'long',
            'lots': 0.01,
            'entry_price': 1.3500,
            'rule_code': 'Bb33_QSHR'
        }
        last_row = self.df_15m_bull.iloc[-1]
        self.assertGreater(last_row['ema3'], last_row['ema9'])
        
        upper_bb = last_row['upper_band_15m']
        res = evaluate_qshr_trailing_and_exit(pos_qshr, self.df_5m, self.df_15m_bull, upper_bb + 0.0005, 'GBPUSD')
        if res:
            self.assertNotEqual(res.get('action'), 'close_bollinger_exhaustion')

    def test_aduana_trend_guard_blocks_short_bollinger_exhaustion(self):
        """Si EMA3 < EMA9 en 15m, close_bollinger_exhaustion debe ser bloqueado en SHORT."""
        pos_qshr = {
            'id': 'pos-qshr-2',
            'symbol': 'GBPUSD',
            'side': 'short',
            'lots': 0.01,
            'entry_price': 1.3650,
            'rule_code': 'Bb33_QSHR'
        }
        last_row = self.df_15m_bear.iloc[-1]
        self.assertLess(last_row['ema3'], last_row['ema9'])

        lower_bb = last_row['lower_band_15m']
        df_5m_bear = self.df_5m.copy()
        df_5m_bear.iloc[-1, df_5m_bear.columns.get_loc('low')] = 1.3520
        df_5m_bear.iloc[-2, df_5m_bear.columns.get_loc('low')] = 1.3510

        res = evaluate_qshr_trailing_and_exit(pos_qshr, df_5m_bear, self.df_15m_bear, lower_bb - 0.0005, 'GBPUSD')
        if res:
            self.assertNotEqual(res.get('action'), 'close_bollinger_exhaustion')

    def test_cascada_stepped_trailing_protects_profit_not_breakeven(self):
        """Trailing Stop Escalonado CASCADA debe asegurar piso real de ganancia y no breakeven plano."""
        symbol = 'GBPUSD'
        entry_price = 1.3500
        current_price = 1.3510 # Precio retrocediendo
        best_price = 1.3518    # Pico alcanzó +18 pips (Nivel 2-3 CASCADA)
        current_sl = 1.3480    # SL original abajo

        res = evaluate_volatile_trailing_v2(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            current_price=current_price,
            best_price=best_price,
            current_sl=current_sl,
            df_15m=self.df_15m_bull,
            df_5m=self.df_5m,
            atr_snap=0.0010
        )

        self.assertEqual(res['action'], 'update_sl')
        new_sl = res['sl_price']
        locked_pips = round((new_sl - entry_price) / 0.0001, 1)
        self.assertGreaterEqual(locked_pips, 8.0, f"Debe asegurar al menos 8 pips, pero dio {locked_pips:.1f} pips")
        self.assertGreater(new_sl, entry_price + 0.0007, "El SL protegido no debe ser el breakeven plano (+0.5 pips / +$0.05)")

    def test_cascada_stepped_trailing_at_level1(self):
        """Con pico de 12 pips (Nivel 1-2 CASCADA), debe asegurar al menos 5.0 pips."""
        symbol = 'GBPUSD'
        entry_price = 1.3500
        current_price = 1.3506
        best_price = 1.3512 # Pico alcanzó +12 pips
        current_sl = 1.3480

        res = evaluate_volatile_trailing_v2(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            current_price=current_price,
            best_price=best_price,
            current_sl=current_sl,
            df_15m=self.df_15m_bull,
            df_5m=self.df_5m,
            atr_snap=0.0010
        )

        self.assertEqual(res['action'], 'update_sl')
        new_sl = res['sl_price']
        locked_pips = round((new_sl - entry_price) / 0.0001, 1)
        self.assertGreaterEqual(locked_pips, 5.0, f"Debe asegurar al menos 5 pips, dio {locked_pips:.1f}")

if __name__ == '__main__':
    unittest.main()
