import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_ada():
    sb = get_supabase()
    print("--- POSITIONS ADAUSDT ---")
    res = sb.table('positions').select('*').eq('symbol', 'ADAUSDT').order('opened_at', desc=True).limit(5).execute()
    for row in res.data:
        print(f"ID: {row.get('id')} | Entry: {row.get('entry_price')} | Size: {row.get('size')} | Opened: {row.get('opened_at')} | Closed: {row.get('closed_at')} | Reason: {row.get('close_reason')} | PNL: {row.get('realized_pnl')} | Rule: {row.get('rule_code')}")

    print("\n--- RECENT LOGS ADAUSDT ---")
    logs = sb.table('system_logs').select('*').eq('symbol', 'ADAUSDT').order('timestamp', desc=True).limit(50).execute()
    for log in logs.data:
        ts = log.get('timestamp')
        if ts and '2026-05-28T21' in ts:
            print(f"[{ts}] {log.get('level')} - {log.get('action')}: {log.get('message')}")

if __name__ == "__main__":
    check_ada()
