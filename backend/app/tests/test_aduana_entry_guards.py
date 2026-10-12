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

    def test_aduana_fullspan_divergence_approves_with_50pct_sizing(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=50.0)
        market_data = {
            'df_15m': df_15m,
            'price': 65000.0,
            'squeeze_velocity': 0.45,
            'is_divergent': True,
            'bandwidth_ratio': 1.10,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_FULLSPAN_LONG'
        )
        assert res.approved is True
        assert res.rule_triggered == 'QSHR_FULLSPAN_DIVERGENCE_APPROVED'
        assert res.detail.get('sizing_factor') == 0.5

    def test_aduana_fullspan_high_velocity_approves_with_100pct_sizing(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=50.0)
        market_data = {
            'df_15m': df_15m,
            'price': 65000.0,
            'squeeze_velocity': 2.8,
            'is_divergent': True,
            'bandwidth_ratio': 1.30,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_FULLSPAN_LONG'
        )
        assert res.approved is True
        assert res.rule_triggered == 'QSHR_FULLSPAN_HIGH_VELOCITY'
        assert res.detail.get('sizing_factor') == 1.0

    def test_aduana_fullspan_no_divergence_low_velocity_rejects(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=50.0)
        market_data = {
            'df_15m': df_15m,
            'price': 65000.0,
            'squeeze_velocity': 0.45,
            'is_divergent': False,
            'bandwidth_ratio': 1.05,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_FULLSPAN_LONG'
        )
        assert res.approved is False
        assert res.rule_triggered == 'QSHR_LOW_VELOCITY'

    def test_aduana_climax_reversal_approves(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=22.0)
        market_data = {
            'df_15m': df_15m,
            'price': 62000.0,
            'squeeze_velocity': 0.15,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_CLIMAX_LOWER6_LONG'
        )
        assert res.approved is True
        assert res.rule_triggered == 'QSHR_CLIMAX_APPROVED'
        assert res.detail.get('sizing_factor') == 1.0

    def test_aduana_crypto_vs_forex_velocity_thresholds(self):
        df_15m = _create_sample_df_15m(n=25, rsi_val=55.0)
        market_data = {
            'df_15m': df_15m,
            'price': 65000.0,
            'squeeze_velocity': 1.5,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        # En Crypto (BTCUSDT), umbral es 1.2 -> 1.5 debe aprobar
        res_crypto = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_DIRECT_LONG'
        )
        assert res_crypto.approved is True

        # En Forex (EURUSD), umbral es 2.5 -> 1.5 debe rechazar
        market_data_forex = {
            'df_15m': df_15m,
            'price': 1.1680,
            'squeeze_velocity': 1.5,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res_forex = self.validator.validate(
            symbol='EURUSD',
            side='long',
            order_type='MARKET',
            market_data=market_data_forex,
            strategy='Bb33_QSHR_DIRECT_LONG'
        )
        assert res_forex.approved is False
        assert res_forex.rule_triggered == 'QSHR_LOW_VELOCITY'

    def test_post_sl_cooldown_blocks_crypto_entry(self):
        from datetime import datetime, timezone
        from app.strategy.position_guards import register_sl_event, SL_COOLDOWN_REGISTRY
        
        # Registrar SL en BTCUSDT
        register_sl_event('BTCUSDT', 'long')
        
        df_15m = _create_sample_df_15m(n=25, rsi_val=50.0)
        market_data = {
            'df_15m': df_15m,
            'price': 60000.0,
            'squeeze_velocity': 3.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_DIRECT_LONG'
        )
        assert res.approved is False
        assert res.rule_triggered == 'POST_SL_COOLDOWN_ACTIVE'
        assert 'enfriamiento post-sl' in res.reason.lower()

        # Limpiar registro para otras pruebas
        SL_COOLDOWN_REGISTRY.clear()

    def test_post_sl_cooldown_expires_after_45m(self):
        from datetime import datetime, timezone, timedelta
        from app.strategy.position_guards import SL_COOLDOWN_REGISTRY
        
        # Simular SL ocurrido hace 46 minutos
        SL_COOLDOWN_REGISTRY['BTCUSDT_ANY'] = datetime.now(timezone.utc) - timedelta(minutes=46)
        SL_COOLDOWN_REGISTRY['BTCUSDT_any'] = datetime.now(timezone.utc) - timedelta(minutes=46)
        
        df_15m = _create_sample_df_15m(n=25, rsi_val=50.0)
        market_data = {
            'df_15m': df_15m,
            'price': 60000.0,
            'squeeze_velocity': 3.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_DIRECT_LONG'
        )
        assert res.approved is True
        
        SL_COOLDOWN_REGISTRY.clear()

    def test_post_sl_cooldown_bypass_for_erep_and_booster(self):
        from datetime import datetime, timezone
        from app.strategy.position_guards import register_sl_event, SL_COOLDOWN_REGISTRY
        
        register_sl_event('BTCUSDT', 'long')
        
        df_15m = _create_sample_df_15m(n=25, rsi_val=50.0)
        market_data = {
            'df_15m': df_15m,
            'price': 60000.0,
            'squeeze_velocity': 3.0,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        # Estrategia EREP debe hacer bypass al cooldown
        res_erep = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_EREP_RECOVERY'
        )
        assert res_erep.rule_triggered != 'POST_SL_COOLDOWN_ACTIVE'
        
        # Estrategia BOOSTER debe hacer bypass al cooldown
        res_booster = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_BOOSTER_LONG'
        )
        assert res_booster.rule_triggered != 'POST_SL_COOLDOWN_ACTIVE'
        
        SL_COOLDOWN_REGISTRY.clear()

    def test_aduana_macro_trend_filter_blocks_counter_trend(self):
        # Crear df_15m con tendencia bajista (close cayendo -> EMA20 < EMA50)
        df_15m = _create_sample_df_15m(n=35, rsi_val=50.0)
        df_15m['close'] = [60000.0 - i * 100 for i in range(len(df_15m))]
        market_data = {
            'df_15m': df_15m,
            'price': 56500.0,
            'squeeze_velocity': 2.5,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        # Intentar LONG en tendencia bajista -> debe ser rechazado
        res_long = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_MOMENTUM_LONG'
        )
        assert res_long.approved is False
        assert res_long.rule_triggered == 'MACRO_TREND_DISCORDANT'

        # Intentar SHORT en tendencia bajista -> debe ser aprobado
        res_short = self.validator.validate(
            symbol='BTCUSDT',
            side='short',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_MOMENTUM_SHORT'
        )
        assert res_short.approved is True

    def test_aduana_macro_trend_filter_bypasses_climax(self):
        # Tendencia bajista (EMA20 < EMA50)
        df_15m = _create_sample_df_15m(n=35, rsi_val=22.0)
        df_15m['close'] = [60000.0 - i * 100 for i in range(len(df_15m))]
        market_data = {
            'df_15m': df_15m,
            'price': 56500.0,
            'squeeze_velocity': 0.5,
            'open_symbols': [],
            'max_active_symbols': 3
        }
        # Climax LONG en piso extremo debe ser aprobado incluso con EMA20 < EMA50
        res = self.validator.validate(
            symbol='BTCUSDT',
            side='long',
            order_type='MARKET',
            market_data=market_data,
            strategy='Bb33_QSHR_CLIMAX_LOWER6_LONG'
        )
        assert res.approved is True
        assert res.rule_triggered == 'QSHR_CLIMAX_APPROVED'



