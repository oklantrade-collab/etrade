
from app.core.supabase_client import get_supabase
import asyncio

async def list_config():
    sb = get_supabase()
    res = sb.table("trading_config").select("*").eq("id", 1).maybe_single().execute()
    print("--- TRADING CONFIG (id=1) ---")
    if res.data:
        for k, v in res.data.items():
            print(f"{k}: {v}")
    
    res2 = sb.table("risk_config").select("*").limit(1).execute()
    print("\n--- RISK CONFIG ---")
    if res2.data:
        for k, v in res2.data[0].items():
            print(f"{k}: {v}")

if __name__ == "__main__":
    asyncio.run(list_config())
