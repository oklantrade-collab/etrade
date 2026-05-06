import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_crypto_today():
    sb = get_supabase()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        res = sb.table("paper_trades").select("*").gte("closed_at", today).execute()
        print(f"Found {len(res.data)} Crypto trades closed today.")
        for p in res.data:
            print(f"[{p['closed_at']}] {p['symbol']} {p['side']} PnL: {p.get('total_pnl_usd')}$ Reason: {p.get('close_reason')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_crypto_today())
