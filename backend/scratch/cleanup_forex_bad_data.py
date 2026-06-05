import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    
    ids_to_delete = [
        '0435ed72-2364-4c39-a6c2-a13eac0ec391',  # XAUUSD anomaly (+$4302.51)
        'd5807bc5-269d-4719-86c9-3ed978678ad6'   # GBPUSD anomaly (+$1084.71)
    ]
    
    print(f"Starting cleanup of anomalous paper positions: {ids_to_delete}")
    
    for pos_id in ids_to_delete:
        # Check first
        check_res = sb.table('forex_positions').select('id, symbol, pnl_usd').eq('id', pos_id).execute()
        if check_res.data:
            pos = check_res.data[0]
            print(f"Deleting position ID: {pos['id']} | Symbol: {pos['symbol']} | Bad PNL: ${pos['pnl_usd']}")
            del_res = sb.table('forex_positions').delete().eq('id', pos_id).execute()
            if del_res.data or del_res.status_code == 200 or len(del_res.data) >= 0:
                print(f"Successfully deleted position ID: {pos_id}")
            else:
                print(f"Failed to delete position ID: {pos_id}")
        else:
            print(f"Position ID: {pos_id} not found in database.")
            
    print("Cleanup completed.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
