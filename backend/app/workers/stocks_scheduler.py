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
from app.analysis.candle_patterns import detect_patterns
from app.core.market_hours import is_market_open, get_nyc_now
from app.core.symbol_state import SymbolStateMachine, detect_market_ambiguity
from app.stocks.stocks_tp_manager import (
    calculate_tp_blocks,
    evaluate_tp_blocks,
    execute_partial_sell,
)
from app.stocks.stocks_adaptive_tp import (
    evaluate_adaptive_tp,
    fetch_macro_data,
)
from app.stocks.stocks_adaptive_sl import (
    load_sl_config,
    evaluate_adaptive_sl,
    execute_adaptive_sl_close,
)

sm = SymbolStateMachine.get_instance()

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

        # 3. Fallback: most recent watchlist (last 3 days)
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
        df_5m  = await provider.get_ohlcv(ticker, interval="5m",  period="5d")
        df_15m = await provider.get_ohlcv(ticker, interval="15m", period="60d")
        df_4h  = await provider.get_ohlcv(ticker, interval="4h",  period="120d")
        df_1d  = await provider.get_ohlcv(ticker, interval="1d",  period="365d")

        # ROBUST NULL CHECK — skip ticker entirely if any timeframe fails
        if df_5m is None or df_5m.empty or len(df_5m) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 5m data")
            return None
        if df_15m is None or df_15m.empty or len(df_15m) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 15m data")
            return None
        if df_1d is None or df_1d.empty or len(df_1d) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 1d data")
            return None

        # 2. CALCULATE INDICATORS
        ind_5m  = calculate_stock_indicators(df_5m,  "5m",  ticker)
        ind_15m = calculate_stock_indicators(df_15m, "15m", ticker)
        ind_4h  = calculate_stock_indicators(df_4h,  "4h",  ticker)
        ind_1d  = calculate_stock_indicators(df_1d,  "1d",  ticker)

        if not ind_5m or not ind_15m:
            return None

        # ── DETECCIÓN: BOLLINGER EXPLOSION (Sugerencia Usuario) ──
        # Detectamos si las bandas se están "abriendo" (Upper sube, Lower baja)
        df_5m_calc = ind_5m["_df"]
        if len(df_5m_calc) >= 3:
            last_5 = df_5m_calc.iloc[-1]
            prev_5 = df_5m_calc.iloc[-2]
            
            upper_expanding = last_5["bb_upper"] > prev_5["bb_upper"]
            lower_expanding = last_5["bb_lower"] < prev_5["bb_lower"]
            price_breakout  = last_5["close"] > last_5["bb_upper"]
            volume_spike    = last_5["rvol"] > 2.0
            
            if upper_expanding and lower_expanding and price_breakout and volume_spike:
                log_info(MODULE, f"🚀 BOLLINGER EXPLOSION detected in {ticker} (5m)!")
                # Configurar targets específicos solicitados:
                # B1: Upper_6 (15m) | B2: Bollinger Upper (Upper_5 15m) | B3: Trailing
                fib_15m = fibonacci_bollinger(df_15m)
                last_fib = fib_15m.iloc[-1]
                
                tp1 = float(last_fib["upper_6"])
                tp2 = float(last_fib["upper_5"])
                sl  = float(last_5["bb_middle"]) # SL en la base de las bandas
                
                # Crear oportunidad automática
                from app.analysis.opportunity_service import create_stock_opportunity
                await create_stock_opportunity(
                    ticker=ticker,
                    entry_price=float(last_5["close"]),
                    sl=sl,
                    tp1=tp1,
                    tp2=tp2,
                    reason="BOLLINGER_EXPLOSION_5M",
                    strength="STRONG"
                )

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

        # 3b. GAP PROTECTION FILTER (Anti-IFRX & Anti-Falling Knife)
        gap_pct = float(f_data.get("gap_pct", 0) if f_data else 0)
        today_open = float(df_1d.iloc[-1]["open"])
        current_price = float(df_15m.iloc[-1]["close"])

        # Case 1: Gap Up Trap (Price opens high and starts falling)
        if gap_pct > 5.0 and current_price < today_open:
            log_info(MODULE, f"🚫 Blocking {ticker}: Gap Up Trap ({gap_pct}%). Price below open (${current_price} < ${today_open}).")
            return None

        # Case 2: Falling Knife (Price gaps down and stays down)
        if gap_pct < -5.0 and current_price <= today_open:
            log_info(MODULE, f"🚫 Blocking {ticker}: Falling Knife ({gap_pct}%). No bounce from open yet.")
            return None

        # Case 3: Extreme Extension
        if gap_pct > 12.0:
            log_info(MODULE, f"🚫 Blocking {ticker}: Extremely extended Gap ({gap_pct}%). High reversal risk.")
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
        a_rating = 0.0
        if f_data and isinstance(f_data, dict):
            a_rating = float(f_data.get("analyst_rating", 0) or 0)
        
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
            ib_data=f_data if (f_data and isinstance(f_data, dict)) else {},
            sector=f_data.get("sector", "Other") if (f_data and isinstance(f_data, dict)) else "Other",
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
        ia_ia = comp.get("ia", {}).get("score", 5.0) if comp else 5.0
        ia_math = comp.get("math", {}).get("score", 5.0) if comp else 5.0
        c4_txt = f"CAPA 4 (IA Score): {pro_score:.1f} (Math: {ia_math:.1f}, IA: {ia_ia:.1f})."
        piot_score = comp.get("piotroski", {}).get("score", 0) if comp else 0
        altman_z = float(comp.get("altman", {}).get("z_score", 0) or 0) if comp else 0.0
        graham_val = float(comp.get("graham", {}).get("value", 0) or 0) if comp else 0.0
        dcf_val = float(comp.get("dcf", {}).get("value", 0) or 0) if comp else 0.0
        intrinsic = float(fundamental_res.get("intrinsic_value", 0) or 0)
        mos = float(fundamental_res.get("margin_of_safety", 0) or 0)
        status = fundamental_res.get("valuation_status", "N/A").upper()
        icon = "🟢" if status == "UNDERVALUED" else "🔴" if status == "OVERVALUED" else "⚪"

        # Capa 1: Universo
        pool_val = f_data.get('pool_type', 'STANDARD') if (f_data and isinstance(f_data, dict)) else 'STANDARD'
        c1_txt = f"CAPA 1 (Universo): Pool {pool_val} | MCap ${mcap/1e6:.1f}M."
        
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

        # ── NUEVO: SM MOMENTUM SCORE (Data IB Sentiment Proxy) ──
        # V1: RVOL (30%)
        rvol_val = ind_1d.get("rvol", 1.0)
        v1 = min(max(0, (rvol_val - 1) / 4), 1.0)
        
        # V2 & V3: Social Sentiment (IB Generic Ticks 293, 294) 
        # TODO: Implement real fetch from IB in Sprint 8. Using placeholders for now.
        s_score = 0.0   # Range -3 to +3
        sv_score = 5.0  # Range 0 to 10
        v2 = (s_score + 3) / 6
        v3 = sv_score / 10
        
        # V4: Catalyst (25%)
        v4 = float(f_data.get("catalyst_score", 5)) / 10 if f_data else 0.5
        
        # V5: Technical (15%)
        v5 = base_score / 100
        
        sm_raw = (v1 * 0.30) + (v2 * 0.20) + (v3 * 0.10) + (v4 * 0.25) + (v5 * 0.15)
        sm_score = round(sm_raw * 10, 1)
        if f_data and float(f_data.get("catalyst_score", 5)) == 0:
            sm_score = 1.0 # Golden rule: no catalyst = no momentum
            
        ind_15m["sm_score"] = max(1.0, min(sm_score, 10.0))
        ind_15m["s_score"] = s_score
        ind_15m["sv_score"] = sv_score

        # 6. CAPTURE LIVE PRICE
        current_price = float(df_15m["close"].iloc[-1])
        ind_15m["price"] = current_price
        
        # Inject metadata for persistence
        ind_15m["change_pct"] = ind_1d.get("change_pct", 0.0)
        ind_15m["market_cap"] = mcap
        ind_15m["rvol"] = ind_1d.get("rvol", 1.0)
        ind_15m["volume"] = volume_24h
        
        # 7. SMART LIMITS & MOVEMENT TYPE
        movement_15m = classify_movement(df_15m)
        
        # ── NUEVO: SIPV (Candle Patterns) 15m ──
        sipv_15m = detect_patterns(df_15m, ticker, "15m")
        sipv_signal_15m = ""
        if sipv_15m:
            # Si hay patrones, tomamos el primero (o el más fuerte)
            # detect_patterns devuelve una lista formateada
            # En SIPV v2 (app.candle_signals), result.action es lo que importa
            # Pero detect_patterns lo mapea a bullish/bearish.
            # Sin embargo, el detector original está disponible.
            from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC
            det = CandlePatternDetector(market="stocks")
            last_c = df_15m.iloc[-1]
            curr = CandleOHLC(open=float(last_c['open']), high=float(last_c['high']), low=float(last_c['low']), close=float(last_c['close']), volume=float(last_c.get('volume', 0)))
            hist = [CandleOHLC(open=float(r['open']), high=float(r['high']), low=float(r['low']), close=float(r['close']), volume=float(r.get('volume',0))) for _, r in df_15m.tail(10).iloc[:-1].iterrows()]
            res_sipv = det.evaluate(curr, history=hist)
            sipv_signal_15m = res_sipv.action # "BUY", "SELL", or "HOLD"
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

        # ── NUEVO: ACTUALIZAR MARKET SNAPSHOT (Para Dashboard Portfolio) ──
        try:
            ema20 = float(ind_15m.get("ema_20") or ind_15m.get("basis") or current_price)
            atr = float(ind_15m.get("atr") or (current_price * 0.02))
            multipliers = [1.0, 1.618, 2.618, 3.618, 4.236, 5.618]
            zone = 0
            if atr > 0:
                for idx in range(6, 0, -1):
                    if current_price > ema20 + (atr * multipliers[idx-1]): zone = idx; break
                    if current_price < ema20 - (atr * multipliers[idx-1]): zone = -idx; break
            
            snap_data = {
                'symbol': ticker,
                'price': float(current_price),
                'basis': float(ema20),
                'atr': float(atr),
                'fibonacci_zone': int(zone),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'pinescript_signal': str(ps_signal_4h) if ps_signal_4h else None
            }
            sb = get_supabase()
            sb.table('market_snapshot').upsert(snap_data, on_conflict='symbol').execute()
        except Exception as snap_e:
            log_warning(MODULE, f"Error updating snapshot for {ticker}: {snap_e}")

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
            pool_type=ind_15m.get("pool_type", ""),
            sm_score=ind_15m.get("sm_score", 1.0),
            piotroski_score=ind_15m.get("piotroski_score", 0),
            sipv_signal=sipv_signal_15m
        )
        rule_ctx["revenue_growth_yoy"] = ind_15m.get("revenue_growth_yoy", 0)
        rule_ctx["sm_score"] = ind_15m.get("sm_score", 1.0)
        rule_ctx["piotroski_score"] = ind_15m.get("piotroski_score", 0)
        rule_ctx["sipv_signal"] = sipv_signal_15m
        
        # Use 15m PineScript Signal for rules that require it (like HOT_SENTMARKET_BUY)
        ps_signal_15m = ind_15m.get("last_pinescript_signal")
        ps_age_15m = ind_15m.get("signal_age", 999)
        if ps_signal_15m == "Buy" and ps_age_15m <= 3: # Age 0-3 for 15m (Relaxed from 1 to capture more moves)
             rule_ctx["pine_signal"] = "B" # Map 'Buy' to 'B' as requested
        elif t01_confirmed:
             rule_ctx["pine_signal"] = "Buy" # Default 4h signal
        
        # Sync positions with state machine for accurate can_open/can_close logic
        all_pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
        sm.sync_from_positions(ticker, all_pos_res.data or [])
        
        # ── NUEVO: AUTO-CLEANUP DE ESTADOS ZOMBIES ──
        sm.cleanup_zombie_states(ticker, all_pos_res.data or [])

        snap_for_sm = {
            'price': current_price,
            'adx': ind_15m.get('adx', 25),
            'mtf_score': base_score / 100, # Use technical score as proxy for MTF in stocks
            'fibonacci_zone': movement_15m['fib_zone_current'],
            'sar_trend_15m': 1 if sipv_signal_15m == "BUY" else (-1 if sipv_signal_15m == "SELL" else 0),
            'sar_trend_4h': 1 if ps_signal_4h == "Buy" else (-1 if ps_signal_4h == "Sell" else 0)
        }
        ambiguity = detect_market_ambiguity(snap_for_sm)
        if ambiguity['is_ambiguous']:
            log_info(MODULE, f"Skipping {ticker}: Market ambiguous ({ambiguity['reason']})")
            sm.set_ambiguous(ticker, ambiguity['reason'])
            return None

        buying_results = re.evaluate_all(rule_ctx, direction="buy")
        for res in buying_results:
            if res["triggered"]:
                # Check State Machine
                max_pos = int(config.get("max_concurrent_positions", 5))
                sm_check = sm.can_open(ticker, "long", current_price, max_pos)
                if not sm_check['allowed']:
                    log_info(MODULE, f"🚀 RULE TRIGGERED: {res['rule_code']} for {ticker} BLOCKED BY SM: {sm_check['reason']}")
                    continue

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
        
        # Determine if we should run anyway (e.g. if we have open positions to monitor)
        open_tickers = await get_open_positions_tickers()
        has_positions = len(open_tickers) > 0
        
        if not force and not is_open and not has_positions:
            log_info(MODULE, f"Cycle skipped: Market is {status_text} and no active positions")
            return
        
        if not is_open and has_positions:
            log_info(MODULE, f"Market is {status_text}, but running cycle to monitor {len(open_tickers)} active positions")

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

        # ── TICK STATE MACHINE (Waiting/Ambiguous) ──
        for ticker in tickers:
            sm.tick_waiting(ticker)
            sm.tick_ambiguous(ticker)
        
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


async def _get_timeframe_df_for_tp(ticker: str, interval: str = '15m', period: str = '5d') -> pd.DataFrame:
    """Helper to get timeframe OHLCV DataFrame for adaptive TP analysis."""
    try:
        from app.data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        df = await provider.get_ohlcv(ticker, interval=interval, period=period)
        return df
    except Exception as e:
        log_warning(MODULE, f"TP: Cannot get {interval} df for {ticker}: {e}")
        return None

async def _get_daily_df_for_tp(ticker: str) -> pd.DataFrame:
    """Helper to get daily OHLCV DataFrame for ATR calculation in TP manager."""
    try:
        from app.data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        df = await provider.get_ohlcv(ticker, interval="1d", period="60d")
        return df
    except Exception as e:
        log_warning(MODULE, f"TP: Cannot get daily df for {ticker}: {e}")
        return None


async def run_stocks_tp_cycle():
    """
    Ciclo de gestión de TP para stocks.
    Corre cada 5m en horario de mercado.
    Evalúa los 3 bloques de Take Profit para cada posición abierta.
    """
    sb = get_supabase()
    
    try:
        from app.data.ib_provider import IBProvider
    except ImportError:
        from data.ib_provider import IBProvider
        
    ib_provider = IBProvider()
    await ib_provider.connect()

    try:
        pos_res = sb.table('stocks_positions').select('*').eq('status', 'open').execute()
        positions = pos_res.data or []
        if not positions:
            return

        log_info(MODULE, f"📊 TP Cycle: evaluando {len(positions)} posiciones abiertas")
        macro = await fetch_macro_data(sb)
        sl_config = await load_sl_config(sb)

        for pos in positions:
            ticker = pos['ticker']
            try:
                snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).execute()
                snap = snap_res.data[0] if snap_res.data else {}
                price = float(snap.get('price') or 0)
                if price <= 0: continue

                # Inicializar TPs si faltan
                if not pos.get('tp_block1_price'):
                    df_daily = await _get_daily_df_for_tp(ticker)
                    tp_data = calculate_tp_blocks(
                        ticker=ticker,
                        entry_price=float(pos.get('avg_price') or pos.get('entry_price') or 0),
                        total_shares=int(pos.get('shares') or 0),
                        snap=snap,
                        df_daily=df_daily,
                    )
                    if 'error' not in tp_data:
                        sb.table('stocks_positions').update({
                            'tp_block1_price': tp_data['tp_block1_price'],
                            'tp_block2_price': tp_data['tp_block2_price'],
                            'tp_block1_shares': tp_data['tp_block1_shares'],
                            'tp_block2_shares': tp_data['tp_block2_shares'],
                            'tp_block3_shares': tp_data['tp_block3_shares'],
                            'shares_remaining': int(pos.get('shares') or 0),
                            'tp_atr_14': tp_data['atr_14'],
                            'tp_trailing_high': price,
                        }).eq('id', pos['id']).execute()
                        pos.update(tp_data)
                        pos['shares_remaining'] = int(pos.get('shares') or 0)
                        pos['tp_trailing_high'] = price

                df_daily = await _get_daily_df_for_tp(ticker)
                result = evaluate_tp_blocks(pos, price, snap, df_daily)
                
                # Actualizar trailing high
                if float(result.get('new_trail_high') or 0) > float(pos.get('tp_trailing_high') or 0):
                    sb.table('stocks_positions').update({
                        'tp_trailing_high': result['new_trail_high'],
                        'tp_trailing_sl': result.get('b3_trail_sl', 0),
                    }).eq('id', pos['id']).execute()

                action = result['action']
                if action.startswith('execute_'):
                    await execute_partial_sell(
                        ticker=ticker,
                        position=pos,
                        block=result['block'],
                        shares=result['shares'],
                        price=price,
                        action=action,
                        new_sl=result.get('new_sl', 0),
                        new_trail_high=result['new_trail_high'],
                        b3_trail_sl=result['b3_trail_sl'],
                        supabase=sb,
                        ib_provider=ib_provider,
                    )

            except Exception as e:
                log_error(MODULE, f'{ticker} TP error: {e}')
    except Exception as e:
        log_error(MODULE, f'TP cycle failed: {e}')
    finally:
        try: await ib_provider.disconnect()
        except: pass


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

    # 1. HOT BY VOLUME: every 5 minutes during market hours
    scheduler.add_job(
        run_stocks_cycle,
        trigger=IntervalTrigger(minutes=5),
        id="stocks_hot_cycle",
        name="Hot by Volume (5m intraday cycle)",
        kwargs={"force": force},
        max_instances=1,
        replace_existing=True,
    )

    # 1b. TP MANAGER: every 5 minutes during market hours
    scheduler.add_job(
        run_stocks_tp_cycle,
        trigger=IntervalTrigger(minutes=5),
        id="stocks_tp_cycle",
        name="Stocks TP Manager (3 Blocks, 5m)",
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

    # Run first cycles immediately
    asyncio.create_task(run_stocks_tp_cycle())
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

