import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_sigs_type():
    sb = get_supabase()
    res = sb.table("technical_scores").select("*").order("timestamp", desc=True).limit(1).execute()
    if res.data:
        sigs = res.data[0].get('signals_json')
        print(f"Type of sigs: {type(sigs)}")
        print(f"Sigs: {sigs}")
        if isinstance(sigs, str):
            print("Sigs is a string! Need to json.loads it.")
    else:
        print("No data")

if __name__ == "__main__":
    asyncio.run(check_sigs_type())
