from app.core.supabase_client import get_supabase
import sys
import os

# Ensure we can import from app
sys.path.insert(0, 'c:/Fuentes/eTrade/backend')

def cleanup_slashed_symbols():
    sb = get_supabase()
    
    print("Finding symbols with slashes in market_candles...")
    # We can't use LIKE in Supabase easily with select, but we can try to fetch symbols that contain /
    # Actually, we can just delete directly
    try:
        # Delete from market_candles where symbol contains /
        # We use 'like' filter: symbol.like.*/*
        res = sb.table('market_candles').delete().like('symbol', '%/%').execute()
        print(f"Deleted rows with slashes from market_candles: {len(res.data) if res.data else 0}")
        
        # Also check other tables
        res = sb.table('market_snapshot').delete().like('symbol', '%/%').execute()
        print(f"Deleted rows with slashes from market_snapshot: {len(res.data) if res.data else 0}")
        
        res = sb.table('technical_indicators').delete().like('symbol', '%/%').execute()
        print(f"Deleted rows with slashes from technical_indicators: {len(res.data) if res.data else 0}")

        print("Cleanup complete.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    cleanup_slashed_symbols()
