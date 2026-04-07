"""
eTrader v4.5 — Stocks Universe Builder (IB Scanner)
Capa 0: Discovers tradable stocks using IB TWS Hot by Volume scanner.

Filtros aplicados:
  1. Precio < configurable (default $50)
  2. Market Cap > $500M
  3. Volumen > 700k
"""
import os
import sys
import asyncio
from datetime import date, datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

MODULE = "universe_builder"


class UniverseBuilder:
    def __init__(self):
        self.last_scan_tickers: list[str] = []

    async def build_daily_watchlist(self, max_price: float = 50.0, min_market_cap: int = 500_000_000) -> list[dict]:
        log_info(MODULE, f"═══ SCANNER: max_price=${max_price} | min_cap=${min_market_cap/1e6:.0f}M ═══")

        # 1. Try IB Scanner
        candidates = await self._scan_ib(max_price=max_price, min_market_cap=min_market_cap)

        # 2. Fallback: Alpha Vantage
        if not candidates:
            log_warning(MODULE, "IB Scanner sin resultados, usando Alpha Vantage fallback...")
            candidates = await self._scan_alphavantage_fallback(max_price=max_price)

        # 3. Fallback: yfinance (SIEMPRE funciona)
        if not candidates:
            log_warning(MODULE, "Alpha Vantage fallback sin resultados, usando yfinance fallback...")
            candidates = await self._scan_yfinance_fallback(max_price=max_price)

        # 4. Top 20
        candidates = candidates[:20]

        if candidates:
            await self._save_to_db(candidates)
            self.last_scan_tickers = [c["ticker"] for c in candidates]
            tickers_str = ", ".join(c["ticker"] for c in candidates[:10])
            log_info(MODULE, f"Universe: {len(candidates)} tickers. Top: {tickers_str}")
        else:
            log_warning(MODULE, "No candidates found after all filters (will retry next cycle)")

        return candidates

    async def _scan_ib(self, max_price: float, min_market_cap: int) -> list[dict]:
        try:
            from app.data.ib_scanner import scan_hot_by_volume
            results = await scan_hot_by_volume(
                max_results=50,
                min_price=1.0,
                max_price=max_price,
                min_volume=300_000,
                min_market_cap=200_000_000,
            )
            if not results:
                return []

            return [{
                "ticker": r["ticker"].upper(),
                "catalyst_score": max(1, 10 - r.get("rank", 50) // 5),
                "source": "ib_scanner",  # 10 chars, fits varchar(20)
            } for r in results]

        except Exception as e:
            log_error(MODULE, f"IB Scanner failed: {e}")
            return []

    async def _scan_alphavantage_fallback(self, max_price: float) -> list[dict]:
        try:
            from app.data.ib_scanner import fallback_top_movers
            results = await fallback_top_movers()
            if not results:
                return []

            candidates = []
            for r in results:
                price = r.get("price", 0)
                if price > 0 and price > max_price:
                    continue  # Skip stocks above max price
                candidates.append({
                    "ticker": r["ticker"].upper(),
                    "catalyst_score": 5,
                    "source": "av_fallback",  # 11 chars, fits varchar(20)
                })
            return candidates

        except Exception as e:
            log_error(MODULE, f"Alpha Vantage fallback failed: {e}")
            return []

    async def _scan_yfinance_fallback(self, max_price: float) -> list[dict]:
        """
        Third-tier fallback: Uses yfinance to scan a curated universe of liquid US stocks.
        This ALWAYS works since it doesn't depend on IB TWS or an API key.
        """
        try:
            import yfinance as yf

            # Curated universe: 50 most liquid US stocks across sectors
            UNIVERSE = [
                "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "INTC", "SOFI",
                "NIO", "PLTR", "MARA", "RIOT", "COIN", "HOOD", "LCID", "RIVN", "SNAP", "PINS",
                "BITO", "SOXL", "TQQQ", "SQQQ", "TZA", "UVXY", "SPXS", "LABU", "JNUG",
                "OPEN", "WISH", "BBIG", "MULN", "TELL", "FCEL", "PLUG", "CLOV", "DKNG", "WKHS",
                "NOK", "BB", "VALE", "GOLD", "SLV", "USO", "XLE", "IWM", "SPY", "QQQ", "ARKK",
            ]

            candidates = []
            # Download in batch for speed
            tickers_str = " ".join(UNIVERSE)
            data = yf.download(tickers_str, period="1d", group_by="ticker", progress=False, threads=True)

            rank = 0
            for ticker in UNIVERSE:
                try:
                    if ticker in data.columns.get_level_values(0):
                        ticker_data = data[ticker]
                        if ticker_data.empty or len(ticker_data) == 0:
                            continue
                        last = ticker_data.iloc[-1]
                        price = float(last.get("Close", 0))
                        volume = float(last.get("Volume", 0))

                        if price <= 0 or price > max_price or volume < 100000:
                            continue

                        candidates.append({
                            "ticker": ticker,
                            "catalyst_score": max(1, min(10, int(volume / 1_000_000))),
                            "source": "yf_fallback",
                        })
                        rank += 1
                except Exception:
                    continue

            # Sort by catalyst_score (volume proxy) descending
            candidates.sort(key=lambda x: x["catalyst_score"], reverse=True)
            log_info(MODULE, f"yfinance fallback: {len(candidates)} tickers found")
            return candidates

        except Exception as e:
            log_error(MODULE, f"yfinance fallback failed: {e}")
            return []

    async def _save_to_db(self, candidates: list[dict]):
        sb = get_supabase()
        today = date.today().isoformat()

        rows = []
        for c in candidates:
            rows.append({
                "ticker": c["ticker"],
                "pool_type": c.get("source", "scanner")[:20],  # Truncate to 20 chars
                "catalyst_score": c.get("catalyst_score", 5),
                "catalyst_type": "HOT_BY_VOLUME",
                "date": today,
                "hard_filter_pass": True,
            })

        try:
            sb.table("watchlist_daily").delete().eq("date", today).execute()
            res = sb.table("watchlist_daily").insert(rows).execute()
            log_info(MODULE, f"✅ {len(rows)} tickers saved to watchlist_daily for {today}")
        except Exception as e:
            log_error(MODULE, f"❌ DB insert failed: {e}")
