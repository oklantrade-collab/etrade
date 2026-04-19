from app.core.supabase_client import get_supabase
import json

sb = get_supabase()
res = sb.table('positions').select('id, symbol, side, entry_price, current_price, unrealized_pnl').eq('status', 'open').execute()
print(json.dumps(res.data, indent=2))
