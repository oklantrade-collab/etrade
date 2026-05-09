import asyncio
from app.core.supabase_client import get_supabase

async def check_columns():
    sb = get_supabase()
    # Query one row to see columns
    res = sb.table("technical_scores").select("*").limit(1).execute()
    if res.data:
        print(f"COLUMNS: {res.data[0].keys()}")
    else:
        print("No data in technical_scores")

if __name__ == "__main__":
    asyncio.run(check_columns())
