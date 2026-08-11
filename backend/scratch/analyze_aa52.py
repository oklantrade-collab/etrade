import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def analyze_aa52():
    sb = get_supabase()
    
    # Get positions from the last few days with rule Aa52
    print("\n--- RECENT Aa52 POSITIONS ---")
    positions = sb.table('positions').select('*').ilike('rule_code', '%Aa52%').order('id', desc=True).limit(50).execute()
    
    erep_count = 0
    total_count = 0
    total_pnl = 0.0
    
    for p in positions.data:
        total_count += 1
        is_erep = p.get('erep_active') or p.get('status') == 'CLOSED_EREP' or p.get('status') == 'CLOSED' and (p.get('close_reason') == 'EREP' or (p.get('erep_active') == True))
        pnl = float(p.get('realized_pnl') or p.get('pnl') or 0.0)
        total_pnl += pnl
        
        print(f"[{p.get('symbol')}] ID: {p.get('id')} - {p.get('side')} - Entry: {p.get('entry_price')} - Rule: {p.get('rule_code')}")
        print(f"  > Open: {p.get('open_time')} - Close: {p.get('close_time')} - Status: {p.get('status')} - PNL: {pnl}")
        print(f"  > EREP Active: {p.get('erep_active')} - Phase: {p.get('erep_phase')} - Cycles: {p.get('erep_cycles_elapsed')}")
        if is_erep:
            erep_count += 1
            
    print(f"\nTotal positions: {total_count}")
    print(f"Total EREP: {erep_count}")
    print(f"Total PNL: {total_pnl}")

    # Also let's get the rule details
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa52').execute()
    if res.data:
        rule = res.data[0]
        print('\nRule details:', json.dumps(rule, indent=2))
        cond_ids = rule['condition_ids']
        if cond_ids:
            cond_res = sb.table('strategy_conditions').select('id,name,description').in_('id', cond_ids).execute()
            print('\nConditions:')
            for c in cond_res.data:
                print(f"ID: {c['id']}, Name: {c['name']}, Desc: {c['description']}")

if __name__ == '__main__':
    analyze_aa52()
