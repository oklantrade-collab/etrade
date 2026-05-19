import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv('backend/.env')

from app.core.supabase_client import get_supabase

async def check_diagnostics():
    print("Checking Crypto Pilot Diagnostics for today...")
    try:
        sb = get_supabase()
        # Today in Lima is 16th
        today = "2026-05-16"
        
        res = sb.table("pilot_diagnostics")\
            .select("timestamp, symbol, entry_blocked_by, mtf_score, rule_evaluated")\
            .gte("timestamp", today)\
            .order("timestamp", desc=True)\
            .limit(20)\
            .execute()
        
        data = res.data or []
        print(f"Found {len(data)} diagnostics for today.")
        
        for d in data:
            print(f"[{d.get('timestamp')}] {d.get('symbol')} | Blocked By: {d.get('entry_blocked_by')} | MTF: {d.get('mtf_score')} | Rule: {d.get('rule_evaluated')}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error checking diagnostics: {e}")

if __name__ == "__main__":
    asyncio.run(check_diagnostics())
