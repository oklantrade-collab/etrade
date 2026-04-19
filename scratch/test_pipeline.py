"""
Test completo del pipeline: Scorer + Save to DB
Simula exactamente lo que hace universe_builder.build_daily_watchlist()
"""
import sys, os, asyncio, json
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")

from app.analysis.fundamental_scorer import FundamentalScorer
from app.core.supabase_client import get_supabase
from datetime import date

async def test_full_pipeline():
    scorer = FundamentalScorer()
    
    # 1. Simular settings parciales (como vienen de Supabase/JSON)
    partial_settings = {
        "w_rev_growth": 25, "w_gross_margin": 20, "w_eps_growth": 20, 
        "w_rs_score": 20, "w_inst_ownership": 15,
        "fg_mcap_min": 300
        # NOTA: faltan ex_vol_min, ex_debt_equity_max, fg_mcap_max, etc.
    }
    
    spy_perf = await scorer.get_spy_performance_6m()
    print(f"SPY 6m perf: {spy_perf:.1f}%")
    
    # 2. Probar con NOK
    result = await scorer.calculate_score("NOK", spy_perf, 5.0, partial_settings)
    if result:
        print(f"\nNOK Score: {result['fundamental_score']}")
        print(f"  Pool: {result['pool_type']}")
        print(f"  Rev Growth: {result['revenue_growth_yoy']}%")
        print(f"  Margin: {result['gross_margin']}%")
        print(f"  RS: {result['rs_score_6m']}")
        print(f"  Inst Own: {result['inst_ownership_pct']}%")
        print(f"  MCap: {result['market_cap_mln']}M")
        print(f"  Quality: {result['quality_flag']}")
    else:
        print("SCORER RETURNED None - STILL BROKEN!")
        return
    
    # 3. Probar guardado en DB (Ticker corto < 10 chars)
    sb = get_supabase()
    today = date.today().isoformat()
    test_row = {
        "ticker": "TS_PIPEL",
        "pool_type": result.get("pool_type", "")[:50] if result.get("pool_type") else "",
        "catalyst_score": 5,
        "catalyst_type": "SWEEP",
        "date": today,
        "price": 5.12,
        "hard_filter_pass": True,
        "quality_flag": result.get("quality_flag", "PASS"),
        "fundamental_score": round(float(result.get("fundamental_score", 0) or 0), 2),
        "revenue_growth_yoy": round(float(result.get("revenue_growth_yoy", 0) or 0), 2),
        "gross_margin": round(float(result.get("gross_margin", 0) or 0), 2),
        "eps_growth_qoq": round(float(result.get("eps_growth_qoq", 0) or 0), 2),
        "rs_score_6m": round(float(result.get("rs_score_6m", 0) or 0), 2),
        "inst_ownership_pct": round(float(result.get("inst_ownership_pct", 0) or 0), 2),
        "market_cap_mln": round(float(result.get("market_cap_mln", 0) or 0), 2),
    }
    
    try:
        sb.table("watchlist_daily").delete().eq("ticker", "__TEST_PIPELINE__").execute()
        sb.table("watchlist_daily").insert(test_row).execute()
        print(f"\nDB INSERT: SUCCESS!")
        
        # Verify
        res = sb.table("watchlist_daily").select("*").eq("ticker", "__TEST_PIPELINE__").execute()
        if res.data:
            print(f"DB VERIFY: {json.dumps(res.data[0], indent=2, default=str)}")
        
        # Cleanup
        sb.table("watchlist_daily").delete().eq("ticker", "__TEST_PIPELINE__").execute()
    except Exception as e:
        print(f"\nDB INSERT FAILED: {e}")

asyncio.run(test_full_pipeline())
