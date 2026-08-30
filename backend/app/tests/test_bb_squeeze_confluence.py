"""
Unit tests for Triple-Layer Confluence:
1. Macro 1D Direction (EMA3 vs EMA9)
2. 15m Bollinger Bands Squeeze & Extreme Piercing
3. ADUANA Validation for LIMIT and MARKET
4. RADAR Bollinger Events
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.rebote_aduana.aduana_validator import AduanaValidator
from app.radar.crossover_detector import detect_bollinger_squeeze_pierce


def create_mock_df_1d(trend: str = 'bullish', n: int = 30) -> pd.DataFrame:
    """Creates a 1D dataframe with clear EMA3 vs EMA9 relationship."""
    dates = pd.date_range(end='2026-08-20', periods=n, freq='D')
    if trend == 'bullish':
        prices = np.linspace(1.2000, 1.3600, n)
    else:
        prices = np.linspace(1.3600, 1.2000, n)

    df = pd.DataFrame({
        'open': prices - 0.0010,
        'high': prices + 0.0020,
        'low': prices - 0.0020,
        'close': prices,
        'volume': 1000
    }, index=dates)
    return df


def create_mock_df_15m(pierce: str = 'none', n: int = 30) -> pd.DataFrame:
    """Creates a 15m dataframe with Bollinger bands and controlled piercing."""
    dates = pd.date_range(end='2026-08-20 12:00', periods=n, freq='15min')
    base_price = 1.3600
    prices = np.full(n, base_price) + np.sin(np.linspace(0, 3.14, n)) * 0.0020
    
    df = pd.DataFrame({
        'open': prices,
        'high': prices + 0.0002,
        'low': prices - 0.0002,
        'close': prices,
        'volume': 500
    }, index=dates)
    
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    
    if pierce == 'lower':
        sma = df['sma20'].iloc[-1]
        std = df['std20'].iloc[-1]
        lower_bb = sma - 2.0 * std
        df.iloc[-1, df.columns.get_loc('low')] = lower_bb - 0.0015
        df.iloc[-1, df.columns.get_loc('close')] = lower_bb - 0.0005
        df.iloc[-1, df.columns.get_loc('high')] = sma
    elif pierce == 'upper':
        sma = df['sma20'].iloc[-1]
        std = df['std20'].iloc[-1]
        upper_bb = sma + 2.0 * std
        df.iloc[-1, df.columns.get_loc('high')] = upper_bb + 0.0015
        df.iloc[-1, df.columns.get_loc('close')] = upper_bb + 0.0005
        df.iloc[-1, df.columns.get_loc('low')] = sma
    else:
        sma = df['sma20'].iloc[-1]
        df.iloc[-1, df.columns.get_loc('low')] = sma - 0.0001
        df.iloc[-1, df.columns.get_loc('high')] = sma + 0.0001
        df.iloc[-1, df.columns.get_loc('close')] = sma
        
    return df


class TestBBSqueezeConfluence:
    """Test suite verifying Macro 1D + 15m BB Extreme + ADUANA Guardrails."""

    def setup_method(self):
        self.validator = AduanaValidator(oraculo_manager=None)

    def test_macro_1d_bias_blocks_contrarian_long(self):
        """When 1D EMA3 < EMA9 (Bearish), LONG entries must be REJECTED."""
        df_1d_bearish = create_mock_df_1d(trend='bearish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        result = self.validator.validate(
            symbol='GBPUSD',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bearish,
                'df_15m': df_15m_lower,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is False
        assert result.rule_triggered == 'MACRO_BIAS_CONFLICT'
        assert 'sesgo macro bajista en 1D' in result.reason

    def test_macro_1d_bias_blocks_contrarian_short(self):
        """When 1D EMA3 > EMA9 (Bullish), SHORT entries must be REJECTED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_upper = create_mock_df_15m(pierce='upper')
        
        result = self.validator.validate(
            symbol='GBPUSD',
            side='sell',
            order_type='MARKET',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_upper,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is False
        assert result.rule_triggered == 'MACRO_BIAS_CONFLICT'
        assert 'sesgo macro alcista en 1D' in result.reason

    def test_bollinger_15m_extreme_required_long(self):
        """When price is inside the bands without piercing lower BB, LONG is REJECTED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_inside = create_mock_df_15m(pierce='none')
        
        result = self.validator.validate(
            symbol='GBPUSD',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_inside,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is False
        assert result.rule_triggered == 'BB_EXTREME_NOT_REACHED'
        assert 'Banda Inferior de 15m' in result.reason

    def test_bollinger_15m_extreme_approved_when_pierced_and_aligned(self):
        """When 1D is Bullish and 15m Low pierces Lower BB, LONG is APPROVED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        result = self.validator.validate(
            symbol='GBPUSD',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'current_symbol_positions': 1,
                'max_positions_per_symbol': 3,
                'open_symbols': ['GBPUSD'],
                'max_active_symbols': 1,
                'is_test': True
            }
        )
        assert result.approved is True

    def test_aduana_max_positions_per_symbol_limit_and_market(self):
        """When 3 positions already exist, BOTH LIMIT and MARKET orders are BLOCKED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        # Test LIMIT rejection at 3/3
        res_limit = self.validator.validate(
            symbol='GBPUSD',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'current_symbol_positions': 3,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert res_limit.approved is False
        assert res_limit.rule_triggered == 'MAX_POSITIONS_PER_SYMBOL_REACHED'
        assert 'LIMIT' in res_limit.reason

        # Test MARKET rejection at 3/3
        res_market = self.validator.validate(
            symbol='GBPUSD',
            side='buy',
            order_type='MARKET',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'current_symbol_positions': 3,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert res_market.approved is False
        assert res_market.rule_triggered == 'MAX_POSITIONS_PER_SYMBOL_REACHED'
        assert 'MARKET' in res_market.reason

    def test_radar_detect_bollinger_squeeze_pierce(self):
        """RADAR correctly detects cruce_bollinger_LOWER and UPPER."""
        df_lower = create_mock_df_15m(pierce='lower')
        events_lower = detect_bollinger_squeeze_pierce(df_lower)
        assert len(events_lower) == 1
        assert events_lower[0]['event_type'] == 'cruce_bollinger_LOWER'
        assert events_lower[0]['direction'] == 'bullish'

        df_upper = create_mock_df_15m(pierce='upper')
        events_upper = detect_bollinger_squeeze_pierce(df_upper)
        assert len(events_upper) == 1
        assert events_upper[0]['event_type'] == 'cruce_bollinger_UPPER'
        assert events_upper[0]['direction'] == 'bearish'

    def test_halcon_macro_weighting_confluence(self):
        """HALCON Engine correctly weights 60% 1D + 40% 4H."""
        from app.halcon_centinela.halcon_engine import HalconEngine
        engine = HalconEngine()

        df_1d_bull = create_mock_df_1d(trend='bullish')
        df_4h_bull = create_mock_df_1d(trend='bullish', n=30)
        df_15m = create_mock_df_15m(pierce='none')

        # Full Bullish Confluence
        res_bull = engine.evaluate(
            position={'id': 'p1', 'symbol': 'GBPUSD', 'direction': 'long'},
            market_data={'df_1d': df_1d_bull, 'df_4h': df_4h_bull, 'df_15m': df_15m}
        )
        assert res_bull.detail['macro_bias'] == 'BULLISH'
        assert res_bull.detail['macro_weighted_score'] > 0

        # Pullback Scenario: 1D Bullish, 4H Bearish
        df_4h_bear = create_mock_df_1d(trend='bearish', n=30)
        res_pullback = engine.evaluate(
            position={'id': 'p2', 'symbol': 'GBPUSD', 'direction': 'long'},
            market_data={'df_1d': df_1d_bull, 'df_4h': df_4h_bear, 'df_15m': df_15m}
        )
        score_1d_val = res_pullback.detail['raw_scores']['1d']
        score_4h_val = res_pullback.detail['raw_scores']['4h']
        expected_macro = round((0.60 * score_1d_val) + (0.40 * score_4h_val), 2)
        assert res_pullback.detail['macro_weighted_score'] == expected_macro
        assert res_pullback.detail['macro_weights'] == {'1d': 0.60, '4h': 0.40}

    def test_aduana_rsi_deadzone_blocked_when_not_squeeze(self):
        """When not in squeeze and RSI 15m is in deadzone (40-60), trade is REJECTED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        result = self.validator.validate(
            symbol='BTCUSDT',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'rsi_15m': 48.0,
                'is_squeeze': False,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is False
        assert result.rule_triggered == 'RSI_DEADZONE_BLOCKED'

    def test_aduana_rsi_long_rejected_above_35_when_not_squeeze(self):
        """When not in squeeze, LONG with RSI > 35 is REJECTED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        result = self.validator.validate(
            symbol='BTCUSDT',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'rsi_15m': 38.0,
                'is_squeeze': False,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is False
        assert result.rule_triggered == 'RSI_NOT_OVERSOLD'

    def test_aduana_rsi_long_approved_at_30_when_not_squeeze(self):
        """When not in squeeze, LONG with RSI <= 35 and Lower BB pierce is APPROVED."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        result = self.validator.validate(
            symbol='BTCUSDT',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'rsi_15m': 30.0,
                'is_squeeze': False,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is True

    def test_aduana_rsi_short_rejected_below_65_when_not_squeeze(self):
        """When not in squeeze, SHORT with RSI < 65 is REJECTED."""
        df_1d_bearish = create_mock_df_1d(trend='bearish')
        df_15m_upper = create_mock_df_15m(pierce='upper')
        
        result = self.validator.validate(
            symbol='SOLUSDT',
            side='sell',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bearish,
                'df_15m': df_15m_upper,
                'rsi_15m': 62.0,
                'is_squeeze': False,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is False
        assert result.rule_triggered == 'RSI_NOT_OVERBOUGHT'

    def test_aduana_rsi_short_approved_at_68_when_not_squeeze(self):
        """When not in squeeze, SHORT with RSI >= 65 and Upper BB pierce is APPROVED."""
        df_1d_bearish = create_mock_df_1d(trend='bearish')
        df_15m_upper = create_mock_df_15m(pierce='upper')
        
        result = self.validator.validate(
            symbol='SOLUSDT',
            side='sell',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bearish,
                'df_15m': df_15m_upper,
                'rsi_15m': 68.0,
                'is_squeeze': False,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is True

    def test_aduana_squeeze_bypasses_rsi_threshold(self):
        """When in squeeze, trade is evaluated via BB extreme breakout without strict 35/65 RSI."""
        df_1d_bullish = create_mock_df_1d(trend='bullish')
        df_15m_lower = create_mock_df_15m(pierce='lower')
        
        result = self.validator.validate(
            symbol='GBPUSD',
            side='buy',
            order_type='LIMIT',
            market_data={
                'df_1d': df_1d_bullish,
                'df_15m': df_15m_lower,
                'rsi_15m': 45.0,
                'is_squeeze': True,
                'current_symbol_positions': 0,
                'max_positions_per_symbol': 3,
                'is_test': True
            }
        )
        assert result.approved is True


class TestRadarExtremoSniper:
    """Test suite for autonomous BB_EXTREMO_SNIPER detection and band curvature filters."""

    def test_sniper_long_blocked_when_lower_bb_falling(self):
        """If lower BB is expanding downwards in steep drop, sniper avoids catching falling knife."""
        from app.radar.crossover_detector import detect_extremo_opportunity
        
        df_1d = create_mock_df_1d(trend='bullish')
        
        # Create 15m where price is plunging and Lower BB expands sharply downwards
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq='15min')
        closes = [1.3000 - i * 0.0010 for i in range(30)] # plunging
        df_15m = pd.DataFrame({
            'timestamp': dates,
            'open': [c + 0.0005 for c in closes],
            'high': [c + 0.0008 for c in closes],
            'low': [c - 0.0008 for c in closes],
            'close': closes,
            'volume': [1000] * 30
        })
        # Rolling stats
        df_15m['sma20'] = df_15m['close'].rolling(20).mean()
        df_15m['std20'] = df_15m['close'].rolling(20).std()
        df_15m['lower_bb'] = df_15m['sma20'] - 2.0 * df_15m['std20']
        # Lower BB is decreasing: lower_bb[-1] < lower_bb[-2]
        
        op = detect_extremo_opportunity(df_15m, df_1d, symbol='GBPUSD', is_forex=True)
        # Should be None because lower BB is still dropping steeply
        assert op is None

    def test_sniper_long_approved_when_lower_bb_flat_or_ascending(self):
        """When lower BB begins to curl flat or upwards and Low touches lower BB with RSI <= 35, emits LIMIT order."""
        from app.radar.crossover_detector import detect_extremo_opportunity
        
        df_1d = create_mock_df_1d(trend='bullish')
        
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq='15min')
        # Baseline prices
        closes = [1.2500] * 25 + [1.2460, 1.2430, 1.2420, 1.2420, 1.2422]
        lows = [c - 0.0005 for c in closes]
        lows[-1] = 1.2400 # Perforates Lower BB
        
        df_15m = pd.DataFrame({
            'timestamp': dates,
            'open': closes,
            'high': [c + 0.0005 for c in closes],
            'low': lows,
            'close': closes,
            'volume': [1000] * 30,
            'rsi': [50.0] * 27 + [32.0, 31.0, 30.5]
        })
        df_15m['sma20'] = df_15m['close'].rolling(20).mean()
        df_15m['std20'] = df_15m['close'].rolling(20).std()
        df_15m['lower_bb'] = df_15m['sma20'] - 2.0 * df_15m['std20']
        df_15m['upper_bb'] = df_15m['sma20'] + 2.0 * df_15m['std20']
        
        # Ensure flat/ascending curvature for the last 2 candles
        df_15m.loc[df_15m.index[-1], 'lower_bb'] = 1.2405
        df_15m.loc[df_15m.index[-2], 'lower_bb'] = 1.2400
        
        op = detect_extremo_opportunity(df_15m, df_1d, symbol='GBPUSD', is_forex=True)
        assert op is not None
        assert op['strategy'] == 'BB_EXTREMO_SNIPER'
        assert op['side'] == 'buy'
        assert op['order_type'] == 'LIMIT'
        assert op['limit_price'] == 1.2405
        assert op['rsi_15m'] <= 35.0

    def test_sniper_short_blocked_when_upper_bb_rising(self):
        """If upper BB is rising vertically, sniper avoids selling into runaway rally."""
        from app.radar.crossover_detector import detect_extremo_opportunity
        
        df_1d = create_mock_df_1d(trend='bearish')
        
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq='15min')
        closes = [1.2500 + i * 0.0010 for i in range(30)] # skyrocketing
        df_15m = pd.DataFrame({
            'timestamp': dates,
            'open': closes,
            'high': [c + 0.0010 for c in closes],
            'low': [c - 0.0005 for c in closes],
            'close': closes,
            'volume': [1000] * 30
        })
        df_15m['sma20'] = df_15m['close'].rolling(20).mean()
        df_15m['std20'] = df_15m['close'].rolling(20).std()
        df_15m['upper_bb'] = df_15m['sma20'] + 2.0 * df_15m['std20']
        
        op = detect_extremo_opportunity(df_15m, df_1d, symbol='GBPUSD', is_forex=True)
        assert op is None

    def test_sniper_short_approved_when_upper_bb_flat_or_descending(self):
        """When upper BB curls flat/descending and High touches upper BB with RSI >= 65, emits SHORT LIMIT order."""
        from app.radar.crossover_detector import detect_extremo_opportunity
        
        df_1d = create_mock_df_1d(trend='bearish')
        
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq='15min')
        closes = [1.2500] * 25 + [1.2540, 1.2570, 1.2580, 1.2580, 1.2578]
        highs = [c + 0.0005 for c in closes]
        highs[-1] = 1.2600 # Perforates Upper BB
        
        df_15m = pd.DataFrame({
            'timestamp': dates,
            'open': closes,
            'high': highs,
            'low': [c - 0.0005 for c in closes],
            'close': closes,
            'volume': [1000] * 30,
            'rsi': [50.0] * 27 + [67.0, 68.5, 69.0]
        })
        df_15m['sma20'] = df_15m['close'].rolling(20).mean()
        df_15m['std20'] = df_15m['close'].rolling(20).std()
        df_15m['lower_bb'] = df_15m['sma20'] - 2.0 * df_15m['std20']
        df_15m['upper_bb'] = df_15m['sma20'] + 2.0 * df_15m['std20']
        
        # Ensure flat/descending curvature for the last 2 candles
        df_15m.loc[df_15m.index[-1], 'upper_bb'] = 1.2595
        df_15m.loc[df_15m.index[-2], 'upper_bb'] = 1.2600
        
        op = detect_extremo_opportunity(df_15m, df_1d, symbol='GBPUSD', is_forex=True)
        assert op is not None
        assert op['strategy'] == 'BB_EXTREMO_SNIPER'
        assert op['side'] == 'sell'
        assert op['order_type'] == 'LIMIT'
        assert op['limit_price'] == 1.2595
        assert op['rsi_15m'] >= 65.0



