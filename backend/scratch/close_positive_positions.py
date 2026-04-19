import asyncio
import os
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error
from app.core.position_monitor import _execute_paper_close

async def close_positive_positions():
    sb = get_supabase()
    
    # 1. Fetch all open positions
    res = sb.table('positions').select('*').eq('status', 'open').execute()
    positions = res.data or []
    
    log_info("CLEANUP", f"Found {len(positions)} open positions.")
    
    closed_count = 0
    for pos in positions:
        pnl = float(pos.get('unrealized_pnl') or 0)
        symbol = pos.get('symbol')
        
        if pnl > 0:
            log_info("CLEANUP", f"Closing positive position: {symbol} (PnL: ${pnl:.2f})")
            current_price = float(pos.get('current_price') or pos.get('entry_price'))
            await _execute_paper_close(pos, current_price, 'cleanup_positive', sb)
            closed_count += 1
            
    log_info("CLEANUP", f"Finished. Closed {closed_count} positive positions.")

if __name__ == "__main__":
    asyncio.run(close_positive_positions())
