import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_weekly_performance():
    sb = get_supabase()
    
    # Define start and end of week in UTC
    # Since Lima timezone (GMT-5) is 5 hours behind UTC, 9th May Lima start is 2026-05-09T05:00:00+00:00
    # Let's just query everything and parse dates in python to be 100% precise and robust.
    
    print("--- FETCHING CLOSED TRADES FOR WEEKLY ANALYSIS (MAY 9 - MAY 17) ---")
    
    # 1. Forex Positions
    forex_res = sb.table('forex_positions').select('*').eq('status', 'closed').execute()
    forex_trades = forex_res.data or []
    
    # 2. Crypto Trades (paper_trades)
    crypto_res = sb.table('paper_trades').select('*').not_.is_('closed_at', 'null').execute()
    crypto_trades = crypto_res.data or []
    
    # 3. Stocks Positions
    stocks_res = sb.table('stocks_positions').select('*').eq('status', 'closed').execute()
    stocks_trades = stocks_res.data or []
    
    print(f"Total historical closed trades - Forex: {len(forex_trades)}, Crypto: {len(crypto_trades)}, Stocks: {len(stocks_trades)}")
    
    # Helper to parse dates and filter
    start_date = datetime(2026, 5, 9, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc) # May 18th start of day to cover all of May 17th
    
    print(f"Filtering trades closed between {start_date.isoformat()} and {end_date.isoformat()} (UTC)")
    
    def parse_dt(dt_str):
        if not dt_str:
            return None
        ts = dt_str.replace('Z', '+00:00')
        if '.' in ts:
            prefix, rest = ts.split('.', 1)
            sep = '+' if '+' in rest else ('-' if '-' in rest else None)
            if sep:
                micro_part, tz_part = rest.split(sep, 1)
                micro_part = micro_part.ljust(6, '0')[:6]
                ts = f"{prefix}.{micro_part}{sep}{tz_part}"
            else:
                micro_part = rest.ljust(6, '0')[:6]
                ts = f"{prefix}.{micro_part}"
        return datetime.fromisoformat(ts)

    # Forex Weekly Filtering
    weekly_forex = []
    for t in forex_trades:
        closed_at_str = t.get('closed_at')
        if closed_at_str:
            closed_at = parse_dt(closed_at_str)
            if closed_at and start_date <= closed_at < end_date:
                weekly_forex.append(t)
                
    # Crypto Weekly Filtering
    weekly_crypto = []
    for t in crypto_trades:
        closed_at_str = t.get('closed_at')
        if closed_at_str:
            closed_at = parse_dt(closed_at_str)
            if closed_at and start_date <= closed_at < end_date:
                weekly_crypto.append(t)
                
    # Stocks Weekly Filtering
    weekly_stocks = []
    for t in stocks_trades:
        closed_at_str = t.get('updated_at') or t.get('exit_date')
        if closed_at_str:
            closed_at = parse_dt(closed_at_str)
            if closed_at and start_date <= closed_at < end_date:
                weekly_stocks.append(t)

    # Calculations
    total_forex_all_pnl = sum(float(p['pnl_usd'] or 0) for p in forex_trades)
    total_crypto_all_pnl = sum(float(p['total_pnl_usd'] or 0) for p in crypto_trades)
    total_stocks_all_pnl = sum(float(p.get('unrealized_pnl') or p.get('pnl_usd') or 0) for p in stocks_trades)

    weekly_forex_pnl = sum(float(p['pnl_usd'] or 0) for p in weekly_forex)
    weekly_crypto_pnl = sum(float(p['total_pnl_usd'] or 0) for p in weekly_crypto)
    weekly_stocks_pnl = sum(float(p.get('unrealized_pnl') or p.get('pnl_usd') or 0) for p in weekly_stocks)
    
    print("\n--- RESULTS FOR THE WEEK (MAY 9 - MAY 17) ---")
    print(f"Forex Weekly Trades Closed: {len(weekly_forex)}, Weekly PNL: ${weekly_forex_pnl:.2f}")
    print(f"Crypto Weekly Trades Closed: {len(weekly_crypto)}, Weekly PNL: ${weekly_crypto_pnl:.2f}")
    print(f"Stocks Weekly Trades Closed: {len(weekly_stocks)}, Weekly PNL: ${weekly_stocks_pnl:.2f}")
    
    print("\n--- GLOBAL CUMULATIVE RESULTS (AS OF MAY 17) ---")
    print(f"Forex Cumulative PNL: ${total_forex_all_pnl:.2f}")
    print(f"Crypto Cumulative PNL: ${total_crypto_all_pnl:.2f}")
    print(f"Stocks Cumulative PNL: ${total_stocks_all_pnl:.2f}")

    # Let's inspect some of the weekly trades details to show to the user
    print("\n--- DETAILS OF WEEKLY FOREX TRADES ---")
    for t in weekly_forex[:5]:
        print(f"Symbol: {t.get('symbol')}, Side: {t.get('side')}, PNL: ${t.get('pnl_usd')}, Closed: {t.get('closed_at')}")
        
    print("\n--- DETAILS OF WEEKLY CRYPTO TRADES ---")
    for t in weekly_crypto[:5]:
        print(f"Symbol: {t.get('symbol')}, Side: {t.get('side')}, PNL: ${t.get('total_pnl_usd')}, Closed: {t.get('closed_at')}, Rule: {t.get('rule_code')}")
        
    print("\n--- DETAILS OF WEEKLY STOCKS TRADES ---")
    for t in weekly_stocks[:5]:
        print(f"Symbol: {t.get('ticker') or t.get('symbol')}, PNL: ${t.get('unrealized_pnl') or t.get('pnl_usd')}, Closed: {t.get('updated_at')}, Strategy: {t.get('strategy') or t.get('pool_type')}")

if __name__ == "__main__":
    asyncio.run(check_weekly_performance())
