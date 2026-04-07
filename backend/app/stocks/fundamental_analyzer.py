"""
eTrader v4.5 — Fundamental Analyzer (Capa 3)
Determines Valuation Mode (A: Value | B: Growth) and prepares 
fundamental metrics for AI validation.

Mode A: Fundamental/Intrinsic Value Focus (Low P/E, Dividend, Safety)
Mode B: Growth/Momentum Focus (RVOL, High Growth, Narrative)
"""
import json
import os
import sys
from typing import Optional

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.data.yfinance_provider import YFinanceProvider

MODULE = "fundamental_analyzer"

class FundamentalAnalyzer:
    def __init__(self):
        self.provider = YFinanceProvider()

    async def analyze_ticker(self, ticker: str) -> dict | None:
        """
        Executes Capa 3 logic for a stock.
        """
        log_info(MODULE, f"Analyzing fundamentals for {ticker}...")
        
        try:
            # 1. Fetch info from yfinance
            info = await self.provider.get_ticker_info(ticker)
            if not info:
                return None

            # 2. Determine Mode (A vs B)
            # Default to B (Growth) if no PE or high Beta
            pe = info.get("pe_ratio")
            beta = info.get("beta", 1.0) or 1.0
            div_yield = info.get("dividend_yield", 0) or 0
            
            if pe and pe < 20 and div_yield > 0.01:
                mode = "A" # Value
            elif beta > 1.5:
                mode = "B" # High Beta / Growth
            else:
                mode = "B" # Conservative Growth

            # 3. Calculate Margin of Safety (for A) or Momentum (for B)
            price = info.get("current_price", 0)
            
            if mode == "A":
                # Graham Formula simplified for intrinsic value
                # IV = SQRT(22.5 * Earnings * BookValue)
                # But here we estimate based on target price (if available)
                intrinsic = info.get("50d_avg", price) * 1.1 # Placeholder formula
                margin = ((intrinsic - price) / intrinsic) * 100 if intrinsic > 0 else 0
            else:
                intrinsic = info.get("200d_avg", price)
                margin = ((price - intrinsic) / intrinsic) * 100 if intrinsic > 0 else 0

            status = "stable" if abs(margin) < 15 else "volatile"
            
            # 4. Prepare result for DB Cache & AI validation
            result = {
                "ticker":            ticker,
                "valuation_mode":    mode,
                "intrinsic_value":   round(float(intrinsic), 2),
                "current_price":     round(float(price), 2),
                "margin_of_safety":  round(float(margin), 2),
                "valuation_status":  status,
                "fundamental_score": 0.0, # To be filled by AI validation
                "mode_b_metrics_json": {
                    "pe": pe,
                    "beta": beta,
                    "yield": div_yield,
                    "sector": info.get("sector"),
                    "peg": info.get("peg_ratio"),
                },
                "confidence": "medium"
            }

            # 5. Save to fundamental_cache
            await self._save_cache(result)
            return result

        except Exception as e:
            log_error(MODULE, f"Fundamental analysis failed for {ticker}: {e}")
            return None

    async def _save_cache(self, data: dict):
        """Upserts result to fundamental_cache table."""
        sb = get_supabase()
        try:
            # Prepare row for Supabase
            row = {
                "ticker":              data["ticker"],
                "valuation_mode":      data["valuation_mode"],
                "intrinsic_value":     data["intrinsic_value"],
                "current_price":       data["current_price"],
                "margin_of_safety":    data["margin_of_safety"],
                "valuation_status":    data["valuation_status"],
                "fundamental_score":   data["fundamental_score"],
                "mode_b_metrics_json": data["mode_b_metrics_json"],
                "confidence":          data["confidence"],
                "refreshed_at":       "now()"
            }
            
            sb.table("fundamental_cache").upsert(row, on_conflict="ticker").execute()
            log_info(MODULE, f"Saved fundamental cache for {data['ticker']}")
        except Exception as e:
            log_error(MODULE, f"Error saving fundamental cache: {e}")

if __name__ == "__main__":
    import asyncio
    analyzer = FundamentalAnalyzer()
    asyncio.run(analyzer.analyze_ticker("AAPL"))
