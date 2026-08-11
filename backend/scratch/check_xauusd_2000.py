import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_xauusd():
    sb = get_supabase()
    
    print("--- 1. BUSCANDO REGLAS DE SHORT EN FOREX / TRADING_RULES ---")
    try:
        rules = sb.table('trading_rules').select('*').execute()
        short_rules = [r for r in rules.data if 'short' in (r.get('rule_name') or r.get('name') or r.get('rule_code') or '').lower() or (r.get('rule_code') or '').startswith('Bb')]
        print(f"Total reglas SHORT encontradas: {len(short_rules)}")
        for r in short_rules:
            print(f"Code: {r.get('rule_code')} | Name: {r.get('rule_name')} | Active: {r.get('enabled') or r.get('is_active')}")
    except Exception as e:
        print("Error fetching trading_rules:", e)

    print("\n--- 2. REGLAS EN strategy_rules_v2 ---")
    try:
        r2 = sb.table('strategy_rules_v2').select('*').execute()
        for r in r2.data:
            code = r.get('rule_code', '')
            if code.startswith('Bb') or 'short' in code.lower():
                print(f"Code: {code} | Min Score: {r.get('min_score')} | Cond IDs: {r.get('condition_ids')} | Weights: {r.get('condition_weights')}")
    except Exception as e:
        print("Error fetching strategy_rules_v2:", e)

    print("\n--- 3. ÚLTIMOS DIAGNÓSTICOS DE XAUUSD HOY (2026-08-09 19:00 - 20:15) ---")
    try:
        diag = sb.table('pilot_diagnostics').select('*').eq('symbol', 'XAUUSD').order('timestamp', desc=True).limit(20).execute()
        print(f"Diagnósticos encontrados para XAUUSD: {len(diag.data)}")
        for d in diag.data:
            print(f"[{d.get('timestamp')}] Direction: {d.get('direction_evaluated')} | Rule: {d.get('rule_evaluated')} | Triggered: {d.get('rule_triggered')} | BlockedBy: {d.get('entry_blocked_by')}")
    except Exception as e:
        print("Error fetching pilot_diagnostics:", e)

if __name__ == "__main__":
    check_xauusd()
