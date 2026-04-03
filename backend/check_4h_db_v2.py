from app.core.supabase_client import get_supabase
import pandas as pd

def check():
    sb = get_supabase()
    # 1. Check trading_config
    cfg_res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
    print("--- TRADING CONFIG ---")
    print(cfg_res.data)
    
    # 2. Check 4h candles
    res = sb.table('market_candles') \
        .select('symbol, timeframe, open_time, is_closed, basis, upper_6, lower_6') \
        .eq('symbol', 'BTCUSDT') \
        .eq('timeframe', '4h') \
        .order('open_time', desc=True) \
        .limit(10) \
        .execute()
    
    df = pd.DataFrame(res.data)
    print("\n--- 4h CANDLES ---")
    print(df)

if __name__ == "__main__":
    check()
