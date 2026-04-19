import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Reasons to delete
reasons = ["candle_signal_Aa41", "CLEANUP_EXCESS"]

# Delete from positions table
# Condition: status='closed', close_reason in [reasons], realized_pnl=0
# Note: In Supabase/PostgREST, pnl=0 can be tricky with floating points, 
# but usually it's stored as 0.0. I'll use filter.

res = sb.table('positions')\
    .delete()\
    .eq('status', 'closed')\
    .in_('close_reason', reasons)\
    .eq('realized_pnl', 0)\
    .execute()

print(f"Deleted {len(res.data or [])} rows from positions table.")

# Also check paper_trades table just in case
res_pt = sb.table('paper_trades')\
    .delete()\
    .in_('close_reason', reasons)\
    .eq('total_pnl_usd', 0)\
    .execute()

print(f"Deleted {len(res_pt.data or [])} rows from paper_trades table.")
