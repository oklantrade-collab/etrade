"""
eTrader v4.5 — Stocks Scheduler (Worker)
Main worker for the Stocks module running 5-minute cycles during US market hours.

Market Hours (Eastern Time):
  - Pre-market scan: 09:00 ET
  - Market open: 09:30 ET
  - Market close: 16:00 ET
  - Post-market: until 16:30 ET

The worker:
  1. Downloads OHLCV data via yfinance (historical/swing)
  2. Calculates technical indicators (TA-Lib via 'ta')
  3. Calculates RVOL and volume spikes
  4. Estimates slippage and liquidity
  5. Upserts results to Supabase
  6. Triggers AI analysis pipelines when scores warrant (Sprint 6+)
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import numpy as np

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning, log_debug
from app.core.supabase_client import get_supabase
from app.workers.market_sweep import run_market_sweep
from app.analysis.movement_classifier import classify_movement
from app.analysis.smart_limit import calculate_smart_limit_price
from app.analysis.fibonacci_bb import fibonacci_bollinger
from app.core.market_hours import is_market_open, get_nyc_now

MODULE = "stocks_scheduler"

# ── Market Hours (Eastern Time) ──
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
PREMARKET_HOUR = 4
PREMARKET_MINUTE = 0


def is_market_hours_simple() -> bool:
    """Check if current time is within US market hours (ET) using centralized utility."""
    is_open, _ = is_market_open()
    return is_open



def get_stocks_config() -> dict:
    """Load stocks configuration from Supabase."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_config").select("key, value").execute()
        config = {}
        for row in res.data:
            val = row["value"]
            # Auto-cast numeric values
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except (ValueError, TypeError):
                pass
            config[row["key"]] = val
        return config
    except Exception as e:
        log_warning(MODULE, f"Error loading stocks_config: {e}")
        return {
            "total_capital_usd": 5000,
            "paper_mode_active": True,
            "kill_switch_active": False,
        }


async def get_open_positions_tickers() -> set[str]:
    """Helper to get tickers with open positions."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_positions").select("ticker").eq("status", "open").execute()
        return set(p["ticker"] for p in (res.data or []))
    except:
        return set()


async def get_watchlist(config: dict) -> list[str]:
    """
    Get the active watchlist tickers.
    
    Priority:
    1. Today's watchlist_daily entries that passed hard_filter
    2. Most recent watchlist_daily entries (yesterday, etc.)
    3. Fall back to default core tickers
    """
    sb = get_supabase()
    try:
        from datetime import date, timedelta
        today = date.today().isoformat()

        # 1. Today's watchlist
        res = sb.table("watchlist_daily")\
            .select("ticker")\
            .eq("date", today)\
            .eq("hard_filter_pass", True)\
            .order("catalyst_score", desc=True)\
            .limit(500)\
            .execute()

        tickers = set(r["ticker"] for r in (res.data or []))

        # 2. Add open positions (CRITICAL for monitoring SELL signals)
        pos_res = sb.table("stocks_positions").select("ticker").eq("status", "open").execute()
        for p in (pos_res.data or []):
            tickers.add(p["ticker"])

        if tickers:
            ticker_list = list(tickers)
            log_info(MODULE, f"Watchlist from DB (today + positions): {len(ticker_list)} tickers")
            return ticker_list

        # Fallback: most recent watchlist (last 3 days)
        recent_date = (date.today() - timedelta(days=3)).isoformat()
        res_recent = sb.table("watchlist_daily")\
            .select("ticker, date")\
            .gte("date", recent_date)\
            .eq("hard_filter_pass", True)\
            .order("date", desc=True)\
            .order("catalyst_score", desc=True)\
            .limit(500)\
            .execute()

        if res_recent.data and len(res_recent.data) > 0:
            # Get tickers from the most recent date available
            latest_date = res_recent.data[0]["date"]
            tickers = list(set(
                r["ticker"] for r in res_recent.data 
                if r["date"] == latest_date
            ))
            log_info(MODULE, f"Watchlist from DB (fallback date={latest_date}): {len(tickers)} tickers")
            return tickers

    except Exception as e:
        log_warning(MODULE, f"Error loading watchlist from DB: {e}")

    # Final fallback: default core tickers
    default_tickers = [
        "AAL", "WULF", "ET",
        "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "GOOGL", "AMZN",
        "META", "INTC", "SQ", "PYPL", "COIN", "MARA", "RIOT",
        "TQQQ", "SOXL", "SOFI", "LCID", "PLTR", "PLUG", "SNAP",
    ]
    log_info(MODULE, f"Using default watchlist: {len(default_tickers)} tickers")
    return default_tickers


async def process_ticker(ticker: str, config: dict, f_data: dict | None = None, is_pro_member: bool = False) -> dict | None:
    from app.data.yfinance_provider import YFinanceProvider
    from app.analysis.stocks_indicators import calculate_stock_indicators

    try:
        provider = YFinanceProvider()
        
        # 1. DOWNLOAD MULTI-TIMEFRAME DATA (Optimized periods)
        df_15m = await provider.get_ohlcv(ticker, interval="15m", period="60d")
        df_4h  = await provider.get_ohlcv(ticker, interval="4h",  period="120d")
        df_1d  = await provider.get_ohlcv(ticker, interval="1d",  period="365d")

        # ROBUST NULL CHECK — skip ticker entirely if any timeframe fails
        if df_15m is None or df_15m.empty or len(df_15m) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 15m data")
            return None
        if df_1d is None or df_1d.empty or len(df_1d) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 1d data")
            return None
        if df_4h is None or df_4h.empty or len(df_4h) < 2:
            log_warning(MODULE, f"Skipping {ticker}: no 4h/1h data")
            return None

        # 2. CALCULATE INDICATORS
        ind_15m = calculate_stock_indicators(df_15m, "15m", ticker)
        ind_4h  = calculate_stock_indicators(df_4h,  "4h",  ticker)
        ind_1d  = calculate_stock_indicators(df_1d,  "1d",  ticker)

        if not ind_15m or not ind_4h or not ind_1d:
            log_warning(MODULE, f"Skipping {ticker}: indicator calculation failed")
            return None

        # Overwrite with enriched dataframes (containing EMAs, PSAR, etc.)
        df_15m = ind_15m["_df"]
        df_1d  = ind_1d["_df"]

        # 2b. ADD FIBONACCI BANDS FOR MOVEMENT DETECTION
        df_15m = fibonacci_bollinger(df_15m, length=200, mult=3.0)
        df_1d  = fibonacci_bollinger(df_1d,  length=200, mult=3.0)

        # 3. VOLUME FILTER
        min_vol = float(config.get("min_daily_volume", 500000))
        volume_24h = ind_1d.get("volume", 0)
        if volume_24h < min_vol:
            log_debug(MODULE, f"Skipping {ticker}: volume {volume_24h} < {min_vol}")
            return None

        # 4. TECHNICAL RULES
        ps_signal_4h = ind_4h.get("last_pinescript_signal")
        ps_age_4h = ind_4h.get("signal_age", 999)
        t01_confirmed = (ps_signal_4h == "Buy" and ps_age_4h <= 3)

        ema_50_1d = ind_1d.get("ema_50") or 0.0
        ema_200_1d = ind_1d.get("ema_200") or 999999.0
        t02_confirmed = (ema_50_1d > ema_200_1d)

        candle_4h_green = 1 if df_4h.iloc[-1]["close"] > df_4h.iloc[-1]["open"] else 0

        # SCORING
        base_score = 0.0
        if t01_confirmed:   base_score += 40.0
        if t02_confirmed:   base_score += 30.0
        if candle_4h_green: base_score += 20.0
        
        rsi_val = ind_15m.get("rsi_14")
        if rsi_val and 40 <= rsi_val <= 70:
            base_score += 10.0

        # 5. CAPA 3: UNIFIED ANALYSIS (Math + IA Enrichment)
        from app.analysis.capa3_fundamentals import analyze_fundamentals
        
        # Recuperar metadatos para el análisis
        a_rating = float(f_data.get("analyst_rating", 0)) if f_data else 0.0
        
        # Obtener Market Cap antes del rationale
        import yfinance as yf
        t_obj = yf.Ticker(ticker)
        mcap = 0.0
        try:
            # fast_info puede ser None o no tener el atributo get en algunas versiones de yf
            info = getattr(t_obj, "fast_info", {})
            mcap = float(info.get("marketCap") or 0) if info else 0.0
        except:
            mcap = 0.0

        fundamental_res = await analyze_fundamentals(
            ticker=ticker,
            current_price=float(ind_15m.get("close", 0)),
            ib_data=f_data or {},
            sector=f_data.get("sector", "Other") if f_data else "Other",
            analyst_rating=a_rating,
            technical_score=base_score,
            supabase=get_supabase()
        )
        
        # Seguridad ante retorno nulo
        if not fundamental_res:
            fundamental_res = {"pro_score": 1.0, "explanation": "Error en análisis fundamental", "components": {}}

        pro_score = fundamental_res.get("pro_score") or 0.0
        
        # ── 5.5 CONSTRUIR MASTER RATIONALE (Sustento Multi-Capa) ──
        # Componentes de valoración para formateo seguro
        comp = fundamental_res.get("components", {})
        piot_score = comp.get("piotroski", {}).get("score", 0)
        altman_z = float(comp.get("altman", {}).get("z_score", 0) or 0)
        graham_val = float(comp.get("graham", {}).get("value", 0) or 0)
        dcf_val = float(comp.get("dcf", {}).get("value", 0) or 0)
        intrinsic = float(fundamental_res.get("intrinsic_value", 0) or 0)
        mos = float(fundamental_res.get("margin_of_safety", 0) or 0)
        status = fundamental_res.get("valuation_status", "N/A").upper()
        icon = "🟢" if status == "UNDERVALUED" else "🔴" if status == "OVERVALUED" else "⚪"

        # Capa 1: Universo
        c1_txt = f"CAPA 1 (Universo): Pool {f_data.get('pool_type', 'STANDARD')} | MCap ${mcap/1e6:.1f}M."
        
        # Capa 2: Técnico
        c2_txt = (
            f"CAPA 2 (Técnico): T01(Pine)={'OK' if t01_confirmed else 'FAIL'}, "
            f"T02(EMA)={'OK' if t02_confirmed else 'FAIL'}, "
            f"T03(Vela)={'OK' if candle_4h_green else 'FAIL'}, "
            f"T04(RSI)={'OK' if (rsi_val and 40<=rsi_val<=70) else 'FAIL'}."
        )
        
        # Capa 3: Engine
        c3_txt = (
            f"CAPA 3 (Engine): {icon} {status} | Intrínseco: ${intrinsic:.2f} (Margen: {mos:+.1f}%) | "
            f"Piotroski={piot_score}/9, Altman={altman_z:.2f}, Graham=${graham_val:.2f}, DCF=${dcf_val:.2f}."
        )
        
        # Fórmula y Resultado
        formula_txt = fundamental_res.get("explanation", "Cálculo matemático puro.")
        master_rationale = f"{c1_txt}\n{c2_txt}\n{c3_txt}\n{formula_txt}"
        
        # Inyectar resultados en ind_15m para persistencia y UI
        ind_15m["pro_score"] = pro_score
        ind_15m["fundamental_score"] = pro_score * 10
        ind_15m["math_score"] = fundamental_res.get("math_score")
        ind_15m["ai_rationale"] = master_rationale
        ind_15m["qwen_summary"] = fundamental_res.get("qwen_summary", "")
        ind_15m["gemini_summary"] = fundamental_res.get("gemini_summary", "")
        ind_15m["intrinsic_value"] = intrinsic
        ind_15m["margin_of_safety"] = mos
        ind_15m["undervaluation"] = mos  # Campo que usa el UI para el % arriba a la derecha
        ind_15m["piotroski_score"] = piot_score
        ind_15m["intrinsic_price"] = intrinsic
        ind_15m["is_undervalued"] = (status == "UNDERVALUED")
        ind_15m["pool_type"] = f_data.get("pool_type", "HOT") if f_data else "HOT"

        # 6. CAPTURE LIVE PRICE
        current_price = float(df_15m["close"].iloc[-1])
        
        # Inject metadata for persistence
        ind_15m["change_pct"] = ind_1d.get("change_pct", 0.0)
        ind_15m["market_cap"] = mcap
        ind_15m["rvol"] = ind_1d.get("rvol", 1.0)
        ind_15m["volume"] = volume_24h
        
        # 7. SMART LIMITS & MOVEMENT TYPE
        movement_15m = classify_movement(df_15m)
        limit_long_15m  = calculate_smart_limit_price(df_15m, 'long',  movement_15m['movement_type'])
        limit_short_15m = calculate_smart_limit_price(df_15m, 'short', movement_15m['movement_type'])

        movement_1d = classify_movement(df_1d)
        limit_long_1d  = calculate_smart_limit_price(df_1d, 'long',  movement_1d['movement_type'])
        limit_short_1d = calculate_smart_limit_price(df_1d, 'short', movement_1d['movement_type'])

        bb_lower_1d = float(df_1d.iloc[-1].get("bb_lower", current_price * 0.95))
        ind_15m["bb_lower"] = bb_lower_1d
        
        # 8. SAVE TO DB
        from app.analysis.stocks_indicators import upsert_technical_score
        is_acceptable = t01_confirmed and t02_confirmed and candle_4h_green
        
        current_time_str = datetime.now().strftime("%H:%M")
        ind_15m["last_scan_time"] = current_time_str

        # Inyectar ambos en ind_15m para señales_json
        ind_15m["movement_15m"] = movement_15m["movement_type"]
        ind_15m["fib_zone_15m"] = movement_15m["fib_zone_current"]
        ind_15m["smart_limit_long_15m"] = limit_long_15m.get("limit_price")
        ind_15m["smart_limit_short_15m"] = limit_short_15m.get("limit_price")

        ind_15m["movement_1d"] = movement_1d["movement_type"]
        ind_15m["fib_zone_1d"] = movement_1d["fib_zone_current"]
        ind_15m["smart_limit_long_1d"] = limit_long_1d.get("limit_price")
        ind_15m["smart_limit_short_1d"] = limit_short_1d.get("limit_price")

        ind_15m["t01_confirmed"] = t01_confirmed
        ind_15m["t02_confirmed"] = t02_confirmed
        ind_15m["t03_confirmed"] = bool(candle_4h_green)
        ind_15m["t04_confirmed"] = (rsi_val is not None and 40 <= rsi_val <= 70)
        
        upsert_technical_score(ticker, ind_15m, base_score, is_acceptable, pro_score)

        # 9. RULE ENGINE
        from app.stocks.stocks_rule_engine import StocksRuleEngine
        from app.stocks.stocks_order_executor import execute_market_order, place_limit_order
        
        re = StocksRuleEngine.get_instance()
        rule_ctx = re.build_context(
            ticker=ticker,
            snap=ind_15m,
            ia_score=pro_score,
            tech_score=base_score,
            fundamental_score=ind_15m.get("fundamental_score", 0),
            rvol=ind_15m.get("rvol", 1.0),
            pine_signal="Buy" if t01_confirmed else "",
            movement_type=movement_15m["movement_type"],
            fib_zone=movement_15m["fib_zone_current"],
            bb_lower=bb_lower_1d,
            intrinsic_price=ind_15m["intrinsic_price"],
            pool_type=ind_15m.get("pool_type", "")
        )
        rule_ctx["revenue_growth_yoy"] = ind_15m.get("revenue_growth_yoy", 0)
        
        buying_results = re.evaluate_all(rule_ctx, direction="buy")
        for res in buying_results:
            if res["triggered"]:
                log_info(MODULE, f"🚀 RULE TRIGGERED: {res['rule_code']} for {ticker}")
                if res["order_type"] == "market":
                    execute_market_order(ticker, "buy", res["rule_code"], rule_ctx, re.rules[res["rule_code"]])
                    break
                elif res["order_type"] == "limit":
                    place_limit_order(ticker, "buy", res["rule_code"], rule_ctx, re.rules[res["rule_code"]])
                    break

        if ticker in (await get_open_positions_tickers()):
            selling_results = re.evaluate_all(rule_ctx, direction="sell")
            for res in selling_results:
                if res["triggered"]:
                    log_info(MODULE, f"🔻 SELL RULE TRIGGERED: {res['rule_code']} for {ticker}")
                    if res["order_type"] == "market":
                        execute_market_order(ticker, "sell", res["rule_code"], rule_ctx, re.rules[res["rule_code"]])
                        break
                    elif res["order_type"] == "limit":
                        place_limit_order(ticker, "sell", res["rule_code"], rule_ctx, re.rules[res["rule_code"]])
                        break

        if is_acceptable:
            log_info(MODULE, f"🌟 {ticker} BULLISH Score={base_score} | Pro_Score={pro_score}")
        else:
            log_info(MODULE, f"📊 {ticker} Processed. Score={base_score} | Mov={movement_15m['movement_type']}")

        return {
            "ticker": ticker,
            "technical_score": base_score,
            "pro_score": pro_score,
            "rvol": ind_15m.get("rvol", 1.0),
            "price": float(current_price),
            "acceptable": is_acceptable,
            "movement_15m": movement_15m["movement_type"],
            "last_scan_time": ind_15m["last_scan_time"],
            "pool_type": ind_15m.get("pool_type", "HOT")
        }

    except Exception as e:
        log_warning(MODULE, f"Skipping {ticker}: {e}")
        return None


async def run_stocks_cycle(force=False):
    """
    Main stocks cycle — runs every 5 minutes during market hours.
    """
    cycle_start = time.time()
    log_info(MODULE, "═══ STOCKS CYCLE START ═══" if not force else "═══ STOCKS CYCLE START (FORCED) ═══")

    try:
        config = get_stocks_config()

        # Check kill switch
        if config.get("kill_switch_active", "false") == "true":
            log_warning(MODULE, "Kill switch ACTIVE — skipping cycle")
            return

        # Check market hours
        is_open, status_text = is_market_open()
        if not force and not is_open:
            log_info(MODULE, f"Cycle skipped: Market is {status_text}")
            return

        # ── CAPA 0: Dynamic Scanner — Refresh universe every cycle ──
        scanner_max_price = float(config.get("scanner_max_price", 20))
        scanner_min_price = float(config.get("scanner_min_price", 1))
        scanner_min_cap = int(config.get("min_market_cap_usd", 1_000_000_000))
        scanner_min_vol = int(config.get("min_daily_volume", 1_000_000))
        scanner_max_results = int(config.get("watchlist_core_count", 50))
        
        try:
            from app.stocks.universe_builder import UniverseBuilder
            builder = UniverseBuilder()
            candidates = await builder.build_daily_watchlist(
                max_price=scanner_max_price,
                min_price=scanner_min_price,
                min_market_cap=scanner_min_cap,
                min_volume=scanner_min_vol,
                max_results=scanner_max_results,
            )
            if candidates:
                log_info(MODULE, f"Scanner: {len(candidates)} candidatos "
                                f"(${scanner_min_price}-${scanner_max_price} | "
                                f"Vol>{scanner_min_vol/1e6:.0f}M | MCap>{scanner_min_cap/1e9:.0f}B)")
        except Exception as e:
            log_warning(MODULE, f"Scanner refresh skipped: {e}")

        # Get watchlist (populated by IB Scanner, limited to top 20)
        tickers = await get_watchlist(config)
        if not tickers:
            log_warning(MODULE, "Empty watchlist — nothing to process")
            return

        # Process tickers in parallel
        # OPTIMIZACIÓN: Cargar datos fundamentales de todos los tickers de una vez para evitar 30 queries individuales
        log_info(MODULE, f"🚀 Analyzing {len(tickers)} tickers in parallel...")
        
        sb = get_supabase()
        today = datetime.now().date().isoformat()
        f_data_res = sb.table("watchlist_daily")\
            .select("ticker, fundamental_score, pool_type, analyst_rating")\
            .in_("ticker", tickers)\
            .eq("date", today)\
            .execute()
        
        f_cache = {r["ticker"]: r for r in (f_data_res.data or [])}
        watchlist_pro = [t for t, d in f_cache.items() if d.get("pool_type") and ("GIANT" in d["pool_type"] or "LEADER" in d["pool_type"])]

        tasks = [process_ticker(ticker, config, f_cache.get(ticker), is_pro_member=(ticker in watchlist_pro)) for ticker in tickers]
        
        # Run all tasks concurrently
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        processed_count = 0
        for i, res in enumerate(results_raw):
            if isinstance(res, Exception):
                log_error(MODULE, f"Error analyzing {tickers[i]}: {res}")
            elif res:
                results.append(res)
                processed_count += 1

        log_info(MODULE, f"✅ Cycle finished: {processed_count} tickers analyzed/passed filters.")

        # Summary
        duration_s = round(time.time() - cycle_start, 1)
        threshold = float(config.get("technical_score_threshold", 60))
        high_score_count = sum(1 for r in results if r["technical_score"] >= threshold)
        spike_count = sum(1 for r in results if r["rvol"] >= 2.5)

        log_info(MODULE,
                 f"═══ STOCKS CYCLE END ═══ "
                 f"Processed: {len(results)}/{len(tickers)} | "
                 f"High Score (≥{int(threshold)}): {high_score_count} | "
                 f"Volume Spikes: {spike_count} | "
                 f"Duration: {duration_s}s")

        # ── Sprint 7: Execute pending opportunities & monitor positions ──
        try:
            from app.stocks.order_executor import OrderExecutor
            executor = OrderExecutor()
            exec_results = await executor.execute_pending_opportunities()
            if exec_results:
                log_info(MODULE, f"📊 Executed {len(exec_results)} trade(s)")
        except Exception as e:
            log_warning(MODULE, f"Execution step skipped: {e}")

        try:
            from app.stocks.position_monitor import PositionMonitor
            monitor = PositionMonitor()
            await monitor.check_all_positions()
        except Exception as e:
            log_warning(MODULE, f"Monitor step skipped: {e}")

        # Log cycle to system_logs
        sb = get_supabase()
        sb.table("system_logs").insert({
            "module": MODULE,
            "level": "INFO",
            "message": f"Stocks cycle completed: {len(results)} tickers processed",
            "context": str({
                "tickers_processed": len(results),
                "high_score_count": high_score_count,
                "spike_count": spike_count,
                "duration_s": duration_s,
            }),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

    except Exception as e:
        log_error(MODULE, f"Stocks cycle failed: {e}")


async def run_pro_cycle():
    """
    Inversión Pro cycle — runs ONCE at market close (16:05 ET).
    Computes 1D timeframe indicators and PRO scoring for all watchlist tickers.
    This data feeds the 'Inversión Pro' tab in the frontend.
    """
    cycle_start = time.time()
    log_info(MODULE, "═══ PRO SCORING CYCLE START (Market Close) ═══")

    try:
        config = get_stocks_config()

        if config.get("kill_switch_active", "false") == "true":
            log_warning(MODULE, "Kill switch ACTIVE — skipping pro cycle")
            return

        tickers = await get_watchlist(config)
        if not tickers:
            log_warning(MODULE, "Empty watchlist — nothing to process for pro cycle")
            return

        log_info(MODULE, f"📊 PRO cycle: Analyzing {len(tickers)} tickers (1D timeframe)...")
        tasks = [process_ticker(ticker, config, is_pro_member=True) for ticker in tickers]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, res in enumerate(results_raw):
            if isinstance(res, Exception):
                log_error(MODULE, f"PRO cycle error {tickers[i]}: {res}")
            elif res:
                results.append(res)

        duration_s = round(time.time() - cycle_start, 1)
        log_info(MODULE,
                 f"═══ PRO SCORING CYCLE END ═══ "
                 f"Processed: {len(results)}/{len(tickers)} | "
                 f"Duration: {duration_s}s")

        # Also trigger AI analysis for high-score tickers
        threshold = float(config.get("technical_score_threshold", 60))
        high_score_tickers = [r for r in results if r["technical_score"] >= threshold]
        if high_score_tickers:
            log_info(MODULE, f"🧠 {len(high_score_tickers)} tickers qualify for AI analysis")
            try:
                from app.stocks.decision_engine import DecisionEngine
                engine = DecisionEngine()
                sb = get_supabase()
                for r in high_score_tickers[:5]:  # Limit to top 5 to avoid API overuse
                    ticker = r["ticker"]
                    wl_entry = {"ticker": ticker, "catalyst_type": "PRO_SCAN", "catalyst_score": 7}
                    decision = await engine.execute_full_analysis(ticker, wl_entry)
                    if decision:
                        log_info(MODULE, f"🧠 {ticker}: AI Decision = {decision.get('decision', 'N/A')}")
            except Exception as e:
                log_warning(MODULE, f"AI analysis step skipped: {e}")

        # Log to system_logs
        sb = get_supabase()
        sb.table("system_logs").insert({
            "module": MODULE,
            "level": "INFO",
            "message": f"PRO cycle completed: {len(results)} tickers processed at market close",
            "context": str({"tickers_processed": len(results), "duration_s": duration_s}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

    except Exception as e:
        log_error(MODULE, f"PRO scoring cycle failed: {e}")


async def start_stocks_scheduler(force=False):
    """
    Start the stocks scheduler using APScheduler.
    
    Schedule:
      1. Hot by Volume: every 15 minutes during market hours (09:30-16:00 ET)
      2. Inversión Pro: once at market close (16:05 ET, Mon-Fri)
      3. Market Sweep: daily at 2:00 AM ET (Mon-Fri)
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()

    # 1. HOT BY VOLUME: every 2 minutes during market hours
    scheduler.add_job(
        run_stocks_cycle,
        trigger=IntervalTrigger(minutes=2),
        id="stocks_hot_cycle",
        name="Hot by Volume (15m intraday cycle)",
        kwargs={"force": force},
        max_instances=1,
        replace_existing=True,
    )

    # 2. INVERSIÓN PRO: daily at 16:05 ET (5 min after market close)
    scheduler.add_job(
        run_pro_cycle,
        trigger=CronTrigger(day_of_week='mon-fri', hour=16, minute=5, timezone='US/Eastern'),
        id="stocks_pro_cycle",
        name="Inversión Pro (market close daily analysis)",
        max_instances=1,
        replace_existing=True,
    )

    # 3. MEGA BARRIDO DIARIO: 16:01 ET (Justo post-cierre) Lunes a Viernes
    scheduler.add_job(
        run_market_sweep,
        trigger=CronTrigger(day_of_week='mon-fri', hour=16, minute=1, timezone='US/Eastern'),
        id="daily_market_sweep",
        name="Market Sweep (All US Tickers < $200 + 1M Vol)",
        max_instances=1,
        replace_existing=True,
    )

    # 4. REFRESH FUNDAMENTALS: Domingos 18:00 EST (Pre-apertura)
    from app.analysis.fundamental_scorer import FundamentalScorer
    async def weekly_fundamental_update():
        log_info("stocks_scheduler", "🚀 Iniciando actualización semanal de fundamentales...")
        # Lógica para re-escanear el universo actual con el FundamentalScorer
        # (Esto se puede invocar via UniverseBuilder)
        from app.stocks.universe_builder import UniverseBuilder
        builder = UniverseBuilder()
        await builder.build_daily_watchlist() # Esto disparará el Scorer por dentro
        log_info("stocks_scheduler", "✅ Fundamentales actualizados para la semana.")

    scheduler.add_job(
        weekly_fundamental_update,
        trigger=CronTrigger(day_of_week='sun', hour=18, minute=0, timezone='US/Eastern'),
        id="weekly_fundamental_refresh",
        name="Weekly Fundamental Refresh",
        replace_existing=True
    )

    scheduler.start()
    is_open, status_txt = is_market_open()
    log_info(MODULE, f"Stocks scheduler started (Market: {status_txt}). Tasks: Hot(15m) + Pro(16:05ET) + Sweep(16:01ET)")

    # Run first cycle immediately
    await run_stocks_cycle(force=force)

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log_info(MODULE, "Stocks scheduler stopped")


if __name__ == "__main__":
    import sys
    log_info("stocks_scheduler", "CRITICAL: SCRIPT STARTING MANUALLY/PM2")
    force_mode = "--force" in sys.argv
    asyncio.run(start_stocks_scheduler(force=force_mode))

