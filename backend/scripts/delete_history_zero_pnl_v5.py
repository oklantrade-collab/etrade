import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Specific deletion for Strategy Dd51 with CLEANUP_EXCESS where PNL is NULL
res_null = sb.table('positions')\
    .delete()\
    .eq('status', 'closed')\
    .eq('close_reason', 'CLEANUP_EXCESS')\
    .eq('rule_code', 'Dd51')\
    .is_('realized_pnl', 'null')\
    .execute()

print(f"Deleted {len(res_null.data or [])} rows with PNL=NULL.")

# And where PNL=0 (just in case)
res_zero = sb.table('positions')\
    .delete()\
    .eq('status', 'closed')\
    .eq('close_reason', 'CLEANUP_EXCESS')\
    .eq('rule_code', 'Dd51')\
    .eq('realized_pnl', 0)\
    .execute()

print(f"Deleted {len(res_zero.data or [])} rows with PNL=0.")
