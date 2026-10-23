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
    Evalúa si una acción cumple con los 3 disparadores institucionales para CALL o PUT.
    Retorna un diccionario detallado con las métricas, puntajes y calificación.
    """
    sym = symbol.strip().upper()
    res: Dict[str, Any] = {
        "symbol": sym,
        "is_qualified": False,
        "recommended_direction": None,   # 'CALL' | 'PUT' | None
        "score": 0.0,
        "triggers_fired": [],
        "regime_info": {},
        "metrics": {},
        "reason": ""
    }

    if df_5m is None or df_5m.empty or len(df_5m) < 10:
        res["reason"] = "Datos de 5m insuficientes"
        return res

    if df_15m is None or df_15m.empty or len(df_15m) < 8:
        res["reason"] = "Datos de 15m insuficientes"
        return res

    c5 = _safe_col(df_5m, "close")
    o5 = _safe_col(df_5m, "open")
    h5 = _safe_col(df_5m, "high")
    l5 = _safe_col(df_5m, "low")
    v5 = _safe_col(df_5m, "volume")

    c15 = _safe_col(df_15m, "close")
    o15 = _safe_col(df_15m, "open")
    h15 = _safe_col(df_15m, "high")
    l15 = _safe_col(df_15m, "low")
    v15 = _safe_col(df_15m, "volume")

    cur_price = float(c5.iloc[-1])
    if cur_price <= 0:
        res["reason"] = "Precio inválido"
        return res

    # ─────────────────────────────────────────────────────────────
    # 1. EVALUACIÓN DE RÉGIMEN ESTRUCTURAL 1D
    # ─────────────────────────────────────────────────────────────
    st_reg = evaluate_structural_regime(sym, cur_price, df_1d=df_1d)
    regime_code = st_reg.get("regime_code", "NEUTRAL")
    target_wall = float(st_reg.get("target_resistance_wall") or 0.0)
    target_ceiling = float(st_reg.get("target_ceiling") or 0.0)
    target_floor = float(st_reg.get("key_levels_1d", {}).get("bb_lower") or 0.0)
    room_up_pct = float(st_reg.get("room_to_bb_upper_pct") or 0.0)
    room_wall_pct = float(st_reg.get("room_to_resistance_pct") or 0.0)

    # ─────────────────────────────────────────────────────────────
    # 2. DISPARADOR 1: DUAL-TIMEFRAME EMA3/EMA9 + VWAP + BOLLINGER
    # ─────────────────────────────────────────────────────────────
    # 15m Macro Slope
    ema3_15m_s = c15.ewm(span=3, adjust=False).mean()
    ema9_15m_s = c15.ewm(span=9, adjust=False).mean()
    cur_ema3_15m = float(ema3_15m_s.iloc[-1])
    prev_ema3_15m = float(ema3_15m_s.iloc[-2]) if len(ema3_15m_s) >= 2 else cur_ema3_15m
    cur_ema9_15m = float(ema9_15m_s.iloc[-1])
    ema3_slope_15m = ((cur_ema3_15m - prev_ema3_15m) / (prev_ema3_15m + 1e-6)) * 100.0

    # 5m Micro Crossover & Micro Trigger
    ema3_5m_s = c5.ewm(span=3, adjust=False).mean()
    ema9_5m_s = c5.ewm(span=9, adjust=False).mean()
    cur_ema3_5m = float(ema3_5m_s.iloc[-1])
    cur_ema9_5m = float(ema9_5m_s.iloc[-1])

    # VWAP en 5m
    vwap_5m_s = compute_vwap(df_5m)
    cur_vwap_5m = float(vwap_5m_s.iloc[-1]) if len(vwap_5m_s) > 0 else cur_price

    # Velas de 5m
    c5_last = float(c5.iloc[-1])
    o5_last = float(o5.iloc[-1])
    is_candle_green_5m = c5_last > o5_last
    is_candle_red_5m = c5_last < o5_last

    # Bandas de Bollinger en 15m (Apertura / Volatilidad en expansión)
    bb_15m = compute_bollinger_bands(c15, period=20, num_std=2.0)
    bw_series = (bb_15m["upper"] - bb_15m["lower"]) / (bb_15m["basis"] + 1e-6)
    bw_15m_cur = float(bw_series.iloc[-1])
    bw_15m_prev = float(bw_series.iloc[-2]) if len(bw_series) >= 2 else bw_15m_cur
    is_bb_opening = bw_15m_cur >= bw_15m_prev * 0.99

    # Verificación Disparador 1 CALL
    trig1_call = (
        (cur_ema3_5m >= cur_ema9_5m) and
        (cur_price >= cur_vwap_5m * 0.998) and
        (ema3_slope_15m >= 0.0) and
        is_candle_green_5m
    )

    # Verificación Disparador 1 PUT
    trig1_put = (
        (cur_ema3_5m <= cur_ema9_5m) and
        (cur_price <= cur_vwap_5m * 1.002) and
        (ema3_slope_15m <= 0.0) and
        is_candle_red_5m
    )

    # ─────────────────────────────────────────────────────────────
    # 3. DISPARADOR 2: CATALIZADOR INSTITUCIONAL EN VIVO
    # ─────────────────────────────────────────────────────────────
    cat_call = analyze_ticker_live_catalyst(sym, news_list=news_items)
    cat_call_score = float(cat_call.get("catalyst_score") or 0.0)
    has_call_catalyst = cat_call_score >= 60.0

    cat_put = analyze_ticker_live_bearish_catalyst(sym, news_list=news_items)
    cat_put_score = float(cat_put.get("catalyst_score") or 0.0)
    has_put_catalyst = cat_put_score >= 60.0

    # ─────────────────────────────────────────────────────────────
    # 4. DISPARADOR 3: VOLUMEN ACELERADO, RVOL & ADX EN TENDENCIA
    # ─────────────────────────────────────────────────────────────
    # ADX en 5m
    df_5m_lower = df_5m.rename(columns={col: col.lower() for col in df_5m.columns})
    adx_df = calculate_adx(df_5m_lower, period=14)
    cur_adx = float(adx_df["adx"].iloc[-1]) if "adx" in adx_df else 20.0
    cur_plus_di = float(adx_df["plus_di"].iloc[-1]) if "plus_di" in adx_df else 20.0
    cur_minus_di = float(adx_df["minus_di"].iloc[-1]) if "minus_di" in adx_df else 20.0
    is_trend_strong = cur_adx >= 22.0

    # RVOL & Ráfaga en 5m
    v5_clean = v5.dropna()
    avg_v5 = float(v5_clean.iloc[-20:].mean()) if len(v5_clean) >= 20 else 1000.0
    last_v5 = float(v5_clean.iloc[-1]) if len(v5_clean) > 0 else 0.0
    volume_burst_5m = (last_v5 >= avg_v5 * 1.40) and (last_v5 > 5000)

    # Estimación de RVOL diario acumulado
    cum_vol = float(v5_clean.sum())
    rvol_est = round(max(1.0, cum_vol / max(1.0, avg_v5 * len(v5_clean))), 2)

    trig3_call = (is_trend_strong and cur_plus_di > cur_minus_di) or (rvol_est >= 1.8) or volume_burst_5m
    trig3_put = (is_trend_strong and cur_minus_di > cur_plus_di) or (rvol_est >= 1.8) or volume_burst_5m

    # ─────────────────────────────────────────────────────────────
    # 5. PUNTUACIÓN Y CLASIFICACIÓN (CALL vs PUT)
    # ─────────────────────────────────────────────────────────────
    # Puntuación CALL
    score_call = 0.0
    if regime_code == "BULL_TREND_EXPANSION":
        score_call += 35.0
    elif regime_code == "COUNTER_TREND_BOUNCE" and room_wall_pct >= 4.0:
        score_call += 25.0
    elif not st_reg.get("is_deep_bear_excluded"):
        score_call += 15.0

    if trig1_call:
        score_call += 25.0
    if has_call_catalyst:
        score_call += 20.0
    if trig3_call:
        score_call += 20.0
    if room_up_pct >= 4.0 or room_wall_pct >= 4.0:
        score_call += 15.0

    # Puntuación PUT
    score_put = 0.0
    if regime_code == "DEEP_BEAR_WINTER" or "BEAR" in regime_code:
        score_put += 35.0
    elif regime_code == "COUNTER_TREND_BOUNCE" and abs(room_wall_pct) <= 1.5:
        score_put += 30.0  # Rechazo en el muro de EMA20
    else:
        score_put += 15.0

    if trig1_put:
        score_put += 25.0
    if has_put_catalyst:
        score_put += 20.0
    if trig3_put:
        score_put += 20.0
    room_floor_pct = ((cur_price - target_floor) / cur_price * 100.0) if target_floor > 0 else 0.0
    if room_floor_pct >= 4.0:
        score_put += 15.0

    # Decisiones finales
    score_call = round(min(100.0, score_call), 1)
    score_put = round(min(100.0, score_put), 1)

    triggers_active = []
    if score_call >= 65.0 and score_call > score_put and not st_reg.get("is_deep_bear_excluded"):
        if trig1_call:
            triggers_active.append("TRIG_EMA_DUAL_TF")
        if has_call_catalyst:
            triggers_active.append("TRIG_LIVE_CATALYST")
        if trig3_call:
            triggers_active.append("TRIG_VOLUME_ADX_BURST")

        res.update({
            "is_qualified": True,
            "recommended_direction": "CALL",
            "score": score_call,
            "triggers_fired": triggers_active,
            "regime_info": st_reg,
            "metrics": {
                "price": cur_price,
                "adx": round(cur_adx, 1),
                "plus_di": round(cur_plus_di, 1),
                "minus_di": round(cur_minus_di, 1),
                "rvol": rvol_est,
                "target_resistance_wall": target_wall,
                "target_ceiling": target_ceiling,
                "room_to_resistance_pct": room_wall_pct,
                "room_to_bb_upper_pct": room_up_pct,
            },
            "reason": f"CALL calificado ({score_call} pts): Régimen {regime_code}, Disparadores: {', '.join(triggers_active)}"
        })
        return res

    elif score_put >= 65.0 and score_put > score_call:
        if trig1_put:
            triggers_active.append("TRIG_EMA_DUAL_TF")
        if has_put_catalyst:
            triggers_active.append("TRIG_LIVE_CATALYST")
        if trig3_put:
            triggers_active.append("TRIG_VOLUME_ADX_BURST")

        res.update({
            "is_qualified": True,
            "recommended_direction": "PUT",
            "score": score_put,
            "triggers_fired": triggers_active,
            "regime_info": st_reg,
            "metrics": {
                "price": cur_price,
                "adx": round(cur_adx, 1),
                "plus_di": round(cur_plus_di, 1),
                "minus_di": round(cur_minus_di, 1),
                "rvol": rvol_est,
                "target_support_floor": target_floor,
                "room_to_support_pct": round(room_floor_pct, 2),
            },
            "reason": f"PUT calificado ({score_put} pts): Régimen {regime_code}, Disparadores: {', '.join(triggers_active)}"
        })
        return res

    res["reason"] = f"Puntuación insuficiente (CALL: {score_call}, PUT: {score_put} < 65.0)"
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
    sb = supabase or get_supabase()
    provider = YFinanceProvider()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    today_date = now_dt.date()

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
            return

        strat_type = "long_call" if direction == "CALL" else "long_put"
        dir_norm = "bullish" if direction == "CALL" else "bearish"
        status = "selected" if rank == 1 else "eligible"

        entry_debit = float(best_contract.ask if best_contract.ask > 0 else best_contract.mid)
        mid_debit = float(best_contract.mid)
        qty = max(1, best_contract.target_total_contracts)
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

        exit_plan = {
            "initial_sl": initial_sl,
            "stop_loss_underlying": initial_sl,
            "trailing_sl_type": "OPT_GAP_SL_EMA9_15M",
            "target_ceiling": target_ceiling,
            "target_resistance_wall": target_wall,
            "target_support_floor": target_floor,
            "proximity_threshold_pct": 0.80,
            "take_profit_structural": True,
            "is_runner": True,
            "gap_type": "OPEN_GAP_UP" if direction == "CALL" else "OPEN_GAP_DOWN",
            "last_eval_at": now_iso
        }

        score_breakdown = {
            "setup_name": st_reg.get("regime_code", "MOMENTUM_RUNNER"),
            "setup_label": f"🚀 {direction} {sym} ({score} pts) | {cand.get('reason')}",
            "triggers_fired": cand.get("triggers_fired"),
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
                log_info(MODULE, f"✅ OPORTUNIDAD CARGADA: {sym} {direction} (ID: {cid}, Strike: ${best_contract.strike}, Score: {score}, Status: {status})")
                selected_options.append({"id": cid, "symbol": sym, "direction": direction, "strike": best_contract.strike, "score": score})
        except Exception as e_ins:
            log_error(MODULE, f"Error insertando candidata en opt_candidates para {sym}: {e_ins}")

    # Ejecutar carga para los Top CALLs
    for r, c in enumerate(top_calls, start=1):
        await process_selected_underlying(c, "CALL", r)

    # Ejecutar carga para los Top PUTs
    for r, p in enumerate(top_puts, start=1):
        await process_selected_underlying(p, "PUT", r)

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
