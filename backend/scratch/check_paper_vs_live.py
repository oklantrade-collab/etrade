import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_paper_vs_live():
    sb = get_supabase()
    
    print("--- PAPER TRADES (Today 2026-08-09) ---")
    pt = sb.table('paper_trades').select('*').order('created_at', desc=True).limit(10).execute()
    for row in pt.data:
        print(f"ID: {row.get('id')} | Symbol: {row.get('symbol')} | Side: {row.get('side')} | Strategy: {row.get('strategy_code')} | Entry: {row.get('entry_price')} | Close: {row.get('close_price')} | Reason: {row.get('close_reason')} | Created: {row.get('created_at')}")

    print("\n--- ORDERS (Today 2026-08-09) ---")
    orders = sb.table('orders').select('*').order('created_at', desc=True).limit(10).execute()
    for o in orders.data:
        print(f"ID: {o.get('id')} | Symbol: {o.get('symbol')} | Side: {o.get('side')} | Status: {o.get('status')} | IsPaper: {o.get('is_paper')} | BinanceID: {o.get('binance_order_id')} | Created: {o.get('created_at')}")

if __name__ == "__main__":
    check_paper_vs_live()
