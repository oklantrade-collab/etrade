import asyncio
from app.core.supabase_client import get_supabase

async def delete_trades():
    sb = get_supabase()
    
    ids_to_delete = [
        '388917de-8dac-422a-a263-1d2f5ad6e188', # EURUSD -2.84
        '9bd536bc-a513-4e43-9a8b-83c4693b7de6'  # GBPUSD -8.68
    ]
    
    for row_id in ids_to_delete:
        print(f"Deleting {row_id} from forex_positions...")
        res1 = sb.table('forex_positions').delete().eq('id', row_id).execute()
        print(f"Deleted forex_positions: {res1.data}")
        
    print("Done")

asyncio.run(delete_trades())
