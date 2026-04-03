from app.core.supabase_client import get_supabase
import pandas as pd

def check_candles():
    sb = get_supabase()
    res = sb.table('market_candles') \
        .select('symbol, timeframe, open_time, is_closed, basis, upper_6, lower_6') \
        .eq('symbol', 'BTCUSDT') \
        .eq('timeframe', '4h') \
        .order('open_time', desc=True) \
        .limit(10) \
        .execute()
    
    df = pd.DataFrame(res.data)
    print(df)

if __name__ == "__main__":
    check_candles()
