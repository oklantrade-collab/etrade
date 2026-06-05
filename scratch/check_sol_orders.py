import os
import sys
# Add backend to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from app.core.supabase_client import get_supabase

def check_sol():
    sb = get_supabase()
    
    # 1. Query pending_orders for SOLUSDT
    print("--- PENDING ORDERS FOR SOLUSDT ---")
    res = sb.table('pending_orders').select('*').eq('symbol', 'SOLUSDT').order('created_at', desc=True).limit(5).execute()
    if res.data:
        for o in res.data:
            print(f"ID: {o['id']} | LimitPrice: {o['limit_price']} | Status: {o['status']} | CreatedAt: {o['created_at']} | Rule: {o['rule_code']} | Sizing: {o.get('sizing_pct')}%")
    else:
        print("No pending orders found for SOLUSDT")
        
    # 2. Query positions for SOLUSDT
    print("\n--- POSITIONS FOR SOLUSDT ---")
    res_pos = sb.table('positions').select('*').eq('symbol', 'SOLUSDT').order('opened_at', desc=True).limit(5).execute()
    if res_pos.data:
        for p in res_pos.data:
            print(f"ID: {p['id']} | Status: {p['status']} | Rule: {p.get('rule_code')} | EntryPrice: {p['entry_price']} | SL: {p['sl_price']} | OpenedAt: {p['opened_at']} | RealizedPNL: {p.get('realized_pnl')}")
    else:
        print("No positions found for SOLUSDT")

if __name__ == "__main__":
    check_sol()
