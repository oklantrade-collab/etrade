import os
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()

res = sb.table('forex_positions')\
    .select('id, symbol, side, entry_price, sl_price, slv_price, recovery_mode, recovery_cycles, close_reason')\
    .eq('id', '04f0a681-a7c7-4b8f-951c-423dbd5c1505')\
    .execute()

if res.data:
    pos = res.data[0]
    for k, v in pos.items():
        print(f"{k}: {v}")
else:
    print("Position not found.")
