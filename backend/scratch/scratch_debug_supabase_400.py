import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from datetime import date
from app.core.supabase_client import get_supabase

async def debug_insert():
    sys.stdout.reconfigure(encoding='utf-8')
    sb = get_supabase()
    today = date.today().isoformat()
    
    mock_row = {
        "ticker": "TESTX",
        "pool_type": "HOT",
        "catalyst_score": 5,
        "catalyst_type": "HOT_BY_VOLUME",
        "date": today,
        "price": 10.0,
        "hard_filter_pass": True,
        "quality_flag": "PASS",
        "fundamental_score": 50.0,
        "revenue_growth_yoy": 10.0,
        "gross_margin": 40.0,
        "eps_growth_qoq": 5.0,
        "rs_score_6m": 80.0,
        "inst_ownership_pct": 15.0,
        "market_cap_mln": 1200.0,
        "gap_pct": 1.5,
        "intrinsic_value": 15.0,
        "is_overvalued": False
    }
    
    print("Attempting to insert a mock row into watchlist_daily...")
    try:
        res = sb.table("watchlist_daily").insert(mock_row).execute()
        print("SUCCESS! Insert completed successfully.")
        print(res.data)
        
        # Clean up
        sb.table("watchlist_daily").delete().eq("ticker", "TESTX").eq("date", today).execute()
        print("Cleaned up mock row.")
    except Exception as e:
        print("\n❌ DATABASE INSERT FAILED WITH EXCEPTION:")
        print(f"Exception Type: {type(e)}")
        print(f"Exception string: {e}")
        
        # Try to print dict/attributes of the exception
        if hasattr(e, '__dict__'):
            print("\nException Dict Details:")
            for k, v in e.__dict__.items():
                print(f"  {k}: {v}")
                
        # If it's a postgrest APIError, let's extract more details
        if hasattr(e, 'message'):
            print(f"  message: {getattr(e, 'message')}")
        if hasattr(e, 'code'):
            print(f"  code: {getattr(e, 'code')}")
        if hasattr(e, 'details'):
            print(f"  details: {getattr(e, 'details')}")
        if hasattr(e, 'hint'):
            print(f"  hint: {getattr(e, 'hint')}")

if __name__ == "__main__":
    asyncio.run(debug_insert())
