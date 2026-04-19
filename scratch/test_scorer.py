import asyncio
import os
import sys
from datetime import date

# Añadir path para importar app
sys.path.append(os.path.abspath(os.path.join(os.getcwd())))

from app.analysis.fundamental_scorer import FundamentalScorer
from app.core.logger import log_info

async def test_ticker(ticker):
    scorer = FundamentalScorer()
    # Simular settings
    settings = {
        "fg_mcap_min": 100, "fg_rev_growth_min": 20, "fg_price_max": 200, "fg_rs_min": 50,
        "gl_mcap_min": 500, "gl_rev_growth_min": 10, "gl_margin_min": 15, "gl_rs_min": 60, "gl_inst_min": 10, "gl_price_max": 500,
        "w_rev_growth": 25, "w_gross_margin": 20, "w_eps_growth": 20, "w_rs_score": 20, "w_inst_ownership": 15,
        "ex_debt_equity_max": 3.0, "ex_vol_min": 100000
    }
    
    spy_perf = await scorer.get_spy_performance_6m()
    print(f"\n--- Probando {ticker} ---")
    result = await scorer.calculate_score(ticker, spy_perf, 0, settings)
    import json
    print(json.dumps(result, indent=4))

if __name__ == "__main__":
    asyncio.run(test_ticker("NOK"))
    asyncio.run(test_ticker("WULF"))
