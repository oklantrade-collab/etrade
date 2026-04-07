"""Direct test: Insert real sub-$50 stocks into watchlist and verify dashboard."""
import asyncio
import os
import sys
import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.core.logger import log_info
from datetime import date

async def main():
    sb = get_supabase()
    today = date.today().isoformat()
    
    # STEP 1: Get real stocks from Alpha Vantage fallback
    print("[1] Fetching active stocks from Alpha Vantage...")
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "MTUVLAIDW7DCRUGF")
    resp = requests.get("https://www.alphavantage.co/query", params={
        "function": "TOP_GAINERS_LOSERS",
        "apikey": api_key,
    }, timeout=15)
    data = resp.json()
    
    active = data.get("most_actively_traded", [])
    print(f"    Got {len(active)} actively traded stocks from AV")
    
    # STEP 2: Filter < $50
    max_price = 50.0
    candidates = []
    for item in active:
        ticker = item.get("ticker", "")
        price = float(item.get("price", 0))
        volume = int(item.get("volume", 0))
        
        if not ticker or "." in ticker:  # skip non-standard
            continue
        if price <= 0 or price > max_price:
            continue
        if volume < 500_000:
            continue
            
        candidates.append({
            "ticker": ticker,
            "price": price,
            "volume": volume,
            "change_pct": item.get("change_percentage", ""),
        })
    
    print(f"\n[2] Stocks with price < ${max_price}: {len(candidates)}")
    for c in candidates[:20]:
        print(f"    {c['ticker']:6s} | ${c['price']:8.2f} | Vol: {c['volume']:>12,} | {c['change_pct']}")
    
    # STEP 3: Insert into watchlist_daily
    print(f"\n[3] Inserting top 20 into watchlist_daily...")
    rows = []
    for c in candidates[:20]:
        rows.append({
            "ticker": c["ticker"],
            "pool_type": "av_fallback",
            "catalyst_score": 7,
            "catalyst_type": "HOT_BY_VOLUME",
            "date": today,
            "hard_filter_pass": True,
        })
    
    # Clear today and insert
    sb.table("watchlist_daily").delete().eq("date", today).execute()
    result = sb.table("watchlist_daily").insert(rows).execute()
    print(f"    ✅ Inserted {len(rows)} tickers for {today}")
    
    # STEP 4: Verify
    verify = sb.table("watchlist_daily").select("ticker").eq("date", today).execute()
    print(f"\n[4] Verification: {len(verify.data)} tickers in DB for today")
    print(f"    Tickers: {', '.join(r['ticker'] for r in verify.data)}")
    
    # STEP 5: Run yfinance analysis on top 3
    print(f"\n[5] Running technical analysis on top 3...")
    from app.workers.stocks_scheduler import process_ticker, get_stocks_config
    config = get_stocks_config()
    
    for c in candidates[:3]:
        ticker = c["ticker"]
        print(f"\n    Analyzing {ticker} (${c['price']:.2f})...")
        result = await process_ticker(ticker, config)
        if result:
            print(f"    ✅ {ticker}: Score={result['technical_score']} | RVOL={result['rvol']:.2f} | Price=${result['price']:.2f}")
        else:
            print(f"    ⚠️  {ticker}: Did not pass technical filters (EMA/SAR/4H)")

    print("\n" + "="*50)
    print(" DONE — Refresh your dashboard now!")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
