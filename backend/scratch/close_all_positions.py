import asyncio
from app.core.supabase_client import get_supabase
from app.core.logger import log_info
from app.core.position_monitor import _execute_paper_close

async def close_all_open_positions():
    sb = get_supabase()
    
    # 1. Fetch all open positions
    res = sb.table('positions').select('*').eq('status', 'open').execute()
    positions = res.data or []
    
    log_info("CLEANUP", f"Found {len(positions)} open positions to close.")
    
    count = 0
    for pos in positions:
        symbol = pos.get('symbol')
        current_price = float(pos.get('current_price') or pos.get('entry_price'))
        log_info("CLEANUP", f"Closing {symbol} (ID: {pos['id']})")
        await _execute_paper_close(pos, current_price, 'manual_cleanup', sb)
        count += 1
        
    log_info("CLEANUP", f"Finished. Closed {count} positions.")

if __name__ == "__main__":
    asyncio.run(close_all_open_positions())
