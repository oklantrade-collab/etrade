from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

sb = get_supabase()
print("--- RECENT ORDERS ---")
orders = sb.table('stocks_orders').select('*').order('created_at', desc=True).limit(10).execute()
for o in orders.data:
    print(f"{o['ticker']} | {o['status']} | {o['direction']} | {o['created_at']}")

print("\n--- OPEN POSITIONS ---")
positions = sb.table('stocks_positions').select('*').eq('status', 'open').execute()
for p in positions.data:
    print(f"{p['ticker']} | {p['shares']} | {p['avg_price']} | {p['status']}")
