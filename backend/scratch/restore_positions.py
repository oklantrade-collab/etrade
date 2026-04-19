import asyncio
from app.core.supabase_client import get_supabase
from app.core.logger import log_info

async def restore_positions():
    sb = get_supabase()
    
    # 1. Fetch positions closed by the cleanup script
    res = sb.table('positions').select('*').eq('close_reason', 'cleanup_positive').execute()
    positions = res.data or []
    
    log_info("RESTORE", f"Found {len(positions)} positions to restore.")
    
    restored_count = 0
    for pos in positions:
        # Update back to open
        update_data = {
            'status': 'open',
            'is_open': True,
            'close_reason': None,
            'closed_at': None,
            'realized_pnl': 0,
            'realized_pnl_pct': 0
        }
        sb.table('positions').update(update_data).eq('id', pos['id']).execute()
        restored_count += 1
        
    log_info("RESTORE", f"Finished restoring {restored_count} positions.")

if __name__ == "__main__":
    asyncio.run(restore_positions())
