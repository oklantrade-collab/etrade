import asyncio
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase
from app.core.logger import log_info

async def clean_paper_trades_by_time():
    sb = get_supabase()
    
    # Looking at the screenshot, the times are April 13, 2026 around 00:08 to 00:12 UTC
    
    start_time = "2026-04-13T00:05:00+00:00"
    end_time = "2026-04-13T00:15:00+00:00"
    
    res = sb.table('paper_trades').select('*').gte('closed_at', start_time).lte('closed_at', end_time).execute()
    trades = res.data or []
    
    log_info("CLEAN_TRADES", f"Found {len(trades)} trade entries to remove from history based on April 13 timestamp.")
    
    count = 0
    for t in trades:
        sb.table('paper_trades').delete().eq('id', t['id']).execute()
        count += 1
        
    log_info("CLEAN_TRADES", f"Finished removing {count} history entries.")

if __name__ == "__main__":
    asyncio.run(clean_paper_trades_by_time())
