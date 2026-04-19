import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Specific deletion for Strategy Dd51 with CLEANUP_EXCESS and zero PnL
res = sb.table('positions')\
    .delete()\
    .eq('status', 'closed')\
    .eq('close_reason', 'CLEANUP_EXCESS')\
    .eq('realized_pnl', 0)\
    .eq('rule_code', 'Dd51')\
    .execute()

print(f"Deleted {len(res.data or [])} rows from positions table with Strategy Dd51.")
