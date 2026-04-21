import os
from datetime import datetime, timezone
import sys
sys.path.append('backend')

from dotenv import load_dotenv
load_dotenv('backend/.env')

from app.core.supabase_client import get_supabase

async def delete_xau_losses():
    sb = get_supabase()
    now_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Fetch XAUUSD positions from today with loss < -20
    res = sb.table('forex_positions')\
        .select('*')\
        .eq('symbol', 'XAUUSD')\
        .gte('opened_at', now_date)\
        .execute()
    
    positions = res.data or []
    to_delete = [p for p in positions if (p.get('pnl_usd') or 0) < -20]
    
    if not to_delete:
        print("No XAUUSD losing positions (< -20) found for today.")
        return

    print(f"Found {len(to_delete)} positions to delete.")
    
    for pos in to_delete:
        pid = pos['id']
        pnl = pos['pnl_usd']
        print(f"Deleting position {pid} with P&L: {pnl}")
        sb.table('forex_positions').delete().eq('id', pid).execute()
        
    print("Cleanup completed.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(delete_xau_losses())
