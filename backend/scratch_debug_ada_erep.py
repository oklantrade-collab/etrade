import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def debug_erep():
    sb = get_supabase()
        
    print("\n--- RECENT Aa30C POSITIONS ---")
    positions = sb.table('positions').select('*').eq('symbol', 'ADAUSDT').ilike('rule_code', '%Aa30C%').execute()
    for p in positions.data:
        print(f"Position ID: {p.get('id')} - {p.get('side')} - Entry: {p.get('entry_price')} - Rule: {p.get('rule_code')} - Open Time: {p.get('open_time')}")
        print(f"  > EREP Active: {p.get('erep_active')} - Phase: {p.get('erep_phase')}")
        print(f"  > Cycles: {p.get('erep_cycles_elapsed')} - P1: {p.get('erep_p1_price')} - Start Phase 2: {p.get('erep_phase2_start_time')}")
        
    print("\n--- ADAUSDT SYSTEM LOGS AROUND 18/07/2026 ---")
    try:
        logs = sb.table('system_logs').select('*').ilike('message', '%ADA%').gte('timestamp', '2026-07-18T21:00:00').lte('timestamp', '2026-07-19T05:00:00').order('timestamp', desc=False).execute()
        for log in logs.data:
            print(f"[{log.get('timestamp')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")
    except Exception as e:
        print(f"Failed to query system logs by timestamp: {e}")
        try:
            logs = sb.table('system_logs').select('*').ilike('message', '%ADA%').gte('created_at', '2026-07-18T21:00:00').lte('created_at', '2026-07-19T05:00:00').order('created_at', desc=False).execute()
            for log in logs.data:
                print(f"[{log.get('created_at')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")
        except Exception as e2:
            print(f"Failed to query system logs by created_at: {e2}")

if __name__ == '__main__':
    debug_erep()
