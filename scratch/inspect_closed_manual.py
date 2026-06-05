import os
import sys

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    print("--- DETALLES DE POSICIONES CERRADAS MANUALMENTE EN CRYPTO ---")
    res = sb.table('positions') \
        .select('*') \
        .eq('status', 'closed') \
        .order('closed_at', desc=True) \
        .limit(5) \
        .execute()
    
    positions = res.data or []
    for p in positions:
        print(f"ID: {p.get('id')}")
        print(f"  Symbol: {p.get('symbol')}")
        print(f"  Side: {p.get('side')}")
        print(f"  Rule Code: {p.get('rule_code')}")
        print(f"  Status: {p.get('status')}")
        print(f"  Opened At: {p.get('opened_at')}")
        print(f"  Closed At: {p.get('closed_at')}")
        print(f"  Close Reason: {p.get('close_reason')}")
        print(f"  Entry Price: {p.get('entry_price')}")
        print(f"  Current Price: {p.get('current_price')}")
        print(f"  Realized PNL: {p.get('realized_pnl')}")
        print(f"  Realized PNL %: {p.get('realized_pnl_pct')}")
        print("-" * 50)

if __name__ == '__main__':
    main()
