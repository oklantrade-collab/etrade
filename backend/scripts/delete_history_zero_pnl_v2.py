import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Reasons to delete (updated list)
reasons = ["unauthorized_symbol", "candle_signal_Bb41", "CLEANUP_EXCESS", "candle_signal_Aa41"]

# Delete from positions table
res = sb.table('positions')\
    .delete()\
    .eq('status', 'closed')\
    .in_('close_reason', reasons)\
    .eq('realized_pnl', 0)\
    .execute()

print(f"Deleted {len(res.data or [])} rows from positions table.")

# Also check paper_trades table
res_pt = sb.table('paper_trades')\
    .delete()\
    .in_('close_reason', reasons)\
    .eq('total_pnl_usd', 0)\
    .execute()

print(f"Deleted {len(res_pt.data or [])} rows from paper_trades table.")
