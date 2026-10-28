from fastapi import APIRouter, Depends, HTTPException
import asyncio
import time
import os
import json
from pydantic import BaseModel
from typing import Optional
import traceback
from datetime import datetime, date, timezone, timedelta

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase, reset_supabase
from dateutil.parser import parse as parse_dt
from app.core.market_hours import is_market_open, get_nyc_now, convert_to_lima
from app.data.ib_provider import IBProvider

# Initialize router
router = APIRouter()
_ib = IBProvider() # Shared IB connection for the API process

# CACHE LOCAL PARA REDUCIR EGRESS
METADATA_CACHE = {}
LAST_DATA_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 45  # 5 segundos de gracia para el Dashboard

@router.get("/opportunities")
async def get_stocks_opportunities(gap_runner_only: bool = False):
    """
    Get current stock opportunities and scanner results.
    Aggregates watchlist_daily + technical_scores + trade_opportunities.
    Includes retry logic for Supabase connection issues.
    """
    global LAST_DATA_CACHE
    now_ts = time.time()
    if not gap_runner_only and LAST_DATA_CACHE.get("data") is not None and (now_ts - LAST_DATA_CACHE.get("timestamp", 0) < CACHE_TTL):
        return LAST_DATA_CACHE["data"]
    max_retries = 2
    for attempt in range(max_retries):
        try:
            sb = get_supabase()
            # 1. Market Status
            is_open, status_text = is_market_open()
            market_status = {
                "is_open": is_open,
                "status": status_text,
                "nyc_now": get_nyc_now().isoformat()
            }

            # 2. Get today's date in Lima/NYC
            today = get_nyc_now().date().isoformat()

            # 3. Fetch Technical Scores (Today only)
            today_dt = get_nyc_now().date()
            today_str = today_dt.isoformat()
            
            res_tech = sb.table("technical_scores")\
                .select("*")\
                .gte("timestamp", today_str)\
                .order("timestamp", desc=True)\
                .limit(200)\
                .execute()
            
            tech_data = res_tech.data or []

            # FALLBACK: If no data for today (e.g. Weekend), fetch the latest 200 records regardless of date
            if not tech_data:
                res_tech = sb.table("technical_scores")\
                    .select("*")\
                    .order("timestamp", desc=True)\
                    .limit(200)\
                    .execute()
                tech_data = res_tech.data or []

            # 3.4 Fetch Watchlist Daily to identify PRO members
            wl_res = sb.table("watchlist_daily")\
                .select("ticker, pool_type, fundamental_score")\
                .eq("date", today_str)\
                .execute()
            wl_map = {r["ticker"]: r for r in (wl_res.data or [])}

            # If empty, try to get from any date to have some metadata
            if not wl_map:
                wl_res = sb.table("watchlist_daily")\
                    .select("ticker, pool_type, fundamental_score")\
                    .order("date", desc=True)\
                    .limit(100)\
                    .execute()
                wl_map = {r["ticker"]: r for r in (wl_res.data or [])}

            # 3.5 Fetch Market Snapshot for latest APEX scores (Sync with Queue)
            snap_res = sb.table("market_snapshot")\
                .select("symbol, apex_4h, apex_1d, apex_signal, apex_conf")\
                .execute()
            snap_map = {r["symbol"]: r for r in (snap_res.data or [])}

            # 3.6 Fetch Queue Statuses to join
            q_res = sb.table("stocks_priority_queue")\
                .select("ticker, status, is_overbought")\
                .execute()
            q_map = {r["ticker"]: r for r in (q_res.data or [])}
            
            # 3.7 Fetch Open Positions to correct status
            pos_res = sb.table("stocks_positions")\
                .select("ticker")\
                .eq("status", "open")\
                .execute()
            owned_tickers = {p["ticker"] for p in (pos_res.data or [])}
            
            # FLATTEN signals_json into the root for the Dashboard
            flattened = []
            for item in tech_data:
                try:
                    sigs = item.get("signals_json")
                    if isinstance(sigs, str):
                        try: sigs = json.loads(sigs)
                        except: sigs = {}
                    
                    if not sigs or not isinstance(sigs, dict):
                        sigs = {}
                    
                    # Combine item and sigs
                    merged = {**item, **sigs}
                    ticker = item.get("ticker") or sigs.get("ticker", "UNKNOWN")
                    merged["ticker"] = ticker
                    merged["created_at"] = item.get("timestamp")

                    # SYNC APEX with Market Snapshot (Authoritative source)
                    s_info = snap_map.get(ticker, {})
                    if s_info:
                        merged["apex_4h"] = s_info.get("apex_4h") or merged.get("apex_4h")
                        merged["apex_1d"] = s_info.get("apex_1d") or merged.get("apex_1d")
                        merged["apex_signal"] = s_info.get("apex_signal") or merged.get("apex_signal")
                        merged["apex_conf"] = s_info.get("apex_conf") or merged.get("apex_conf")
                    
                    # Identify if it's PRO member
                    wl_info = wl_map.get(ticker, {})
                    pool = wl_info.get("pool_type", "HOT")
                    f_score = float(wl_info.get("fundamental_score") or 0)
                    mos = float(wl_info.get("margin_of_safety") or sigs.get("margin_of_safety") or 0)
                    
                    is_pro = (pool in ["PRO", "PREMIUM"]) or (f_score >= 80)
                    merged["is_pro_member"] = is_pro
                    merged["pool_type"] = pool

                    # Ensure last_scan_time is present and formatted with date
                    ts = item.get("timestamp")
                    if ts:
                        try:
                            dt = parse_dt(ts)
                            dt_lima = convert_to_lima(dt)
                            dt_nyc = get_nyc_now()
                            merged["last_scan_time"] = f"{dt_lima.strftime('%H:%M')} Lima ({dt_nyc.strftime('%H:%M')} ET) · {dt_lima.strftime('%d/%m/%Y')}"
                        except:
                            if not merged.get("last_scan_time"):
                                merged["last_scan_time"] = "--:--"
                    
                    if not merged.get("last_scan_time"):
                        merged["last_scan_time"] = "--:--"

                    # Join Queue Status
                    q_info = q_map.get(ticker, {})
                    
                    if ticker in owned_tickers:
                        merged["queue_status"] = "owned"
                    else:
                        merged["queue_status"] = q_info.get("status", "watching")

                    merged["is_overbought_queue"] = q_info.get("is_overbought", False)

                    # Campos de Alto Crecimiento y Fuerza de Compra (1H Swing)
                    merged["buying_force_score"] = int(sigs.get("buying_force_score") or item.get("buying_force_score") or 0)
                    merged["is_high_growth_opp"] = bool(sigs.get("is_high_growth_opp") or item.get("is_high_growth_opp") or False)
                    merged["is_high_priority"] = bool(sigs.get("is_high_priority") or item.get("is_high_priority") or False)
                    merged["entry_route_1h"] = sigs.get("entry_route_1h") or item.get("entry_route_1h")
                    merged["entry_support_1h"] = sigs.get("entry_support_1h") or item.get("entry_support_1h")
                    merged["entry_reason_1h"] = sigs.get("entry_reason_1h") or item.get("entry_reason_1h")

                    # Trap Shield & Intraday Alpha
                    merged["is_intraday_alpha"] = bool(sigs.get("is_intraday_alpha") or item.get("is_intraday_alpha") or False)
                    merged["is_trap"] = bool(sigs.get("is_trap") or item.get("is_trap") or False)
                    merged["trap_reason"] = sigs.get("trap_reason") or item.get("trap_reason") or ""
                    merged["gap_pct"] = float(sigs.get("gap_pct") or item.get("gap_pct") or 0.0)
                    merged["growth_potential_pct"] = float(sigs.get("growth_potential_pct") or item.get("growth_potential_pct") or 0.0)
                    merged["intraday_alpha_score"] = int(sigs.get("intraday_alpha_score") or item.get("intraday_alpha_score") or 0)
                    merged["catalyst_tier"] = int(sigs.get("catalyst_tier") or item.get("catalyst_tier") or 3)
                    merged["catalyst_name"] = sigs.get("catalyst_name") or item.get("catalyst_name") or ""
                    merged["catalyst_reason"] = sigs.get("catalyst_reason") or item.get("catalyst_reason") or ""
                    merged["catalyst_headline"] = sigs.get("catalyst_headline") or item.get("catalyst_headline") or ""
                    merged["target_upper5"] = float(sigs.get("target_upper5") or item.get("target_upper5") or 0.0)
                    merged["target_upper6"] = float(sigs.get("target_upper6") or item.get("target_upper6") or 0.0)
                    merged["fast_entry_type"] = sigs.get("fast_entry_type") or item.get("fast_entry_type") or ""
                    merged["fast_entry_reason"] = sigs.get("fast_entry_reason") or item.get("fast_entry_reason") or ""
                    merged["pullback_triggered"] = bool(sigs.get("pullback_triggered") or item.get("pullback_triggered") or False)
                    merged["pullback_type"] = sigs.get("pullback_type") or item.get("pullback_type") or ""
                    merged["pullback_order_type"] = sigs.get("pullback_order_type") or item.get("pullback_order_type") or ""
                    merged["pullback_reason"] = sigs.get("pullback_reason") or item.get("pullback_reason") or ""
                    merged["pullback_limit_orders"] = sigs.get("pullback_limit_orders") or item.get("pullback_limit_orders") or []

                    flattened.append(merged)
                except Exception as item_e:
                    log_warning("stocks_api", f"Error processing item {item.get('ticker')}: {item_e}")
                    continue

            # ── APEX MINIMUM FILTER: Hide low-probability opportunities ──
            # Read configurable threshold from stocks_config
            apex_min = 0  # default
            try:
                cfg_res = sb.table("stocks_config").select("value").eq("key", "apex_min_opportunities").execute()
                if cfg_res.data:
                    apex_min = float(cfg_res.data[0]["value"])
            except:
                pass
            
            if apex_min > 0:
                before_count = len(flattened)
                safe_flattened = []
                for item in flattened:
                    val = item.get("apex_4h")
                    try:
                        f_val = float(val) if val not in (None, "", "N/A", "NaN") else 0.0
                    except:
                        f_val = 0.0
                    if f_val >= apex_min:
                        safe_flattened.append(item)
                flattened = safe_flattened
                filtered_count = before_count - len(flattened)
                if filtered_count > 0:
                    log_info("stocks_api", f"APEX filter: {filtered_count} opportunities hidden (APEX < {apex_min})")

            # ── 4. INTEGRACIÓN DE LIVE ALPHA RUNNERS (TOP GAINERS) & FUERZA COMPRADORA ──
            try:
                from app.stocks.alpha_runner_scanner import scan_top_gainers_live
                live_gainers = await asyncio.to_thread(scan_top_gainers_live, 25)
                existing_map = {item.get("ticker"): item for item in flattened if item.get("ticker")}

                for g in live_gainers:
                    sym = g.get("ticker")
                    if sym in existing_map:
                        existing_map[sym].update(g)
                    else:
                        flattened.append(g)
            except Exception as e_live:
                log_warning("stocks_api", f"Live top gainers scan skipped: {e_live}")

            # ── 5. EVALUACIÓN Y PRIORIZACIÓN INSTITUCIONAL ADUANA OPEN GAP UP (LONGs) ──
            from app.options.aduana_gap_runner_options import get_min_gap_threshold, get_asset_class
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv

            for opp in flattened:
                t = (opp.get("ticker") or "").upper()
                gap_val = float(opp.get("gap_pct") or 0.0)
                chg_val = float(opp.get("change_pct") or 0.0)
                eff_gap = gap_val if gap_val != 0.0 else chg_val
                min_thresh = get_min_gap_threshold(t)
                is_trap = bool(opp.get("is_trap", False))

                # Requisito Mínimo en 1H: (EMA3 > EMA9) o (RSI < 80)
                is_ema3_above_ema9 = opp.get("is_ema3_above_ema9")
                rsi_1h_val = opp.get("rsi_1h")
                if is_ema3_above_ema9 is None or rsi_1h_val is None:
                    try:
                        p_val = float(opp.get("price") or 0.0)
                        h1_data = get_live_1h_candle_and_sipv(t, p_val)
                        if is_ema3_above_ema9 is None:
                            is_ema3_above_ema9 = h1_data.get("is_ema3_above_ema9", False)
                            opp["is_ema3_above_ema9"] = is_ema3_above_ema9
                        if rsi_1h_val is None:
                            rsi_1h_val = float(h1_data.get("rsi_1h") or 50.0)
                            opp["rsi_1h"] = rsi_1h_val
                    except Exception:
                        if is_ema3_above_ema9 is None: is_ema3_above_ema9 = False
                        if rsi_1h_val is None: rsi_1h_val = 50.0

                rsi_1h_num = float(rsi_1h_val if rsi_1h_val is not None else 50.0)
                meets_1h_criteria = bool(is_ema3_above_ema9 or (rsi_1h_num < 80.0))
                opp["meets_1h_criteria"] = meets_1h_criteria

                # Califica como Open Gap Up institucional si supera el umbral, no es trampa Y cumple el requisito mínimo de 1H
                is_runner = (eff_gap >= min_thresh) and (not is_trap) and meets_1h_criteria
                opp["is_gap_runner"] = is_runner
                opp["gap_type"] = "OPEN_GAP_UP" if is_runner else None
                opp["gap_pct"] = eff_gap
                opp["asset_class"] = get_asset_class(t)
                opp["min_gap_required"] = min_thresh

                # Enriquecimiento con STRUCTURAL_REGIME_ENGINE (EMA 3/9/20/50/200 + VWAP + ATR)
                try:
                    from app.core.structural_regime_engine import evaluate_structural_regime
                    st_reg = evaluate_structural_regime(t, float(opp.get("price") or 0.0))
                    opp["structural_regime"] = st_reg
                    opp["regime_code"] = st_reg.get("regime_code")
                    opp["regime_label"] = st_reg.get("regime_label")
                    opp["is_deep_bear_excluded"] = st_reg.get("is_deep_bear_excluded", False)
                except Exception:
                    opp["structural_regime"] = {}
                    opp["regime_code"] = "NEUTRAL"
                    opp["regime_label"] = "⚪ NEUTRAL"
                    opp["is_deep_bear_excluded"] = False

                if is_runner:
                    # Score Boost institucional de +25 puntos para liderar la cola de compras
                    base_rank = float(opp.get("rank_score") or opp.get("buying_force_5m") or 50.0)
                    opp["gap_runner_boost"] = 25.0
                    opp["rank_score"] = round(min(100.0, base_rank + 25.0), 1)
                    opp["is_high_priority"] = True
                else:
                    opp["gap_runner_boost"] = 0.0
                    opp["is_high_priority"] = False

                # Si está en DEEP BEAR WINTER, castigar ranking para evitar compras de acciones atrapadas
                if opp.get("is_deep_bear_excluded"):
                    opp["rank_score"] = max(0.0, float(opp.get("rank_score") or 50.0) - 40.0)
                    opp["is_high_priority"] = False

            if gap_runner_only:
                flattened = [i for i in flattened if i.get("is_gap_runner")]

            # Re-rankear y ordenar: Prioridad 0 absoluta a OPEN GAP UP, luego rank_score desc, gap_pct desc
            flattened.sort(key=lambda x: (
                0 if x.get("is_gap_runner") else 1,
                -float(x.get("rank_score") or x.get("buying_force_5m") or 0.0),
                -float(x.get("gap_pct") or 0.0)
            ))
            for idx, item in enumerate(flattened, 1):
                item["rank"] = idx

            gap_runners = [i for i in flattened if i.get("is_gap_runner")]

            res_obj = {
                "opportunities": flattened,
                "total": len(flattened),
                "total_gap_runners": len(gap_runners),
                "has_gap_runners": len(gap_runners) > 0,
                "market_status": market_status
            }
            if not gap_runner_only:
                LAST_DATA_CACHE["data"] = res_obj
                LAST_DATA_CACHE["timestamp"] = time.time()
            return res_obj
        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in get_stocks_opportunities: {e}")
            return {"opportunities": [], "total": 0, "market_status": {"is_open": False, "status": "ERROR"}}

@router.get("/news/{ticker}")
async def get_ticker_news_endpoint(ticker: str):
    """
    Retorna el resumen de noticias y catalizadores clasificados para un ticker
    para el modal flotante en la UI.
    """
    try:
        from app.stocks.news_catalyst_service import fetch_stock_news
        news_data = fetch_stock_news(ticker)
        return news_data
    except Exception as e:
        log_error("stocks_api", f"Error fetching news for {ticker}: {e}")
        return {
            "ticker": ticker.upper(),
            "has_news": False,
            "catalyst_badge": None,
            "bonus_points": 0,
            "top_headline": "",
            "articles": []
        }

@router.get("/positions")
async def get_stocks_positions():
    """
    Get active stock positions (INTERNAL ONLY).
    Optimized to read ONLY from DB with retry logic.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            sb = get_supabase()
            # 1. Fetch all open positions (excluding options)
            res = sb.table("stocks_positions")\
                .select("*")\
                .eq("status", "open")\
                .neq("group_name", "OPTIONS")\
                .order("first_buy_at", desc=True)\
                .execute()
            
            # Obtener símbolos con opciones abiertas (ej. SPY) para excluirlos de STOCKS
            open_opt_symbols = set()
            try:
                opt_res = sb.table("opt_paper_trades").select("symbol").eq("status", "open").execute()
                for o in (opt_res.data or []):
                    open_opt_symbols.add(str(o.get("symbol", "")).upper())
            except Exception:
                pass

            positions = [
                p for p in (res.data or [])
                if ":OPT:" not in str(p.get("ticker", ""))
                and p.get("group_name") != "OPTIONS"
                and str(p.get("ticker", "")).upper() not in open_opt_symbols
            ]
            if not positions:
                return {"positions": []}

            tickers = [p["ticker"] for p in positions]

            # 2. Bulk fetch strategy info from orders
            strategy_map = {}
            try:
                order_res = sb.table("stocks_orders")\
                    .select("ticker, rule_code")\
                    .in_("ticker", tickers)\
                    .eq("direction", "buy")\
                    .order("created_at", desc=True)\
                    .execute()
                for o in (order_res.data or []):
                    if o["ticker"] not in strategy_map:
                        strategy_map[o["ticker"]] = o["rule_code"]
            except: pass

            # 2.5 Only use IB prices if already connected (never block HTTP request)
            live_prices = {}
            if _ib.conn and _ib.conn.connected:
                try:
                    live_prices = await _ib.get_multiple_prices(tickers)
                except Exception:
                    pass

            # 3.1 Fetch Market Snapshots para diagnósticos
            snap_map = {}
            try:
                snap_res = sb.table("market_snapshot").select("*").in_("symbol", tickers).execute()
                for s in (snap_res.data or []):
                    snap_map[s["symbol"]] = s
            except Exception as snap_e:
                log_debug("stocks_api", f"Error fetching snapshot map: {snap_e}")

            from app.stocks.diagnostic_validator import build_position_diagnostics, check_and_auto_establish_trailing

            for pos in positions:
                ticker = pos["ticker"]
                
                # Obtener precio real de IB (en memoria)
                cur_price = live_prices.get(ticker, 0)
                
                # Fallback a market_snapshot (cotizaciones reales actualizadas minuto a minuto en DB)
                if cur_price <= 0 and ticker in snap_map and snap_map[ticker].get("price"):
                    try:
                        cur_price = float(snap_map[ticker]["price"])
                    except Exception:
                        pass

                # Fallback a DB si IB ni snapshot tienen el dato todavía
                if cur_price <= 0:
                    cur_price = float(pos.get("current_price") or pos.get("avg_price") or 0)
                
                avg_entry = float(pos.get("avg_price") or 0)
                shares = float(pos.get("shares") or 0)

                pos["company_name"] = ticker
                pos["sector"] = "Stocks"
                pos["side"] = "buy"
                pos["strategy"] = strategy_map.get(ticker) or "V5_INDUSTRIAL"
                pos["current_price"] = round(cur_price, 2)
                
                pos["unrealized_pnl"] = round((cur_price - avg_entry) * shares, 2)
                pos["unrealized_pnl_pct"] = round(((cur_price - avg_entry) / avg_entry * 100), 2) if avg_entry > 0 else 0
                pos["total_cost"] = round(avg_entry * shares, 2)

                # Garantizar que trailing stop no esté en blanco en BD
                pos = await check_and_auto_establish_trailing(pos, sb)

                # Adjuntar diagnóstico técnico y de riesgo completo
                pos["diagnostics"] = build_position_diagnostics(pos, snap_db=snap_map.get(ticker))

            # Excluir cualquier posición cuya estrategia sea de opciones
            positions = [p for p in positions if not str(p.get("strategy", "")).upper().startswith("OPT")]

            return {"positions": positions}

        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in get_stocks_positions: {e}")
            return {"positions": [], "error": str(e)}

@router.get("/market-status")
async def get_market_status_endpoint():
    """Get precise market status, NYC time and open/close schedule."""
    from app.core.market_hours import get_market_status_dict
    return get_market_status_dict()

@router.get("/status")
async def get_stocks_status():
    """Get overall status of the stocks engine."""
    try:
        sb = get_supabase()
        config_res = sb.table("stocks_config").select("*").execute()
        config = {r["key"]: r["value"] for r in (config_res.data or [])}

        hb_raw = config.get("ib_bridge_heartbeat")
        hb_data = None
        if hb_raw:
            try:
                import ast
                hb_data = ast.literal_eval(hb_raw) if isinstance(hb_raw, str) else hb_raw
            except Exception:
                hb_data = {"raw": str(hb_raw)}
        
        return {
            "capital_usd": float(config.get("total_capital", 5000)),
            "universe_size": 0,
            "paper_mode": str(config.get("paper_mode_active", "true")).lower() == "true",
            "max_risk_pct": float(config.get("max_risk_pct", 60)),
            "ib_bridge": hb_data
        }
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_status: {e}")
        return {"capital_usd": 5000, "universe_size": 0, "paper_mode": True, "ib_bridge": None}

@router.get("/orders")
async def get_stocks_orders(limit: int = 100):
    """Get stock orders history from stocks_orders table."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_orders")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return res.data or []
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_orders: {e}")
        return []

@router.get("/journal")
async def get_stocks_journal(limit: int = 100):
    """Get trade journal history from trades_journal (real executions) and stocks_positions, filtering out 0.00 ghost sync rows."""
    sb = get_supabase()
    entries = []

    # 1. Consultar trades_journal (fuente primaria de trades reales ejecutados y confirmados)
    try:
        t_res = sb.table("trades_journal")\
            .select("*")\
            .order("exit_date", desc=True)\
            .limit(limit)\
            .execute()
        for t in (t_res.data or []):
            ticker_str = str(t.get("ticker", "")).upper()
            tt_str = str(t.get("trade_type") or t.get("group_name") or "").upper()
            if ":OPT:" in ticker_str or ticker_str.startswith("OPT:") or tt_str.startswith("OPT") or "OPTION" in tt_str:
                continue

            entry_p = float(t.get("entry_price") or 0.0)
            exit_p = float(t.get("exit_price") or entry_p)
            sh = int(float(t.get("shares") or 0))
            pnl_u = float(t.get("pnl_usd") if t.get("pnl_usd") is not None else (exit_p - entry_p) * sh)
            pnl_p = float(t.get("pnl_pct") if t.get("pnl_pct") is not None else (((exit_p - entry_p) / entry_p * 100) if entry_p > 0 else 0.0))

            entries.append({
                "id": t.get("id"),
                "ticker": ticker_str,
                "group_name": t.get("trade_type") or "HOT",
                "strategy": t.get("trade_type") or "V5_STOCKS",
                "side": "buy",
                "shares": sh,
                "entry_price": entry_p,
                "avg_price": entry_p,
                "exit_price": exit_p,
                "current_price": exit_p,
                "total_cost": round(entry_p * sh, 2),
                "pnl_usd": round(pnl_u, 2),
                "unrealized_pnl": round(pnl_u, 2),
                "pnl_pct": round(pnl_p, 2),
                "unrealized_pnl_pct": round(pnl_p, 2),
                "exit_reason": t.get("exit_reason") or "CLOSED",
                "first_buy_at": t.get("entry_date"),
                "entry_date": t.get("entry_date"),
                "updated_at": t.get("exit_date"),
                "exit_date": t.get("exit_date"),
                "status": "closed"
            })
    except Exception as je:
        log_warning("stocks_api", f"Error reading trades_journal: {je}")

    # 2. Complementar con stocks_positions cerradas pero descartando registros ficticios con PnL = 0.00
    try:
        JOURNAL_COLS = (
            "id, ticker, group_name, direction, shares, avg_price, "
            "current_price, total_cost, unrealized_pnl, unrealized_pnl_pct, "
            "status, first_buy_at, updated_at, exit_triggered_by, sl_close_reason"
        )
        p_res = sb.table("stocks_positions")\
            .select(JOURNAL_COLS)\
            .eq("status", "closed")\
            .neq("group_name", "OPTIONS")\
            .order("updated_at", desc=True)\
            .limit(limit)\
            .execute()

        seen_keys = {f"{e['ticker']}_{e['first_buy_at']}" for e in entries}
        for p in (p_res.data or []):
            ticker_str = str(p.get("ticker", "")).upper()
            grp_str = str(p.get("group_name") or "").upper()
            if ":OPT:" in ticker_str or ticker_str.startswith("OPT:") or grp_str.startswith("OPT") or "OPTION" in grp_str:
                continue

            avg_p = float(p.get("avg_price") or 0.0)
            cur_p = float(p.get("current_price") or 0.0)
            pnl_u = float(p.get("unrealized_pnl") or 0.0)

            # FILTRO: Descartar cierres artificiales/ficticios donde entry == exit y pnl == 0 (ej. sync o limpieza sin trade real)
            if abs(avg_p - cur_p) < 0.0001 and abs(pnl_u) < 0.0001:
                continue

            key = f"{ticker_str}_{p.get('first_buy_at')}"
            if key in seen_keys:
                continue

            entries.append({
                "id": p.get("id"),
                "ticker": ticker_str,
                "group_name": p.get("group_name") or "HOT",
                "strategy": p.get("group_name") or "V5_STOCKS",
                "side": "buy",
                "shares": int(float(p.get("shares") or 0)),
                "entry_price": avg_p,
                "avg_price": avg_p,
                "exit_price": cur_p,
                "current_price": cur_p,
                "total_cost": round(avg_p * float(p.get("shares") or 0), 2),
                "pnl_usd": round(pnl_u, 2),
                "unrealized_pnl": round(pnl_u, 2),
                "pnl_pct": round(float(p.get("unrealized_pnl_pct") or 0.0), 2),
                "unrealized_pnl_pct": round(float(p.get("unrealized_pnl_pct") or 0.0), 2),
                "exit_reason": p.get("exit_triggered_by") or p.get("sl_close_reason") or "CLOSED",
                "first_buy_at": p.get("first_buy_at"),
                "entry_date": p.get("first_buy_at"),
                "updated_at": p.get("updated_at"),
                "exit_date": p.get("updated_at"),
                "status": "closed"
            })
    except Exception as pe:
        log_warning("stocks_api", f"Error reading stocks_positions fallback in journal: {pe}")

    # Ordenar por fecha de salida descendente
    entries.sort(key=lambda x: str(x.get("exit_date") or x.get("updated_at") or ""), reverse=True)
    return entries[:limit]

@router.get("/rules")
async def get_stocks_rules():
    """Get all stocks trading rules from stocks_rules table."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_rules").select("*").order("rule_code").execute()
        return res.data or []
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_rules: {e}")
        return []

@router.put("/rules/{rule_code}")
async def update_stocks_rule(rule_code: str, payload: dict):
    """Update an existing stocks rule."""
    try:
        sb = get_supabase()
        # Campos permitidos para actualización (evitar sobreescritura accidental)
        allowed = {
            "name", "enabled", "ia_min", "tech_score_min", "fundamental_score_min",
            "movements_allowed", "notes", "order_type", "limit_trigger_pct",
            "dca_enabled", "dca_max_buys", "dca_min_drop_pct"
        }
        update_data = {k: v for k, v in payload.items() if k in allowed}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        res = sb.table("stocks_rules").update(update_data).eq("rule_code", rule_code).execute()
        if res.data:
            return {"success": True, "rule": res.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Regla no encontrada")
    except Exception as e:
        log_error("stocks_api", f"Error updating rule {rule_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/universe")
async def get_stocks_universe():
    """Get the daily watchlist/universe from watchlist_daily."""
    try:
        sb = get_supabase()
        today = get_nyc_now().date().isoformat()
        
        # Intentar obtener lo de hoy
        res = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .order("fundamental_score", desc=True)\
            .execute()
        
        data = res.data or []
        
        # Si no hay hoy, buscar lo más reciente
        if not data:
            res_recent = sb.table("watchlist_daily")\
                .select("*")\
                .order("date", desc=True)\
                .limit(50)\
                .execute()
            data = res_recent.data or []
            
        return {"universe": data, "count": len(data), "date": data[0]["date"] if data else today}
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_universe: {e}")
        return {"universe": [], "count": 0, "error": str(e)}

@router.post("/refresh-fundamentals")
async def refresh_stocks_fundamentals():
    """Trigger a manual refresh of the universe fundamentals."""
    try:
        from app.stocks.universe_builder import UniverseBuilder
        builder = UniverseBuilder()
        # Esto es asíncrono pero lo esperamos para confirmar a la UI
        await builder.build_daily_watchlist()
        return {"success": True, "message": "Universe rebuilt successfully"}
    except Exception as e:
        log_error("stocks_api", f"Error refreshing fundamentals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import uuid

def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False

@router.delete("/positions/{position_id}")
async def delete_stock_position(position_id: str):
    """Hard delete a stock position or trade journal record from stocks_positions and trades_journal."""
    if not _is_valid_uuid(position_id):
        raise HTTPException(status_code=400, detail=f"ID de posicion invalido: '{position_id}'. Debe ser un UUID valido.")
    try:
        sb = get_supabase()
        deleted_any = False
        
        # 1. Intentar borrar en trades_journal
        try:
            res_tj = sb.table("trades_journal").delete().eq("id", position_id).execute()
            if res_tj.data:
                deleted_any = True
                log_info("stocks_api", f"Journal entry {position_id} deleted from trades_journal")
        except Exception as e_tj:
            log_warning("stocks_api", f"Aviso borrando en trades_journal: {e_tj}")

        # 2. Intentar borrar en stocks_positions
        try:
            res_sp = sb.table("stocks_positions").delete().eq("id", position_id).execute()
            if res_sp.data:
                deleted_any = True
                log_info("stocks_api", f"Position {position_id} deleted from stocks_positions")
        except Exception as e_sp:
            log_warning("stocks_api", f"Aviso borrando en stocks_positions: {e_sp}")

        return {"success": True, "message": "Record deleted successfully"}
            
    except Exception as e:
        log_error("stocks_api", f"Error deleting position/journal {position_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar registro: {str(e)}")

@router.delete("/journal/{journal_id}")
async def delete_stock_journal_entry(journal_id: str):
    """Hard delete an entry from trades_journal and stocks_positions."""
    return await delete_stock_position(journal_id)

@router.post("/positions/{position_id}/close")
async def manual_close_stock_position(position_id: str):
    """Manually close a stock position (updates status to 'closed')."""
    if not _is_valid_uuid(position_id):
        raise HTTPException(status_code=400, detail=f"ID de posicion invalido: '{position_id}'. Debe ser un UUID valido.")
    try:
        sb = get_supabase()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        
        # 1. Obtener la posición
        res = sb.table("stocks_positions").select("*").eq("id", position_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Posición no encontrada")
        
        pos = res.data[0]
        ticker = pos["ticker"]
        avg_price = float(pos.get("avg_price") or 0)
        shares = float(pos.get("shares") or 0)
        
        # 2. Obtener precio actual (de snapshot)
        snap_res = sb.table("market_snapshot").select("price").eq("symbol", ticker).execute()
        current_price = float(snap_res.data[0]["price"]) if snap_res.data else avg_price
        
        # 3. Calcular PnL Realizado
        pnl_usd = (current_price - avg_price) * shares
        pnl_pct = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        
        # 4. Actualizar registro a 'closed'
        update_res = sb.table("stocks_positions").update({
            "status": "closed",
            "updated_at": now,
            "current_price": current_price,
            "unrealized_pnl": round(pnl_usd, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2)
        }).eq("id", position_id).execute()
        
        # 5. Registrar en Journal para que aparezca en "Closed History"
        try:
            journal_entry = {
                "ticker": ticker,
                "shares": int(shares),
                "entry_price": avg_price,
                "exit_price": current_price,
                "entry_date": pos.get("first_buy_at") or pos.get("entry_date"),
                "exit_date": now,
                "pnl_usd": round(pnl_usd, 2),
                "pnl_pct": round(pnl_pct, 2),
                "result": "win" if pnl_usd > 0 else "loss",
                "exit_reason": "MANUAL_CLOSE",
                "trade_type": pos.get("strategy") or pos.get("rule_code") or "V5_INDUSTRIAL"
            }
            sb.table("trades_journal").insert(journal_entry).execute()
            log_info("stocks_api", f"Manual close for {ticker} recorded in journal")
        except Exception as journal_e:
            log_error("stocks_api", f"Error recording manual close in journal for {ticker}: {journal_e}")
        
        return {"success": True, "pnl_usd": pnl_usd}
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("stocks_api", f"Error closing position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/positions/{position_id}/diagnostics/refresh")
async def refresh_stock_position_diagnostics(position_id: str):
    """Force an on-demand calculation and refresh of technical diagnostics for a position."""
    if not _is_valid_uuid(position_id):
        raise HTTPException(status_code=400, detail=f"ID de posicion invalido: '{position_id}'. Debe ser un UUID valido.")
    try:
        sb = get_supabase()
        res = sb.table("stocks_positions").select("*").eq("id", position_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Posición no encontrada")
        pos = res.data[0]
        ticker = pos["ticker"]

        # 1. Fetch Snapshot
        snap_res = sb.table("market_snapshot").select("*").eq("symbol", ticker).limit(1).execute()
        snap_data = snap_res.data[0] if snap_res.data else None

        from app.stocks.diagnostic_validator import build_position_diagnostics, check_and_auto_establish_trailing
        pos = await check_and_auto_establish_trailing(pos, sb)
        diag = build_position_diagnostics(pos, snap_db=snap_data)

        return {"success": True, "ticker": ticker, "diagnostics": diag}
    except HTTPException:
        raise
    except Exception as e:
        log_error("stocks_api", f"Error refreshing diagnostics for position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/priority-queue")
async def get_priority_queue():
    """Get current APEX priority queue for the dashboard.
    
    Enhanced to:
      - Auto-clean stale 'buying' entries (>30 min without completion)
      - Mark owned tickers as 'owned'
      - Dynamically populate from market_snapshot APEX data when queue is stale
    """
    try:
        sb = get_supabase()

        # 0. Get owned tickers to exclude/mark
        pos_res = sb.table("stocks_positions")\
            .select("ticker")\
            .eq("status", "open")\
            .execute()
        owned_tickers = {p["ticker"] for p in (pos_res.data or [])}

        # 1. Auto-clean stale "buying" entries (stuck >30 min)
        try:
            stale_res = sb.table("stocks_priority_queue")\
                .select("id, ticker, status, last_updated")\
                .eq("status", "buying")\
                .execute()
            
            now = datetime.now(timezone.utc)
            for item in (stale_res.data or []):
                last_upd = item.get("last_updated")
                if last_upd:
                    try:
                        upd_dt = parse_dt(last_upd)
                        if upd_dt.tzinfo is None:
                            upd_dt = upd_dt.replace(tzinfo=timezone.utc)
                        age_mins = (now - upd_dt).total_seconds() / 60
                        
                        if item["ticker"] in owned_tickers:
                            # Actually bought — mark as owned
                            sb.table("stocks_priority_queue").update({
                                "status": "owned",
                                "last_updated": now.isoformat()
                            }).eq("id", item["id"]).execute()
                        elif age_mins > 30:
                            # Stuck in buying — revert to watching
                            sb.table("stocks_priority_queue").update({
                                "status": "watching",
                                "last_updated": now.isoformat(),
                                "capital_assigned": 0,
                                "shares_target": 0
                            }).eq("id", item["id"]).execute()
                            log_warning("stocks_api", f"Cleaned stale 'buying' entry: {item['ticker']} (age={age_mins:.0f}m)")
                    except Exception:
                        pass
        except Exception as clean_e:
            log_warning("stocks_api", f"Error cleaning stale queue: {clean_e}")

        # 2. Get queue items (excluding owned)
        today_str = datetime.now(timezone.utc).date().isoformat()
        q_res = sb.table("stocks_priority_queue") \
            .select("*") \
            .in_("status", ["pending", "buying", "blocked"]) \
            .gte("last_updated", today_str) \
            .order("composite_rank", desc=True) \
            .limit(20) \
            .execute()

        db_queue = q_res.data or []
        
        # Filter out owned tickers and low APEX scores from DB queue
        queue = []
        existing_tickers = owned_tickers.copy()
        
        for q in db_queue:
            ticker = q["ticker"]
            if ticker in existing_tickers: continue
            
            # Use apex_score_4h from queue or fallback to 0
            apex_4h = float(q.get("apex_score_4h") or 0)
            comp_rank = float(q.get("composite_rank") or 0)
            
            # Filtro estricto: Descartar activos con APEX bajo (< 60) o rendimiento negativo del día
            # Esto evita que acciones en caída (como SOFI) aparezcan en la cola de compras
            ret_exp = float(q.get("return_expected") or q.get("change_pct") or 0.0)
            if apex_4h < 60.0 or ret_exp < -0.5:
                continue
            
            queue.append(q)
            existing_tickers.add(ticker)

        # 3. Dynamic candidates from Alpha Runners (Live Top Gainers & Buying Force)
        if len(queue) < 15:
            try:
                from app.stocks.alpha_runner_scanner import scan_top_gainers_live
                from app.stocks.stocks_orchestrator import load_orchestrator_config, calculate_composite_rank
                cfg = await load_orchestrator_config(sb)
                live_gainers = await asyncio.to_thread(scan_top_gainers_live, 25)

                for g in (live_gainers or []):
                    ticker = g.get("ticker")
                    if not ticker or ticker in existing_tickers:
                        continue
                    
                    bf = float(g.get("buying_force_5m") or 50.0)
                    rvol_val = float(g.get("rvol") or 1.0)
                    chg = float(g.get("change_pct") or 0.0)
                    has_n = bool(g.get("has_news", False))
                    is_ema3_asc = bool(g.get("is_ema3_1h_ascending", True))
                    apex_4h = float(g.get("apex_4h") or bf)
                    apex_1d = float(g.get("apex_1d") or bf)
                    rank_score = float(g.get("rank_score") or bf)

                    # Calcular composite rank con la fórmula unificada de Fuerza Compradora (45%), RVOL (25%), Gainers (20%)
                    comp_rank = calculate_composite_rank(
                        apex_4h=apex_4h,
                        apex_1d=apex_1d,
                        return_pct=chg,
                        confidence="high" if bf >= 70 else "medium",
                        rvol=rvol_val,
                        cfg=cfg or {},
                        buying_force_score=bf,
                        is_intraday_alpha=True,
                        change_pct=chg,
                        has_news=has_n,
                        is_ema3_1h_ascending=is_ema3_asc
                    )
                    # Tomar el mayor entre rank_score de Alpha Runners y comp_rank
                    final_rank = max(rank_score, comp_rank)

                    is_climax = (g.get("semaphore") == "CLIMAX")

                    dynamic_entry = {
                        "ticker": ticker,
                        "group_name": "ALPHA_RUNNER",
                        "apex_score_4h": apex_4h,
                        "apex_score_1d": apex_1d,
                        "buying_force_score": round(bf, 0),
                        "rvol": round(rvol_val, 2),
                        "return_expected": round(chg, 2),
                        "confidence": "high" if bf >= 70 else "medium",
                        "composite_rank": round(final_rank, 1),
                        "status": "watching",
                        "entry_reason": g.get("semaphore_label") or "Alpha Runner (Rally)",
                        "triggered_rule": "ALPHA_RUNNER",
                        "is_overbought": is_climax,
                        "rsi_at_entry": 0,
                        "fib_zone": 0,
                        "capital_assigned": 0,
                        "shares_target": 0,
                        "price_at_rank": float(g.get("price") or 0),
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                    queue.append(dynamic_entry)
                    existing_tickers.add(ticker)

                # Re-ordenar la cola completa: 1. No clímax/sobrecompra, 2. BF >= 70, 3. Composite rank descendente
                queue.sort(
                    key=lambda q: (
                        not bool(q.get("is_overbought")),
                        float(q.get("buying_force_score") or 0.0) >= 70.0,
                        float(q.get("composite_rank") or 0.0)
                    ),
                    reverse=True
                )
            except Exception as dyn_e:
                log_warning("stocks_api", f"Dynamic queue generation from Alpha Runners error: {dyn_e}")

        # 4. Capital summary
        try:
            from app.stocks.stocks_orchestrator import (
                load_orchestrator_config,
                calculate_available_capital,
            )
            cfg = await load_orchestrator_config(sb)
            capital = await calculate_available_capital(cfg, sb)
        except Exception:
            capital = {
                'capital_available': 0,
                'capital_max_total': 0,
                'capital_invested': 0,
                'ops_possible': 0,
                'can_buy': False,
                'reason': 'Config not loaded',
            }

        return {
            "queue": queue,
            "capital": capital,
            "summary": {
                "total": len(queue),
                "active": sum(1 for q in queue if not q.get("is_overbought")),
                "blocked": sum(1 for q in queue if q.get("is_overbought")),
                "with_signal": sum(1 for q in queue if q.get("triggered_rule")),
            }
        }
    except Exception as e:
        log_error("stocks_api", f"Error in get_priority_queue: {e}")
        return {"queue": [], "capital": {}, "summary": {"total": 0, "active": 0, "blocked": 0, "with_signal": 0}}

