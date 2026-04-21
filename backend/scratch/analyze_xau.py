import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_xau_positions():
    sb = get_supabase()
    # Query positions with XAUUSD
    res = sb.table('positions').select('*').eq('symbol', 'XAUUSD').execute()
    print(f"Total XAUUSD positions: {len(res.data)}")
    
    threshold = 10.0
    to_delete = []
    
    for p in res.data:
        # Check realized or unrealized pnl
        pnl = p.get('realized_pnl') or p.get('unrealized_pnl') or 0
        # Wait, usually PNL is negative if it's a loss. 
        # The user says "PNL con inversiones mayor al monto de inversion... no debe exceder a los 10 dolares".
        # This could mean the PNL (loss) exceeded $10.
        # Or maybe they mean the 'investment' (margin) was more than $10?
        # Let's check 'size' or other fields.
        
        # In the screenshot, I see -$49.23.
        if abs(pnl) > threshold:
            to_delete.append(p)
            print(f"ID: {p['id']}, Symbol: {p['symbol']}, PNL: {pnl}, Status: {p['status']}")

    print(f"\nPositions to delete: {len(to_delete)}")
    
    # If the user wants to delete them, I should proceed.
    # But wait, I'll first list them and confirm.
    # Actually, the prompt says "Si esto es asi elimna...". 
    # I'll do it if I'm sure.

if __name__ == "__main__":
    asyncio.run(check_xau_positions())
