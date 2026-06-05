import asyncio
from app.core.supabase_client import get_supabase
from app.stocks.apex_score import calculate_apex_score
import json

async def debug_apex():
    supabase = get_supabase()
    for ticker in ["ASPI", "YMM", "SIDU"]:
        print(f"--- Debugging {ticker} ---")
        snap_res = supabase.table("market_snapshot").select("*").eq("symbol", ticker).execute()
        if not snap_res.data:
            continue
        snap = snap_res.data[0]
        
        fund_res = supabase.table("fundamental_cache").select("*").eq("ticker", ticker).execute()
        fund = fund_res.data[0] if fund_res.data else {}
        
        res = calculate_apex_score(
            ticker=ticker,
            snap=snap,
            fundamental_cache=fund,
            macro={'score': 0, 'sentiment': 'neutral', 'flags': []},
            df_5m=None,
            df_15m=None,
            df_4h=None,
            df_daily=None,
            ia_score=5.0
        )
        
        print(json.dumps(res['detail'], indent=2))
        print(f"APEX 1D: {res['apex_score_1d']}\n")

if __name__ == "__main__":
    asyncio.run(debug_apex())
