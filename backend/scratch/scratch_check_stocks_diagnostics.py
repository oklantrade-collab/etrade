import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
from app.core.supabase_client import get_supabase

async def check_stocks_diagnostics():
    # Force sys.stdout to handle UTF-8 safely on Windows
    sys.stdout.reconfigure(encoding='utf-8')
    sb = get_supabase()
    
    # 1. Query the technical_scores to see all active tickers
    print("=== QUERYING TECHNICAL SCORES / APEX SCORES ===")
    res_tech = sb.table("technical_scores").select("*").execute()
    tech_data = res_tech.data or []
    print(f"Total tickers in technical_scores: {len(tech_data)}")
    
    if not tech_data:
        print("No records found in technical_scores.")
        return
        
    # Sort by apex_4h descending
    tech_sorted = sorted(tech_data, key=lambda x: float(x.get('apex_4h') or 0), reverse=True)
    
    print("\n--- TOP TICKERS BY APEX 4H SCORE ---")
    for row in tech_sorted[:15]:
        print(f"Ticker: {row.get('ticker'):<6} | APEX 4H: {row.get('apex_4h')}% | APEX 1D: {row.get('apex_1d')}% | Signal: {row.get('apex_signal'):<10} | RVOL: {row.get('rvol'):.2f}x | RSI: {row.get('rsi_14'):.1f} | MACD: {row.get('macd_signal')} | MTF Confirmed: {row.get('mtf_confirmed')}")

    # Let's inspect some of the top ones in detail
    print("\n--- DETAILED SCORE OF TOP 3 ---")
    for row in tech_sorted[:3]:
        ticker = row.get('ticker')
        print(f"\nTicker: {ticker}")
        for k, v in sorted(row.items()):
            # Safe print
            print(f"  {k}: {v}")

    # 2. Check the macro parameters and general stock snapshots
    print("\n=== QUERYING MARKET SNAPSHOT / MACRO REGIME ===")
    res_snap = sb.table("market_snapshot").select("*").execute()
    snap_data = res_snap.data or []
    
    print(f"Total entries in market_snapshot: {len(snap_data)}")
    
    stock_tickers = set(t.get('ticker') for t in tech_data)
    stock_snaps = [s for s in snap_data if s.get('symbol') in stock_tickers]
    
    if stock_snaps:
        print("\n--- STOCK SNAPSHOT PARAMETERS (AVERAGES) ---")
        avg_rvol = sum(float(s.get('rvol') or 0) for s in stock_snaps) / len(stock_snaps)
        avg_rsi = sum(float(s.get('rsi_14') or 50) for s in stock_snaps) / len(stock_snaps)
        avg_adx = sum(float(s.get('adx') or 25) for s in stock_snaps) / len(stock_snaps)
        
        # Calculate avg_mtf safely
        valid_mtfs = [float(s.get('mtf_score')) for s in stock_snaps if s.get('mtf_score') is not None]
        avg_mtf = sum(valid_mtfs) / len(valid_mtfs) if valid_mtfs else 0.0
        
        print(f"  Average RVOL (Relative Volume): {avg_rvol:.2f}x")
        print(f"  Average RSI (14): {avg_rsi:.1f}")
        print(f"  Average ADX (Trend Strength): {avg_adx:.1f}")
        print(f"  Average MTF Score: {avg_mtf:.2f}")
        
        # Detail some snapshots
        print("\n--- INDIVIDUAL SNAPSHOT DETAILS (First 10) ---")
        for s in stock_snaps[:10]:
            print(f"  Symbol: {s.get('symbol'):<6} | RVOL: {s.get('rvol') or 0.0:.2f}x | RSI: {s.get('rsi_14') or 50.0:.1f} | ADX: {s.get('adx') or 25.0:.1f} | MTF Score: {s.get('mtf_score')} | Fib Zone: {s.get('fib_zone_15m')}")

    # Let's inspect the watchlist_daily table to see if universe functions correctly
    print("\n=== QUERYING WATCHLIST_DAILY ===")
    res_wl = sb.table("watchlist_daily").select("*").execute()
    wl_data = res_wl.data or []
    print(f"Total entries in watchlist_daily: {len(wl_data)}")
    if wl_data:
        print("\n--- WATCHLIST DAILY SAMPLES (First 5) ---")
        for w in wl_data[:5]:
            print(f"  Ticker: {w.get('ticker'):<6} | Vol: {w.get('volume_24h')} | Min price: {w.get('price')} | Updated At: {w.get('updated_at')}")

if __name__ == "__main__":
    asyncio.run(check_stocks_diagnostics())
