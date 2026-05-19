import os
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Query positions for GBPUSD on 15/05/2026
res = sb.table('forex_positions')\
    .select('*')\
    .eq('symbol', 'GBPUSD')\
    .eq('status', 'closed')\
    .execute()

data = res.data or []
print(f"Found {len(data)} closed GBPUSD positions.")

# Filter for the one that lost -15.55 on 15/05/2026
for pos in data:
    if '2026-05-15' in pos.get('closed_at', '') or '2026-05-15' in pos.get('opened_at', ''):
        pnl = pos.get('pnl_usd', 0)
        print(f"ID: {pos.get('id')}")
        print(f"Symbol: {pos.get('symbol')}")
        print(f"Side: {pos.get('side')}")
        print(f"Lots: {pos.get('lots')}")
        print(f"Entry: {pos.get('entry_price')}")
        print(f"SL: {pos.get('sl_price')}")
        print(f"TP: {pos.get('tp_price')}")
        print(f"PnL: {pnl}")
        print(f"Rule: {pos.get('rule_code')}")
        print(f"Opened: {pos.get('opened_at')}")
        print(f"Closed: {pos.get('closed_at')}")
        print(f"Close Reason: {pos.get('close_reason')}")
        print("-" * 40)
