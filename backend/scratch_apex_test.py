import asyncio
import os
import sys

sys.path.append(r'c:\Fuentes\eTrade\backend')

from app.core.supabase_client import get_supabase
from app.stocks.apex_score import calculate_apex_score

async def main():
    sb = get_supabase()
    ticker = "TE"
    
    # Obtener snapshot
    snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).limit(1).execute()
    snap = snap_res.data[0] if snap_res.data else {}

    # Obtener fundamentales
    fund_res = sb.table('watchlist_daily').select('*').eq('ticker', ticker).limit(1).execute()
    fund = fund_res.data[0] if fund_res.data else {}

    fund_cache = {
        'piotroski_score':    fund.get('piotroski_score', 4),
        'margin_of_safety':   fund.get('margin_of_safety', 0),
        'altman_zone':        fund.get('altman_zone', 'grey'),
        'fundamental_score':  fund.get('fundamental_score', 50),
        'analyst_rating':     fund.get('analyst_rating', 5),
        'short_interest_pct': fund.get('short_interest_pct', 5),
        'days_to_earnings':   fund.get('days_to_earnings', 30),
        'valuation_status':   fund.get('valuation_status', 'fairly_valued'),
    }

    macro = {"score": 50, "sentiment": "neutral"} # mock

    apex = calculate_apex_score(
        ticker=ticker,
        snap=snap,
        fundamental_cache=fund_cache,
        macro=macro,
        df_5m=None,
        df_15m=None,
        df_4h=None,
        df_daily=None,
        ia_score=float(fund_cache.get('fundamental_score', 50)) / 10,
    )
    
    print(f"--- {ticker} APEX ---")
    print(apex['blocks'])
    print(f"APEX 4H: {apex['apex_score_4h']}")
    print(f"Detail: {apex['detail']}")

if __name__ == '__main__':
    asyncio.run(main())
