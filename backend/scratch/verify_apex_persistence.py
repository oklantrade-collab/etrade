import asyncio
from app.core.supabase_client import get_supabase

async def check_apex_data():
    sb = get_supabase()
    res = sb.table("technical_scores").select("ticker, apex_4h, apex_1d, apex_signal").not_.is_("apex_4h", "null").limit(5).execute()
    if res.data:
        print("FOUND APEX DATA:")
        for row in res.data:
            print(f"Ticker: {row['ticker']} | 4H: {row['apex_4h']}% | 1D: {row['apex_1d']}% | Signal: {row['apex_signal']}")
    else:
        print("No records found with apex_4h data yet. Waiting for scheduler cycle...")

if __name__ == "__main__":
    asyncio.run(check_apex_data())
