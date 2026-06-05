import os
import sys

# Ensure backend root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.supabase_client import get_supabase

def check_corrupted():
    sb = get_supabase()
    print("Checking for closed positions with null 'closed_at' or null 'close_reason'...")
    
    res = sb.table('positions').select('*').eq('status', 'closed').execute()
    data = res.data or []
    
    corrupted = []
    for pos in data:
        if pos.get('closed_at') is None or pos.get('close_reason') is None:
            corrupted.append(pos)
            
    print(f"Found {len(corrupted)} potentially corrupted closed positions:")
    for pos in corrupted:
        print(f"ID: {pos.get('id')} | Symbol: {pos.get('symbol')} | Side: {pos.get('side')} | Entry: {pos.get('entry_price')} | Close Reason: {pos.get('close_reason')} | Closed At: {pos.get('closed_at')}")
        
if __name__ == "__main__":
    check_corrupted()
