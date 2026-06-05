import asyncio
import os
import sys

sys.path.append(r'c:\Fuentes\eTrade\backend')

from app.core.supabase_client import get_supabase
from app.stocks.apex_score import calculate_apex_score
from app.stocks.stocks_adaptive_tp import fetch_macro_data

async def main():
    sb = get_supabase()
    macro = await fetch_macro_data(sb)
    print(f"Macro Score: {macro}")

    # Top 5 by technical score or fundamental
    res = sb.table('watchlist_daily').select('*').order('fundamental_score', desc=True).limit(5).execute()
    
    for fund in res.data:
        ticker = fund['ticker']
        snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).execute()
        snap = snap_res.data[0] if snap_res.data else {}
        
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
        print(f"--- {ticker} ---")
        print(f"APEX 4H: {apex['apex_score_4h']}")
        print(f"Blocks: {apex['blocks']}")

if __name__ == '__main__':
    asyncio.run(main())
