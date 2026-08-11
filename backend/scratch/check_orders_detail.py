import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_details():
    sb = get_supabase()
    orders = sb.table('orders').select('*').order('created_at', desc=True).limit(10).execute()
    print("Recent 10 Orders in DB:")
    for o in orders.data:
        print(f"ID: {o.get('id')} | Sym: {o.get('symbol')} | Side: {o.get('side')} | Strategy: {o.get('strategy')} | IsPaper: {o.get('is_paper')} | Created: {o.get('created_at')} | BinanceID: {o.get('binance_order_id')}")

    # Check positions table (trading_positions or positions or paper_trades)
    print("\nPositions tables in DB:")
    for t in ['positions', 'trading_positions', 'paper_trades', 'crypto_positions']:
        try:
            res = sb.table(t).select('*').order('created_at', desc=True).limit(5).execute()
            print(f"Table '{t}': {len(res.data)} rows found.")
            for r in res.data:
                print(f"  - [{r.get('created_at')}] Sym: {r.get('symbol')} | IsPaper: {r.get('is_paper')} | Strat: {r.get('strategy_code') or r.get('strategy')}")
        except Exception as e:
            print(f"Table '{t}': error ({e})")

if __name__ == "__main__":
    check_details()
