"""
eTrader v4.5 — Stocks API Endpoints
REST API for the Stocks module frontend pages.

Endpoints:
  GET /api/v1/stocks/status         — Connection status and config
  GET /api/v1/stocks/watchlist      — Today's watchlist with scores
  GET /api/v1/stocks/universe       — Universe Builder output
  GET /api/v1/stocks/opportunities  — Trade opportunities from Claude
  GET /api/v1/stocks/positions      — Active positions
  GET /api/v1/stocks/journal        — Trade journal history
  GET /api/v1/stocks/performance    — Performance metrics
  GET /api/v1/stocks/config         — Stocks configuration
  PUT /api/v1/stocks/config         — Update configuration
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timezone

from app.core.supabase_client import get_supabase

router = APIRouter()


@router.get("/status")
async def get_stocks_status(sb=Depends(get_supabase)):
    """Check Stocks module status and configuration."""
    try:
        # Load config
        config_res = sb.table("stocks_config").select("key, value").execute()
        config = {r["key"]: r["value"] for r in (config_res.data or [])}

        paper_mode = config.get("paper_mode_active", "true") == "true"
        kill_switch = config.get("kill_switch_active", "false") == "true"
        capital = float(config.get("total_capital_usd", 0))

        # Check if IB is configured
        import os
        has_ib = bool(os.getenv("IB_HOST") or os.getenv("IB_PORT"))

        # Check yfinance availability
        try:
            import yfinance
            has_yfinance = True
        except ImportError:
            has_yfinance = False

        return {
            "connected":      has_yfinance,
            "paper_mode":     paper_mode,
            "kill_switch":    kill_switch,
            "capital_usd":    capital,
            "has_ib":         has_ib,
            "has_yfinance":   has_yfinance,
            "data_source":    "yfinance" if has_yfinance else "none",
            "broker":         "IB Paper" if has_ib else "None",
            "module_version": "5.0",
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }


@router.get("/watchlist")
async def get_stocks_watchlist(sb=Depends(get_supabase)):
    """Get today's watchlist with scores."""
    try:
        today = date.today().isoformat()

        res = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .order("catalyst_score", desc=True)\
            .limit(50)\
            .execute()

        return {"watchlist": res.data or [], "date": today}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/universe")
async def get_stocks_universe(sb=Depends(get_supabase)):
    """Get Universe Builder output (watchlist + technical scores)."""
    try:
        today = date.today().isoformat()

        # Get watchlist
        watchlist = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .eq("hard_filter_pass", True)\
            .order("catalyst_score", desc=True)\
            .execute()

        # Get latest technical scores
        tech_scores = sb.table("technical_scores")\
            .select("ticker, technical_score, rvol, mtf_confirmed, ema_alignment, timestamp")\
            .order("timestamp", desc=True)\
            .limit(50)\
            .execute()

        # Merge
        tech_map = {}
        for ts in (tech_scores.data or []):
            ticker = ts["ticker"]
            if ticker not in tech_map:  # Keep latest only
                tech_map[ticker] = ts

        universe = []
        for w in (watchlist.data or []):
            ticker = w["ticker"]
            tech = tech_map.get(ticker, {})
            universe.append({
                "ticker":          ticker,
                "pool_type":       w.get("pool_type", "tactical"),
                "catalyst_score":  w.get("catalyst_score", 0),
                "catalyst_type":   w.get("catalyst_type", ""),
                "market_regime":   w.get("market_regime", "sideways"),
                "technical_score": tech.get("technical_score", 0),
                "rvol":            tech.get("rvol", 0),
                "mtf_confirmed":   tech.get("mtf_confirmed", False),
                "ema_alignment":   tech.get("ema_alignment", "unknown"),
            })

        return {"universe": universe, "date": today, "total": len(universe)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities")
async def get_stocks_opportunities(
    sb=Depends(get_supabase),
):
    """Get ALL watchlist companies with their technical analysis status."""
    try:
        today = date.today().isoformat()

        # 1. Get full watchlist (ALL 30 tickers)
        from datetime import timedelta
        d_val = (date.today() - timedelta(days=1)).isoformat()
        wl = sb.table("watchlist_daily")\
            .select("*")\
            .gte("date", d_val)\
            .execute()

        # 2. Get latest technical scores
        tech = sb.table("technical_scores")\
            .select("ticker, technical_score, mtf_confirmed, ema_alignment, rsi_14, signals_json, timestamp")\
            .order("timestamp", desc=True)\
            .limit(100)\
            .execute()

        tech_map = {}
        for t in (tech.data or []):
            if t["ticker"] not in tech_map:
                tech_map[t["ticker"]] = t

        # 3. Get existing trade_opportunities for status overlay
        opps = sb.table("trade_opportunities")\
            .select("ticker, meta_score, status, trade_type, entry_zone_high, stop_loss, target_1")\
            .order("created_at", desc=True)\
            .limit(50)\
            .execute()

        opp_map = {}
        for o in (opps.data or []):
            if o["ticker"] not in opp_map:
                opp_map[o["ticker"]] = o

        # 4. Get stored prices and volumes from signals_json
        price_map = {}
        volume_map = {}
        for w in (wl.data or []):
            ticker = w["ticker"]
            t = tech_map.get(ticker, {})
            sj = t.get("signals_json") or {} if t else {}
            if sj.get("price"):
                price_map[ticker] = float(sj["price"])
            if sj.get("volume"):
                volume_map[ticker] = float(sj["volume"])

        # 5. Build combined list and apply 1M volume filter
        result = []
        for w in (wl.data or []):
            ticker = w["ticker"]
            t = tech_map.get(ticker, {})
            o = opp_map.get(ticker, {})

            # Filter by 1M volume
            vol = volume_map.get(ticker, 0)
            if vol < 1000000:
                continue

            result.append({
                "ticker": ticker,
                "company_name": w.get("company_name") or w.get("name") or ticker,
                "sector": w.get("sector", "Technology"),
                "price": price_map.get(ticker, 0),
                "volume": vol,
                "catalyst_type": w.get("catalyst_type", "Scan"),

                "catalyst_score": w.get("catalyst_score", 5),
                "market_regime": w.get("market_regime", "sideways"),
                # Technical status
                "technical_score": t.get("technical_score", 0),
                "pro_score": t.get("signals_json", {}).get("pro_score", 0) if t.get("signals_json") else 0,
                "mtf_confirmed": t.get("mtf_confirmed", False),
                "ema_alignment": t.get("ema_alignment", "unknown"),
                "rsi": t.get("rsi_14"),
                "analyzed": True,
                # Opportunity status
                "meta_score": o.get("meta_score", 0),
                "trade_type": o.get("trade_type", ""),
                "status": o.get("status", "scanning"),
                "entry_price": o.get("entry_zone_high"),
                "stop_loss": o.get("stop_loss"),
                "target_1": o.get("target_1"),
            })

        # Sort: by volume desc (User request)
        result.sort(key=lambda x: x["volume"], reverse=True)


        return {"opportunities": result, "total": len(result), "date": today}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_stocks_positions(sb=Depends(get_supabase)):
    """Get active stock positions."""
    try:
        res = sb.table("trades_active")\
            .select("*")\
            .eq("status", "active")\
            .order("entry_time", desc=True)\
            .execute()

        return {"positions": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/journal")
async def get_stocks_journal(
    limit: int = 50,
    sb=Depends(get_supabase),
):
    """Get trade journal history."""
    try:
        res = sb.table("trades_journal")\
            .select("*")\
            .order("exit_date", desc=True)\
            .limit(limit)\
            .execute()

        return {"trades": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_stocks_performance(sb=Depends(get_supabase)):
    """Get performance metrics."""
    try:
        # Latest daily metrics
        metrics_res = sb.table("performance_metrics")\
            .select("*")\
            .order("date", desc=True)\
            .limit(1)\
            .execute()

        # Calculate from journal if no metrics yet
        if not metrics_res.data:
            journal = sb.table("trades_journal").select("result, pnl_pct, pnl_usd").execute()
            trades = journal.data or []
            total = len(trades)
            wins = sum(1 for t in trades if t.get("result") == "win")

            return {
                "win_rate":     round(wins / total * 100, 1) if total > 0 else 0,
                "total_trades": total,
                "pnl_total":    sum(float(t.get("pnl_usd", 0) or 0) for t in trades),
                "sharpe":       0,
                "source":       "calculated",
            }

        m = metrics_res.data[0]
        return {
            "win_rate":      m.get("win_rate_overall", 0),
            "win_rate_swing": m.get("win_rate_swing_a", 0),
            "win_rate_scalp": m.get("win_rate_scalping_c", 0),
            "avg_rr":        m.get("avg_rr_achieved", 0),
            "avg_slippage":  m.get("avg_slippage_actual", 0),
            "sharpe":        m.get("sharpe_rolling_20", 0),
            "regime":        m.get("regime", ""),
            "trades_count":  m.get("trades_count", 0),
            "source":        "metrics_table",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_stocks_config_api(sb=Depends(get_supabase)):
    """Get all stocks configuration."""
    try:
        res = sb.table("stocks_config").select("*").order("key").execute()
        return {"config": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConfigUpdate(BaseModel):
    key: str
    value: str


@router.put("/config")
async def update_stocks_config(
    update: ConfigUpdate,
    sb=Depends(get_supabase),
):
    """Update a stocks configuration value."""
    try:
        sb.table("stocks_config").upsert({
            "key":         update.key,
            "value":       update.value,
            "updated_at":  datetime.now(timezone.utc).isoformat(),
        }, on_conflict="key").execute()

        return {"status": "ok", "key": update.key, "value": update.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime")
async def get_market_regime():
    """Get current S&P 500 market regime (Bull/Bear/Sideways)."""
    try:
        from app.data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        regime = await provider.get_spy_regime()
        return regime
    except Exception as e:
        return {"regime": "sideways", "vix": 0, "error": str(e)}


# ── Sprint 7: Execution Endpoints ─────────────────────────

@router.post("/execute")
async def execute_pending_opportunities():
    """Execute all pending trade opportunities (Paper or Live)."""
    try:
        from app.stocks.order_executor import OrderExecutor
        executor = OrderExecutor()
        results = await executor.execute_pending_opportunities()
        return {"executed": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitor")
async def run_position_monitor():
    """Run position monitor cycle (check SL/TP/trailing)."""
    try:
        from app.stocks.position_monitor import PositionMonitor
        monitor = PositionMonitor()
        await monitor.check_all_positions()
        return {"status": "ok", "message": "Position monitor cycle completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close-all")
async def close_all_positions():
    """Emergency: close all active positions at market price."""
    try:
        from app.stocks.position_monitor import PositionMonitor
        monitor = PositionMonitor()
        results = await monitor.force_close_all(reason="api_emergency_close")
        return {"closed": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline")
async def run_full_pipeline():
    """
    Run the complete AI → Execution pipeline:
    1. Universe Builder (Capa 0)
    2. Technical Analysis (Sprint 5)
    3. Fundamental + Context (Capas 3-4)
    4. Decision Engine (Capa 5)
    5. Order Execution (Capa 6)
    6. Position Monitoring (Capa 7)
    """
    try:
        from app.stocks.universe_builder import UniverseBuilder
        from app.stocks.decision_engine import DecisionEngine
        from app.stocks.order_executor import OrderExecutor
        from app.stocks.position_monitor import PositionMonitor
        from app.workers.stocks_scheduler import process_ticker, get_stocks_config

        log = []

        # Step 1: Build universe
        config = get_stocks_config()
        scanner_max_price = float(config.get("scanner_max_price", 200))
        builder = UniverseBuilder()
        candidates = await builder.build_daily_watchlist(max_price=scanner_max_price)
        log.append(f"Universe: {len(candidates)} candidates (max_price=${scanner_max_price})")

        # Step 2-5: For each candidate, run full analysis
        config = get_stocks_config()
        engine = DecisionEngine()
        decisions = []
        for c in candidates[:5]:  # Max 5 per pipeline run
            ticker = c["ticker"]
            # Technical sync
            await process_ticker(ticker, config)
            # AI Decision
            decision = await engine.execute_full_analysis(ticker, c)
            if decision:
                decisions.append({"ticker": ticker, "decision": decision.get("decision"), "meta_score": decision.get("meta_score")})
        log.append(f"Decisions: {len(decisions)} analyzed")

        # Step 6: Execute
        executor = OrderExecutor()
        exec_results = await executor.execute_pending_opportunities()
        log.append(f"Executed: {len(exec_results)} trades")

        # Step 7: Monitor existing
        monitor = PositionMonitor()
        await monitor.check_all_positions()
        log.append("Monitoring completed")

        return {"status": "ok", "pipeline": log, "decisions": decisions, "executions": exec_results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
