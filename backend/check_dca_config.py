import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def dump_all_cfg():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').execute()
    if res.data:
        cfg = res.data[0]
        for k, v in cfg.items():
            if k in ['symbols_active', 'active_symbols']: continue
            print(f"{k}: {v}")

if __name__ == "__main__":
    dump_all_cfg()
