import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def inspect():
    sb = get_supabase()
    res = sb.table('positions').select('*').order('opened_at', desc=True).limit(20).execute()
    print("LAST 20 POSITIONS (BY OPENED_AT DESC):")
    for pos in res.data:
        print(f"ID: {pos.get('id')} | Sym: {pos.get('symbol')} | Status: {pos.get('status')} | Side: {pos.get('side')} | Entry: {pos.get('entry_price')} | Close: {pos.get('current_price')} | Reason: {pos.get('close_reason')} | ClosedAt: {pos.get('closed_at')} | OpenedAt: {pos.get('opened_at')}")

if __name__ == "__main__":
    inspect()
