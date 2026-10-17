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
from zoneinfo import ZoneInfo

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
from app.stocks.stocks_adaptive_tp_v2 import (
    evaluate_stock_tp_v2,
    check_overnight_protection,
)
from app.stocks.stocks_adaptive_sl import (
    load_sl_config,
    evaluate_adaptive_sl,
    execute_adaptive_sl_close,
)
from app.stocks.apex_scheduler import (
    run_apex_cycle,
    run_apex_backtesting,
)
from app.strategy.erep_manager import (
    evaluate_erep_phase,
    execute_erep_action,
    check_erep_activation_conditions,
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
            "min_daily_volume": 1000000,
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


async def cleanup_low_volume_opportunities():
    """
    Remove tickers from technical_scores that have volume < 1,000,000
    or haven't been updated in more than 48 hours.
    """
    sb = get_supabase()
    config = get_stocks_config()
    min_vol = float(config.get("min_daily_volume", 1000000))

    try:
        # 1. Get all current opportunities
        res = sb.table("technical_scores").select("ticker, signals_json, timestamp").execute()
        if not res.data:
            return

        to_delete = []
        now = datetime.now(timezone.utc)
        
        for row in res.data:
            ticker = row["ticker"]
            signals = row.get("signals_json") or {}
            
            # Volume check
            volume = float(signals.get("volume", 0) or 0)
            if volume < min_vol and volume > 0:
                to_delete.append(ticker)
                continue
                
            # Staleness check (more than 3 days)
            updated_at_str = row.get("timestamp")
            if updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                    if (now - updated_at).days >= 3:
                        to_delete.append(ticker)
                except: pass

        if to_delete:
            log_info(MODULE, f"🗑️ Cleaning up {len(to_delete)} low volume/stale opportunities: {to_delete}")
            sb.table("technical_scores").delete().in_("ticker", to_delete).execute()
    except Exception as e:
        log_error(MODULE, f"Error in opportunity cleanup: {e}")


async def process_ticker(ticker: str, config: dict, f_data: dict | None = None, is_pro_member: bool = False, market_open: bool | None = None) -> dict | None:
    if market_open is None:
        from app.core.market_hours import is_market_open
        is_open, _ = is_market_open()
        market_open = is_open

    sb = get_supabase()
    from app.data.yfinance_provider import YFinanceProvider
    from app.analysis.stocks_indicators import calculate_stock_indicators

    try:
        provider = YFinanceProvider()
        
        # 1. DOWNLOAD MULTI-TIMEFRAME DATA (Optimized periods)
        df_5m  = await provider.get_ohlcv(ticker, interval="5m",  period="5d")
        df_15m = await provider.get_ohlcv(ticker, interval="15m", period="60d")
        df_1h  = await provider.get_ohlcv(ticker, interval="1h",  period="60d")
        df_4h  = await provider.get_ohlcv(ticker, interval="4h",  period="120d")
        df_1d  = await provider.get_ohlcv(ticker, interval="1d",  period="365d")

        # Fallback de resample para 1h si vino vacío
        if (df_1h is None or df_1h.empty or len(df_1h) < 5) and df_15m is not None and len(df_15m) >= 8:
            try:
                df_c = df_15m.copy()
                t_col = 'open_time' if 'open_time' in df_c.columns else ('date' if 'date' in df_c.columns else None)
                if t_col:
                    df_c[t_col] = pd.to_datetime(df_c[t_col])
                    df_c = df_c.set_index(t_col)
                df_1h = df_c.resample('1h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
            except Exception:
                pass

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
        if df_4h is None or df_4h.empty or len(df_4h) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 4h data")
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
            price_safe      = last_5["high"] < last_5["bb_upper"]
            volume_spike    = last_5["rvol"] > 2.0
            
            if market_open and upper_expanding and lower_expanding and price_safe and volume_spike:
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

        # Case 1: Gap Up Trap (Merged)
        # Si abre con gap alcista (> 1.5%) pero la vela del día ya es roja (precio < apertura),
        # significa debilidad inmediata y toma de ganancias.
        if gap_pct > 1.5 and current_price < today_open:
            log_info(MODULE, f"🚫 Blocking {ticker}: Gap Up Trap (${current_price} < Open ${today_open}). Gap: {gap_pct}%.")
            return None
        # Case 2: Falling Knife (Gap Down)
        # Un gap a la baja severo arruina el sentimiento para todo el día.
        # Bloqueamos inmediatamente si la acción abre con -2.0% o peor.
        if gap_pct < -2.0:
            log_info(MODULE, f"🚫 Blocking {ticker}: Gap Down ({gap_pct}%). Bearish sentiment for the day.")
            return None

        # Case 3: Extreme Parabolic Extension (> 45% governed by TrapShield)
        # Fast-Track para IPO Super-Runners: Si la acción tiene <= 15 velas diarias o es IPO con volumen fuerte (>= 1.5M o RVOL >= 2.0),
        # permitimos el paso a la categoría especializada IPO_SUPER_RUNNER con stops de 5m en vez de vetarlo.
        rvol_1d_init = float(ind_1d.get("rvol", 1.0))
        is_ipo_runner = (len(df_1d) <= 15 and (volume_24h >= 1_500_000 or rvol_1d_init >= 2.0)) or ("IPO" in str(f_data.get("pool_type", "") if f_data else ""))
        if gap_pct > 45.0:
            if is_ipo_runner:
                log_info(MODULE, f"🚀 FAST-TRACK IPO SUPER-RUNNER for {ticker}: Gap {gap_pct:.1f}% admitido por volumen masivo ({volume_24h:,.0f}) e historial joven ({len(df_1d)} velas 1D).")
            else:
                log_info(MODULE, f"🚫 Blocking {ticker}: Extremely extended Parabolic Gap ({gap_pct}%). High reversal risk.")
                return None

        # 4. TECHNICAL RULES
        # ── MOMENTUM FAST-TRACK: Relax rules for high-RVOL explosive movers ──
        momentum_rvol_threshold = float(config.get("momentum_rvol_threshold", 2.5))
        rvol_current = float(ind_1d.get("rvol", 1.0))
        is_momentum_mode = (rvol_current >= momentum_rvol_threshold)
        
        if is_momentum_mode:
            log_info(MODULE, f"⚡ MOMENTUM MODE for {ticker}: RVOL={rvol_current:.1f} >= {momentum_rvol_threshold}")

        ps_signal_4h = ind_4h.get("last_pinescript_signal")
        ps_age_4h = ind_4h.get("signal_age", 999)
        t01_confirmed = (ps_signal_4h == "Buy" and ps_age_4h <= 3)
        
        # Momentum: Accept 15m PineScript signal if 4h hasn't triggered yet
        if is_momentum_mode and not t01_confirmed:
            ps_signal_15m = ind_15m.get("last_pinescript_signal")
            ps_age_15m = ind_15m.get("signal_age", 999)
            if ps_signal_15m == "Buy" and ps_age_15m <= 3:
                t01_confirmed = True
                log_info(MODULE, f"⚡ {ticker}: T01 relaxed — using 15m Buy signal (age={ps_age_15m})")

        ema_50_1d = ind_1d.get("ema_50") or 0.0
        ema_200_1d = ind_1d.get("ema_200") or 999999.0
        t02_confirmed = (ema_50_1d > ema_200_1d)
        
        # Momentum: Skip macro trend requirement for explosive pumps
        if is_momentum_mode and not t02_confirmed:
            t02_confirmed = True
            log_info(MODULE, f"⚡ {ticker}: T02 relaxed — macro trend bypassed (RVOL={rvol_current:.1f})")

        candle_4h_green = 1 if df_4h.iloc[-1]["close"] > df_4h.iloc[-1]["open"] else 0

        # SCORING
        base_score = 0.0
        if t01_confirmed:   base_score += 40.0
        if t02_confirmed:   base_score += 30.0
        if candle_4h_green: base_score += 20.0
        
        rsi_val = ind_15m.get("rsi_14")
        # Momentum: Allow RSI up to 85 (overbought is natural for pumps)
        rsi_upper = 85 if is_momentum_mode else 70
        if rsi_val and 40 <= rsi_val <= rsi_upper:
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
            hist = [CandleOHLC(open=float(r['open']), high=float(r['high']), low=float(r['low']), close=float(r['close']), volume=float(r.get('volume') or 0)) for _, r in df_15m.tail(10).iloc[:-1].iterrows()]
            res_sipv = det.evaluate(curr, history=hist)
            sipv_signal_15m = res_sipv.action # "BUY", "SELL", or "HOLD"
        limit_long_15m  = calculate_smart_limit_price(df_15m, 'long',  movement_15m['movement_type'])
        limit_short_15m = calculate_smart_limit_price(df_15m, 'short', movement_15m['movement_type'])

        movement_1d = classify_movement(df_1d)
        limit_long_1d  = calculate_smart_limit_price(df_1d, 'long',  movement_1d['movement_type'])
        limit_short_1d = calculate_smart_limit_price(df_1d, 'short', movement_1d['movement_type'])

        bb_lower_1d = float(df_1d.iloc[-1].get("bb_lower", current_price * 0.95))
        ind_15m["bb_lower"] = bb_lower_1d
        
        # ── NUEVO: ADR & Volatility Fuel Gate ──
        from app.stocks.adr_volatility_gate import evaluate_adr_and_volatility_gate
        adr_gate_res = evaluate_adr_and_volatility_gate(
            df_1d=df_1d,
            df_15m=df_15m,
            current_price=current_price,
            rvol_15m_override=ind_15m.get("rvol")
        )
        ind_15m["adr_14_pct"] = adr_gate_res['adr_pct']
        ind_15m["adr_consumed_pct"] = adr_gate_res['consumed_pct']
        ind_15m["bandwidth_15m"] = adr_gate_res['bandwidth_pct']
        ind_15m["is_dead_compression"] = adr_gate_res['is_dead_compression']
        ind_15m["candle_vol_15m"] = adr_gate_res['candle_vol_15m']
        ind_15m["breakout_prob"] = adr_gate_res['breakout_prob']
        ind_15m["adr_gate_summary"] = adr_gate_res['summary']

        # ── NUEVO: BUYING FORCE & GATILLOS 1H (Swing High Growth) ──
        from app.stocks.buying_force_detector import (
            evaluate_macro_1d_alignment,
            calculate_buying_force_score,
            detect_pullback_and_climax_1h
        )
        macro_1d_info = evaluate_macro_1d_alignment(df_1d)
        rvol_1h_val = float(ind_15m.get("rvol") or 1.0)
        buying_force_info = calculate_buying_force_score(
            adr_pct=float(adr_gate_res['adr_pct']),
            consumed_pct=float(adr_gate_res['consumed_pct']),
            rvol_1h=rvol_1h_val,
            df_1h=df_1h,
            macro_aligned=macro_1d_info['aligned'],
            bandwidth_1h=float(adr_gate_res.get('bandwidth_pct', 3.0))
        )
        entry_1h_info = detect_pullback_and_climax_1h(
            current_price=current_price,
            df_1h=df_1h,
            macro_aligned=macro_1d_info['aligned'],
            df_15m=df_15m
        )

        ind_15m["macro_1d_aligned"] = macro_1d_info['aligned']
        ind_15m["macro_1d_reason"] = macro_1d_info['reason']
        ind_15m["ema_20_1d"] = macro_1d_info.get('ema20', 0.0)
        ind_15m["ema_50_1d"] = macro_1d_info.get('ema50', 0.0)
        ind_15m["ema_200_1d"] = macro_1d_info.get('ema200', 0.0)
        ind_15m["buying_force_score"] = buying_force_info['score']
        ind_15m["is_high_growth_opp"] = buying_force_info['is_qualified']
        ind_15m["is_high_priority"] = buying_force_info['is_high_priority']
        ind_15m["entry_route_1h"] = entry_1h_info.get('route')
        ind_15m["entry_support_1h"] = entry_1h_info.get('support_level')
        ind_15m["entry_reason_1h"] = entry_1h_info.get('reason')

        # ── NUEVO: TRAP SHIELD & INTRADAY ALPHA CANDIDATE ──
        from app.stocks.trap_shield import evaluate_trap_shield
        prev_close_1d = current_price
        open_price_today = current_price
        if df_1d is not None and len(df_1d) >= 2:
            prev_close_1d = float(df_1d['close'].iloc[-2]) if 'close' in df_1d.columns else current_price
            open_price_today = float(df_1d['open'].iloc[-1]) if 'open' in df_1d.columns else current_price
        elif df_5m is not None and len(df_5m) >= 1:
            open_price_today = float(df_5m['open'].iloc[0]) if 'open' in df_5m.columns else current_price

        ind_15m["open_1d"] = open_price_today

        trap_shield_res = evaluate_trap_shield(
            current_price=current_price,
            prev_close=prev_close_1d,
            open_price=open_price_today,
            df_5m=df_5m,
            df_15m=df_15m,
            rvol=rvol_1h_val,
            adr_pct=float(adr_gate_res.get('adr_pct', 4.0)),
            consumed_pct=float(adr_gate_res.get('consumed_pct', 30.0)),
            bands_15m=movement_15m.get('bands') or {}
        )

        # ── NUEVO: EVALUACIÓN DE CATALIZADOR / NOTICIAS EN VIVO ──
        from app.stocks.catalyst_classifier import analyze_ticker_live_catalyst
        news_items = f_data.get('news') if f_data else None
        cat_info = analyze_ticker_live_catalyst(ticker, news_items)
        ind_15m["catalyst_tier"] = cat_info['tier']
        ind_15m["catalyst_name"] = cat_info['catalyst_name']
        ind_15m["catalyst_reason"] = cat_info['reason']
        ind_15m["catalyst_headline"] = cat_info.get('headline', '')

        # Si la noticia anuncia dilución tóxica directa (Tier 0), vetar de inmediato
        if cat_info.get('is_toxic'):
            trap_shield_res['is_trap'] = True
            trap_shield_res['trap_type'] = 'TOXIC_DILUTION_RISK'
            trap_shield_res['trap_reason'] = f"VETO NOTICIAS: {cat_info['reason']}"

        # ── NUEVO: FAST ENTRY ENGINE (MULTI-TF ADX/DI + VELAS) ──
        from app.stocks.fast_entry_engine import evaluate_fast_entry
        fast_entry_res = evaluate_fast_entry(
            current_price=current_price,
            df_5m=df_5m,
            df_15m=df_15m,
            df_1h=df_1h,
            df_4h=df_4h,
            df_1d=df_1d,
            rvol=rvol_1h_val,
            bands_15m=movement_15m.get('bands') or {},
            is_trap=trap_shield_res['is_trap']
        )

        ind_15m["fast_entry_triggered"] = fast_entry_res['fast_entry_triggered']
        ind_15m["fast_entry_type"] = fast_entry_res['entry_type']
        ind_15m["fast_entry_reason"] = fast_entry_res['entry_reason']
        ind_15m["recommended_sl"] = fast_entry_res['recommended_sl']
        ind_15m["target_upper5"] = fast_entry_res['target_upper5']
        ind_15m["target_upper6"] = fast_entry_res['target_upper6']
        ind_15m["adx_5m"] = fast_entry_res['adx_metrics'].get('5m', {}).get('adx', 0)
        ind_15m["plus_di_5m"] = fast_entry_res['adx_metrics'].get('5m', {}).get('plus_di', 0)
        ind_15m["minus_di_5m"] = fast_entry_res['adx_metrics'].get('5m', {}).get('minus_di', 0)

        # ── NUEVO: PULLBACK & STRUCTURAL BUY ENGINE (SECCIÓN B: 3a, 4a, 4b, 4c, 4d) ──
        from app.stocks.pullback_engine import evaluate_pullback_setup
        pine_sig_str = str(ind_15m.get("last_pinescript_signal") or ind_5m.get("last_pinescript_signal") or "")
        pullback_res = evaluate_pullback_setup(
            current_price=current_price,
            df_5m=df_5m,
            df_15m=df_15m,
            df_1h=df_1h,
            bands_15m=movement_15m.get('bands') or {},
            vwap=trap_shield_res.get('vwap', 0.0),
            spread=0.02,
            pinescript_signal=pine_sig_str,
            sipv_signal_15m=sipv_signal_15m,
            is_ipo_runner=is_ipo_runner,
        )

        ind_15m["pullback_triggered"] = pullback_res['pullback_triggered']
        ind_15m["pullback_type"] = pullback_res['trigger_type']
        ind_15m["pullback_order_type"] = pullback_res['order_type']
        ind_15m["pullback_reason"] = pullback_res['reason']
        ind_15m["pullback_limit_orders"] = pullback_res.get('limit_orders', [])
        if pullback_res['pullback_triggered'] and pullback_res.get('recommended_sl', 0) > 0:
            ind_15m["recommended_sl"] = pullback_res['recommended_sl']

        # Si es IPO Super-Runner, inmunizar del filtro de trampa por gap genérico (salvo dilución tóxica)
        if is_ipo_runner and not trap_shield_res.get('is_toxic_dilution', False):
            trap_shield_res['is_trap'] = False
            ind_15m["pool_type"] = "IPO_SUPER_RUNNER, ALPHA_RUNNER"
            ind_15m["is_intraday_alpha"] = True

        ind_15m["is_trap"] = trap_shield_res['is_trap']
        ind_15m["trap_type"] = trap_shield_res['trap_type']
        ind_15m["trap_reason"] = trap_shield_res['trap_reason']
        ind_15m["gap_pct"] = trap_shield_res['gap_pct']
        ind_15m["is_sweet_spot"] = trap_shield_res['is_sweet_spot']
        ind_15m["is_intraday_alpha"] = trap_shield_res['is_intraday_alpha']
        ind_15m["growth_potential_pct"] = trap_shield_res['growth_potential_pct']
        ind_15m["intraday_alpha_score"] = trap_shield_res.get('intraday_alpha_score', 0)

        # Clasificar categoría ALPHA_RUNNER explícitamente si es runner de $15M-$500M o Intraday Alpha
        is_alpha_runner_cat = (
            trap_shield_res.get('is_intraday_alpha', False)
            or (15_000_000 <= mcap <= 500_000_000 and (rvol_1h_val >= 1.8 or abs(float(ind_15m.get("change_pct") or 0)) >= 4.0))
            or ("ALPHA_RUNNER" in str(ind_15m.get("pool_type", "")))
        )
        if is_alpha_runner_cat and not trap_shield_res['is_trap']:
            cur_pt = str(ind_15m.get("pool_type", "") or "").strip()
            if "ALPHA_RUNNER" not in cur_pt and "IPO_SUPER_RUNNER" not in cur_pt:
                ind_15m["pool_type"] = f"ALPHA_RUNNER, {cur_pt}".strip(", ") if cur_pt and cur_pt != "HOT" else "ALPHA_RUNNER"
            ind_15m["is_intraday_alpha"] = True

        # ── GESTIÓN DE COLA DE ALTA PRIORIDAD & EXCLUSIÓN DE TRAMPAS ──
        # 1. Si es TRAMPA: Bloquear en la cola para erradicar compras no deseadas
        if trap_shield_res['is_trap']:
            try:
                sb.table("stocks_priority_queue").upsert({
                    'ticker': ticker,
                    'group_name': ind_15m.get('pool_type', 'HOT'),
                    'price_at_rank': current_price,
                    'apex_score_4h': float(ind_15m.get('apex_4h') or 50.0),
                    'apex_score_1d': float(ind_15m.get('apex_1d') or 50.0),
                    'return_expected': 0.0,
                    'confidence': 'low',
                    'composite_rank': 0.0,
                    'status': 'blocked',
                    'entry_reason': f"TRAP_SHIELD_{trap_shield_res['trap_type']}",
                    'triggered_rule': 'NONE',
                    'is_overbought': True,
                    'rsi_at_entry': float(ind_15m.get('rsi_14', 50.0)),
                    'fib_zone': int(movement_15m.get('fib_zone_current', 0)),
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }, on_conflict='ticker').execute()
                log_warning(MODULE, f"🚫 TRAMPA BLOQUEADA EN COLA: {ticker} ({trap_shield_res['trap_reason']})")
            except Exception as q_err:
                log_warning(MODULE, f"Error bloqueando trampa para {ticker}: {q_err}")

        # 1.5 Si es candidato FAST-TRACK IPO SUPER-RUNNER / ALPHA RUNNER: Máxima Prioridad Rank 99.5
        elif (is_ipo_runner or is_alpha_runner_cat) and not trap_shield_res.get('is_toxic_dilution', False):
            try:
                from app.stocks.fast_track_runner_engine import evaluate_fast_track_entry, evaluate_fast_track_reentry
                pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
                active_pos = pos_res.data[0] if (pos_res.data and len(pos_res.data) > 0) else None

                if active_pos is None:
                    from app.stocks.fast_track_runner_engine import (
                        evaluate_fast_track_entry,
                        evaluate_fast_track_reentry,
                        evaluate_leg2_reversal_entry
                    )
                    ft_entry_res = evaluate_fast_track_entry(
                        ticker=ticker,
                        df_5m=df_5m,
                        df_15m=df_15m,
                        df_1h=df_1h,
                        df_1d=df_1d,
                        gap_pct=float(trap_shield_res.get('gap_pct', 0.0)),
                        config=config
                    )
                    # Si no califica por Fast-Track Open (o ya pasó la apertura), evaluar Re-Ignición OLA 2 (Leg-2 Reversal)
                    if not ft_entry_res.get('is_valid'):
                        ft_entry_res = evaluate_leg2_reversal_entry(
                            ticker=ticker,
                            df_5m=df_5m,
                            df_15m=df_15m,
                            df_1h=df_1h,
                            current_price=current_price,
                            config=config
                        )

                    if ft_entry_res.get('is_valid'):
                        rank_boost = 99.5
                        sb.table("stocks_priority_queue").upsert({
                            'ticker': ticker,
                            'group_name': 'IPO_SUPER_RUNNER',
                            'price_at_rank': current_price,
                            'apex_score_4h': 98.0,
                            'apex_score_1d': 98.0,
                            'return_expected': trap_shield_res.get('growth_potential_pct', 25.0) or 25.0,
                            'confidence': 'high',
                            'composite_rank': rank_boost,
                            'status': 'pending',
                            'entry_reason': ft_entry_res['reason'],
                            'triggered_rule': ft_entry_res['rule_code'],
                            'is_overbought': False,
                            'rsi_at_entry': float(ind_15m.get('rsi_14', 50.0)),
                            'fib_zone': int(movement_15m.get('fib_zone_current', 0)),
                            'last_updated': datetime.now(timezone.utc).isoformat()
                        }, on_conflict='ticker').execute()
                        log_info(MODULE, f"🚀 GATILLO FAST-TRACK RUNNER 99.5: {ticker} | {ft_entry_res['rule_code']} | {ft_entry_res['reason']}")
                else:
                    ft_reentry_res = evaluate_fast_track_reentry(
                        position=active_pos,
                        df_5m=df_5m,
                        df_15m=df_15m,
                        df_1h=df_1h,
                        current_price=current_price
                    )
                    if ft_reentry_res.get('should_reenter'):
                        # Sizing de re-compra: 35% del total asignado por % Inversión por Operación
                        initial_shares = int(active_pos.get('initial_shares') or active_pos.get('shares', 0))
                        re_shares = max(5, int((initial_shares * (0.35 / 0.30)) // 5) * 5)
                        sb.table("stocks_orders").insert({
                            "ticker": ticker,
                            "group_name": "FAST_TRACK",
                            "rule_code": "FT_REENTRY_BUY",
                            "order_type": "market",
                            "direction": "buy",
                            "shares": re_shares,
                            "market_price": current_price,
                            "status": "pending",
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }).execute()
                        new_sl = ft_reentry_res.get('new_global_sl')
                        new_count = int(active_pos.get('reentry_count') or 0) + 1
                        sb.table("stocks_positions").update({
                            "stop_loss": new_sl,
                            "reentry_count": new_count,
                            "last_reentry_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", active_pos["id"]).execute()
                        log_info(MODULE, f"🔥 RECOMPRA PYRAMIDING DISPARADA ({new_count}/2): {ticker} +{re_shares} sh @ ${current_price:.2f} (SL a ${new_sl:.2f})")
                    elif ft_reentry_res.get('is_range_compressed_exhaustion'):
                        log_warning(MODULE, f"⚠️ DESACELERACIÓN Y COMPRESIÓN DE RANGO 1H para {ticker}: Recompra cancelada. Ajustando Trailing Stop defensivo.")
                        if df_1h is not None and len(df_1h) >= 2:
                            l1h_cur = float(_safe_col(df_1h, 'low').iloc[-1])
                            cur_sl = float(active_pos.get('stop_loss') or 0.0)
                            if l1h_cur > cur_sl and l1h_cur < current_price:
                                sb.table("stocks_positions").update({
                                    "stop_loss": round(l1h_cur, 2),
                                    "sl_activation_reason": "1H Range Compression Defensivo"
                                }).eq("id", active_pos["id"]).execute()
            except Exception as e_ft_sched:
                log_warning(MODULE, f"Error en Fast-Track Scheduler para {ticker}: {e_ft_sched}")

        # 2. Si GATILLO DE ENTRADA RÁPIDA (FAST ENTRY) está activo:
        # Veto estricto: Prohibido si la vela diaria es roja o tendencia 1D es bajista (Evitar casos tipo SOFI)
        elif fast_entry_res['fast_entry_triggered'] and not ((open_price_today > 0 and current_price < open_price_today * 0.995) or (movement_1d.get("movement_type") == "descending")):
            try:
                real_apex_4h = float(ind_15m.get('apex_4h') or 0.0)
                real_apex_1d = float(ind_15m.get('apex_1d') or 0.0)
                bf_val = float(ind_15m.get('buying_force_score') or 50.0)

                # Solo califica a la cola si tiene momentum y APEX real >= 60 o fuerza compradora >= 70
                if (real_apex_4h >= 60.0 or bf_val >= 70.0):
                    rank_boost = round(min(98.5, max(75.0, (real_apex_4h * 0.4 + real_apex_1d * 0.3 + bf_val * 0.3))), 1)
                    sb.table("stocks_priority_queue").upsert({
                        'ticker': ticker,
                        'group_name': ind_15m.get('pool_type', 'HOT'),
                        'price_at_rank': current_price,
                        'apex_score_4h': real_apex_4h,
                        'apex_score_1d': real_apex_1d,
                        'return_expected': trap_shield_res['growth_potential_pct'],
                        'confidence': 'high' if rank_boost >= 85 else 'medium',
                        'composite_rank': rank_boost,
                        'status': 'pending',
                        'entry_reason': str(fast_entry_res['entry_reason'])[:50],
                        'triggered_rule': f"FAST_{fast_entry_res['entry_type']}"[:50],
                        'is_overbought': False,
                        'rsi_at_entry': float(ind_15m.get('rsi_14', 50.0)),
                        'fib_zone': int(movement_15m.get('fib_zone_current', 0)),
                        'last_updated': datetime.now(timezone.utc).isoformat()
                    }, on_conflict='ticker').execute()
                    log_info(MODULE, f"⚡ GATILLO FAST ENTRY {rank_boost}: {ticker} | {fast_entry_res['entry_type']} | {fast_entry_res['entry_reason']}")
            except Exception as q_err:
                log_warning(MODULE, f"Error asignando fast entry en cola para {ticker}: {q_err}")

        # 3. Si GATILLO DE COMPRA EN RETROCESO (PULLBACK) está activo: Rank 98.8 (LOWER) o 98.6 (EMA LIMIT)
        elif pullback_res['pullback_triggered'] and not trap_shield_res['is_trap'] and not (open_price_today > 0 and current_price < open_price_today * 0.985):
            try:
                rank_boost = 98.8 if pullback_res['trigger_type'] == 'PULLBACK_LOWER_ABSORPTION' else 98.6
                sb.table("stocks_priority_queue").upsert({
                    'ticker': ticker,
                    'group_name': ind_15m.get('pool_type', 'HOT'),
                    'price_at_rank': current_price,
                    'apex_score_4h': float(ind_15m.get('apex_4h') or 92.0),
                    'apex_score_1d': float(ind_15m.get('apex_1d') or 92.0),
                    'return_expected': trap_shield_res['growth_potential_pct'] or 7.0,
                    'confidence': 'high',
                    'composite_rank': rank_boost,
                    'status': 'pending',
                    'entry_reason': str(pullback_res['reason'])[:50],
                    'triggered_rule': f"PULLBACK_{pullback_res['trigger_type']}"[:50],
                    'is_overbought': False,
                    'rsi_at_entry': float(ind_15m.get('rsi_14', 50.0)),
                    'fib_zone': int(movement_15m.get('fib_zone_current', 0)),
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }, on_conflict='ticker').execute()
                log_info(MODULE, f"🎯 GATILLO PULLBACK {rank_boost}: {ticker} | {pullback_res['trigger_type']} | {pullback_res['reason']}")

                # Si es PULLBACK_EMA_LIMIT, colocar orden LIMIT con TTL de 5m
                if pullback_res['trigger_type'] == 'PULLBACK_EMA_LIMIT' and pullback_res.get('limit_orders'):
                    best_limit = pullback_res['limit_orders'][0]
                    rule_ctx_pb = {
                        "price": current_price,
                        "smart_limit_price": best_limit['limit_price'],
                        "limit_price": best_limit['limit_price'],
                        "band_name": f"{best_limit['ema_target']}_PULLBACK",
                        "ttl_minutes": 5,
                        "movement_type": movement_15m.get("movement_type"),
                        "rvol": rvol_1h_val,
                    }
                    rule_pb = {
                        "group_name": ind_15m.get('pool_type', 'HOT'),
                        "limit_trigger_pct": 0.005,
                    }
                    try:
                        from app.stocks.stocks_order_executor import place_limit_order
                        place_limit_order(ticker, "buy", "PULLBACK_EMA_LMT", rule_ctx_pb, rule_pb)
                    except Exception as lmt_e:
                        log_warning(MODULE, f"Error colocando orden LIMIT pullback para {ticker}: {lmt_e}")
            except Exception as q_err:
                log_warning(MODULE, f"Error asignando pullback en cola para {ticker}: {q_err}")

        # 4. Si es INTRADAY ALPHA CANDIDATE: Rank 98.5
        elif trap_shield_res['is_intraday_alpha']:
            try:
                rank_boost = 98.5
                sb.table("stocks_priority_queue").upsert({
                    'ticker': ticker,
                    'group_name': ind_15m.get('pool_type', 'HOT'),
                    'price_at_rank': current_price,
                    'apex_score_4h': float(ind_15m.get('apex_4h') or 90.0),
                    'apex_score_1d': float(ind_15m.get('apex_1d') or 90.0),
                    'return_expected': trap_shield_res['growth_potential_pct'],
                    'confidence': 'high',
                    'composite_rank': rank_boost,
                    'status': 'pending',
                    'entry_reason': f"intraday_alpha_pot_{trap_shield_res['growth_potential_pct']}%"[:50],
                    'triggered_rule': 'INTRADAY_ALPHA_BUY',
                    'is_overbought': False,
                    'rsi_at_entry': float(ind_15m.get('rsi_14', 50.0)),
                    'fib_zone': int(movement_15m.get('fib_zone_current', 0)),
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }, on_conflict='ticker').execute()
                log_info(MODULE, f"🚀 ALTA PRIORIDAD INTRADÍA (Rank 98.5): {ticker} (Potencial=+{trap_shield_res['growth_potential_pct']}%, Gap=+{trap_shield_res['gap_pct']}%, RVOL={rvol_1h_val:.1f}x)")
            except Exception as q_err:
                log_warning(MODULE, f"Error asignando intraday alpha en cola para {ticker}: {q_err}")

        # 3. Ruta alternativa: Swing 1H Buying Force
        elif buying_force_info['is_qualified'] and entry_1h_info.get('triggered'):
            try:
                rank_boost = min(99.0, 92.0 + (buying_force_info['score'] * 0.07))
                sb.table("stocks_priority_queue").upsert({
                    'ticker': ticker,
                    'group_name': ind_15m.get('pool_type', 'HOT'),
                    'price_at_rank': current_price,
                    'apex_score_4h': float(ind_15m.get('apex_4h') or 85.0),
                    'apex_score_1d': float(ind_15m.get('apex_1d') or 85.0),
                    'return_expected': 6.5,
                    'confidence': 'high',
                    'composite_rank': round(rank_boost, 2),
                    'status': 'pending',
                    'entry_reason': f"high_growth_{entry_1h_info.get('route', '1h')}_{entry_1h_info.get('support_level', '')}"[:50],
                    'triggered_rule': f"LONG_{entry_1h_info.get('route', 'PULLBACK')}_1H"[:50],
                    'is_overbought': False,
                    'rsi_at_entry': float(ind_15m.get('rsi_14', 50.0)),
                    'fib_zone': int(movement_15m.get('fib_zone_current', 0)),
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }, on_conflict='ticker').execute()
                log_info(MODULE, f"🔥 ALTA PRIORIDAD EN COLA: {ticker} (Score={buying_force_info['score']}, Entrada={entry_1h_info.get('route')} en {entry_1h_info.get('support_level')})")
            except Exception as q_err:
                log_warning(MODULE, f"Error asignando alta prioridad en cola para {ticker}: {q_err}")

        # 8. SAVE TO DB
        from app.analysis.stocks_indicators import upsert_technical_score
        is_acceptable = t01_confirmed and t02_confirmed and candle_4h_green
        
        from app.core.market_hours import get_lima_now
        current_time_str = get_lima_now().strftime("%H:%M")
        ind_15m["last_scan_time"] = current_time_str

        # Inyectar ambos en ind_15m para señales_json
        ind_15m["movement_15m"] = movement_15m["movement_type"]
        ind_15m["fib_zone_15m"] = movement_15m["fib_zone_current"]
        ind_15m["smart_limit_long_15m"] = limit_long_15m.get("limit_price")
        ind_15m["smart_limit_short_15m"] = limit_short_15m.get("limit_price")

        # ── 11. APEX SCORE — Probabilidad de subida ──
        # Sync positions with state machine for accurate logic
        all_pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
        sm.sync_from_positions(ticker, all_pos_res.data or [], is_stock=True)
        sm.cleanup_zombie_states(ticker, all_pos_res.data or [])

        snap_for_sm = {
            'price': current_price,
            'adx': ind_15m.get('adx', 25),
            'mtf_score': base_score / 100,
            'fibonacci_zone': movement_15m['fib_zone_current'],
            'sar_trend_15m': 1 if (ind_15m.get("last_pinescript_signal") == "Buy") else 0,
            'sar_trend_4h': 1 if (ind_4h.get("last_pinescript_signal") == "Buy") else 0
        }

        apex_result = None
        try:
            from app.stocks.apex_score import calculate_apex_score_v2
            from app.stocks.stocks_adaptive_tp import fetch_macro_data

            # Garantizar que sb esté disponible para fetch_macro_data
            if 'sb' not in locals(): sb = get_supabase()
            macro_data = await fetch_macro_data(sb)
            fund_cache = {
                'piotroski_score': ind_15m.get('piotroski_score', 4),
                'margin_of_safety': ind_15m.get('margin_of_safety', 0),
                'altman_zone': fundamental_res.get('components', {}).get('altman', {}).get('zone', 'grey') if fundamental_res.get('components') else 'grey',
                'fundamental_score': ind_15m.get('fundamental_score', 50),
                'analyst_rating': a_rating or 5,
                'valuation_status': fundamental_res.get('valuation_status', 'fairly_valued'),
                'days_to_earnings': f_data.get('days_to_earnings', 30) if f_data else 30,
                'short_interest_pct': f_data.get('short_interest_pct', 5) if f_data else 5,
                
                # Nuevas métricas v2.0
                'peg_ratio':           fundamental_res.get('peg_ratio', 0),
                'pe_ratio':            fundamental_res.get('pe_ratio', 0),
                'forward_pe':          fundamental_res.get('forward_pe', 0),
                'free_cash_flow':      fundamental_res.get('free_cash_flow', 0),
                'market_cap':          float(fundamental_res.get('market_cap') or (f_data.get('market_cap_mln', 1000) * 1e6) if f_data else 1e9),
                'eps_growth_pct':      fundamental_res.get('eps_growth_qoq', 0),
                'revenue_growth_yoy':  ind_15m.get('revenue_growth_yoy', 0),
                'revenue_growth_qoq':  fundamental_res.get('revenue_growth_qoq', 0),
                'fcf_growth_pct':      fundamental_res.get('fcf_growth_pct', 0),
                'short_percent_float': fundamental_res.get('short_percent_float', 5),
            }
            apex_result = calculate_apex_score_v2(
                ticker=ticker,
                snap={**ind_15m, **snap_for_sm, 'price': current_price},
                fundamental_cache=fund_cache,
                macro=macro_data,
                df_5m=df_5m, df_15m=df_15m,
                df_4h=df_4h, df_daily=df_1d,
                ia_score=ia_ia,
            )
        except Exception as apex_e:
            log_warning(MODULE, f"APEX skip {ticker}: {apex_e}")

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
                'fibonacci_zone': int(zone),
                'atr': float(atr),
                'upper_1': round(ema20 + (atr * multipliers[0]), 4),
                'upper_2': round(ema20 + (atr * multipliers[1]), 4),
                'upper_3': round(ema20 + (atr * multipliers[2]), 4),
                'upper_4': round(ema20 + (atr * multipliers[3]), 4),
                'upper_5': round(ema20 + (atr * multipliers[4]), 4),
                'upper_6': round(ema20 + (atr * multipliers[5]), 4),
                'lower_1': round(ema20 - (atr * multipliers[0]), 4),
                'lower_2': round(ema20 - (atr * multipliers[1]), 4),
                'lower_3': round(ema20 - (atr * multipliers[2]), 4),
                'lower_4': round(ema20 - (atr * multipliers[3]), 4),
                'lower_5': round(ema20 - (atr * multipliers[4]), 4),
                'lower_6': round(ema20 - (atr * multipliers[5]), 4),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'pinescript_signal': str(ps_signal_4h) if ps_signal_4h else None,
                'apex_4h': apex_result['apex_score_4h'] if apex_result else None,
                'apex_1d': apex_result['apex_score_1d'] if apex_result else None,
                'apex_signal': apex_result['signal'] if apex_result else None,
                'apex_conf': apex_result['confidence'] if apex_result else None,
                
                # Nuevas columnas v2.0
                'trade_score':  apex_result.get('trade_score') if apex_result else None,
                'xg_score':     apex_result.get('xg_score') if apex_result else None,
                'timing_score': apex_result.get('timing_score') if apex_result else None,
                'etv':          apex_result.get('etv') if apex_result else None,
            }

            try:
                sb.table('market_snapshot').upsert(snap_data, on_conflict='symbol').execute()
            except Exception as snap_upsert_e:
                log_warning(MODULE, f"Error upserting snapshot for {ticker}: {snap_upsert_e}")
        except Exception as snap_e:
            log_warning(MODULE, f"Error preparing snapshot for {ticker}: {snap_e}")

        ind_15m["movement_1d"] = movement_1d["movement_type"]
        ind_15m["fib_zone_1d"] = movement_1d["fib_zone_current"]
        ind_15m["smart_limit_long_1d"] = limit_long_1d.get("limit_price")
        ind_15m["smart_limit_short_1d"] = limit_short_1d.get("limit_price")

        ind_15m["t01_confirmed"] = t01_confirmed
        ind_15m["t02_confirmed"] = t02_confirmed
        ind_15m["t03_confirmed"] = bool(candle_4h_green)
        ind_15m["t04_confirmed"] = (rsi_val is not None and 40 <= rsi_val <= 70)
        
        # ── DETECCIÓN DE EXPANSIÓN BOLLINGER (Integrada) ──
        bb_expanding = bool(ind_15m.get("bb_expanding", False)) or bool(ind_5m.get("bb_expanding", False))
        ema_exhaustion = bool(ind_15m.get("ema_exhaustion", False))
        ind_15m["bb_expanding"] = bb_expanding
        ind_15m["ema_exhaustion"] = ema_exhaustion
        
        upsert_technical_score(ticker, ind_15m, base_score, is_acceptable, pro_score)

        # 9. RULE ENGINE
        from app.stocks.stocks_rule_engine import StocksRuleEngine
        from app.stocks.stocks_order_executor import execute_market_order, place_limit_order
        

        re = StocksRuleEngine.get_instance()

        # ── Extraer indicadores de 5m para el Rule Engine ──
        ema_3_5m  = float(ind_5m.get('ema_3') or 0)
        ema_9_5m  = float(ind_5m.get('ema_9') or 0)
        ema_20_5m = float(ind_5m.get('ema_20') or 0)
        bb_expanding_5m = bool(ind_5m.get('bb_expanding', False))
        rsi_5m = float(ind_5m.get('rsi_14') or 50.0)

        # ── Gap Up Exhaustion Detection ──
        # Si la acción abrió con un gap up significativo (>3%) y ya han
        # pasado varias horas, el momentum está probablemente agotado.
        gap_up_exhaustion = False
        try:
            now_et = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
            hours_since_open = (now_et.hour - 9) + (now_et.minute - 30) / 60.0
            if gap_pct > 3.0 and hours_since_open > 2.0:
                # Gap Up + más de 2 horas desde apertura = momentum agotado
                gap_up_exhaustion = True
                log_info(MODULE, f"⚠️ Gap Up Exhaustion: {ticker} gap={gap_pct:.1f}% hours={hours_since_open:.1f}h")
            elif gap_pct > 5.0 and hours_since_open > 1.0:
                gap_up_exhaustion = True
                log_info(MODULE, f"⚠️ Gap Up Exhaustion (Fast): {ticker} gap={gap_pct:.1f}% hours={hours_since_open:.1f}h")
        except Exception:
            pass

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
            sipv_signal=sipv_signal_15m,
            # Nuevos datos para HOT_CANDLE
            ema_3=ind_15m.get("ema_3"),
            ema_9=ind_15m.get("ema_9"),
            ema_20=ind_15m.get("ema_20"),
            bb_expanding=bb_expanding,
            ema_exhaustion=ema_exhaustion,
            ema3_cross_age=ind_15m.get("ema3_cross_ema9_age", 999),
            ema_50=ind_15m.get("ema_50")
        )
        # ── Calculate PSAR Trend Age ──
        psar_trend_age = 0
        if "psar_direction" in df_15m.columns:
            last_dir = df_15m["psar_direction"].iloc[-1]
            for i in range(len(df_15m) - 2, -1, -1):
                if df_15m["psar_direction"].iloc[i] == last_dir:
                    psar_trend_age += 1
                else:
                    break
        rule_ctx['psar_direction'] = ind_15m.get("psar_direction")
        rule_ctx['psar_trend_age'] = psar_trend_age
        
        # ── Inyectar indicadores de 5 minutos al contexto ──
        rule_ctx['ema_3_5m'] = ema_3_5m
        rule_ctx['ema_9_5m'] = ema_9_5m
        rule_ctx['ema_20_5m'] = ema_20_5m
        rule_ctx['ema_3_1d'] = float(ind_1d.get("ema_3") or 0.0)
        rule_ctx['ema_9_1d'] = float(ind_1d.get("ema_9") or 0.0)
        rule_ctx['ema_20_1d'] = float(ind_1d.get("ema_20") or 0.0)
        rule_ctx['ema_50_1d'] = float(ind_1d.get("ema_50") or 0.0)
        rule_ctx['ema_200_1d'] = float(ind_1d.get("ema_200") or 999999.0)
        
        rule_ctx['open_1d'] = open_price_today
        rule_ctx['ema_3_4h'] = float(ind_4h.get("ema_3") or 0.0)
        rule_ctx['ema_9_4h'] = float(ind_4h.get("ema_9") or 0.0)
        rule_ctx['ema_20_4h'] = float(ind_4h.get("ema_20") or 0.0)
        rule_ctx['bb_expanding_5m'] = bb_expanding_5m
        rule_ctx['rsi_5m'] = rsi_5m
        rule_ctx['gap_up_exhaustion'] = gap_up_exhaustion
        rule_ctx['gap_pct'] = gap_pct
        rule_ctx["revenue_growth_yoy"] = ind_15m.get("revenue_growth_yoy", 0)
        rule_ctx["sm_score"] = ind_15m.get("sm_score", 1.0)
        rule_ctx["piotroski_score"] = ind_15m.get("piotroski_score", 0)
        rule_ctx["sipv_signal"] = sipv_signal_15m
        
        # Inyectar métricas de Volatilidad y ADR
        rule_ctx['adr_14_pct'] = float(ind_15m.get("adr_14_pct") or 0.0)
        rule_ctx['adr_consumed_pct'] = float(ind_15m.get("adr_consumed_pct") or 0.0)
        rule_ctx['bandwidth_15m'] = float(ind_15m.get("bandwidth_15m") or 2.5)
        rule_ctx['is_dead_compression'] = bool(ind_15m.get("is_dead_compression", False))
        rule_ctx['candle_vol_15m'] = float(ind_15m.get("candle_vol_15m") or 0.0)
        rule_ctx['breakout_prob'] = int(ind_15m.get("breakout_prob", 50))
        rule_ctx['macro_1d_aligned'] = bool(ind_15m.get("macro_1d_aligned", False))
        rule_ctx['buying_force_score'] = int(ind_15m.get("buying_force_score", 0))
        rule_ctx['is_high_growth_opp'] = bool(ind_15m.get("is_high_growth_opp", False))
        rule_ctx['entry_route_1h'] = ind_15m.get("entry_route_1h")
        rule_ctx['entry_support_1h'] = ind_15m.get("entry_support_1h")
        rule_ctx['rvol_1h'] = float(ind_15m.get("rvol") or 1.0)
        
        # Use 15m PineScript Signal for rules that require it (like HOT_SENTMARKET_BUY)
        ps_signal_15m = ind_15m.get("last_pinescript_signal")
        ps_age_15m = ind_15m.get("signal_age", 999)
        if ps_signal_15m == "Buy" and ps_age_15m <= 3: # Age 0-3 for 15m (Relaxed from 1 to capture more moves)
             rule_ctx["pine_signal"] = "B" # Map 'Buy' to 'B' as requested
        elif t01_confirmed:
             rule_ctx["pine_signal"] = "Buy" # Default 4h signal
        
        ambiguity = detect_market_ambiguity(snap_for_sm)
        if ambiguity['is_ambiguous']:
            log_info(MODULE, f"Skipping {ticker}: Market ambiguous ({ambiguity['reason']})")
            sm.set_ambiguous(ticker, ambiguity['reason'])
            return None

        # 9. EVALUATE BUY RULES (Only if market is open or After-Hours is enabled)
        allow_after_hours = str(config.get("allow_after_hours", "false")).lower() == "true"
        if market_open or allow_after_hours:
            # En mercado Bearish, las compras directas se restringen estrictamente a Alpha/Super-Runners
            macro_sentiment = str(macro_data.get('sentiment', '')).lower() if 'macro_data' in locals() and macro_data else ''
            if macro_sentiment == 'bearish':
                is_runner = bool(
                    ind_15m.get('is_expansion_runner') or
                    ind_15m.get('is_intraday_alpha') or
                    'ALPHA_RUNNER' in str(ind_15m.get('group_name', '')) or
                    float(ind_15m.get('buying_force_score') or 0.0) >= 70.0
                )
                if not is_runner:
                    buying_results = []
                else:
                    buying_results = re.evaluate_all(rule_ctx, direction="buy")
            else:
                buying_results = re.evaluate_all(rule_ctx, direction="buy")
            for res in buying_results:
                if res["triggered"]:
                    # Cutoff 15:15 ET (últimas 3 velas de 15m)
                    try:
                        from datetime import time as dt_time
                        nyc_now = get_nyc_now()
                        if nyc_now.time() >= dt_time(15, 15):
                            rule_obj = re.rules.get(res["rule_code"], {})
                            grp = str(rule_obj.get("group_name", "")).lower()
                            rc = str(res["rule_code"]).lower()
                            if "hot" in grp or "scalp" in grp or "hot" in rc or "scalp" in rc or res["rule_code"] in ('Aa30_STK', 'S05', 'S06', 'S07', 'S08'):
                                log_info(MODULE, f"⛔ Cutoff 15:15 ET ({nyc_now.strftime('%H:%M')} ET): Saltando compra HOT {res['rule_code']} para {ticker}")
                                continue
                    except Exception as e_cut:
                        log_warning(MODULE, f"Error validando cutoff 15:15 ET en scheduler: {e_cut}")

                    # Check State Machine
                    max_pos = int(config.get("max_per_symbol", 4))
                    sm.sync_single_symbol(ticker, table_name="stocks_positions")
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

        # 10. EVALUATE SELL RULES (Only for open positions > 6 min)
        open_pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
        open_pos = open_pos_res.data[0] if open_pos_res.data else None
        
        if open_pos:
            entry_time_str = open_pos.get("first_buy_at") or open_pos.get("entry_time")
            age_mins = 0.0
            if entry_time_str:
                try:
                    entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                    age_mins = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
                except: pass
            
            if age_mins >= 6.0:
                # Add current PnL to context for sell rules (like PRO_CANDLE_SELL)
                current_p = float(rule_ctx.get("close", 0))
                avg_p = float(open_pos.get("avg_price") or open_pos.get("entry_price") or current_p)
                pnl_pct = ((current_p - avg_p) / avg_p * 100) if avg_p > 0 else 0.0
                rule_ctx["unrealized_pnl_pct"] = pnl_pct

                selling_results = re.evaluate_all(rule_ctx, direction="sell")
                for res in selling_results:
                    if res["triggered"]:
                        log_info(MODULE, f"🔻 SELL RULE TRIGGERED: {res['rule_code']} for {ticker} (Age: {age_mins:.1f}m)")
                        if res["order_type"] == "market":
                            execute_market_order(ticker, "sell", res["rule_code"], rule_ctx, re.rules[res["rule_code"]])
                            break
                        elif res["order_type"] == "limit":
                            place_limit_order(ticker, "sell", res["rule_code"], rule_ctx, re.rules[res["rule_code"]])
                            break
            else:
                log_debug(MODULE, f"Skipping sell rules for {ticker}: age {age_mins:.1f} < 6.0m")


        # ── 12. PERSISTENCE — technical_scores ──
        try:
            # We explicitly include APEX fields instead of merging components to avoid type conflicts
            full_indicators = {
                **ind_15m,
                "t01_confirmed": bool(ind_15m.get("ema_3", 0) > ind_15m.get("ema_9", 0)),
                "t02_confirmed": bool(ind_15m.get("ema_50", 0) > ind_15m.get("ema_200", 0)),
                "t03_confirmed": bool(ind_15m.get("change_pct", 0) > 0),
                "t04_confirmed": bool(40 <= ind_15m.get("rsi_14", 50) <= 70),
                "last_scan_time": ind_15m["last_scan_time"],
                "piotroski_score": ind_15m.get("piotroski_score", 0),
                "revenue_growth_yoy": ind_15m.get("revenue_growth_yoy", 0),
                "fundamental_score": ind_15m.get("fundamental_score", 0),
                "sm_score": ind_15m.get("sm_score", 1.0),
                "intrinsic_price": ind_15m.get("intrinsic_value", 0),
                "movement_15m": movement_15m["movement_type"],
                "fib_zone_15m": movement_15m["fib_zone_current"],
                "movement_1d": movement_1d["movement_type"] if movement_1d else "unknown",
                "fib_zone_1d": movement_1d["fib_zone_current"] if movement_1d else 0,
                "macro_1d_aligned": bool(ind_15m.get("macro_1d_aligned", False)),
                "macro_1d_reason": ind_15m.get("macro_1d_reason", ""),
                "buying_force_score": int(ind_15m.get("buying_force_score", 0)),
                "is_high_growth_opp": bool(ind_15m.get("is_high_growth_opp", False)),
                "is_high_priority": bool(ind_15m.get("is_high_priority", False)),
                "entry_route_1h": ind_15m.get("entry_route_1h"),
                "entry_support_1h": ind_15m.get("entry_support_1h"),
                "entry_reason_1h": ind_15m.get("entry_reason_1h"),
                "is_trap": bool(ind_15m.get("is_trap", False)),
                "trap_type": ind_15m.get("trap_type", "NONE"),
                "trap_reason": ind_15m.get("trap_reason", ""),
                "gap_pct": float(ind_15m.get("gap_pct", 0.0)),
                "is_sweet_spot": bool(ind_15m.get("is_sweet_spot", False)),
                "is_intraday_alpha": bool(ind_15m.get("is_intraday_alpha", False)),
                "growth_potential_pct": float(ind_15m.get("growth_potential_pct", 0.0)),
                "intraday_alpha_score": int(ind_15m.get("intraday_alpha_score", 0)),
            }
            # Append APEX data for UI
            if apex_result:
                full_indicators.update({
                    "apex_4h": apex_result['apex_score_4h'],
                    "apex_1d": apex_result['apex_score_1d'],
                    "apex_signal": apex_result['signal'],
                    "apex_conf": apex_result['confidence'],
                    "apex_edge": apex_result['edge_4h'],
                })

            upsert_technical_score(
                ticker=ticker,
                indicators=full_indicators,
                technical_score=base_score,
                mtf_confirmed=is_acceptable,
                pro_score=pro_score
            )
        except Exception as db_e:
            log_warning(MODULE, f"Persistence error for {ticker}: {db_e}")

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
            "pool_type": ind_15m.get("pool_type", "HOT"),
            "apex_4h": apex_result['apex_score_4h'] if apex_result else None,
            "apex_1d": apex_result['apex_score_1d'] if apex_result else None,
            "apex_signal": apex_result['signal'] if apex_result else None,
            "apex_conf": apex_result['confidence'] if apex_result else None,
            "apex_edge": apex_result['edge_4h'] if apex_result else None,
        }

    except Exception as e:
        log_warning(MODULE, f"Skipping {ticker}: {e}")
        return None


async def run_stocks_cycle(force=False):
    """
    Main stocks cycle — runs every 5 minutes during market hours.
    """
    cycle_start = time.time()
    from app.core.safety_manager import register_heartbeat
    register_heartbeat('stocks_scheduler')
    log_info(MODULE, "═══ STOCKS CYCLE START ═══" if not force else "═══ STOCKS CYCLE START (FORCED) ═══")

    try:
        config = get_stocks_config()
        
        # ── Cleanup low volume ──
        await cleanup_low_volume_opportunities()

        # Check kill switch
        if config.get("kill_switch_active", "false") == "true":
            log_warning(MODULE, "Kill switch ACTIVE — skipping cycle")
            return

        # Check market hours
        is_open, status_text = is_market_open()
        allow_after_hours = str(config.get("allow_after_hours", "false")).lower() == "true"
        
        # Determine if we should run anyway (e.g. if we have open positions to monitor)
        open_tickers = await get_open_positions_tickers()
        has_positions = len(open_tickers) > 0
        
        if not force and not is_open:
            if not allow_after_hours:
                log_info(MODULE, f"Cycle skipped: Market is {status_text} and After-Hours is DISABLED.")
                return
            elif not has_positions:
                log_info(MODULE, f"Cycle skipped: Market is {status_text} and no active positions to monitor.")
                return
        
        if not is_open and has_positions:
            log_info(MODULE, f"Market is {status_text}, but running cycle to monitor {len(open_tickers)} active positions (After-Hours ENABLED)")

        # ── CAPA 0: Dynamic Scanner — Refresh universe every cycle ──
        scanner_max_price = float(config.get("max_stock_price", config.get("scanner_max_price", 20.0)))
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
        base_tickers = await get_watchlist(config)

        # ── CAPA ALPHA RUNNERS EN VIVO: Inyectar líderes intradía calificados ──
        # Permite capturar joyas intradía (como $IAM con aprobación FDA) generadas durante la sesión
        # Excluye estrictamente micro-caps sin volumen o trampas de un día (como $JAGX, $CCEL)
        live_runner_tickers = []
        try:
            from app.stocks.alpha_runner_scanner import scan_top_gainers_live
            from app.core.market_hours import get_nyc_now
            from datetime import time as dt_time
            nyc_time = get_nyc_now().time()
            is_post_lunch = (nyc_time >= dt_time(12, 30))

            live_gainers = scan_top_gainers_live(limit=15)
            for g in (live_gainers or []):
                sym = g.get("ticker")
                bf = float(g.get("buying_force_5m") or 0.0)
                vol = int(g.get("volume") or 0)
                mcap = float(g.get("market_cap") or 0.0)
                rvol_val = float(g.get("rvol") or 1.0)
                chg = float(g.get("change_pct") or 0.0)
                has_news = bool(g.get("has_news", False))
                is_ema3_asc = bool(g.get("is_ema3_1h_ascending", True))

                # Filtro estricto: Volumen >= 1M, Market Cap >= $15M y Fuerza Compradora activa >= 65
                if not (sym and vol >= 1_000_000 and mcap >= 15_000_000 and bf >= 65.0):
                    continue

                # ── FILTRO HORARIO INTELIGENTE (CICLO DE VIDA DEL MOMENTUM) ──
                # Pasadas las 12:30 ET, se descartan los rallies matutinos agotados (slow bleed).
                # PERO se permiten dos excepciones críticas que renuevan el ciclo:
                # 1. Ignición Intradía Nueva: RVOL >= 3.0x, BF >= 75, Var >= +12% o Noticia relevante de impacto
                # 2. Ruptura de Consolidación Base 1H (Leg-2 Breakout): EMA3 1H ascendente, BF >= 70 y RVOL >= 2.0x
                if is_post_lunch:
                    is_midday_ignition = (rvol_val >= 3.0 and bf >= 75.0 and chg >= 12.0) or (has_news and bf >= 70.0)
                    is_leg2_breakout = (is_ema3_asc and bf >= 70.0 and rvol_val >= 2.0)
                    if not (is_midday_ignition or is_leg2_breakout):
                        log_debug(MODULE, f"⏳ Filtro Horario: {sym} descartado post 12:30 ET (Ciclo matutino agotado sin ruptura fresca).")
                        continue

                live_runner_tickers.append(sym)

            if live_runner_tickers:
                log_info(MODULE, f"⚡ Inyectando {len(live_runner_tickers)} Alpha Runners calificados al ciclo de compras: {live_runner_tickers}")
        except Exception as e_ar_inject:
            log_warning(MODULE, f"Error inyectando Alpha Runners en vivo al ciclo: {e_ar_inject}")

        # Priorizar Alpha Runners al inicio de la lista de evaluación
        tickers = list(dict.fromkeys(live_runner_tickers + (base_tickers or [])))
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

        tasks = [process_ticker(ticker, config, f_cache.get(ticker), is_pro_member=(ticker in watchlist_pro), market_open=is_open) for ticker in tickers]
        
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

        # Log cycle to system_logs (desactivado)
        #     "level": "INFO",
        #     "message": f"Stocks cycle completed: {len(results)} tickers processed",
        #     "context": str({
        #         "tickers_processed": len(results),
        #         "high_score_count": high_score_count,
        #         "spike_count": spike_count,
        #         "duration_s": duration_s,
        #     }),
        #     "created_at": datetime.now(timezone.utc).isoformat(),
        # }).execute()

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
        tasks = [process_ticker(ticker, config, is_pro_member=True, market_open=False) for ticker in tickers]
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

        # Log to system_logs (Desactivado para reducir Disk IO)
        # sb = get_supabase()
        # sb.table("system_logs").insert({
        #     "module": MODULE,
        #     "level": "INFO",
        #     "message": f"PRO cycle completed: {len(results)} tickers processed at market close",
        #     "context": str({"tickers_processed": len(results), "duration_s": duration_s}),
        #     "created_at": datetime.now(timezone.utc).isoformat(),
        # }).execute()

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


async def open_stock_position(symbol: str, side: str, size: float, price: float, reason: str, supabase):
    """Abre o actualiza una posición de Stock para EREP P2."""
    from app.stocks.stocks_order_executor import _open_or_update_position
    _open_or_update_position(symbol, price, size, "EREP")
    now = datetime.now(timezone.utc).isoformat()
    order_data = {
        "ticker": symbol,
        "group_name": "EREP",
        "rule_code": "EREP_P2",
        "order_type": "market",
        "direction": side,
        "shares": size,
        "market_price": price,
        "status": "filled",
        "filled_price": price,
        "filled_at": now,
        "created_at": now,
    }
    try:
        supabase.table("stocks_orders").insert(order_data).execute()
    except Exception as e:
        log_error("stocks_scheduler", f"Error inserting EREP order: {e}")

async def close_stock_position(symbol: str, side: str, size: float, price: float, reason: str, supabase):
    """Cierra una posición de Stock completamente para EREP."""
    res = supabase.table("stocks_positions").select("*").eq("ticker", symbol).eq("status", "open").execute()
    if not res.data:
        res = supabase.table("stocks_positions").select("*").eq("ticker", symbol).order("updated_at", desc=True).limit(1).execute()
        
    if res.data:
        pos = res.data[0]
        entry_price = float(pos.get("avg_price") or pos.get("entry_price") or price)
        shares = float(pos.get("shares_remaining") or pos.get("shares") or size)
        
        pnl_usd = round((price - entry_price) * shares, 2)
        pnl_pct = round(((price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0

    from app.stocks.stocks_order_executor import _close_all_positions
    _close_all_positions(symbol, price)
    
    if res.data:
        pos = res.data[0]
        entry_price = float(pos.get("avg_price") or pos.get("entry_price") or price)
        shares = float(pos.get("shares_remaining") or pos.get("shares") or size)
        
        now = datetime.now(timezone.utc).isoformat()
        pnl_usd = round((price - entry_price) * shares, 2)
        pnl_pct = round(((price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0
        
        journal_entry = {
            "ticker": symbol,
            "shares": int(shares),
            "entry_price": entry_price,
            "exit_price": price,
            "entry_date": pos.get("first_buy_at") or pos.get("entry_time") or now,
            "exit_date": now,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "result": "win" if pnl_usd > 0 else "loss",
            "exit_reason": reason,
            "trade_type": "EREP"
        }
        try:
            supabase.table("trades_journal").insert(journal_entry).execute()
            try:
                from app.core.capital_manager import register_realized_pnl
                register_realized_pnl('stocks', pnl_usd)
            except Exception as cap_e:
                log_error("stocks_scheduler", f"Error registering capital P&L: {cap_e}")
        except Exception as e:
            log_error("stocks_scheduler", f"Error inserting EREP journal: {e}")

async def get_df(ticker: str, timeframe: str, supabase) -> pd.DataFrame:
    """Helper to get yfinance data for a given ticker and timeframe."""
    from app.data.yfinance_provider import YFinanceProvider
    provider = YFinanceProvider()
    period = "120d" if timeframe == "4h" else "60d"
    return await provider.get_ohlcv(ticker, interval=timeframe, period=period)

async def check_sl_with_erep(
    symbol:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_4h:         pd.DataFrame,
    market_type:   str,
    supabase,
    df_5m:         pd.DataFrame = None,
    df_1h:         pd.DataFrame = None,
) -> bool:
    """
    Verifica si el precio tocó el SL y decide si cerrar normalmente o activar EREP para Stocks.

    Se llama en el ciclo de monitoreo de Stocks SOLO cuando el precio está cerca o en el SL.
    """
    from app.strategy.erep_manager import evaluate_erep_phase, execute_erep_action
    from app.core.market_hours import get_nyc_now
    
    # ── PROTECCIÓN EOD (15:50 ET): NUNCA DEJAR POSICIONES EN NEGATIVO / EREP OVERNIGHT ──
    nyc_now = get_nyc_now()
    if nyc_now.weekday() < 5 and (nyc_now.hour > 15 or (nyc_now.hour == 15 and nyc_now.minute >= 50)):
        log_warning(MODULE, f"⏰ EOD HARD-EXIT (15:50+ ET): {symbol} en zona EREP/SL liquidando a mercado para evitar riesgo nocturno.")
        await close_stock_position(symbol, 'long', float(position.get('shares', 0)), current_price, 'eod_hard_exit_1550', supabase)
        return True

    sl_price = float(position.get('stop_loss_price') or
                     position.get('sl_dynamic_price') or
                     position.get('stop_loss') or 0)
    side     = str(position.get('side', 'long'))
    is_long  = side.lower() in ('long', 'buy')

    # Stocks only support LONG spot in EREP
    if not is_long:
        return False

    if sl_price <= 0:
        return False

    # ¿Tocó el SL?
    sl_touched = current_price <= sl_price

    erep_active = bool(position.get('erep_active'))

    if not sl_touched and not erep_active:
        return False  # Normal, sin acción

    async def open_position(symbol: str, side: str, size: float, price: float, reason: str, supabase):
        await open_stock_position(symbol, side, size, price, reason, supabase)

    async def close_position(*args, **kwargs):
        price = current_price
        reason = 'erep_close'
        if len(args) >= 3:
            reason = args[2]
        if len(args) >= 2:
            price = args[1]
            
        if 'price' in kwargs:
            price = kwargs['price']
        if 'reason' in kwargs:
            reason = kwargs['reason']
        elif 'close_reason' in kwargs:
            reason = kwargs['close_reason']
            
        await close_stock_position(symbol, side, size, price, reason, supabase)

    # ── SI EREP YA ESTÁ ACTIVO ─────────────────
    if erep_active:
        action = evaluate_erep_phase(
            position, current_price,
            snap, df_15m, df_4h, market_type, df_5m,
            df_1h=df_1h
        )
        result = await execute_erep_action(
            action        = action,
            position      = position,
            current_price = current_price,
            symbol        = symbol,
            market_type   = market_type,
            supabase      = supabase,
            open_func     = open_position,
            close_func    = close_position,
        )
        return result.get('executed') == 'closed'

    # ── SL RECIÉN TOCADO ───────────────────────
    if sl_touched:
        entry = float(position.get('avg_price') or position.get('entry_price') or current_price)
        q1 = float(position.get('shares_remaining') or position.get('shares') or 0)
        
        supabase.table('stocks_positions').update({
            'erep_phase':   1,
            'erep_p1_price': entry,
            'erep_q1':      q1,
            'erep_market_type': market_type,
        }).eq('id', position['id']).execute()

        position['erep_phase']   = 1
        position['erep_p1_price'] = entry
        position['erep_q1']      = q1
        position['erep_market_type'] = market_type

        action = evaluate_erep_phase(
            position, current_price,
            snap, df_15m, df_4h, market_type, df_5m,
            df_1h=df_1h
        )

        await execute_erep_action(
            action, position, current_price,
            symbol, market_type, supabase,
            open_position, close_position
        )
        return False

    return False


async def check_stocks_erep(
    ticker:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    supabase,
    df_5m:         pd.DataFrame = None,
) -> bool:
    """
    EREP para Stocks. Solo aplica a posiciones
    LONG (compras directas sin apalancamiento).
    """
    market_type = 'stocks_spot'
    df_4h = await get_df(ticker, '4h', supabase)
    df_1h = await get_df(ticker, '1h', supabase)

    return await check_sl_with_erep(
        symbol=ticker,
        position=position,
        current_price=current_price,
        snap=snap,
        df_15m=df_15m,
        df_4h=df_4h,
        market_type=market_type,
        supabase=supabase,
        df_5m=df_5m,
        df_1h=df_1h
    )


async def run_stocks_tp_v2_cycle():
    """
    Ciclo principal de TP v2 para Stocks.
    Corre cada 5m en horario de mercado.
    """
    nyc_now = get_nyc_now()
    # Si es fin de semana, el mercado bursátil está completamente cerrado
    if nyc_now.weekday() > 4:
        return

    # Si el mercado regular de acciones está cerrado (después de 16:00 ET o antes de 09:30 ET),
    # NO evaluar salidas intradiarias por momentum o estancamiento de TP v2.
    is_open, _ = is_market_open()
    if not is_open:
        return

    sb = get_supabase()
    pos_res = sb\
        .table('stocks_positions')\
        .select('*')\
        .eq('status', 'open')\
        .execute()

    positions = pos_res.data or []

    for pos in positions:
        ticker = pos['ticker']

        try:
            snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).execute()
            snap = snap_res.data[0] if snap_res.data else {}
            price = float(snap.get('price') or snap.get('close', 0))
            if price <= 0:
                continue

            df_15m = await _get_timeframe_df_for_tp(ticker, '15m', '60d')
            if df_15m is None or (isinstance(df_15m, pd.DataFrame) and df_15m.empty):
                log_warning('TP_v2', f'{ticker}: Sin datos 15m disponibles en este ciclo, posponiendo evaluación')
                continue

            df_5m  = await _get_timeframe_df_for_tp(ticker, '5m', '5d')
            
            # ── Integración EREP para Stocks ──
            try:
                if await check_stocks_erep(ticker, pos, price, snap, df_15m, sb, df_5m):
                    continue
                
                # Recargar posición local para verificar si EREP ya está activo
                fresh_pos = sb.table('stocks_positions').select('erep_active').eq('id', pos['id']).execute()
                if fresh_pos.data and fresh_pos.data[0].get('erep_active'):
                    # Si EREP ya está activo, saltear el resto del ciclo TP v2 normal (EREP gestiona sus propias salidas)
                    continue
            except Exception as erep_err:
                log_warning('EREP_SCHEDULER', f"Error checking EREP for {ticker}: {erep_err}")
            df_4h  = await _get_timeframe_df_for_tp(ticker, '4h', '120d')
            rvol   = float(snap.get('rvol', 1.0))
            sar_15m = int(snap.get('sar_trend_15m', 1))

            # ── Protección anti-gap overnight ──
            entry   = float(pos.get('avg_price', 0))
            gain    = (price - entry) / entry * 100 \
                      if entry > 0 else 0
            ag = check_overnight_protection(
                pos, price, gain
            )
            if ag.get('apply'):
                log_info('TP_v2',
                    f'{ticker}: {ag["reason"]}'
                )
                await execute_partial_sell(
                    ticker=ticker, position=pos,
                    block='anti_gap', shares=ag['shares_to_sell'],
                    price=price, action='anti_gap', new_sl=0, new_trail_high=price,
                    supabase=sb, ib_provider=None
                )
                sb\
                    .table('stocks_positions')\
                    .update({'anti_gap_applied': True})\
                    .eq('id', pos['id'])\
                    .execute()
                continue

            # ── TP Adaptativo v2 ───────────────
            result = evaluate_stock_tp_v2(
                ticker=ticker, 
                position=pos, 
                current_price=price, 
                snap=snap,
                df_15m=df_15m, 
                df_5m=df_5m, 
                df_4h=df_4h,
                rvol=rvol, 
                sar_15m=sar_15m
            )

            action = result.get('action', 'hold')
            log_info('TP_v2',
                f'{ticker}: {action} — '
                f'{result.get("reason","")[:80]}'
            )

            # Actualizar estado en BD
            try:
                sb\
                    .table('stocks_positions')\
                    .update({
                        'sl_last_evaluated': 'now()',
                    })\
                    .eq('id', pos['id'])\
                    .execute()
            except Exception as db_e:
                log_warning('TP_v2', f'{ticker}: Error update DB {db_e}')

            # Ejecutar según acción
            shares = result.get('shares', 0)

            if action == 'close_total' and shares:
                await execute_partial_sell(
                    ticker=ticker, position=pos, block='tp_total',
                    shares=shares, price=price, action=action, new_sl=0, new_trail_high=price,
                    supabase=sb, ib_provider=None
                )

            elif action == 'close_block1' and shares:
                await execute_partial_sell(
                    ticker=ticker, position=pos, block='tp_b1',
                    shares=shares, price=price, action=action, new_sl=0, new_trail_high=price,
                    supabase=sb, ib_provider=None
                )

            elif action == 'close_block2' and shares:
                await execute_partial_sell(
                    ticker=ticker, position=pos, block='tp_b2',
                    shares=shares, price=price, action=action, new_sl=0, new_trail_high=price,
                    supabase=sb, ib_provider=None
                )

            elif action == 'close_block3' and shares:
                await execute_partial_sell(
                    ticker=ticker, position=pos, block='tp_b3',
                    shares=shares, price=price, action=action, new_sl=0, new_trail_high=price,
                    supabase=sb, ib_provider=None
                )

            elif action == 'close_blocks_2_and_3' \
                 and shares:
                await execute_partial_sell(
                    ticker=ticker, position=pos, block='tp_b2b3',
                    shares=shares, price=price, action=action, new_sl=0, new_trail_high=price,
                    supabase=sb, ib_provider=None
                )

        except Exception as e:
            log_error('TP_v2',
                f'{ticker}: {e}'
            )


async def start_stocks_scheduler(force=False):
    """
    Start the stocks scheduler using APScheduler.
    
    Schedule:
      1. Hot by Volume: every 15 minutes during market hours (09:30-16:00 ET)
      2. Inversión Pro: once at market close (16:05 ET, Mon-Fri)
      3. Market Sweep: daily at 2:00 AM ET (Mon-Fri)
    """
    from app.core.safety_manager import set_current_worker
    set_current_worker('stocks_scheduler')

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
        run_stocks_tp_v2_cycle,
        trigger=IntervalTrigger(minutes=5),
        id="stocks_tp_cycle",
        name="Stocks TP Manager (3 Blocks, 5m)",
        max_instances=1,
        replace_existing=True,
    )

    # 1c. FAST-TICK POSITION MONITOR (15 segundos): Seguimiento al minuto/15s para Regla 2d-3, 2a, 2b y TSL B.5
    async def run_fast_tick_position_monitor():
        is_open, _ = is_market_open()
        if not is_open:
            return
        try:
            from app.stocks.position_monitor import PositionMonitor
            pm = PositionMonitor()
            await pm.check_fast_tick_positions()
        except Exception as ft_err:
            log_warning(MODULE, f"Fast-tick position monitor warning: {ft_err}")

    scheduler.add_job(
        run_fast_tick_position_monitor,
        trigger=IntervalTrigger(seconds=15),
        id="stocks_fast_tick_monitor",
        name="Alpha Runner Fast-Tick Monitor (15s)",
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

    # 5. APEX SCORE: every 15 minutes during market hours
    scheduler.add_job(
        run_apex_cycle,
        trigger=IntervalTrigger(minutes=15),
        id="apex_score_cycle",
        name="APEX Score (15m probability engine)",
        max_instances=1,
        replace_existing=True,
    )

    # 6. APEX BACKTESTING: every 4 hours
    scheduler.add_job(
        run_apex_backtesting,
        trigger=IntervalTrigger(hours=4),
        id="apex_backtesting",
        name="APEX Backtesting (4H accuracy check)",
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
    asyncio.create_task(run_stocks_tp_v2_cycle())
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

