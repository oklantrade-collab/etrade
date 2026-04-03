import asyncio
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

async def convert_symbols():
    # 1. Fetch distinct symbols with slash
    # (Usually few: BTC/USDT, ETH/USDT, etc.)
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT']
    
    for old_sym in symbols:
        new_sym = old_sym.replace('/', '')
        print(f"Converting {old_sym} -> {new_sym}...")
        
        # In PostgREST, we can't easily bulk-update thousands of rows by id efficiently without RPC.
        # But we can update all rows that match a filter.
        try:
            # THIS IS THE NATIVE WAY - Update all matching rows
            res = sb.table('market_candles')\
                .update({'symbol': new_sym})\
                .eq('symbol', old_sym)\
                .execute()
            
            print(f"Done {old_sym} ({len(res.data)} updated)")
        except Exception as e:
            print(f"Error converting {old_sym}: {e}")

async def main():
    await convert_symbols()

if __name__ == "__main__":
    asyncio.run(main())
