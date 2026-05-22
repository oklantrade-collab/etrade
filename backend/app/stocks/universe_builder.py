"""
eTrader v4.5 — Stocks Universe Builder (Dynamic Scanner)
Capa 0: Discovers tradable stocks using multiple data sources.

Scanner Priority:
  1. IB TWS HOT_BY_VOLUME scanner (when connected)
  2. Yahoo Finance Screener API (always available, real-time)
  3. Alpha Vantage Top Movers fallback
  4. Static curated universe fallback

Filtros configurables:
  1. Precio: $1 – $20 (configurable)
  2. Volumen Relativo > 1.5 (configurable)
  3. Volumen > 1M acciones (configurable)
  4. Market Cap > $1B (configurable)
"""
import os
import sys
import asyncio
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.analysis.fundamental_scorer import FundamentalScorer

MODULE = "universe_builder"


class UniverseBuilder:
    def __init__(self):
        self.last_scan_tickers: list[str] = []
        self.f_scorer = FundamentalScorer()

    async def build_daily_watchlist(
        self,
        max_price: float = 20.0,
        min_price: float = 1.0,
        min_market_cap: int = 1_000_000_000,
        min_volume: int = 1_000_000,
        min_rvol: float = 1.5,
        max_results: int = 50,
    ) -> list[dict]:
        """
        Build a dynamic watchlist of Hot by Volume candidates.

        Uses IB Scanner as primary source, then Yahoo Finance Screener as
        fallback. The Yahoo Screener queries Yahoo's real-time database of
        ALL US equities — no hardcoded ticker lists needed.
        """
        log_info(MODULE, f"═══ SCANNER: ${min_price}-${max_price} | "
                         f"Vol>{min_volume/1e6:.0f}M | MCap>{min_market_cap/1e9:.0f}B | "
                         f"RVOL>{min_rvol} ═══")

        candidates = []

        # 1. Try IB Scanner (best quality — real TWS data)
        candidates = await self._scan_ib(
            max_price=max_price, min_price=min_price,
            min_market_cap=min_market_cap, min_volume=min_volume,
            max_results=max_results,
        )

        # 2. Fallback: Yahoo Finance Screener (excellent — full US market)
        if not candidates:
            log_info(MODULE, "IB Scanner unavailable — using Yahoo Finance Screener...")
            candidates = await self._scan_yahoo_screener(
                max_price=max_price, min_price=min_price,
                min_market_cap=min_market_cap, min_volume=min_volume,
                min_rvol=min_rvol, max_results=max_results,
            )

        # 3. Fallback: Alpha Vantage
        if not candidates:
            log_warning(MODULE, "Yahoo Screener failed — trying Alpha Vantage...")
            candidates = await self._scan_alphavantage_fallback(max_price=max_price)

        # 4. Final fallback: static curated list
        if not candidates:
            log_warning(MODULE, "All scanners failed — using static fallback...")
            candidates = await self._scan_static_fallback(max_price=max_price)

        # Limit results
        candidates = candidates[:max_results]

        # ── 5. FUNDAMENTAL SCORING (Capa 0+ — "Futuras Gigantes") ──
        if candidates:
            log_info(MODULE, f"🧠 Calculando Fundamental Scores para {len(candidates)} candidatos...")
            # Cargar configuración HIBRIDA (Nube + Local Fallback)
            u_settings = None
            try:
                settings_res = get_supabase().table("universe_settings").select("*").eq("id", 1).maybe_single().execute()
                u_settings = settings_res.data
            except:
                pass

            if not u_settings:
                try:
                    import json
                    spath = "c:/Fuentes/eTrade/backend/data/universe_settings.json"
                    if os.path.exists(spath):
                        with open(spath, 'r') as f:
                            u_settings = json.load(f)
                except:
                    pass

            # 3. Obtener performance del SPY (Index Benchmark)
            spy_perf = await self.f_scorer.get_spy_performance_6m()
            
            # Procesar fundamentales en lotes para no saturar
            tasks = []
            for c in candidates:
                price = c.get("_price", 100) # Fallback 100 si no hay precio
                rvol = c.get("_rvol", 1.0)
                tasks.append(self.f_scorer.calculate_score(c["ticker"], spy_perf, price, u_settings, rvol=rvol))
            
            f_results = await asyncio.gather(*tasks)
            
            for i, f_data in enumerate(f_results):
                if f_data:
                    candidates[i].update(f_data)
                else:
                    # Fallback si falla el fundamental
                    candidates[i]["fundamental_score"] = 0

        if candidates:
            await self._save_to_db(candidates)
            self.last_scan_tickers = [c["ticker"] for c in candidates]
            
            # Preparar estadisticas para el Dashboard
            counts = {"FUTURE_GIANT": 0, "GROWTH_LEADER": 0, "TOTAL": len(candidates)}
            for c in candidates:
                pt = str(c.get("pool_type", ""))
                if "GIANT" in pt: counts["FUTURE_GIANT"] += 1
                if "LEADER" in pt: counts["GROWTH_LEADER"] += 1
            
            log_info(MODULE, f"✅ Universe Sweep Complete: {counts}")
            return candidates
        else:
            log_warning(MODULE, "No candidates found after all scanners")
            return []

    # ─── 1. IB Scanner (Primary) ───────────────────────────────
    async def _scan_ib(self, max_price, min_price, min_market_cap, min_volume, max_results) -> list[dict]:
        try:
            from app.data.ib_scanner import scan_hot_by_volume, scan_top_gainers
            
            # 1a. HOT_BY_VOLUME (original scanner)
            results_vol = await scan_hot_by_volume(
                max_results=max_results,
                min_price=min_price,
                max_price=max_price,
                min_volume=min_volume,
                min_market_cap=min_market_cap,
            )
            
            # 1b. TOP_PERC_GAIN (momentum scanner — catches explosive movers)
            results_gain = []
            try:
                results_gain = await scan_top_gainers(
                    max_results=30,
                    min_price=min_price,
                    max_price=max_price,
                    min_volume=min_volume,
                )
                if results_gain:
                    log_info(MODULE, f"🚀 Top Gainers scanner: {len(results_gain)} momentum candidates found")
            except Exception as tg_e:
                log_warning(MODULE, f"Top Gainers scanner skipped: {tg_e}")

            if not results_vol and not results_gain:
                return []
            
            # Merge and deduplicate (HOT_BY_VOLUME first, then TOP_PERC_GAIN)
            seen_tickers = set()
            merged = []
            
            for r in (results_vol or []):
                ticker = r["ticker"].upper()
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    merged.append({
                        "ticker": ticker,
                        "catalyst_score": max(1, 10 - r.get("rank", 50) // 5),
                        "source": "ib_scanner",
                    })
            
            for r in (results_gain or []):
                ticker = r["ticker"].upper()
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    merged.append({
                        "ticker": ticker,
                        "catalyst_score": max(1, 10 - r.get("rank", 50) // 5),
                        "source": "ib_top_gainers",
                    })
            
            log_info(MODULE, f"IB Scanners merged: {len(merged)} unique tickers "
                             f"(Vol: {len(results_vol or [])}, Gain: {len(results_gain or [])})")
            
            return merged

        except Exception as e:
            log_warning(MODULE, f"IB Scanner not available: {e}")
            return []

    # ─── 2. Yahoo Finance Screener (Primary Fallback) ──────────
    async def _scan_yahoo_screener(
        self,
        max_price: float,
        min_price: float,
        min_market_cap: int,
        min_volume: int,
        min_rvol: float,
        max_results: int,
    ) -> list[dict]:
        """
        Uses yfinance's built-in Screener API to query Yahoo Finance's
        real-time stock database. This dynamically discovers ALL US equities
        matching the user's 4 criteria — no hardcoded ticker lists.

        Returns stocks sorted by volume (descending), matching:
          - Price: $min_price to $max_price
          - Volume: > min_volume
          - Market Cap: > min_market_cap
          - Region: US only
        """
        try:
            from yfinance.screener import EquityQuery, screen

            # Build the query matching all 4 criteria
            query = EquityQuery('AND', [
                EquityQuery('EQ', ['region', 'us']),
                EquityQuery('GT', ['intradaymarketcap', min_market_cap]),
                EquityQuery('GT', ['dayvolume', min_volume]),
                EquityQuery('LT', ['intradayprice', max_price]),
                EquityQuery('GT', ['intradayprice', min_price]),
            ])

            # Fetch from Yahoo — get a large pool, then filter by RVOL locally
            # Yahoo max size is 250. We fetch all matching, then rank by RVOL.
            fetch_size = min(250, max(max_results * 3, 100))
            res = screen(query, size=fetch_size, sortField='dayvolume', sortAsc=False)

            if not res or not res.get('quotes'):
                log_warning(MODULE, "Yahoo Screener: no results returned")
                return []

            total_in_yahoo = res.get('total', 0)
            log_info(MODULE, f"Yahoo Screener: {total_in_yahoo} total matches in US market, "
                             f"fetched {len(res['quotes'])} by volume")

            candidates = []
            for rank, q in enumerate(res['quotes']):
                sym = q.get('symbol', '')
                if not sym or '.' in sym:  # Skip ADRs with dots
                    continue

                price = q.get('regularMarketPrice', 0)
                vol = q.get('regularMarketVolume', 0)
                avg_vol = q.get('averageDailyVolume3Month', 1)
                mcap = q.get('marketCap', 0)
                chg_pct = q.get('regularMarketChangePercent', 0)
                name = q.get('shortName', '')

                # Compute RVOL (today's volume / 3-month average)
                rvol = vol / avg_vol if avg_vol > 0 else 0

                candidates.append({
                    "ticker": sym.upper(),
                    "catalyst_score": max(1, min(10, int(vol / 5_000_000))),
                    "source": "yf_screener",
                    # Extra metadata for downstream processing
                    "_price": price,
                    "_volume": vol,
                    "_avg_volume": avg_vol,
                    "_rvol": rvol,
                    "_market_cap": mcap,
                    "_change_pct": chg_pct,
                    "_name": name,
                })

            # To ensure we don't miss high volume leaders (like OPEN, SOFI), 
            # we will keep the top 50% by raw volume, and the top 50% by RVOL.
            candidates_by_vol = sorted(candidates, key=lambda x: x.get("_volume", 0), reverse=True)
            candidates_by_rvol = sorted(candidates, key=lambda x: x.get("_rvol", 0), reverse=True)
            
            half_results = max_results // 2
            
            final_candidates_set = set()
            final_candidates = []
            
            # 1. Add top by RVOL
            for c in candidates_by_rvol:
                if len(final_candidates) >= half_results:
                    break
                if c["ticker"] not in final_candidates_set:
                    final_candidates.append(c)
                    final_candidates_set.add(c["ticker"])
                    
            # 2. Add top by Volume
            for c in candidates_by_vol:
                if len(final_candidates) >= max_results:
                    break
                if c["ticker"] not in final_candidates_set:
                    final_candidates.append(c)
                    final_candidates_set.add(c["ticker"])

            # Log RVOL distribution for debugging
            rvol_above_15 = sum(1 for c in final_candidates if c.get("_rvol", 0) >= 1.5)
            rvol_above_10 = sum(1 for c in final_candidates if c.get("_rvol", 0) >= 1.0)
            log_info(MODULE, f"Yahoo Screener: {len(candidates)} US stocks fetched | "
                             f"Kept {len(final_candidates)} | RVOL>=1.5: {rvol_above_15} | RVOL>=1.0: {rvol_above_10}")

            return final_candidates

        except Exception as e:
            log_warning(MODULE, f"Yahoo Screener failed: {e}")
            return []

    async def _calculate_gap(self, ticker: str, current_price: float) -> float:
        """
        Calculates the gap percentage from yesterday's close.
        (CurrentPrice - PrevClose) / PrevClose
        """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            # Fetch only today and yesterday
            hist = t.history(period="2d")
            if len(hist) < 2:
                return 0.0
            
            prev_close = hist['Close'].iloc[-2]
            if prev_close <= 0:
                return 0.0
            
            gap = (current_price - prev_close) / prev_close
            return round(gap * 100, 2)
        except Exception:
            return 0.0

    # ─── 3. Alpha Vantage Fallback ─────────────────────────────
    async def _scan_alphavantage_fallback(self, max_price: float) -> list[dict]:
        try:
            from app.data.ib_scanner import fallback_top_movers
            results = await fallback_top_movers()
            if not results:
                return []

            candidates = []
            for r in results:
                price = r.get("price", 0)
                if price <= 0 or price > max_price:
                    continue
                candidates.append({
                    "ticker": r["ticker"].upper(),
                    "catalyst_score": 5,
                    "source": "av_fallback",
                })
            return candidates

        except Exception as e:
            log_warning(MODULE, f"Alpha Vantage fallback failed: {e}")
            return []

    # ─── 4. Static Curated Fallback ────────────────────────────
    async def _scan_static_fallback(self, max_price: float) -> list[dict]:
        """Last-resort fallback using a curated list of liquid US stocks."""
        UNIVERSE = [
            "AAL", "WULF", "ET", "SOFI", "NIO", "PLUG", "SNAP", "MARA",
            "RIOT", "LCID", "HOOD", "RIVN", "PLTR", "NOK", "F", "JBLU",
            "COIN", "SQ", "DKNG", "OPEN", "BBD", "VALE", "KOS", "DNN",
        ]
        return [{
            "ticker": t,
            "catalyst_score": 5,
            "source": "static_fallback",
        } for t in UNIVERSE]

    # ─── Save to Database ──────────────────────────────────────
    async def _save_to_db(self, candidates: list[dict]):
        sb = get_supabase()
        today = date.today().isoformat()

        rows = []
        for c in candidates:
            rows.append({
                "ticker": c["ticker"],
                "pool_type": c.get("pool_type", "")[:50] if c.get("pool_type") else "",
                "catalyst_score": c.get("catalyst_score", 5),
                "catalyst_type": "HOT_BY_VOLUME" if c.get("_price", 100) < 20 else "SWEEP",
                "date": today,
                "price": round(float(c.get("_price", 0) or 0), 2),
                "hard_filter_pass": True,
                "quality_flag": c.get("quality_flag", "PASS"),
                # CAMPOS FUNDAMENTALES
                "fundamental_score": round(float(c.get("fundamental_score", 0) or 0), 2),
                "revenue_growth_yoy": round(float(c.get("revenue_growth_yoy", 0) or 0), 2),
                "gross_margin": round(float(c.get("gross_margin", 0) or 0), 2),
                "eps_growth_qoq": round(float(c.get("eps_growth_qoq", 0) or 0), 2),
                "rs_score_6m": round(float(c.get("rs_score_6m", 0) or 0), 2),
                "inst_ownership_pct": round(float(c.get("inst_ownership_pct", 0) or 0), 2),
                "market_cap_mln": round(float(c.get("market_cap_mln", 0) or 0), 2),
                "gap_pct": round(float(c.get("_change_pct", 0) or 0), 2),
                "intrinsic_value": round(float(c.get("intrinsic_value", 0) or 0), 2),
                "is_overvalued": bool(c.get("is_overvalued", False))
            })

        # Log sample for debugging
        if rows:
            sample = rows[0]
            log_info(MODULE, f"Sample row to save: {sample['ticker']} | price={sample['price']} | "
                             f"fund_score={sample['fundamental_score']} | pool={sample['pool_type']}")

        # 3. Guardar con Reintentos (PGRST002/Timeout protection)
        max_retries = 5
        current_rows = [dict(r) for r in rows]
        for attempt in range(max_retries):
            try:
                # LIMPIEZA SELECTIVA: Borramos lo que el escáner automático encontró hoy, 
                # PERO preservamos lo que el usuario agregó manualmente (MANUAL_ADD).
                sb.table("watchlist_daily")\
                    .delete()\
                    .eq("date", today)\
                    .neq("catalyst_type", "MANUAL_ADD")\
                    .execute() 
                
                sb.table("watchlist_daily").insert(current_rows).execute()
                log_info(MODULE, f"DB OK: {len(current_rows)} tickers saved for {today}")
                return # Exit on success
            except Exception as e:
                e_str = str(e)
                # Check for missing columns in Supabase schema cache
                missing_col = None
                if "Could not find the" in e_str and "column of 'watchlist_daily' in the schema cache" in e_str:
                    # Extract the missing column name
                    import re
                    match = re.search(r"Could not find the '([^']+)' column", e_str)
                    if match:
                        missing_col = match.group(1)
                
                if missing_col:
                    log_warning(MODULE, f"Schema mismatch: column '{missing_col}' does not exist in watchlist_daily table. Removing it and retrying...")
                    # Remove the missing column from all rows
                    for r in current_rows:
                        if missing_col in r:
                            del r[missing_col]
                    # Retry immediately without waiting
                    continue
                    
                if "PGRST002" in e_str or "schema cache" in e_str or "Timeout" in e_str:
                    log_warning(MODULE, f"Supabase busy (Attempt {attempt+1}/{max_retries}). Retrying in 1s...")
                    await asyncio.sleep(1)
                    continue
                
                import traceback
                log_error(MODULE, f"DB insert failed: {e}\n{traceback.format_exc()}")
                break
