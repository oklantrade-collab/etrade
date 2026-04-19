import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Inspect data to find why it didn't delete
res = sb.table('positions')\
    .select('id, close_reason, realized_pnl, rule_code')\
    .eq('status', 'closed')\
    .eq('close_reason', 'CLEANUP_EXCESS')\
    .execute()

data = res.data or []
print(f"Found {len(data)} rows with status='closed' and close_reason='CLEANUP_EXCESS'")
for row in data[:10]:
    print(f"ID: {row['id']} | PNL: {row['realized_pnl']} | Strategy: {row['rule_code']}")

# Try a broader delete if precision is the issue
# We can delete where realized_pnl is between -0.00001 and 0.00001
res_del = sb.table('positions')\
    .delete()\
    .eq('status', 'closed')\
    .eq('close_reason', 'CLEANUP_EXCESS')\
    .eq('rule_code', 'Dd51')\
    .lte('realized_pnl', 0.0001)\
    .gte('realized_pnl', -0.0001)\
    .execute()

print(f"Deleted {len(res_del.data or [])} rows with broader range.")
