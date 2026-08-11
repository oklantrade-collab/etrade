import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_forex_pos():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').order('opened_at', desc=True).limit(10).execute()
    print("=== RECENT FOREX POSITIONS IN DB ===")
    for p in res.data:
        print(f"ID: {p.get('id')} | Sym: {p.get('symbol')} | Side: {p.get('side')} | Entry: {p.get('entry_price')} | Status: {p.get('status')} | Reason: {p.get('close_reason')} | Opened: {p.get('opened_at')} | Closed: {p.get('closed_at')}")

if __name__ == "__main__":
    check_forex_pos()
