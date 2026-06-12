import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client

def test_dbs():
    db1_url = "https://dfrsccxkhicyhkprpsqt.supabase.co"
    # Service key from backend .env
    db1_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw"
    
    db2_url = "https://iriotnsoauqrfsjbqyyp.supabase.co"
    # Anon key from frontend .env.local
    db2_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlyaW90bnNvYXVxcmZzamJxeXlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0MTI3NzcsImV4cCI6MjA4ODk4ODc3N30.Q66IwV3GhiiKT7h6Wuy8T--KWtw0wlRj0siKg68sBo0"

    print("--- CONNECTING TO BACKEND DB (dfrsccxkhicyhkprpsqt) ---")
    try:
        sb1 = create_client(db1_url, db1_key)
        
        # Count positions
        res_open = sb1.table("positions").select("id", count="exact").eq("status", "open").execute()
        res_closed = sb1.table("positions").select("id", count="exact").eq("status", "closed").execute()
        print(f"Backend DB (positions): Open={res_open.count}, Closed={res_closed.count}")
        
        # Forex positions
        res_forex_open = sb1.table("forex_positions").select("id", count="exact").eq("status", "open").execute()
        res_forex_closed = sb1.table("forex_positions").select("id", count="exact").eq("status", "closed").execute()
        print(f"Backend DB (forex_positions): Open={res_forex_open.count}, Closed={res_forex_closed.count}")
        
        # Get some recent closed position dates
        recent_closed = sb1.table("positions").select("symbol, closed_at, status").eq("status", "closed").order("closed_at", desc=True).limit(5).execute()
        print("Backend DB recent closed positions:")
        for r in recent_closed.data:
            print(f"  - {r.get('symbol')}: {r.get('closed_at')} ({r.get('status')})")
            
    except Exception as e:
        print(f"Error backend DB: {e}")

    print("\n--- CONNECTING TO FRONTEND DB (iriotnsoauqrfsjbqyyp) ---")
    try:
        sb2 = create_client(db2_url, db2_key)
        
        # Count positions
        res_open = sb2.table("positions").select("id", count="exact").eq("status", "open").execute()
        res_closed = sb2.table("positions").select("id", count="exact").eq("status", "closed").execute()
        print(f"Frontend DB (positions): Open={res_open.count}, Closed={res_closed.count}")
        
        # Forex positions
        res_forex_open = sb2.table("forex_positions").select("id", count="exact").eq("status", "open").execute()
        res_forex_closed = sb2.table("forex_positions").select("id", count="exact").eq("status", "closed").execute()
        print(f"Frontend DB (forex_positions): Open={res_forex_open.count}, Closed={res_forex_closed.count}")
        
        # Get some recent closed position dates
        recent_closed = sb2.table("positions").select("symbol, closed_at, status").eq("status", "closed").order("closed_at", desc=True).limit(5).execute()
        print("Frontend DB recent closed positions:")
        for r in recent_closed.data:
            print(f"  - {r.get('symbol')}: {r.get('closed_at')} ({r.get('status')})")
            
    except Exception as e:
        print(f"Error frontend DB: {e}")

if __name__ == "__main__":
    test_dbs()
