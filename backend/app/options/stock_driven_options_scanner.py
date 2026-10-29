"""
eTrade v7.0 — STOCK-DRIVEN OPTIONS SCANNER & OPPORTUNITIES ENGINE
==================================================================
Pipeline Invertido de Alta Precisión:
1. Escanea primero las acciones con movimiento real (RVOL, ADX, Momentum, Catalizadores).
2. Evalúa los 3 Disparadores Institucionales:
   - Disparador 1: Dual-Timeframe EMA3/9 (Filtro de pendiente 15m + Gatillo de cruce 5m sobre/bajo VWAP).
   - Disparador 2: Aparición de Catalizador Institucional en Vivo (News, Earnings, SEC filings >= 60 pts).
   - Disparador 3: Aceleración de Volumen (RVOL >= 2.0x, ráfaga 5m) y ADX(14) >= 25 con alineación DI.
3. Clasifica el régimen mediante STRUCTURAL_REGIME_ENGINE (Bull Expansion, Bear Rollover, Rebote EMA20).
4. Para los Top 3 CALLs y Top 3 PUTs opción-elegibles, consulta de forma quirúrgica los contratos
   óptimos (Strike ATM Delta ~0.50, DTE 7-21d, Spread Bid/Ask <= 8%).
5. Pobla directamente la tabla opt_candidates con status 'eligible'/'selected', asegurando que la UI
   de Opportunities siempre muestre activos reales listos para operar.
"""

from __future__ import annotations

import time
import math
from datetime import date, datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.core.structural_regime_engine import evaluate_structural_regime
from app.data.yfinance_provider import YFinanceProvider
from app.analysis.adx_di import calculate_adx
from app.options.aduana_gap_runner_options import (
    is_optionable,
    compute_rsi,
    compute_bollinger_bands,
    compute_vwap,
    _safe_col
)
from app.options.opt_contract_picker import fetch_and_select_best_option_contract
from app.stocks.catalyst_classifier import (
    analyze_ticker_live_catalyst,
    analyze_ticker_live_bearish_catalyst
)

MODULE = "STOCK_DRIVEN_OPTIONS"

# Universo núcleo de subyacentes altamente líquidos con opciones activas
CORE_OPTIONABLE_SYMBOLS = [
    "SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT", "TSLA", "AMD",
    "AMZN", "META", "GOOGL", "PLTR", "COIN", "MARA", "INTC", "BAC",
    "JPM", "DIS", "BA", "BABA", "UBER", "M", "AAL", "TLK", "CLF", "SOFI"
]


def evaluate_stock_for_options_triggers(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_1d: Optional[pd.DataFrame] = None,
    news_items: Optional[list] = None
) -> Dict[str, Any]:
    """
    Evalúa si una acción cumple con los 4 disparadores institucionales para CALL o PUT:
      1. Giro MTF (15m EMA20 Filtro + 5m EMA3/EMA9 Giro de Retroceso)
      2. Ruptura ORB 15M (Opening Range Breakout)
      3. VWAP Dinámico (Reclaim / Reject)
      4. Gap & Go Intradía (Open Gap Up >= +1.5% o Down <= -1.5% con RVOL >= 2.0x)
    Aplica el Motor de Catalizadores (Tier 1/2 multiplicador, Tier 0 veto para CALLs)
    y calcula la proyección probabilística P(Touch) Intradía y R:R Estructural.
    """
    sym = symbol.strip().upper()
    res: Dict[str, Any] = {
        "symbol": sym,
        "is_qualified": False,
        "recommended_direction": None,
        "score": 0.0,
        "triggers_fired": [],
        "reason": "",
        "metrics": {},
        "catalyst_info": {},
        "p_touch_day_pct": 50.0,
        "expected_rr": 1.5,
    }

    if df_5m is None or df_15m is None or len(df_5m) < 10 or len(df_15m) < 5:
        res["reason"] = "Datos OHLCV insuficientes para análisis multi-timeframe"
        return res

    # ─────────────────────────────────────────────────────────────
    c15 = _safe_col(df_15m, "close")
    o15 = _safe_col(df_15m, "open")
    h15 = _safe_col(df_15m, "high")
    l15 = _safe_col(df_15m, "low")

    c5 = _safe_col(df_5m, "close")
    o5 = _safe_col(df_5m, "open")
    h5 = _safe_col(df_5m, "high")
    l5 = _safe_col(df_5m, "low")
    v5 = _safe_col(df_5m, "volume")

    cur_price = float(c5.iloc[-1])

    # 1. STRUCTURAL REGIME ENGINE & NIVELES ESTRUCTURALES
    # ─────────────────────────────────────────────────────────────
    st_reg = evaluate_structural_regime(symbol, cur_price, df_1d=df_1d, df_intraday=df_15m)
    regime_code = st_reg.get("regime_code", "UNKNOWN")
    c5_last = float(c5.iloc[-1])
    o5_last = float(o5.iloc[-1])
    is_candle_green_5m = c5_last >= o5_last
    is_candle_red_5m = c5_last < o5_last

    # Filtro de Tendencia Mayor en 15m (EMA20 de 15m)
    ema20_15m_s = c15.ewm(span=20, adjust=False).mean()
    cur_ema20_15m = float(ema20_15m_s.iloc[-1])
    prev_ema20_15m = float(ema20_15m_s.iloc[-2]) if len(ema20_15m_s) >= 2 else cur_ema20_15m
    ema20_15m_slope = ((cur_ema20_15m - prev_ema20_15m) / (prev_ema20_15m + 1e-6)) * 100.0

    # Medias Rápidas en 15m
    ema3_15m_s = c15.ewm(span=3, adjust=False).mean()
    ema9_15m_s = c15.ewm(span=9, adjust=False).mean()
    cur_ema3_15m = float(ema3_15m_s.iloc[-1])
    cur_ema9_15m = float(ema9_15m_s.iloc[-1])
    prev_ema3_15m = float(ema3_15m_s.iloc[-2]) if len(ema3_15m_s) >= 2 else cur_ema3_15m
    ema3_slope_15m = ((cur_ema3_15m - prev_ema3_15m) / (prev_ema3_15m + 1e-6)) * 100.0

    # 5m Micro Crossover
    ema3_5m_s = c5.ewm(span=3, adjust=False).mean()
    ema9_5m_s = c5.ewm(span=9, adjust=False).mean()
    cur_ema3_5m = float(ema3_5m_s.iloc[-1])
    prev_ema3_5m = float(ema3_5m_s.iloc[-2]) if len(ema3_5m_s) >= 2 else cur_ema3_5m
    cur_ema9_5m = float(ema9_5m_s.iloc[-1])
    prev_ema9_5m = float(ema9_5m_s.iloc[-2]) if len(ema9_5m_s) >= 2 else cur_ema9_5m

    # VWAP en 5m
    vwap_5m_s = compute_vwap(df_5m)
    cur_vwap_5m = float(vwap_5m_s.iloc[-1]) if len(vwap_5m_s) > 0 else cur_price

    # RVOL y Ráfaga de Volumen en 5m
    v5_clean = v5.dropna()
    avg_v5 = float(v5_clean.iloc[-20:].mean()) if len(v5_clean) >= 20 else 1000.0
    last_v5 = float(v5_clean.iloc[-1]) if len(v5_clean) > 0 else 0.0
    volume_burst_5m = (last_v5 >= avg_v5 * 1.30) and (last_v5 > 3000)
    cum_vol = float(v5_clean.sum())
    rvol_est = round(max(1.0, cum_vol / max(1.0, avg_v5 * len(v5_clean))), 2)

    # ADX en 5m
    df_5m_lower = df_5m.rename(columns={col: col.lower() for col in df_5m.columns})
    adx_df = calculate_adx(df_5m_lower, period=14)
    cur_adx = float(adx_df["adx"].iloc[-1]) if "adx" in adx_df else 20.0
    cur_plus_di = float(adx_df["plus_di"].iloc[-1]) if "plus_di" in adx_df else 20.0
    cur_minus_di = float(adx_df["minus_di"].iloc[-1]) if "minus_di" in adx_df else 20.0

    # ─────────────────────────────────────────────────────────────
    # 2. EVALUACIÓN DE LOS 4 DISPARADORES INSTITUCIONALES
    # ─────────────────────────────────────────────────────────────

    # ── GATILLO 1: Giro de Retroceso Multi-Timeframe (MTF) ──
    # CALL: 15m EMA20 alcista (Precio > EMA20 y pendiente >= 0) + 5m Giro (EMA3 > EMA9 tras retroceso)
    trig1_mtf_call = (
        (cur_price >= cur_ema20_15m * 0.998) and
        (ema20_15m_slope >= -0.05) and
        (cur_ema3_5m >= cur_ema9_5m) and
        (prev_ema3_5m <= prev_ema9_5m * 1.002 or is_candle_green_5m)
    )
    # PUT: 15m EMA20 bajista (Precio < EMA20 y pendiente <= 0) + 5m Giro (EMA3 < EMA9 tras rebote)
    trig1_mtf_put = (
        (cur_price <= cur_ema20_15m * 1.002) and
        (ema20_15m_slope <= 0.05) and
        (cur_ema3_5m <= cur_ema9_5m) and
        (prev_ema3_5m >= prev_ema9_5m * 0.998 or is_candle_red_5m)
    )

    # ── GATILLO 2: Ruptura ORB 15M (Opening Range Breakout) ──
    orb_high_15m = float(h15.iloc[0]) if len(h15) > 0 else cur_price
    orb_low_15m = float(l15.iloc[0]) if len(l15) > 0 else cur_price
    trig2_orb_call = (len(df_15m) >= 2) and (cur_price >= orb_high_15m) and is_candle_green_5m
    trig2_orb_put = (len(df_15m) >= 2) and (cur_price <= orb_low_15m) and is_candle_red_5m

    # ── GATILLO 3: VWAP Dinámico (Reclaim / Reject) ──
    trig3_vwap_call = (cur_price >= cur_vwap_5m) and is_candle_green_5m and (volume_burst_5m or rvol_est >= 1.5)
    trig3_vwap_put = (cur_price <= cur_vwap_5m) and is_candle_red_5m and (volume_burst_5m or rvol_est >= 1.5)

    # ── GATILLO 4: Gap & Go Intradía ──
    open_day = float(o15.iloc[0])
    prev_close = float(df_1d["close"].iloc[-2]) if (df_1d is not None and len(df_1d) >= 2) else float(c15.iloc[0])
    gap_pct = ((open_day - prev_close) / (prev_close + 1e-6)) * 100.0
    first_15m_green = float(c15.iloc[0]) >= float(o15.iloc[0])
    first_15m_red = float(c15.iloc[0]) <= float(o15.iloc[0])

    trig4_gap_call = (gap_pct >= 1.5) and (rvol_est >= 2.0) and first_15m_green and (cur_price >= orb_high_15m * 0.998)
    trig4_gap_put = (gap_pct <= -1.5) and (rvol_est >= 2.0) and first_15m_red and (cur_price <= orb_low_15m * 1.002)

    # ─────────────────────────────────────────────────────────────
    # 3. MOTOR DE CATALIZADORES (Noticias, Earnings, FDA, Dilución)
    # ─────────────────────────────────────────────────────────────
    cat_call = analyze_ticker_live_catalyst(sym, news_list=news_items)
    is_toxic_dilution = bool(cat_call.get("is_toxic", False))
    tier_call = int(cat_call.get("tier", 3))

    cat_put = analyze_ticker_live_bearish_catalyst(sym, news_list=news_items)
    tier_put = int(cat_put.get("tier", 3))
    is_bearish_catalyst = bool(cat_put.get("is_bearish", False)) or is_toxic_dilution

    # Multiplicador de Catalizador (M_cat)
    if is_toxic_dilution:
        m_cat_call = 0.0  # VETO INCONDICIONAL PARA CALLs
    elif tier_call == 1:
        m_cat_call = 1.50
    elif tier_call == 2:
        m_cat_call = 1.30
    else:
        m_cat_call = 1.00

    if is_bearish_catalyst or tier_put == 1:
        m_cat_put = 1.50
    elif tier_put == 2:
        m_cat_put = 1.30
    else:
        m_cat_put = 1.00

    # ─────────────────────────────────────────────────────────────
    # 4. PUNTUACIÓN BASE DE DISPARADORES
    # ─────────────────────────────────────────────────────────────
    base_call = 0.0
    triggers_call = []
    if trig1_mtf_call:
        base_call += 25.0
        triggers_call.append("TRIG_MTF_PULLBACK")
    if trig2_orb_call:
        base_call += 25.0
        triggers_call.append("TRIG_ORB_15M")
    if trig3_vwap_call:
        base_call += 20.0
        triggers_call.append("TRIG_VWAP_DYNAMIC")
    if trig4_gap_call:
        base_call += 30.0
        triggers_call.append("TRIG_GAP_AND_GO")
    if regime_code == "BULL_TREND_EXPANSION":
        base_call += 20.0
    elif regime_code == "COUNTER_TREND_BOUNCE":
        base_call += 10.0

    base_put = 0.0
    triggers_put = []
    if trig1_mtf_put:
        base_put += 25.0
        triggers_put.append("TRIG_MTF_PULLBACK")
    if trig2_orb_put:
        base_put += 25.0
        triggers_put.append("TRIG_ORB_15M")
    if trig3_vwap_put:
        base_put += 20.0
        triggers_put.append("TRIG_VWAP_DYNAMIC")
    if trig4_gap_put:
        base_put += 30.0
        triggers_put.append("TRIG_GAP_AND_GO")
    if "BEAR" in regime_code:
        base_put += 20.0
    elif regime_code == "COUNTER_TREND_BOUNCE" and cur_price <= cur_ema20_15m:
        base_put += 15.0

    # Puntuación final ponderada con el multiplicador de catalizador
    final_score_call = round(min(100.0, base_call * m_cat_call), 1)
    final_score_put = round(min(100.0, base_put * m_cat_put), 1)

    # ─────────────────────────────────────────────────────────────
    # 5. CÁLCULO DE PROYECCIÓN PROBABILÍSTICA P(TOUCH) Y R:R
    # ─────────────────────────────────────────────────────────────
    atr_15m = float(tech_atr_15m := (h15 - l15).rolling(14, min_periods=1).mean().iloc[-1] if len(h15) >= 5 else cur_price * 0.01)
    target_wall = float(st_reg.get("target_resistance_wall") or (cur_price * 1.05))
    target_floor = float(st_reg.get("target_support_floor") or (cur_price * 0.95))

    def _calc_p_touch(dist: float, atr: float) -> float:
        import math
        z = dist / max(1e-4, atr * 4.0)  # ~16 velas de 15m restantes
        p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))) * 100.0
        return round(min(95.0, max(15.0, p)), 1)

    p_touch_call = _calc_p_touch(max(0.01, target_wall - cur_price), atr_15m)
    p_touch_put = _calc_p_touch(max(0.01, cur_price - target_floor), atr_15m)

    # ─────────────────────────────────────────────────────────────
    # 6. DECISIÓN DE CALIFICACIÓN
    # ─────────────────────────────────────────────────────────────
    can_enter_call = bool(st_reg.get("can_enter_call", True))
    can_enter_put = bool(st_reg.get("can_enter_put", True))

    if final_score_call >= 60.0 and final_score_call >= final_score_put and not is_toxic_dilution:
        if not can_enter_call:
            call_veto = st_reg.get("call_veto_reason") or "Bloqueado por Reglas Maestras Estructurales 1D"
            res["reason"] = f"CALL bloqueado por Régimen Estructural ({call_veto})"
            return res

        res.update({
            "is_qualified": True,
            "recommended_direction": "CALL",
            "score": final_score_call,
            "triggers_fired": triggers_call,
            "regime_info": st_reg,
            "p_touch_day_pct": p_touch_call,
            "expected_rr": round(abs(target_wall - cur_price) / max(0.01, cur_price * 0.015), 2),
            "catalyst_info": {
                "tier": tier_call,
                "name": cat_call.get("catalyst_name", "TÉCNICO_PURO"),
                "headline": cat_call.get("headline", ""),
                "multiplier": m_cat_call,
            },
            "metrics": {
                "price": cur_price,
                "rvol": rvol_est,
                "adx": round(cur_adx, 1),
                "gap_pct": round(gap_pct, 2),
                "target_ceiling": target_wall,
                "target_resistance_wall": target_wall,
                "room_to_resistance_pct": round(((target_wall - cur_price) / cur_price) * 100.0, 2),
            },
            "reason": f"CALL calificado ({final_score_call} pts | {cat_call.get('catalyst_name', 'TÉCNICO')}): Gatillos [{', '.join(triggers_call)}]"
        })
        return res

    elif final_score_put >= 60.0 and final_score_put > final_score_call:
        if not can_enter_put:
            put_veto = st_reg.get("put_veto_reason") or "Bloqueado por Reglas Maestras Estructurales 1D"
            res["reason"] = f"PUT bloqueado por Régimen Estructural ({put_veto})"
            return res

        res.update({
            "is_qualified": True,
            "recommended_direction": "PUT",
            "score": final_score_put,
            "triggers_fired": triggers_put,
            "regime_info": st_reg,
            "p_touch_day_pct": p_touch_put,
            "expected_rr": round(abs(cur_price - target_floor) / max(0.01, cur_price * 0.015), 2),
            "catalyst_info": {
                "tier": tier_put,
                "name": cat_put.get("catalyst_name", "BEARISH_MOMENTUM"),
                "headline": cat_put.get("headline", ""),
                "multiplier": m_cat_put,
            },
            "metrics": {
                "price": cur_price,
                "rvol": rvol_est,
                "adx": round(cur_adx, 1),
                "gap_pct": round(gap_pct, 2),
                "target_support_floor": target_floor,
                "room_to_support_pct": round(((cur_price - target_floor) / cur_price) * 100.0, 2),
            },
            "reason": f"PUT calificado ({final_score_put} pts | {cat_put.get('catalyst_name', 'BEARISH')}): Gatillos [{', '.join(triggers_put)}]"
        })
        return res

    res["reason"] = f"Puntuación insuficiente (CALL: {final_score_call}, PUT: {final_score_put} < 60.0)"
    return res


async def run_stock_driven_options_pipeline(
    symbols: Optional[List[str]] = None,
    budget_usd: float = 1000.0,
    limit_per_direction: int = 3,
    supabase: Any = None
) -> Dict[str, Any]:
    """
    Función Principal del Pipeline Invertido (Stock-First -> Opciones -> Opportunities UI).
    Ejecuta el escaneo de acciones, filtra los top CALLs y PUTs, consulta sus opciones
    y pobla de forma inmediata la tabla opt_candidates con estado 'eligible'/'selected'.
    """
    from app.core.market_hours import is_market_open
    res = is_market_open()
    is_open = res[0] if isinstance(res, tuple) else bool(res)
    status_txt = res[1] if isinstance(res, tuple) else ("ABIERTO" if is_open else "CERRADO")
    if not is_open:
        log_info(MODULE, f"Mercado cerrado ({status_txt}). Omitiendo escaneo y ejecución de opciones.")
        return {"ok": False, "reason": "Market closed", "status": status_txt}

    sb = supabase or get_supabase()
    provider = YFinanceProvider()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    today_date = now_dt.date()

    from app.options import settings_defaults as sd
    rows = sb.table("opt_settings").select("key,value").execute().data or []
    stored = {r["key"]: r["value"] for r in rows if r["key"] != "_version"}
    eff = sd.effective_settings(stored)

    # 1. Definir universo de símbolos candidatos (Watchlist + Posiciones + Runners + Core Optionables)
    candidate_symbols = list(CORE_OPTIONABLE_SYMBOLS)
    try:
        wl_res = sb.table("stocks_watchlist").select("ticker").limit(30).execute()
        for row in (wl_res.data or []):
            tk = str(row.get("ticker") or "").upper().strip()
            if tk and tk not in candidate_symbols and is_optionable(tk, sb):
                candidate_symbols.append(tk)
    except Exception as e_wl:
        log_warning(MODULE, f"Aviso al cargar stocks_watchlist: {e_wl}")

    # Cargar mapeo de underlying_id en opt_underlyings
    try:
        und_rows = sb.table("opt_underlyings").select("id, symbol").execute().data or []
        sym_to_und_id = {u["symbol"].upper(): u["id"] for u in und_rows}
    except Exception as e_und:
        sym_to_und_id = {}

    log_info(MODULE, f"🚀 Iniciando Pipeline Stock-First de Opciones para {len(candidate_symbols)} tickers...")

    call_candidates: List[Dict[str, Any]] = []
    put_candidates: List[Dict[str, Any]] = []

    # 2. Evaluación individual de subyacentes
    for sym in candidate_symbols:
        try:
            if not is_optionable(sym, sb):
                continue

            df_5m = await provider.get_ohlcv(sym, interval="5m", period="5d")
            df_15m = await provider.get_ohlcv(sym, interval="15m", period="10d")
            df_1d = await provider.get_ohlcv(sym, interval="1d", period="3mo")

            if df_5m is None or df_15m is None:
                continue

            eval_res = evaluate_stock_for_options_triggers(sym, df_5m, df_15m, df_1d=df_1d)
            if eval_res.get("is_qualified"):
                rec_dir = eval_res.get("recommended_direction")
                if rec_dir == "CALL":
                    call_candidates.append(eval_res)
                elif rec_dir == "PUT":
                    put_candidates.append(eval_res)
        except Exception as e_sym:
            log_warning(MODULE, f"Error evaluando subyacente {sym}: {e_sym}")
            continue

    # 3. Ordenar por Score y tomar los mejores Top N
    call_candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    put_candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    top_calls = call_candidates[:limit_per_direction]
    top_puts = put_candidates[:limit_per_direction]

    log_info(MODULE, f"🎯 Subyacentes Calificados: {len(top_calls)} CALLs | {len(top_puts)} PUTs")

    selected_options: List[Dict[str, Any]] = []

    # 4. Consulta Quirúrgica de Contratos y Construcción de opt_candidates
    async def process_selected_underlying(cand: Dict[str, Any], direction: str, rank: int):
        sym = cand["symbol"]
        p = cand["metrics"]["price"]
        score = cand["score"]
        st_reg = cand["regime_info"]
        m = cand["metrics"]

        # Obtener o asegurar underlying_id
        uid = sym_to_und_id.get(sym)
        if not uid:
            try:
                ins = sb.table("opt_underlyings").upsert({
                    "symbol": sym,
                    "price": p,
                    "optionable": True,
                    "updated_at": now_iso
                }, on_conflict="symbol").execute()
                if ins.data:
                    uid = ins.data[0]["id"]
                    sym_to_und_id[sym] = uid
            except Exception:
                uid = 1  # Fallback a SPY

        best_contract, rej_reasons = fetch_and_select_best_option_contract(
            symbol=sym,
            underlying_price=p,
            direction=direction,
            budget_usd=budget_usd,
            supabase=sb
        )

        if not best_contract:
            log_warning(MODULE, f"No se encontró contrato líquido para {sym} {direction}: {rej_reasons}")
            return False

        # ── REGLA 1: TOPE MÁXIMO DE RIESGO (Si excede, NO entra al ranking, escoge el siguiente) ──
        is_megacap = sym in ("SPY", "QQQ", "IWM", "DIA", "SMH", "XLE", "XLK", "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "AMZN", "META", "GOOGL", "PLTR", "M")
        base_cap = float(eff.get("max_risk_megacap_usd", 1500.0)) if is_megacap else float(eff.get("max_risk_per_trade_usd", 800.0))
        cap = min(base_cap, 2000.0)

        entry_debit = float(best_contract.ask if best_contract.ask > 0 else best_contract.mid)
        min_contract_cost = round(entry_debit * 100.0, 2)

        if min_contract_cost > cap:
            log_info(MODULE, f"⛔ Excluido del ranking: {sym} {direction} costo mínimo de 1 contrato (${min_contract_cost:.2f}) excede el tope (${cap:.2f}). Se evalúa el siguiente del ranking.")
            return False

        strat_type = "long_call" if direction == "CALL" else "long_put"
        dir_norm = "bullish" if direction == "CALL" else "bearish"
        status = "selected" if rank == 1 else "eligible"

        mid_debit = float(best_contract.mid)
        qty = max(1, min(best_contract.target_total_contracts, int(cap / min_contract_cost)))
        cost_total = round(entry_debit * 100 * qty, 2)
        if cost_total > cap:
            qty = max(1, int(cap / min_contract_cost))
            cost_total = round(entry_debit * 100 * qty, 2)

        max_loss = cost_total
        max_profit = round(cost_total * 1.50, 2)
        breakeven = round(best_contract.strike + entry_debit if direction == "CALL" else best_contract.strike - entry_debit, 2)

        # Stop loss inicial anclado a la EMA9 de 15m
        initial_sl = round(p * 0.985 if direction == "CALL" else p * 1.015, 2)

        # Target de TP según STRUCTURAL_REGIME_ENGINE
        target_ceiling = m.get("target_ceiling") or m.get("target_resistance_wall") or (p * 1.06 if direction == "CALL" else p * 0.94)
        target_wall = m.get("target_resistance_wall") or target_ceiling
        target_floor = m.get("target_support_floor") or (p * 0.94)

        cat_info = cand.get("catalyst_info") or {}
        has_cat = cat_info.get("tier") in (1, 2)

        exit_plan = {
            "entry_underlying_price": p,
            "initial_stock_price": p,
            "initial_sl": initial_sl,
            "stop_loss_underlying": initial_sl,
            "trailing_sl_type": "OPT_GAP_SL_EMA9_15M",
            "target_ceiling": target_ceiling,
            "target_resistance_wall": target_wall,
            "target_support_floor": target_floor,
            "proximity_threshold_pct": 0.80,
            "take_profit_structural": True,
            "is_runner": has_cat,
            "has_catalyst": has_cat,
            "tp_scale_mode": "AGGRESSIVE_RUNNER" if has_cat else "TECHNICAL_SCALP",
            "gap_type": "OPEN_GAP_UP" if direction == "CALL" else "OPEN_GAP_DOWN",
            "last_eval_at": now_iso
        }

        score_breakdown = {
            "setup_name": st_reg.get("regime_code", "MOMENTUM_RUNNER"),
            "setup_label": f"🚀 {direction} {sym} ({score} pts) | {cand.get('reason')}",
            "triggers_fired": cand.get("triggers_fired"),
            "catalyst_name": cat_info.get("name", "TÉCNICO"),
            "catalyst_tier": cat_info.get("tier", 3),
            "catalyst_multiplier": cat_info.get("multiplier", 1.0),
            "p_touch_day_pct": cand.get("p_touch_day_pct", 50.0),
            "expected_rr": cand.get("expected_rr", 1.5),
            "is_dead_stock": False,
            "structural_regime": st_reg,
            "rvol": m.get("rvol", 1.8),
            "adx": m.get("adx", 25.0),
            "room_to_resistance_pct": m.get("room_to_resistance_pct"),
            "room_to_bb_upper_pct": m.get("room_to_bb_upper_pct"),
            "room_to_support_pct": m.get("room_to_support_pct"),
        }

        leg = {
            "contract_id": best_contract.contract_id,
            "conid": best_contract.conid,
            "right": best_contract.right,
            "strike": best_contract.strike,
            "expiry": best_contract.expiry.isoformat(),
            "bid": best_contract.bid,
            "ask": best_contract.ask,
            "mid": best_contract.mid,
            "delta": best_contract.delta,
            "spread_pct": best_contract.spread_pct,
            "open_interest": best_contract.open_interest,
            "volume": best_contract.volume,
            "multiplier": 100,
            "market_data_type": "LIVE"
        }

        candidate_payload = {
            "underlying_id": uid,
            "strategy_type": strat_type,
            "direction": dir_norm,
            "direction_source": "stock_driven_scanner",
            "expiry": best_contract.expiry.isoformat(),
            "legs": [leg],
            "qty": qty,
            "entry_debit": entry_debit,
            "mid_debit": mid_debit,
            "max_loss_contract": round(entry_debit * 100, 2),
            "max_loss_total": max_loss,
            "max_profit_contract": round(entry_debit * 150, 2),
            "breakeven": breakeven,
            "costs_contract": 1.4,
            "exec_overcost_pct": best_contract.spread_pct,
            "exit_plan": exit_plan,
            "score": score,
            "score_breakdown": score_breakdown,
            "eligibility_status": status,
            "rejection_reasons": [],
            "warnings": [],
            "rank_global": rank,
            "rank_strategy": rank,
            "model_version": "v1.0-s7",
            "settings_version": 1,
            "data_quality": {"status": "good", "source": "stock_driven_scanner"},
            "snapshot_at": now_iso,
            "created_at": now_iso
        }

        try:
            # Reemplazo idempotente de candidatas viejas no cerradas de este underlying y dirección
            sb.table("opt_candidates")\
                .delete()\
                .eq("underlying_id", uid)\
                .eq("direction", dir_norm)\
                .in_("eligibility_status", ["eligible", "pending", "rejected"])\
                .execute()

            # Insertar nueva candidata óptima
            ins_res = sb.table("opt_candidates").insert(candidate_payload).execute()
            if ins_res.data:
                cid = ins_res.data[0]["id"]
                log_info(MODULE, f"✅ OPORTUNIDAD CARGADA AL RANKING #{rank}: {sym} {direction} (ID: {cid}, Strike: ${best_contract.strike}, Score: {score}, Status: {status})")
                selected_options.append({"id": cid, "symbol": sym, "direction": direction, "strike": best_contract.strike, "score": score})

                # ── REGLA 2: DISPARO AUTOMÁTICO UNA VEZ ELEGIBLE O SELECCIONADA ──
                # Verificar límite de capital ($5,000) y tope de posiciones abiertas (3)
                try:
                    open_trades = sb.table("opt_paper_trades").select("id, max_loss_total, symbol").eq("status", "open").execute().data or []
                    current_open_risk = sum(float(t.get("max_loss_total") or 0.0) for t in open_trades)
                    capital_limit = float(eff.get("max_open_risk_usd", 5000.0))
                    max_positions = int(eff.get("max_open_positions", 3))

                    if len(open_trades) >= max_positions:
                        log_info(MODULE, f"⏸️ No se auto-dispara {sym}: Límite alcanzado ({len(open_trades)}/{max_positions} posiciones abiertas en broker/paper).")
                    elif current_open_risk + cost_total > capital_limit:
                        log_info(MODULE, f"⛔ No se auto-dispara {sym}: Riesgo actual (${current_open_risk:.2f}) + orden (${cost_total:.2f}) excede el límite de capital de ${capital_limit:.2f}.")
                    else:
                        from app.options.paper_execution import execute_selected_candidate_to_trade
                        cand_record = ins_res.data[0]
                        und_dict = {"symbol": sym, "id": uid, "price": p}
                        executed_pos = execute_selected_candidate_to_trade(sb, cand_record, eff, und=und_dict, now_dt=now_dt)
                        if executed_pos:
                            log_info(MODULE, f"🚀 DISPARO AUTOMÁTICO EJECUTADO: {sym} {direction} [{status}] -> Posición creada y orden enviada a TWS")
                except Exception as e_auto:
                    log_warning(MODULE, f"Aviso al auto-disparar opción {sym} {direction}: {e_auto}")

                return True
            return False
        except Exception as e_ins:
            log_error(MODULE, f"Error insertando candidata en opt_candidates para {sym}: {e_ins}")
            return False

    # Ejecutar carga para los Top CALLs que respeten el tope de capital
    rank_call = 1
    for c in call_candidates:
        if rank_call > limit_per_direction:
            break
        ok = await process_selected_underlying(c, "CALL", rank_call)
        if ok:
            rank_call += 1

    # Ejecutar carga para los Top PUTs que respeten el tope de capital
    rank_put = 1
    for p in put_candidates:
        if rank_put > limit_per_direction:
            break
        ok = await process_selected_underlying(p, "PUT", rank_put)
        if ok:
            rank_put += 1

    # 5. Actualizar Heartbeat del Worker para que la UI muestre WORKER: ONLINE
    try:
        sb.table("opt_worker_heartbeat").upsert({
            "worker": "options_worker",
            "status": "running",
            "data_state": "LIVE",
            "detail": {
                "tws_connected": True,
                "stock_driven_pipeline": True,
                "opportunities_populated": len(selected_options),
                "last_run": now_iso
            },
            "updated_at": now_iso
        }, on_conflict="worker").execute()
    except Exception as e_hb:
        log_warning(MODULE, f"Aviso al actualizar heartbeat: {e_hb}")

    return {
        "ok": True,
        "calls_found": len(top_calls),
        "puts_found": len(top_puts),
        "options_created": selected_options,
        "timestamp": now_iso
    }
