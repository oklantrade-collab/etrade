import asyncio
from app.core.supabase_client import get_supabase
from app.core.logger import log_info

async def purge_all_cleanup_history():
    sb = get_supabase()
    
    # Remove both 'manual_cleanup' and 'cleanup_positive' to be sure the history is clean
    reasons = ['manual_cleanup', 'cleanup_positive']
    
    res = sb.table('positions').select('*').in_('close_reason', reasons).execute()
    positions = res.data or []
    
    log_info("PURGE", f"Found {len(positions)} extra cleanup positions to purge.")
    
    count = 0
    for p in positions:
        sb.table('positions').delete().eq('id', p['id']).execute()
        count += 1
        
    log_info("PURGE", f"Finished purging {count} extra entries.")

if __name__ == "__main__":
    asyncio.run(purge_all_cleanup_history())
