import os
import sys
import pandas as pd

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.supabase_client import get_supabase
from app.strategy.erep_manager import evaluate_erep_phase

def debug():
    sb = get_supabase()
    pos_id = "bc22cce1-658d-46ea-841d-de70c705b852"
    
    # 1. Fetch exact position
    res = sb.table('positions').select('*').eq('id', pos_id).execute()
    if not res.data:
        print("Position not found!")
        return
    pos = res.data[0]
    
    # Mock current price at the time of close
    current_price = 73596.9
    
    # Mock df_15m
    # We can fetch the actual historical 15m candles for BTCUSDT around 2026-06-01 01:20:00 UTC
    res_candles = sb.table('market_candles')\
        .select('*')\
        .eq('symbol', 'BTCUSDT')\
        .eq('timeframe', '15m')\
        .lte('open_time', '2026-06-01T01:20:00+00:00')\
        .order('open_time', desc=True)\
        .limit(10)\
        .execute()
    
    candles = res_candles.data or []
    print(f"Fetched {len(candles)} candles.")
    
    # Create DataFrame
    df = pd.DataFrame(candles)
    if not df.empty:
        # Sort ascending
        df = df.iloc[::-1].reset_index(drop=True)
        # Calculate fast/slow EMA
        df['close'] = df['close'].astype(float)
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        print("Candles:")
        for idx, row in df.iterrows():
            print(f"Time: {row['open_time']} | Close: {row['close']} | EMA3: {row['ema3']:.4f} | EMA9: {row['ema9']:.4f}")
    
    # Run evaluation
    action = evaluate_erep_phase(
        position=pos,
        current_price=current_price,
        snap={},
        df_15m=df,
        df_4h=None,
        market_type='crypto_futures'
    )
    print("\n=== EVALUATION RESULT ===")
    print(action)

if __name__ == "__main__":
    debug()
