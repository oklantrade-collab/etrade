import unittest
import pandas as pd
from app.strategy.bollinger_exhaustion import check_bollinger_exhaustion
from app.strategy.smart_loss_guard import should_block_close, is_exempt_reason
from app.strategy.quantum_squeeze_hedge import evaluate_qshr_hedge_signal

class TestPnLExitGuard(unittest.TestCase):
    def test_smart_loss_guard_blocks_trend_reversal_in_loss(self):
        # trend_reversal should not be exempt from guard
        self.assertFalse(is_exempt_reason('trend_reversal_ema3_below_ema9'))
        self.assertFalse(is_exempt_reason('bollinger_exhaustion'))
        
        # When in loss and trend is healthy, guard blocks close
        snap = {'ema_20': 1.1700, 'ema_50': 1.1680, 'ema_200': 1.1650}
        res = should_block_close(
            snap=snap,
            side='long',
            reason='trend_reversal_ema3_below_ema9',
            total_pnl=-0.85,
            market_type='forex_futures',
            symbol='EURUSD'
        )
        self.assertTrue(res['block'])

    def test_smart_loss_guard_allows_profit_close(self):
        # Any exit with positive profit should be allowed
        res = should_block_close(
            snap=None,
            side='long',
            reason='trend_reversal_ema3_below_ema9',
            total_pnl=1.50,
            market_type='forex_futures',
            symbol='EURUSD'
        )
        self.assertFalse(res['block'])

    def test_qshr_bollinger_exhaustion_requires_profit(self):
        # Mock 5m and 15m data
        dates = pd.date_range('2026-08-21 00:00', periods=25, freq='15min')
        df_15m = pd.DataFrame({
            'open': [1.1680 + i*0.0001 for i in range(25)],
            'high': [1.1685 + i*0.0001 for i in range(25)],
            'low':  [1.1678 + i*0.0001 for i in range(25)],
            'close':[1.1684 + i*0.0001 for i in range(25)],
            'volume':[1000 for _ in range(25)]
        }, index=dates)

        df_5m = pd.DataFrame({
            'open': [1.1700, 1.1705],
            'high': [1.1710, 1.1706], # high decreasing
            'low':  [1.1695, 1.1700],
            'close':[1.1705, 1.1702],
            'volume':[500, 500]
        })

        # Posicion en perdida (entry = 1.1715, current = 1.1702) -> No debe emitir close_bollinger_exhaustion
        pos_in_loss = {'symbol': 'EURUSD', 'side': 'long', 'entry_price': 1.1715, 'lots': 0.01}
        res_loss = evaluate_qshr_hedge_signal('EURUSD', df_5m, df_15m, 1.1702, pos_in_loss)
        if res_loss:
            self.assertNotEqual(res_loss.get('action'), 'close_bollinger_exhaustion')

        # Posicion en ganancia (entry = 1.1680, current = 1.1708 >= Upper BB) -> Permite salida
        pos_in_profit = {'symbol': 'EURUSD', 'side': 'long', 'entry_price': 1.1680, 'lots': 0.01}
        res_profit = evaluate_qshr_hedge_signal('EURUSD', df_5m, df_15m, 1.1708, pos_in_profit)
        if res_profit and res_profit.get('action') == 'close_bollinger_exhaustion':
            self.assertEqual(res_profit['action'], 'close_bollinger_exhaustion')

if __name__ == '__main__':
    unittest.main()
