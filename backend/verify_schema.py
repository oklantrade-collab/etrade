import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'),
                   os.getenv('SUPABASE_SERVICE_KEY'))

async def verify_schema():
    # En este entorno de python-supabase no puedo hacer SELECT de information_schema
    # Pero puedo hacer un select * de trading_config y ver sus keys (columnas).
    try:
        res = sb.table('trading_config').select('*').limit(1).execute()
        if res.data:
            columns = res.data[0].keys()
            print("Columnas en table 'trading_config':")
            for col in sorted(columns):
                # We can't easily get the type but we can show it exists
                print(f"  {col}")
            
            if 'max_trade_loss_pct' in columns:
                print("\nCORRECTO: 'max_trade_loss_pct' existe en la tabla.")
            else:
                print("\nERROR: 'max_trade_loss_pct' NO existe en la tabla.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_schema())
