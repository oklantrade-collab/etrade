import pytest
import pandas as pd
from app.strategy.proactive_exit import evaluate_proactive_exit

def test_crypto_proactive_exit():
    # Long trade with 0.5% profit, Pine=Sell, SAR=-1, 4H=Bearish
    position = {'side': 'long', 'avg_entry_price': 100.0, 'size': 1.0}
    snap = {'pinescript_signal': 'Sell', 'sar_trend_15m': -1}
    
    # Create bearish 4H candle (+ previous candle to check lower low)
    df_4h = pd.DataFrame([
        {'open': 100, 'high': 105, 'low': 98, 'close': 102}, # t-1
        {'open': 102, 'high': 103, 'low': 95, 'close': 100}, # t (closed, bearish body = 2%, lower low)
        {'open': 100, 'high': 101, 'low': 99, 'close': 99.5}  # t+1 (current)
    ])
    
    current_price = 100.5 # 0.5% profit

    result = evaluate_proactive_exit(position, current_price, snap, df_4h, 'crypto_futures')
    
    assert result['should_close'] == True
    assert result['rule_code'] == 'AaPX51'
    assert result['urgency'] == 'normal'
    assert result['pnl']['has_profit'] == True
    assert result['conditions']['c1_pine']['passed'] == True
    assert result['conditions']['c2_sar']['passed'] == True
    assert result['conditions']['c3_candle']['passed'] == True

def test_forex_urgent_exit():
    # Short trade with huge profit (2%), only 2/3 conditions met
    position = {'symbol': 'EURUSD', 'side': 'short', 'entry_price': 1.1000, 'lots': 10.0}
    snap = {'pinescript_signal': 'Buy', 'sar_trend_15m': 1} # Pine=Buy, SAR=+1 (met 2 conditions)
    
    # Create neutral 4H candle (fails 3rd condition)
    df_4h = pd.DataFrame([
        {'open': 1.1, 'high': 1.11, 'low': 1.09, 'close': 1.105},
        {'open': 1.105, 'high': 1.106, 'low': 1.104, 'close': 1.105}, # DOJI
        {'open': 1.105, 'high': 1.106, 'low': 1.104, 'close': 1.105}
    ])
    
    current_price = 1.0780 # 2% profit

    result = evaluate_proactive_exit(position, current_price, snap, df_4h, 'forex_futures')
    
    assert result['should_close'] == True
    assert result['rule_code'] == 'Bb52' # Urgent
    assert result['urgency'] == 'urgent'
    assert result['conditions']['c3_candle']['passed'] == False

def test_ema_trend_reversal_cut():
    from app.core.memory_store import MEMORY_STORE
    
    # Short trade in loss (-0.5%), EMA3 > EMA9 (bullish crossover -> adverse for short)
    position = {'symbol': 'BTCUSDT', 'side': 'short', 'avg_entry_price': 80000.0, 'size': 0.1}
    snap = {}
    df_4h = pd.DataFrame([
        {'open': 80000, 'high': 81000, 'low': 79000, 'close': 80500},
        {'open': 80500, 'high': 81000, 'low': 79000, 'close': 80500},
        {'open': 80500, 'high': 81000, 'low': 79000, 'close': 80500}
    ])
    current_price = 80400.0 # -0.5% loss for short
    
    # Mock MEMORY_STORE with 15m dataframe having EMA crossover
    # We want trending market (ADX=30) and EMA3=80600 > EMA9=80400 (adverse for short)
    df_15m = pd.DataFrame([
        {'ema_3': 80000, 'ema_9': 80200, 'ema_20': 80300, 'adx_14': 30},
        {'ema_3': 80600, 'ema_9': 80400, 'ema_20': 80300, 'adx_14': 30} # last candle
    ])
    
    MEMORY_STORE['BTCUSDT'] = {'15m': {'df': df_15m}}
    
    result = evaluate_proactive_exit(position, current_price, snap, df_4h, 'crypto_futures')
    
    assert result['should_close'] == True
    assert result['rule_code'] == 'BbTRC'
    assert 'Corte Preventivo' in result['reason']

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
