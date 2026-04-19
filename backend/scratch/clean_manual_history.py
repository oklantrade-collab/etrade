import asyncio
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase
from app.core.logger import log_info

async def clean_manual_history():
    sb = get_supabase()
    
    # Looking for trades with reason 'manual_cleanup' or closed between 03:00 and 03:10 UTC April 13
    start_time = "2026-04-13T03:00:00+00:00"
    end_time = "2026-04-13T03:10:00+00:00"
    
    res = sb.table('paper_trades').select('*').gte('closed_at', start_time).lte('closed_at', end_time).execute()
    trades = res.data or []
    
    log_info("CLEAN_TRADES", f"Found {len(trades)} manual cleanup entries to remove from history.")
    
    count = 0
    for t in trades:
        sb.table('paper_trades').delete().eq('id', t['id']).execute()
        count += 1
        
    log_info("CLEAN_TRADES", f"Finished removing {count} history entries.")

if __name__ == "__main__":
    asyncio.run(clean_manual_history())
