import pytest
import pandas as pd
import numpy as np
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult

def _create_sample_df_15m(n=25, base_price=1.1700, trend='down', rsi_val=50.0):
    prices = []
    current = base_price
    for i in range(n):
        if trend == 'down':
            current -= 0.0002
            o = current + 0.0001
            c = current
            h = o + 0.00005
            l = c - 0.00005
        elif trend == 'up':
            current += 0.0002
            o = current - 0.0001
            c = current
            h = c + 0.00005
            l = o - 0.00005
        else:
            o = current
            c = current
            h = current + 0.0001
            l = current - 0.0001
        prices.append({'open': o, 'high': h, 'low': l, 'close': c, 'atr': 0.0005, 'fibonacci_zone': 0})
    
    df = pd.DataFrame(prices)
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    std = df['close'].rolling(20).std().fillna(0.0005)
    df['lower_2'] = df['ema20'] - (std * 2)
    df['upper_2'] = df['ema20'] + (std * 2)
    df['rsi'] = rsi_val
    return df

class TestAduanaEntryGuards:
    def setup_method(self):
        self.validator = AduanaValidator(oraculo_manager=None)

    def test_aduana_blocks_short_when_rsi_oversold(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=28.0)
        market_data = {
            'df_15m': df_15m,
            'price': 1.16740,
            'rsi_15m': 28.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='EURUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data,
            strategy='Aa61_short'
        )
        assert res.approved is False
        assert res.rule_triggered == 'RSI_EXHAUSTION_OVERSOLD'
        assert 'sobrevendid' in res.reason.lower()

    def test_aduana_blocks_long_when_rsi_overbought(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=72.0)
        market_data = {
            'df_15m': df_15m,
            'price': 1.17500,
            'rsi_15m': 72.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='EURUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Aa61'
        )
        assert res.approved is False
        assert res.rule_triggered == 'RSI_EXHAUSTION_OVERBOUGHT'
        assert 'sobrecomprad' in res.reason.lower()

    def test_aduana_blocks_short_without_pullback_to_ema9(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=45.0)
        df_15m.loc[df_15m.index[-1], 'ema9'] = 1.16800
        df_15m.loc[df_15m.index[-1], 'high'] = 1.16745
        df_15m.loc[df_15m.index[-1], 'close'] = 1.16740
        
        market_data = {
            'df_15m': df_15m,
            'price': 1.16740,
            'rsi_15m': 45.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='EURUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data,
            strategy='Aa61_short'
        )
        assert res.approved is False
        assert res.rule_triggered == 'NO_PULLBACK_OVEREXTENDED'

    def test_aduana_blocks_short_when_bb_lower_curving_up(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=45.0)
        df_15m.loc[df_15m.index[-3], 'lower_2'] = 1.16650
        df_15m.loc[df_15m.index[-2], 'lower_2'] = 1.16670
        df_15m.loc[df_15m.index[-1], 'lower_2'] = 1.16685
        df_15m.loc[df_15m.index[-1], 'ema9'] = 1.16750
        df_15m.loc[df_15m.index[-1], 'high'] = 1.16755
        df_15m.loc[df_15m.index[-1], 'close'] = 1.16745

        market_data = {
            'df_15m': df_15m,
            'price': 1.16745,
            'rsi_15m': 45.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='EURUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data,
            strategy='Aa61_short'
        )
        assert res.approved is False
        assert res.rule_triggered == 'BOLLINGER_BAND_CURVING_AGAINST'

    def test_aduana_blocks_after_consecutive_red_candles(self):
        df_15m = _create_sample_df_15m(n=25, trend='down', rsi_val=45.0)
        df_15m.loc[df_15m.index[-1], 'ema9'] = 1.16700
        df_15m.loc[df_15m.index[-1], 'open'] = 1.16710
        df_15m.loc[df_15m.index[-1], 'high'] = 1.16715
        df_15m.loc[df_15m.index[-1], 'close'] = 1.16695
        df_15m.loc[df_15m.index[-1], 'lower_2'] = 1.16600
        df_15m.loc[df_15m.index[-2], 'lower_2'] = 1.16620
        df_15m.loc[df_15m.index[-3], 'lower_2'] = 1.16640

        market_data = {
            'df_15m': df_15m,
            'price': 1.16695,
            'rsi_15m': 45.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='EURUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data,
            strategy='AaHot'
        )
        assert res.approved is False
        assert res.rule_triggered == 'CONSECUTIVE_CANDLES_EXHAUSTION'

    def test_aduana_allows_rebound_strategy_at_bottom(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=28.0)
        market_data = {
            'df_15m': df_15m,
            'price': 1.16700,
            'rsi_15m': 28.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='EURUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Dd11_15m'
        )
        assert res.rule_triggered != 'RSI_EXHAUSTION_OVERBOUGHT'
        assert res.rule_triggered != 'RSI_EXHAUSTION_OVERSOLD'
