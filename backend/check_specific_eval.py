import os
import sys
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_eval():
    sb = get_supabase()
    
    res = sb.table('strategy_evaluations')\
        .select('*')\
        .eq('symbol', 'ETHUSDT')\
        .eq('rule_code', 'Bb11')\
        .order('created_at', desc=True)\
        .limit(1)\
        .execute()
        
    if res.data:
        row = res.data[0]
        print(f"Time: {row['created_at']}")
        print(f"Symbol: {row['symbol']}")
        print(f"Rule: {row['rule_code']}")
        print(f"Triggered: {row['triggered']}")
        print(f"Score: {row['score']}")
        print("Context:")
        print(json.dumps(row.get('context'), indent=2))
    else:
        print("No evaluation found for ETHUSDT and Bb11")

if __name__ == "__main__":
    check_eval()
