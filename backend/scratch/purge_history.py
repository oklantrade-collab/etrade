import asyncio
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase
from app.core.logger import log_info

async def purge_closed_positions_history():
    sb = get_supabase()
    
    # We want to remove positions from the 'positions' table that were marked as 'manual_cleanup'
    # so they don't show up in the "Closed History" tab.
    
    start_time = "2026-04-13T03:00:00+00:00"
    end_time = "2026-04-13T03:30:00+00:00"
    
    res = sb.table('positions').select('*').eq('status', 'closed').eq('close_reason', 'manual_cleanup').gte('closed_at', start_time).execute()
    positions = res.data or []
    
    log_info("PURGE", f"Found {len(positions)} positions in 'positions' table to purge from history.")
    
    count = 0
    for p in positions:
        sb.table('positions').delete().eq('id', p['id']).execute()
        count += 1
        
    log_info("PURGE", f"Finished purging {count} positions from history.")

if __name__ == "__main__":
    asyncio.run(purge_closed_positions_history())
