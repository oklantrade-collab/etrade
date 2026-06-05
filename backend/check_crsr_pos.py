import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_crsr_pos():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('*').eq('ticker', 'CRSR').execute()
    if res.data:
        for r in res.data:
            print(f"ID: {r.get('id')} - Status: {r.get('status')} - SL: {r.get('stop_loss')} - Dynamic SL: {r.get('sl_dynamic_price')} - Stop Loss Price: {r.get('stop_loss_price')} - Close Reason: {r.get('close_reason')} - Erep Active: {r.get('erep_active')}")

if __name__ == "__main__":
    check_crsr_pos()
