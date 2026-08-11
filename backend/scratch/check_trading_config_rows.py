import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').execute()
    print(f"Total rows in trading_config: {len(res.data)}")
    for r in res.data:
        print(f"ID: {r.get('id')} | Mode: {r.get('mode')} | PaperTrading: {r.get('paper_trading')} | Key: {r.get('key')} | Value: {r.get('value')} | Updated: {r.get('updated_at')}")

if __name__ == "__main__":
    check()
