from app.core.supabase_client import get_supabase
import sys

def add_columns():
    sb = get_supabase()
    print("Trying to add columns to watchlist_daily via SQL (if possible via RPC) or checking status...")
    # Unfortunately, Supabase Python client doesn't support ALTER TABLE directly.
    # Must be done via SQL Editor.
    print("NOTE: Please run this in Supabase SQL Editor:")
    print("ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS volume FLOAT DEFAULT 0;")
    print("ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS rvol FLOAT DEFAULT 0;")
    print("ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS market_cap FLOAT DEFAULT 0;")

if __name__ == "__main__":
    add_columns()
