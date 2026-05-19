import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.core.supabase_client import get_supabase
from app.stocks.apex_score import (
    calculate_b1_momentum,
    calculate_b2_technical,
    calculate_b3_fundamental,
    calculate_b4_regime,
    calculate_b5_sentiment
)

async def analyze_apex_blocks():
    sys.stdout.reconfigure(encoding='utf-8')
    sb = get_supabase()
    
    # 1. Fetch top tickers from technical_scores
    res = sb.table("technical_scores").select("*").execute()
    data = res.data or []
    
    if not data:
        print("No tickers found in technical_scores.")
        return
        
    print(f"Loaded {len(data)} tickers from technical_scores.")
    
    # Let's sort by apex_4h
    sorted_data = sorted(data, key=lambda x: float(x.get('apex_4h') or 0), reverse=True)
    
    from app.stocks.stocks_adaptive_tp import fetch_macro_data
    macro_data = await fetch_macro_data(sb)
    print("\n--- MACRO DATA ---")
    print(macro_data)
    
    print("\n=== APEX BLOCK-BY-BLOCK BREAKDOWN FOR TOP 5 TICKERS ===")
    
    for row in sorted_data[:5]:
        ticker = row.get('ticker')
        signals = row.get('signals_json') or {}
        
        # Reconstruct blocks
        # 1. B1 (Momentum)
        # We pass a mock snap containing the necessary keys
        price = float(signals.get('price') or row.get('price') or 0)
        vwap = float(signals.get('vwap') or price)
        rvol = float(signals.get('rvol') or row.get('rvol') or 1.0)
        
        snap_b1 = {
            'price': price,
            'vwap': vwap,
            'rvol': rvol
        }
        b1 = calculate_b1_momentum(snap_b1)
        
        # 2. B2 (Technical)
        rsi = float(signals.get('rsi') or row.get('rsi_14') or 50)
        macd_hist = float(signals.get('macd_hist') or 0)
        # Assume previous is slightly less or same
        macd_prev = macd_hist * 0.9
        
        snap_b2 = {
            'price': price,
            'rsi_14': rsi,
            'macd_histogram': macd_hist,
            'macd_histogram_prev': macd_prev,
            'ema20': float(signals.get('ema_20') or price),
            'ema50': float(signals.get('ema_50') or price),
            'fibonacci_zone': int(signals.get('fib_zone_15m') or row.get('fib_zone_15m') or 0),
            'sar_trend_15m': 1 if row.get('macd_signal') == 'bullish' else -1,
            'sar_trend_4h': 1 if row.get('macd_signal') == 'bullish' else -1,
        }
        b2 = calculate_b2_technical(snap_b2)
        
        # 3. B3 (Fundamental)
        pro_score_val = float(signals.get('pro_score') or row.get('pro_score') or 0) * 10
        fund_cache = {
            'piotroski_score': int(signals.get('piotroski_score') or row.get('piotroski_score') or 4),
            'margin_of_safety': float(signals.get('margin_of_safety') or row.get('undervaluation') or 0),
            'altman_zone': 'grey' if row.get('pro_score', 0) > 0 else 'danger',
            'fundamental_score': pro_score_val,
        }
        b3 = calculate_b3_fundamental(fund_cache)
        
        # 4. B4 (Regime)
        snap_b4 = {
            'price': price,
            'adx': float(signals.get('adx') or 25),
            'atr': float(row.get('atr_14') or (price * 0.02)),
            'sar_trend_4h': 1,
            'mtf_score': float(row.get('technical_score') or 50) / 100
        }
        b4 = calculate_b4_regime(macro_data, snap_b4)
        
        # 5. B5 (Sentiment)
        ia_score_val = float(signals.get('qwen_score') or 0) or float(signals.get('gemini_score') or 0) or 5.0
        fund_cache_b5 = {
            **fund_cache,
            'analyst_rating': float(signals.get('analyst_rating') or 3.5),
            'valuation_status': 'undervalued' if fund_cache['margin_of_safety'] > 0 else 'fairly_valued',
            'days_to_earnings': int(signals.get('days_to_earnings') or 30),
            'short_interest_pct': float(signals.get('short_interest_pct') or 5.0),
        }
        b5 = calculate_b5_sentiment(fund_cache_b5, snap_b2, ia_score=ia_score_val)
        
        # APEX 4H
        blocks = {
            'b1_momentum':    b1['score'],
            'b2_technical':   b2['score'],
            'b3_fundamental': b3['score'],
            'b4_regime':      b4['score'],
            'b5_sentiment':   b5['score'],
        }
        
        # Weights for 4H
        # 'b1_momentum': 0.40, 'b2_technical': 0.30, 'b3_fundamental': 0.10, 'b4_regime': 0.15, 'b5_sentiment': 0.05
        apex_4h = (
            blocks['b1_momentum'] * 0.40 +
            blocks['b2_technical'] * 0.30 +
            blocks['b3_fundamental'] * 0.10 +
            blocks['b4_regime'] * 0.15 +
            blocks['b5_sentiment'] * 0.05
        )
        
        print(f"\nTicker: {ticker:<6} | APEX 4H Real DB: {row.get('apex_4h')}% | Reconstructed: {apex_4h:.1f}%")
        print(f"  - Block 1 (Momentum - 40% weight):    {blocks['b1_momentum']:.1f}/100 | RVOL={rvol:.2f}x | Dist_VWAP={b1.get('components', {}).get('vwap', {}).get('dist_pct', 'N/A')}%")
        print(f"  - Block 2 (Technical - 30% weight):   {blocks['b2_technical']:.1f}/100 | RSI={rsi:.1f} | Fib Zone={snap_b2['fibonacci_zone']}")
        print(f"  - Block 3 (Fundamental - 10% weight): {blocks['b3_fundamental']:.1f}/100 | Piotroski={fund_cache['piotroski_score']}/9 | MOS={fund_cache['margin_of_safety']}% | ProScore={fund_cache['fundamental_score']}")
        print(f"  - Block 4 (Regime - 15% weight):      {blocks['b4_regime']:.1f}/100 | Type={b4['regime_type']} | ADX={snap_b4['adx']:.1f}")
        print(f"  - Block 5 (Sentiment - 5% weight):     {blocks['b5_sentiment']:.1f}/100 | Analyst={fund_cache_b5['analyst_rating']} | AI={ia_score_val}")

if __name__ == "__main__":
    asyncio.run(analyze_apex_blocks())
