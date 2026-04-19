import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Delete limit_exceeded
p_res = sb.table('positions').delete().eq('close_reason', 'limit_exceeded').execute()
print(f"Deleted {len(p_res.data or [])} positions")
t_res = sb.table('paper_trades').delete().eq('close_reason', 'limit_exceeded').execute()
print(f"Deleted {len(t_res.data or [])} paper trades")

# 2. Check risk_config
r_res = sb.table('risk_config').select('*').execute()
print("risk_config data:", r_res.data)

# 3. Check trading_config
t_res = sb.table('trading_config').select('*').execute()
print("trading_config data:", t_res.data)
