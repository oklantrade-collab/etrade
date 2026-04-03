from app.core.supabase_client import get_supabase
import pandas as pd

def check():
    sb = get_supabase()
    res = sb.table('market_candles') \
        .select('symbol, timeframe, open_time, is_closed, basis, upper_6, lower_6') \
        .eq('symbol', 'BTCUSDT') \
        .eq('timeframe', '4h') \
        .order('open_time', desc=True) \
        .limit(100) \
        .execute()
    
    df = pd.DataFrame(res.data)
    print(f"Total rows fetched: {len(df)}")
    
    # Count non-zero basis
    non_zero = df[df['basis'] > 0]
    print(f"Rows with basis > 0: {len(non_zero)}")
    
    if len(non_zero) > 0:
        print("\nLast 5 rows with basis > 0:")
        print(non_zero.head(5))
    else:
        print("\nNo rows with basis > 0 found in the last 100 rows.")

if __name__ == "__main__":
    check()
