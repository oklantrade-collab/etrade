import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Test: try to insert a minimal row with fundamental columns
test_row = {
    "ticker": "__TEST__",
    "date": "2026-04-09",
    "pool_type": "TEST",
    "catalyst_score": 5,
    "catalyst_type": "SWEEP",
    "hard_filter_pass": True,
    "price": 99.99,
    "quality_flag": "✓ PASS",
    "fundamental_score": 55.5,
    "revenue_growth_yoy": 12.3,
    "gross_margin": 45.6,
    "eps_growth_qoq": 7.8,
    "rs_score_6m": 80.0,
    "inst_ownership_pct": 60.0,
    "market_cap_mln": 5000.0,
}

try:
    # Clean up first
    sb.table("watchlist_daily").delete().eq("ticker", "__TEST__").execute()
    # Try insert
    res = sb.table("watchlist_daily").insert(test_row).execute()
    print(f"INSERT SUCCESS: {res.data}")
    # Clean up
    sb.table("watchlist_daily").delete().eq("ticker", "__TEST__").execute()
except Exception as e:
    print(f"INSERT FAILED: {e}")
    print(f"\nThis means the columns likely don't exist in the table!")
    print("Trying without fundamental columns...")
    
    basic_row = {
        "ticker": "__TEST__",
        "date": "2026-04-09",
        "pool_type": "TEST",
        "catalyst_score": 5,
        "catalyst_type": "SWEEP",
        "hard_filter_pass": True,
        "price": 99.99,
        "quality_flag": "✓ PASS",
    }
    try:
        res2 = sb.table("watchlist_daily").insert(basic_row).execute()
        print(f"BASIC INSERT SUCCESS: {res2.data}")
        sb.table("watchlist_daily").delete().eq("ticker", "__TEST__").execute()
        print("\nCONCLUSION: The fundamental columns (fundamental_score, revenue_growth_yoy, etc.) DO NOT EXIST in the table!")
    except Exception as e2:
        print(f"BASIC INSERT ALSO FAILED: {e2}")
