import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def investigate_crsr():
    sb = get_supabase()
    # Fetch logs for CRSR
    res = sb.table('system_logs').select('*').ilike('message', '%CRSR%').order('created_at', desc=True).limit(50).execute()
    if res.data:
        print(f"--- LOGS FOR CRSR ---")
        for r in res.data:
            print(f"[{r['created_at']}] {r['level']} - {r['module']}: {r['message']}")
    
    # Check if there's a setting that disables EREP for stocks
    cfg = sb.table('trading_config').select('*').execute()
    if cfg.data:
        print(f"\n--- TRADING CONFIG ---")
        c = cfg.data[0]
        for k, v in c.items():
            if 'erep' in k.lower():
                print(f"{k}: {v}")

if __name__ == "__main__":
    investigate_crsr()
