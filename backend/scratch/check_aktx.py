from app.core.supabase_client import get_supabase
import json

sb = get_supabase()
res = sb.table('stocks_positions').select('*').eq('ticker', 'AKTX').execute()
print(json.dumps(res.data, indent=2))

res_orders = sb.table('stocks_orders').select('*').eq('ticker', 'AKTX').order('created_at', desc=True).limit(5).execute()
print("\n--- ORDERS ---")
print(json.dumps(res_orders.data, indent=2))
