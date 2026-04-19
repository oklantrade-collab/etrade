import sys
sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Update to 4
sb.table('risk_config').update({'max_positions_per_symbol': 4}).neq('id', '00000000-0000-0000-0000-000000000000').execute()
print("Updated risk_config max_positions_per_symbol to 4")
