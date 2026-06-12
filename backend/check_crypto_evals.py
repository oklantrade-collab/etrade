import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_crypto_evals():
    sb = get_supabase()
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
    print(f"--- Recent SHORT Evaluations for Crypto Pairs: {symbols} ---")
    
    try:
        res = sb.table('strategy_evaluations')\
            .select('*')\
            .in_('symbol', symbols)\
            .order('created_at', desc=True)\
            .limit(30)\
            .execute()
            
        for row in res.data:
            rule = row['rule_code']
            symbol = row['symbol']
            triggered = row['triggered']
            score = row['score']
            created_at = row['created_at']
            
            # Print if it is a short rule or has direction close / short
            # Check context/direction if present
            direction = row.get('direction', '')
            print(f"Time: {created_at} | Symbol: {symbol} | Rule: {rule} | Direction: {direction} | Triggered: {triggered} | Score: {score}")
            if not triggered and row.get('context'):
                # print some conditions why it failed
                context = row.get('context')
                if isinstance(context, dict) and 'blocked_by' in context:
                    print(f"   Blocked by: {context['blocked_by']}")
                elif isinstance(context, dict) and 'reason' in context:
                    print(f"   Reason: {context['reason']}")
    except Exception as e:
        print(f"Error checking evaluations: {e}")

if __name__ == "__main__":
    check_crypto_evals()
