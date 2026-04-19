import asyncio
from app.core.supabase_client import get_supabase
from app.core.logger import log_info

async def clean_paper_trades():
    sb = get_supabase()
    
    # 1. We know the positions were restored. 
    # The paper_trades entries for those closings should be removed.
    # When we closed them, the 'reason' in paper_trades might have been 'cleanup_positive'
    # if it was passed through. 
    # Let's check for trades where 'reason' matches.
    
    res = sb.table('paper_trades').select('*').eq('reason', 'cleanup_positive').execute()
    trades = res.data or []
    
    log_info("CLEAN_TRADES", f"Found {len(trades)} trade entries to remove from history.")
    
    count = 0
    for t in trades:
        sb.table('paper_trades').delete().eq('id', t['id']).execute()
        count += 1
        
    log_info("CLEAN_TRADES", f"Finished removing {count} history entries.")

if __name__ == "__main__":
    asyncio.run(clean_paper_trades())
