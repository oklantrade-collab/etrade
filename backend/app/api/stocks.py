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
import asyncio
import os
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timezone, timedelta

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.stocks.universe_builder import UniverseBuilder
from app.analysis.fundamental_scorer import FundamentalScorer

router = APIRouter()


def calculate_sm_score(rvol, s_score, sv_score, catalyst_raw, tecnico_raw):
    """
    Calcula el Score de Momentum de 1 a 10 según propuesta técnica.
    Pesos: RVOL(30%), Sentiment(20%), SocVol(10%), Catalyst(25%), Technical(15%)
    """
    # Normalización según especificación
    v1 = min(max(0, (rvol - 1) / 4), 1.0)
    v2 = (s_score + 3) / 6
    v3 = sv_score / 10
    v4 = catalyst_raw / 10
    
    # tecnico_raw viene de 0 a 100 en technical_score, normalizar a 0.0 - 1.0
    v5 = tecnico_raw / 100 

    score_raw = (v1 * 0.30) + (v2 * 0.20) + (v3 * 0.10) + (v4 * 0.25) + (v5 * 0.15)
    score_final = round(score_raw * 10, 1)
    
    # Regla de oro: si no hay catalizador (V4=0), el momentum es bajo
    if catalyst_raw == 0:
        return 1.0
        
    return max(1.0, min(score_final, 10.0))


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
    """Get Universe Builder output (latest scan results)."""
    try:
        today = date.today().isoformat()

        # 1. Intentar obtener el watchlist de HOY
        watchlist = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .execute()
            
        # 2. Si hoy está vacío (zona horaria?), traer los últimos 50 registros del sistema
        if not watchlist.data:
            watchlist = sb.table("watchlist_daily")\
                .select("*")\
                .order("date", desc=True)\
                .limit(50)\
                .execute()

        if not watchlist.data:
            return {"universe": [], "date": today, "total": 0}

        # Última fecha detectada
        actual_date = watchlist.data[0].get("date", today)

        # Get latest technical scores
        tech_scores = sb.table("technical_scores")\
            .select("ticker, technical_score, rvol, mtf_confirmed, ema_alignment, timestamp")\
            .order("timestamp", desc=True)\
            .limit(100)\
            .execute()

        # Merge
        tech_map = {}
        for ts in (tech_scores.data or []):
            ticker = ts["ticker"]
            if ticker not in tech_map:
                tech_map[ticker] = ts

        universe = []
        for w in (watchlist.data or []):
            ticker = w["ticker"]
            tech = tech_map.get(ticker, {})
            universe.append({
                "ticker":          ticker,
                "pool_type":       w.get("pool_type", "tactical"),
                "catalyst_score":  w.get("catalyst_score", 0),
                "technical_score": tech.get("technical_score", 0),
                "rvol":            tech.get("rvol", 0),
                "mtf_confirmed":   tech.get("mtf_confirmed", False),
                "ema_alignment":   tech.get("ema_alignment", "unknown"),
                "fundamental_score": w.get("fundamental_score", 0),
                "quality_flag":      w.get("quality_flag", "PASS"),
                "revenue_growth":    w.get("revenue_growth_yoy", 0),
                "gross_margin":      w.get("gross_margin", 0),
                "rs_score":          w.get("rs_score_6m", 0),
                "inst_ownership":    w.get("inst_ownership_pct", 0),
                "market_cap":        w.get("market_cap_mln", 0),
                "price":             w.get("price", 0)
            })

        return {"universe": universe, "date": actual_date, "total": len(universe)}
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_universe: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities")
async def get_stocks_opportunities(
    sb=Depends(get_supabase),
):
    """Get ALL watchlist companies with their technical analysis status."""
    try:
        today = date.today().isoformat()

        # 1. Get full watchlist (Cleaned automatically by UniverseBuilder)
        wl = sb.table("watchlist_daily")\
            .select("*")\
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

        # 3.5 Get active orders
        orders_res = sb.table("stocks_orders")\
            .select("*")\
            .in_("status", ["pending", "filled"])\
            .order("created_at", desc=True)\
            .execute()
        
        orders_map = {}
        for order in (orders_res.data or []):
            tick = order["ticker"]
            # Solo incluimos órdenes pendientes, o órdenes filled SI la posición sigue abierta
            if order["status"] == "pending" or tick in active_pos_tickers:
                if tick not in orders_map:
                    orders_map[tick] = []
                orders_map[tick].append(order)

        # 3.6 Get active positions to ensure they appear in Opportunities
        pos_res = sb.table("stocks_positions")\
            .select("ticker")\
            .eq("status", "open")\
            .execute()
        active_pos_tickers = [p["ticker"] for p in (pos_res.data or [])]

        # 3.7 Get Extended Fundamental Metrics from fundamental_cache
        funda_res = sb.table("fundamental_cache")\
            .select("ticker, piotroski_score, piotroski_detail, graham_number, graham_margin, dcf_intrinsic, dcf_upside_pct, altman_z_score, altman_zone, math_score, ia_score, data_source, valuation_status, composite_intrinsic")\
            .execute()
        funda_map = {f["ticker"]: f for f in (funda_res.data or [])}

        # 4. Get stored prices and volumes from signals_json/watchlist
        price_map = {}
        volume_map = {}
        for w in (wl.data or []):
            ticker = w["ticker"]
            t = tech_map.get(ticker, {})
            sj = t.get("signals_json") or {} if t else {}
            # Fallback robusto entre Universe (w) y Tech (sj)
            price_map[ticker] = float(sj.get("price") or w.get("price") or 0)
            volume_map[ticker] = float(sj.get("volume") or w.get("volume") or 0)

        # 5. Build combined list
        result = []
        processed_tickers = set()

        for w in (wl.data or []):
            ticker = w["ticker"]
            processed_tickers.add(ticker)
            t = tech_map.get(ticker, {})
            o = opp_map.get(ticker, {})
            f = funda_map.get(ticker, {})

            vol = volume_map.get(ticker, 0)
            result.append({
                "ticker": ticker,
                "company_name": w.get("company_name") or w.get("name") or ticker,
                "sector": w.get("sector", "Technology"),
                "price": price_map.get(ticker, 0),
                "volume": vol,
                "rvol": t.get("signals_json", {}).get("rvol", 1.0) if t.get("signals_json") else 1.0,
                "market_cap": t.get("signals_json", {}).get("market_cap", 0) if t.get("signals_json") else 0,
                "catalyst_type": w.get("catalyst_type", "Scan"),
                "catalyst_score": w.get("catalyst_score", 5),
                "market_regime": w.get("market_regime", "sideways"),
                "technical_score": t.get("technical_score", 0),
                "pro_score": t.get("signals_json", {}).get("pro_score", 0) if t.get("signals_json") else 0,
                "change_pct": t.get("signals_json", {}).get("change_pct", 0) if t.get("signals_json") else 0,
                "mtf_confirmed": t.get("mtf_confirmed", False),
                "ema_alignment": t.get("ema_alignment", "unknown"),
                "rsi": t.get("rsi_14"),
                "analyzed": True,
                # Opportunity status
                "meta_score": o.get("meta_score", 0),
                "trade_type": o.get("trade_type", ""),
                "status": "position" if ticker in active_pos_tickers else o.get("status", "scanning"),
                "entry_price": o.get("entry_zone_high"),
                "stop_loss": o.get("stop_loss"),
                "target_1": o.get("target_1"),
                "movement_15m": t.get("signals_json", {}).get("movement_15m"),
                "fib_zone_15m": t.get("signals_json", {}).get("fib_zone_15m"),
                "smart_limit_long_15m": t.get("signals_json", {}).get("smart_limit_long_15m") or t.get("signals_json", {}).get("limit_long_15m"),
                "smart_limit_short_15m": t.get("signals_json", {}).get("smart_limit_short_15m") or t.get("signals_json", {}).get("limit_short_15m"),
                "movement_1d": t.get("signals_json", {}).get("movement_1d"),
                "fib_zone_1d": t.get("signals_json", {}).get("fib_zone_1d"),
                "smart_limit_long_1d": t.get("signals_json", {}).get("smart_limit_long_1d") or t.get("signals_json", {}).get("limit_long_1d"),
                "smart_limit_short_1d": t.get("signals_json", {}).get("smart_limit_short_1d") or t.get("signals_json", {}).get("limit_short_1d"),
                "t01_confirmed": t.get("signals_json", {}).get("t01_confirmed", False),
                "t02_confirmed": t.get("signals_json", {}).get("t02_confirmed", False),
                "t03_confirmed": t.get("signals_json", {}).get("t03_confirmed", False),
                "t04_confirmed": t.get("signals_json", {}).get("t04_confirmed", False),
                "ai_rationale": t.get("signals_json", {}).get("ai_rationale") or f.get("gemini_summary") or "",
                "qwen_summary": t.get("signals_json", {}).get("qwen_summary") or f.get("qwen_summary") or "",
                "gemini_summary": t.get("signals_json", {}).get("gemini_summary") or f.get("gemini_summary") or "",
                "orders": orders_map.get(ticker, []),
                # ENRIQUECIMIENTO FUNDAMENTAL (Universe Promotion)
                "pool_type": w.get("pool_type") or ("CORE" if ticker in active_pos_tickers else ""),
                "fundamental_score": w.get("fundamental_score", 0),
                "quality_flag": w.get("quality_flag", "PASS"),
                "rev_growth": w.get("revenue_growth_yoy", 0),
                "gross_margin": w.get("gross_margin", 0),
                "rs_score": w.get("rs_score_6m", 0),
                "analyst_rating": w.get("analyst_rating", 0),
                "is_pro_member": (w.get("quality_flag") in ["PASS", "✓ PASS"] and bool(w.get("pool_type"))) or (ticker in active_pos_tickers),
                # Conversión de UTC a Lima (GMT-5) para el Dashboard
                "last_scan_time": (datetime.fromisoformat((t.get("timestamp") or "").split(".")[0][:19] + "+00:00") - timedelta(hours=5)).strftime("%H:%M") if t.get("timestamp") else "—:—",
                
                # VALUATION ENGINE FIELDS
                "piotroski_score": f.get("piotroski_score"),
                "piotroski_detail": f.get("piotroski_detail"),
                "graham_number": f.get("graham_number"),
                "graham_margin": f.get("graham_margin"),
                "dcf_intrinsic": f.get("dcf_intrinsic"),
                "dcf_upside_pct": f.get("dcf_upside_pct"),
                "altman_z_score": f.get("altman_z_score"),
                "altman_zone": f.get("altman_zone"),
                "math_score": f.get("math_score"),
                "ia_score": f.get("ia_score"),
                "data_source": f.get("data_source", "none"),
                "valuation_status": f.get("valuation_status", "unknown"),
                "composite_intrinsic": f.get("composite_intrinsic"),
                "margin_of_safety": f.get("margin_of_safety", 0),
                
                # MOMENTUM SCORE (SM)
                "sm_score": calculate_sm_score(
                    rvol=float(t.get("signals_json", {}).get("rvol", 1.0) if t.get("signals_json") else 1.0),
                    s_score=float(t.get("signals_json", {}).get("s_score", 0.0) if t.get("signals_json") else 0.0),
                    sv_score=float(t.get("signals_json", {}).get("sv_score", 5.0) if t.get("signals_json") else 5.0),
                    catalyst_raw=float(w.get("catalyst_score", 5)),
                    tecnico_raw=float(t.get("technical_score", 0))
                )
            })

        # Extra: Add positions that are NOT in watchlist
        for ticker in active_pos_tickers:
            if ticker in processed_tickers: continue
            t = tech_map.get(ticker, {})
            o = opp_map.get(ticker, {})
            sj = t.get("signals_json") or {}

            result.append({
                "ticker": ticker,
                "company_name": ticker,
                "sector": "Portfolio",
                "price": float(sj.get("price") or 0),
                "volume": float(sj.get("volume") or 0),
                "rvol": sj.get("rvol", 1.0),
                "market_cap": sj.get("market_cap", 0),
                "catalyst_type": "Position",
                "catalyst_score": 5,
                "market_regime": "active",
                "technical_score": t.get("technical_score", 0),
                "pro_score": sj.get("pro_score", 0),
                "change_pct": sj.get("change_pct", 0),
                "mtf_confirmed": t.get("mtf_confirmed", False),
                "ema_alignment": t.get("ema_alignment", "unknown"),
                "rsi": t.get("rsi_14"),
                "analyzed": True,
                "meta_score": o.get("meta_score", 0),
                "status": "position",
                "movement_15m": sj.get("movement_15m"),
                "fib_zone_15m": sj.get("fib_zone_15m"),
                "orders": orders_map.get(ticker, []),
                "is_pro_member": True, # Force to Pro tab
                "last_scan_time": (datetime.fromisoformat((t.get("timestamp") or "").split(".")[0][:19] + "+00:00") - timedelta(hours=5)).strftime("%H:%M") if t.get("timestamp") else "—:—",
                "sm_score": calculate_sm_score(
                    rvol=float(sj.get("rvol", 1.0)),
                    s_score=float(sj.get("s_score", 0.0)),
                    sv_score=float(sj.get("sv_score", 5.0)),
                    catalyst_raw=5, # Fallback for positions
                    tecnico_raw=float(t.get("technical_score", 0))
                )
            })

        # Sort: by volume desc (User request)
        result.sort(key=lambda x: x.get("volume") or 0, reverse=True)


        # 6. Get market status
        from app.core.market_hours import get_market_status_dict
        mstatus = get_market_status_dict()

        return {
            "opportunities": result, 
            "total": len(result), 
            "date": today,
            "market_status": mstatus
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_stocks_positions():
    """Get active stock positions from the industrialised table."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_positions")\
            .select("*")\
            .eq("status", "open")\
            .order("first_buy_at", desc=True)\
            .execute()
        
        positions = res.data or []
        if not positions:
            return []

        # Enriquecer con precios actuales desde technical_scores (más frecuentes que watchlist)
        tickers = [p["ticker"] for p in positions]
        tech_res = sb.table("technical_scores")\
            .select("ticker, signals_json")\
            .in_("ticker", tickers)\
            .execute()
        
        price_map = {}
        for tr in (tech_res.data or []):
            sj = tr.get("signals_json") or {}
            if "price" in sj:
                try:
                    price_map[tr["ticker"]] = float(sj["price"] or 0)
                except:
                    price_map[tr["ticker"]] = 0.0

        for pos in positions:
            ticker = pos["ticker"]
            # Prioridad: technical_scores -> stocks_positions.current_price -> avg_price
            cur_price = price_map.get(ticker) or float(pos.get("current_price") or pos.get("avg_price") or 0)
            avg_entry = float(pos.get("avg_price") or 0)
            shares = float(pos.get("shares") or 0)

            # Recalcular P&L
            unrealized_pnl = (cur_price - avg_entry) * shares
            unrealized_pnl_pct = ((cur_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else 0

            # ── ENRIQUECIMIENTO EXTRA PARA DETALLE ──
            # 1. Traer Company y Sector desde watchlist (Uso select("*") para evitar error si faltan columnas)
            wl_info = sb.table("watchlist_daily").select("*").eq("ticker", ticker).order("date", desc=True).limit(1).execute().data
            if wl_info:
                pos["company_name"] = wl_info[0].get("company_name") or wl_info[0].get("name") or ticker
                pos["sector"] = wl_info[0].get("sector") or "Finance"
            else:
                pos["company_name"] = ticker
                pos["sector"] = "Finance"

            # 2. Traer SL/TP desde Trade Opportunities
            opp_info = sb.table("trade_opportunities").select("stop_loss, target_1").eq("ticker", ticker).order("created_at", desc=True).limit(1).execute().data
            if opp_info:
                pos["sl_price"] = opp_info[0].get("stop_loss")
                pos["tp_price"] = opp_info[0].get("target_1")

            # 3. Side: En stocks solo operamos LONG (BUY). 
            # Mostramos 'buy' siempre que la posición esté abierta, 
            # independientemente de si la última orden fue un cierre parcial o total anterior.
            pos["order_type"] = "market"
            pos["side"] = "buy"  # Stocks are always Long in this model

            pos["current_price"] = cur_price
            pos["unrealized_pnl"] = round(unrealized_pnl, 2)
            pos["unrealized_pnl_pct"] = round(unrealized_pnl_pct, 2)
            pos["total_cost"] = round(avg_entry * shares, 2)

        return positions
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/positions/{position_id}")
async def delete_stocks_position(position_id: str):
    """Manual close/delete of a position."""
    sb = get_supabase()
    try:
        # Get position details first
        pos_res = sb.table("stocks_positions").select("*").eq("id", position_id).single().execute()
        if not pos_res.data:
            raise HTTPException(status_code=404, detail="Position not found")
        
        pos = pos_res.data
        ticker = pos["ticker"]

        # 1. Archive in journal (simplified)
        now = datetime.now(timezone.utc).isoformat()
        journal_entry = {
            "ticker": ticker,
            "shares": int(float(pos.get("shares", 0))),
            "entry_price": float(pos.get("avg_price", 0)),
            "exit_price": float(pos.get("current_price", 0)),
            "entry_date": pos.get("first_buy_at"),
            "exit_date": now,
            "pnl_usd": float(pos.get("unrealized_pnl", 0)),
            "pnl_pct": float(pos.get("unrealized_pnl_pct", 0)),
            "result": "win" if float(pos.get("unrealized_pnl", 0)) > 0 else "loss",
            "exit_reason": "manual_delete",
        }
        sb.table("trades_journal").insert(journal_entry).execute()

        # 2. Mark as closed
        sb.table("stocks_positions").update({
            "status": "closed",
            "updated_at": now
        }).eq("id", position_id).execute()

        return {"status": "ok", "message": f"Position {ticker} closed manually"}
    except Exception as e:
        log_error("stocks_api", f"Error deleting position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders")
async def get_stocks_orders():
    """Get latest stock orders."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_orders")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(100)\
            .execute()

        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/journal")
async def get_stocks_journal(limit: int = 50):
    """Get trade journal history from closed positions."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_positions")\
            .select("*")\
            .eq("status", "closed")\
            .order("updated_at", desc=True)\
            .limit(limit)\
            .execute()

        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_stocks_performance():
    """Get performance metrics for the stocks industrial engine."""
    sb = get_supabase()
    try:
        # Query closed trades
        res = sb.table("stocks_positions").select("*").eq("status", "closed").execute()
        trades = res.data or []
        
        total = len(trades)
        wins = sum(1 for t in trades if (t.get("unrealized_pnl", 0) or 0) > 0)
        pnl_total = sum(float(t.get("unrealized_pnl", 0) or 0) for t in trades)
        
        # Build a cumulative P&L series
        equity_curve = []
        cumulative_pnl = 0
        for t in sorted(trades, key=lambda x: x.get('updated_at', '')):
            cumulative_pnl += float(t.get('unrealized_pnl', 0) or 0)
            equity_curve.append({
                "date": t['updated_at'][:10],
                "equity": cumulative_pnl,
                "pnl": float(t.get('unrealized_pnl', 0) or 0)
            })

        return {
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "total_trades": total,
            "pnl_total": pnl_total,
            "equity_curve": equity_curve,
            "source": "calculated_v5"
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

@router.get("/rules")
async def get_stocks_rules():
    """Get all stocks strategy rules."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_rules").select("*").order("group_name").order("direction").order("order_type").execute()
        rules = res.data or []
        
        # Enriquecimiento dinámico para coherencia UI
        for r in rules:
            code = r.get("rule_code")
            # S01: IA + Técnico + Fundamental
            if code == "S01":
                if "fundamental_score_min" not in r: r["fundamental_score_min"] = 70.0
                r["name"] = "PRO_BUY_MKT — IA + Técnico + Fundamental"
            
            # S02: Compra a Descuento por Valor Intrínseco
            elif code == "S02":
                if "fundamental_score_min" not in r: r["fundamental_score_min"] = 65.0
                r["name"] = "PRO_BUY_LMT — Descuento por Valor Intrínseco"
                r["notes"] = "MODELO MATH S02: Compra LIMIT en min(Bollinger Lower 1D, Precio Intrínseco * 0.95). Activación si precio < (BB Lower * 1.02). Expira en 5 días."
            
            # S09: Compra a Descuento Profundo por Valor Intrínseco
            elif code == "S09":
                if "fundamental_score_min" not in r: r["fundamental_score_min"] = 70.0
                r["name"] = "PRO_BUY_VALUE — Descuento Profundo (10%)"
                r["notes"] = "S09: Precio <= Intrinsic * 0.90. Se activa en valor profundo para GIANT/LEADER."
        
        return rules
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/rules/{rule_code}")
async def update_stocks_rule(rule_code: str, rule_data: dict):
    """Update a specific stocks strategy rule."""
    sb = get_supabase()
    try:
        # Filtro de campos seguros (para evitar errores si la DB no tiene la columna)
        safe_fields = [
            "name", "enabled", "priority", "ia_min", "tech_score_min", 
            "movements_allowed", "pine_signal", "pine_required", 
            "fib_trigger", "rvol_min", "limit_trigger_pct", "close_all",
            "dca_enabled", "dca_max_buys", "dca_min_drop_pct", "notes"
        ]
        
        filtered_data = {k: v for k, v in rule_data.items() if k in safe_fields}
        filtered_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        res = sb.table("stocks_rules").update(filtered_data).eq("rule_code", rule_code).execute()
        return {"status": "success", "data": res.data[0] if res.data else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backtest")
async def run_stocks_backtest(params: dict):
    """Run a real-data backtest for a ticker."""
    try:
        from app.stocks.stocks_backtester import StocksBacktester
        tester = StocksBacktester()
        
        ticker = params.get("ticker", "NVDA")
        rule_code = params.get("rule_code", "S01")
        period = params.get("period", "1y")
        
        results = tester.run_backtest(ticker, rule_code, period)
        return results
    except Exception as e:
        import traceback
        err_msg = str(e)
        stack = traceback.format_exc()
        print(f"BACKTEST ERROR: {err_msg}\n{stack}")
        return {"error": f"Backend Error: {err_msg}", "details": stack}

@router.post("/refresh-fundamentals")
async def manual_fundamental_refresh():
    """Force an immediate refresh of all fundamental data AND trigger technical analysis for candidates."""
    try:
        from app.workers.stocks_scheduler import process_ticker, get_stocks_config
        
        builder = UniverseBuilder()
        # 1. Barrido Fundamental (Capa 0-4)
        summary = await builder.build_daily_watchlist()
        
        # 2. Barrido Técnico Inmediato para los candidatos encontrados
        if summary.get("TOTAL", 0) > 0:
            config = get_stocks_config()
            # Obtenemos los tickers del ultimo escaneo (que estan en el builder o en la DB)
            tickers = getattr(builder, 'last_scan_tickers', [])
            if not tickers:
                # Si por algun motivo no estan en el objeto, los buscamos en la DB del dia
                today = date.today().isoformat()
                from app.core.supabase_client import get_supabase
                sb = get_supabase()
                res = sb.table("watchlist_daily").select("ticker").eq("date", today).execute()
                tickers = [r["ticker"] for r in res.data]

            # Procesar tecnicamente los candidatos en paralelo (batches de 10 para no saturar CPU)
            batch_size = 10
            for i in range(0, len(tickers[:50]), batch_size):
                batch = tickers[i:i+batch_size]
                tasks = [process_ticker(t, config) for t in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                    
        return {"status": "success", "summary": summary}
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/universe/settings")
async def get_universe_settings():
    """Get the current universe building settings (Hybrid with absolute path)."""
    settings = None
    
    # 1. Intentar Supabase
    try:
        sb = get_supabase()
        res = sb.table("universe_settings").select("*").eq("id", 1).maybe_single().execute()
        if res.data:
            settings = res.data
    except:
        pass

    # 2. Fallback a Local JSON ABSOLUTO
    if not settings:
        try:
            import json
            settings_path = "c:/Fuentes/eTrade/backend/data/universe_settings.json"
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
        except:
            pass
            
    # 3. Defaults Institucionales
    if not settings:
        settings = {
            "fg_mcap_min": 300, "fg_mcap_max": 10000, "fg_rev_growth_min": 25, "fg_price_max": 50, "fg_rs_min": 70,
            "gl_mcap_min": 5000, "gl_rev_growth_min": 12, "gl_margin_min": 30, "gl_rs_min": 75, "gl_inst_min": 40, "gl_price_max": 200,
            "w_rev_growth": 25, "w_gross_margin": 20, "w_eps_growth": 20, "w_rs_score": 20, "w_inst_ownership": 15,
            "filter_min_vol": 200000
        }
        
    return settings

@router.post("/universe/settings")
async def save_universe_settings(settings: dict):
    """Save fundamental selection criteria with absolute path fallback."""
    try:
        # Validación de pesos
        w_fields = ["w_rev_growth", "w_gross_margin", "w_eps_growth", "w_rs_score", "w_inst_ownership"]
        total = sum([float(settings.get(f, 0)) for f in w_fields])
        if abs(total - 100) > 0.9:
            raise HTTPException(status_code=400, detail=f"Los pesos deben sumar 100%. Suma actual: {total}%")

        settings["id"] = 1
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # 1. Guardado LOCAL (Prioridad para estabilidad local)
        import json
        # Ruta absoluta garantizada: c:\Fuentes\eTrade\backend\data\universe_settings.json
        base_dir = "c:/Fuentes/eTrade/backend/data"
        os.makedirs(base_dir, exist_ok=True)
        settings_path = os.path.join(base_dir, "universe_settings.json")
        
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
            
        # 2. Intento en la nube (Sincronización opcional)
        try:
            sb = get_supabase()
            sb.table("universe_settings").upsert(settings).execute()
        except:
            pass # Si falla nube, no importa, ya tenemos la local.
            
        return {"status": "success", "data": settings}
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        err_stack = traceback.format_exc()
        log_error("stocks_api", f"Critical fail on settings: {e}\n{err_stack}")
        # Retornamos el error detallado para diagnosticar
        raise HTTPException(
            status_code=500, 
            detail={"message": str(e), "traceback": err_stack}
        )
