import sys, os
from datetime import datetime, timezone
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# 1. Get risk config for limits
risk_res = sb.table("risk_config").select("*").limit(1).execute()
if not risk_res.data:
    print("Risk config not found. Defaulting to 3.")
    MAX_GLOBAL = 3
    MAX_PER_SYMBOL = 3
else:
    config = risk_res.data[0]
    MAX_GLOBAL = int(config.get('max_open_trades', 3))
    MAX_PER_SYMBOL = int(config.get('max_positions_per_symbol', 3))

print(f"Limits: Global={MAX_GLOBAL}, Per Symbol={MAX_PER_SYMBOL}")

# 2. Get all open positions
res = sb.table("positions").select("*").eq("status", "open").execute()
positions = res.data or []
print(f"Total open positions found: {len(positions)}")

# 3. Process by symbol
to_close = []
by_symbol = {}
for p in positions:
    sym = p['symbol']
    if sym not in by_symbol:
        by_symbol[sym] = []
    by_symbol[sym].append(p)

for sym, pos_list in by_symbol.items():
    # Sort by opened_at (oldest first)
    pos_list.sort(key=lambda x: x['opened_at'])
    
    if len(pos_list) > MAX_PER_SYMBOL:
        excess = pos_list[MAX_PER_SYMBOL:]
        print(f"Symbol {sym}: Found {len(pos_list)} positions. Closing {len(excess)} excess.")
        for p in excess:
            to_close.append(p['id'])
    else:
        print(f"Symbol {sym}: {len(pos_list)} positions (within limit).")

# 4. Check global limit among remaining
remaining_positions = [p for p in positions if p['id'] not in to_close]
remaining_positions.sort(key=lambda x: x['opened_at'])

if len(remaining_positions) > MAX_GLOBAL:
    excess_global = remaining_positions[MAX_GLOBAL:]
    print(f"Global: {len(remaining_positions)} positions remain. Closing {len(excess_global)} to meet global limit.")
    for p in excess_global:
        to_close.append(p['id'])

# 5. Perform the update
if to_close:
    print(f"\nClosing {len(to_close)} positions in total...")
    now = datetime.now(timezone.utc).isoformat()
    for pid in to_close:
        try:
            sb.table("positions").update({
                "status": "closed",
                "close_reason": "CLEANUP_EXCESS",
                "closed_at": now
            }).eq("id", pid).execute()
            print(f"  Closed ID: {pid}")
        except Exception as e:
            print(f"  Failed to close ID {pid}: {e}")
    print("\nCleanup complete.")
else:
    print("\nNo excess positions to close.")
