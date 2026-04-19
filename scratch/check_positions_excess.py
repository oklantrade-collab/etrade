import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check open positions
res = sb.table("positions").select("*").eq("status", "open").execute()
positions = res.data or []
print(f"Total open positions: {len(positions)}")

# Group by symbol
by_symbol = {}
for p in positions:
    sym = p['symbol']
    if sym not in by_symbol:
        by_symbol[sym] = []
    by_symbol[sym].append(p)

for sym, pos_list in by_symbol.items():
    print(f"  {sym}: {len(pos_list)} positions")
    # Sort by opened_at to identify oldest
    pos_list.sort(key=lambda x: x['opened_at'])
    for i, p in enumerate(pos_list):
        print(f"    {i+1}. ID: {p['id']}, Side: {p['side']}, Entry: {p['entry_price']}, Opened: {p['opened_at']}")

# Check risk_config
try:
    risk_res = sb.table("risk_config").select("*").limit(1).execute()
    if risk_res.data:
        print(f"\nRisk Config: {risk_res.data[0]}")
    else:
        print("\nRisk Config not found.")
except Exception as e:
    print(f"\nError reading risk_config: {e}")
