import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_forex_xau_positions():
    sb = get_supabase()
    # Query forex_positions with XAUUSD
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').execute()
    print(f"Total XAUUSD Forex positions: {len(res.data)}")
    
    threshold = 10.0
    to_delete = []
    
    for p in res.data:
        pnl = float(p.get('pnl_usd', 0) or 0)
        # The user says: "la inversion de nuestro capital no debe exceder a los 10 dolares por cada posicion"
        # And "tiene PNL con inversiones mayor al monto de inversion establecido"
        # In screenshot 1, the PNL is -$49.23.
        # This is clearly > $10 in magnitude.
        if abs(pnl) > threshold:
            to_delete.append(p)
            print(f"ID: {p['id']}, Symbol: {p['symbol']}, PNL: {pnl}, Status: {p['status']}, Lots: {p.get('lots')}")

    print(f"\nPositions to delete: {len(to_delete)}")
    
    if to_delete:
        print("Deleting these positions as requested...")
        ids = [p['id'] for p in to_delete]
        del_res = sb.table('forex_positions').delete().in_('id', ids).execute()
        print(f"Delete Result: {del_res}")
    else:
        print("No positions exceeded the $10 threshold.")

if __name__ == "__main__":
    asyncio.run(check_forex_xau_positions())
