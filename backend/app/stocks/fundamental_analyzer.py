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
import yfinance as yf
import numpy as np

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
        Executes Capa 3 logic for a stock, fetching all metrics for the Valuation Engine.
        """
        log_info(MODULE, f"Enriching fundamentals for {ticker} via YFinance...")
        
        try:
            t = yf.Ticker(ticker)
            info = t.info
            if not info:
                return None

            # 1. Fetch deep financials (Balance Sheet, Cash Flow, etc.)
            # Nota: yfinance es lento aquí, pero es necesario para el modo matemático preciso.
            # En producción, esto se cachea.
            try:
                bs = t.balance_sheet
                cf = t.cashflow
                is_stmt = t.financials
                
                # Obtener periodos (actual y anterior)
                cols = bs.columns if bs is not None and len(bs.columns) >= 2 else []
                has_prev = len(cols) >= 2
                
                def get_val(df, label, col_idx=0):
                    try:
                        if df is None or label not in df.index: return 0
                        val = df.loc[label].iloc[col_idx]
                        return float(val) if not np.isnan(val) else 0
                    except: return 0

                # Mapeo para Piotroski / Graham / Altman
                f_data = {
                    'roa': info.get('returnOnAssets', 0),
                    'roa_prev': get_val(is_stmt, 'Net Income', 1) / get_val(bs, 'Total Assets', 1) if has_prev and get_val(bs, 'Total Assets', 1) > 0 else 0,
                    'ocf': info.get('operatingCashFlow', 0) or get_val(cf, 'Operating Cash Flow', 0),
                    'net_income': info.get('netIncome', 0) or get_val(is_stmt, 'Net Income', 0),
                    'total_assets': info.get('totalAssets', 0) or get_val(bs, 'Total Assets', 0),
                    'current_assets': info.get('totalCurrentAssets', 0) or get_val(bs, 'Current Assets', 0),
                    'current_liabilities': info.get('totalCurrentLiabilities', 0) or get_val(bs, 'Current Liabilities', 0),
                    'long_term_debt': info.get('longTermDebt', 0) or get_val(bs, 'Long Term Debt', 0),
                    'long_term_debt_prev': get_val(bs, 'Long Term Debt', 1) if has_prev else 0,
                    'total_liabilities': info.get('totalLiabilitiesNetMinorityInterest', 0) or get_val(bs, 'Total Liabilities Net Minority Interest', 0),
                    'retained_earnings': get_val(bs, 'Retained Earnings', 0),
                    'market_cap': info.get('marketCap', 0),
                    'eps': info.get('trailingEps', 0),
                    'fcf_per_share': (info.get('freeCashflow', 0) or get_val(cf, 'Free Cash Flow', 0)) / (info.get('sharesOutstanding', 1)),
                    'book_value_per_share': info.get('bookValue', 0),
                    'current_ratio': info.get('currentRatio', 0),
                    'current_ratio_prev': get_val(bs, 'Current Assets', 1) / get_val(bs, 'Current Liabilities', 1) if has_prev and get_val(bs, 'Current Liabilities', 1) > 0 else 0,
                    'gross_margin': info.get('grossMargins', 0),
                    'gross_margin_prev': get_val(is_stmt, 'Gross Profit', 1) / get_val(is_stmt, 'Total Revenue', 1) if has_prev and get_val(is_stmt, 'Total Revenue', 1) > 0 else 0,
                    'asset_turnover': info.get('totalRevenue', 0) / info.get('totalAssets', 1),
                    'asset_turnover_prev': get_val(is_stmt, 'Total Revenue', 1) / get_val(bs, 'Total Assets', 1) if has_prev and get_val(bs, 'Total Assets', 1) > 0 else 0,
                    'revenue_growth_yoy': info.get('revenueGrowth', 0.05),
                    'ebit': info.get('ebitda', 0) * 0.8, # Estimación simple si no hay EBIT
                    'revenue': info.get('totalRevenue', 0),
                    'shares_outstanding': info.get('sharesOutstanding', 1),
                    'shares_outstanding_prev': get_val(bs, 'Ordinary Shares Number', 1) if has_prev else info.get('sharesOutstanding', 1),
                    'sector': info.get('sector', 'Technology'),
                    'analyst_rating': max(1, min(10, round(-2.25 * (info.get('recommendationMean') or 3) + 12.25, 1)))
                }
                
                # Cleanup de NaNs y ceros críticos
                for k, v in f_data.items():
                    if isinstance(v, float) and np.isnan(v): f_data[k] = 0
                if f_data['total_assets'] <= 0: f_data['total_assets'] = 1
                if f_data['shares_outstanding'] <= 0: f_data['shares_outstanding'] = 1

                return f_data

            except Exception as e:
                log_warning(MODULE, f"Deep financials fetch failed for {ticker}: {e}. Using info fallback.")
                # Fallback to basic info if deep financials fail
                return {
                    'roa': info.get('returnOnAssets', 0),
                    'ocf': info.get('operatingCashFlow', 0),
                    'net_income': info.get('netIncome', 0),
                    'total_assets': info.get('totalAssets', 1),
                    'market_cap': info.get('marketCap', 0),
                    'eps': info.get('trailingEps', 0),
                    'book_value_per_share': info.get('bookValue', 0),
                    'sector': info.get('sector', 'Default'),
                    'revenue_growth_yoy': info.get('revenueGrowth', 0.05),
                    'analyst_rating': max(1, min(10, round(-2.25 * (info.get('recommendationMean') or 3) + 12.25, 1)))
                }

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
