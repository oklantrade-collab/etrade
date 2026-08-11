import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check():
    sb = get_supabase()
    
    print("--- 1. Checking Global Trading Config ---")
    try:
        cfg = sb.table('trading_config').select('*').execute()
        for c in cfg.data:
            print(f"Config: {c}")
    except Exception as e:
        print("Error fetching trading_config:", e)

    print("\n--- 2. Checking Recent Crypto Positions (today 2026-08-09) ---")
    try:
        pos = sb.table('crypto_positions').select('*').order('created_at', desc=True).limit(10).execute()
        for p in pos.data:
            print(f"ID: {p.get('id')} | Symbol: {p.get('symbol')} | Mode/IsPaper: {p.get('is_paper')} | Strategy: {p.get('strategy_code')} | Status: {p.get('status')} | Binance Order ID: {p.get('binance_order_id')} | Created: {p.get('created_at')}")
    except Exception as e:
        print("Error fetching crypto_positions:", e)

    print("\n--- 3. Checking Recent Orders / Signals Log ---")
    try:
        orders = sb.table('orders').select('*').order('created_at', desc=True).limit(10).execute()
        for o in orders.data:
            print(f"Order ID: {o.get('id')} | Symbol: {o.get('symbol')} | Status: {o.get('status')} | Type: {o.get('order_type')} | IsPaper: {o.get('is_paper')} | Binance ID: {o.get('binance_order_id')} | Error: {o.get('error_message')}")
    except Exception as e:
        print("Error fetching orders:", e)

    print("\n--- 4. Checking System Logs for Binance / Execution errors ---")
    try:
        logs = sb.table('system_logs').select('*').order('created_at', desc=True).limit(15).execute()
        for l in logs.data:
            print(f"[{l.get('created_at')}] [{l.get('level')}] {l.get('message')}")
    except Exception as e:
        print("Error fetching system_logs:", e)

if __name__ == "__main__":
    check()
