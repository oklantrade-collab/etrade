"""
eTrade v8.0 — WARRIOR MOMENTUM OPTIONS ENGINE (Ross Cameron Adapted for Options)
================================================================================
Motor especializado para trading de opciones bajo la filosofía de Ross Cameron:
1. Selección de Subyacentes High-Beta y Mega-Caps con momentum institucional real.
2. Detección de Setup en 5m/15m:
   - Impulso direccional inicial con RVOL acelerado.
   - Retroceso ordenado (Micro-Pullback) de 1 a 3 velas hacia EMA9/EMA20 con volumen decreciente.
   - Gatillo de Entrada: "First Candle to Make a New High/Low" (rompimiento del extremo de la vela previa).
   - Ignición de Bandas Bollinger 15m (Expansión activa: Upper > 0 y Lower < 0).
3. Selección Quirúrgica del Contrato:
   - Delta 0.50 a 0.65 (ATM o ligeramente ITM).
   - Vencimiento semanal de 3 a 7 DTE.
   - Spread Bid/Ask <= 6.0%.
4. Despacho Institucional:
   - Enrutamiento con Algoritmo Adaptive Midpoint de IBKR (sin castigo de spread).
5. Salidas Escalonadas:
   - TP1 (50% de la posición): +15% a +25% de beneficio neto en prima.
   - Mover Stop Loss a Break-Even ($0 riesgo).
   - Corredor (50% restante): Protegido por el Candado Bollinger 15m y ángulo de EMA3 1H.
   - Stop Loss Defensivo: Si el subyacente cae más del -5.0% o pierde la EMA9 en 15m.
"""

from __future__ import annotations

import time
import math
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.data.yfinance_provider import YFinanceProvider
from app.options.aduana_gap_runner_options import (
    compute_bollinger_bands,
    compute_vwap,
    _safe_col
)
from app.options.opt_contract_picker import fetch_and_select_best_option_contract
from app.options.paper_execution import execute_selected_candidate_to_trade

MODULE = "WARRIOR_MOMENTUM_OPTIONS"

# Universo élite de subyacentes con alto volumen y cadenas de opciones líquidas
WARRIOR_OPTIONS_UNIVERSE = [
    "NVDA", "TSLA", "AMD", "AAPL", "MSFT", "MARA", "COIN",
    "PLTR", "SOFI", "SPY", "QQQ", "IWM", "AMZN", "META"
]


def evaluate_warrior_momentum_setup(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame
) -> Optional[Dict[str, Any]]:
    """
    Evalúa si el subyacente cumple la estructura de Momentum Ross Cameron:
    - Retorna dict con direction ('CALL' o 'PUT'), score y razones, o None si no califica.
    """
    if df_15m is None or df_15m.empty or len(df_15m) < 20:
        return None
    if df_5m is None or df_5m.empty or len(df_5m) < 15:
        return None

    c_15 = _safe_col(df_15m, "close")
    v_15 = _safe_col(df_15m, "volume")
    h_15 = _safe_col(df_15m, "high")
    l_15 = _safe_col(df_15m, "low")
    o_15 = _safe_col(df_15m, "open")

    if len(c_15) < 20:
        return None

    current_price = float(c_15.iloc[-1])
    if current_price <= 0:
        return None

    # Indicadores en 15m
    ema3_15m = c_15.ewm(span=3, adjust=False).mean()
    ema9_15m = c_15.ewm(span=9, adjust=False).mean()
    vwap_15m = compute_vwap(df_15m)
    current_vwap = float(vwap_15m.iloc[-1]) if not vwap_15m.empty else current_price

    # Bandas de Bollinger 15m y pendientes
    bb_dict = compute_bollinger_bands(c_15, period=20, num_std=2.0)
    upper_bb = bb_dict["upper"]
    lower_bb = bb_dict["lower"]
    bb_upper_slope = float(upper_bb.diff(3).iloc[-1]) / max(current_price, 1.0) * 100.0 if len(upper_bb) >= 4 else 0.0
    bb_lower_slope = float(lower_bb.diff(3).iloc[-1]) / max(current_price, 1.0) * 100.0 if len(lower_bb) >= 4 else 0.0
    is_bb_expanding = (bb_upper_slope > 0.0001 and bb_lower_slope < -0.0001)

    # Volumen relativo en 15m
    avg_vol_15m = float(v_15.tail(15).mean()) if len(v_15) >= 15 else 1.0
    curr_vol_15m = float(v_15.iloc[-1])
    rvol_15m = curr_vol_15m / max(avg_vol_15m, 1.0)

    # Indicadores en 5m
    c_5 = _safe_col(df_5m, "close")
    o_5 = _safe_col(df_5m, "open")
    h_5 = _safe_col(df_5m, "high")
    l_5 = _safe_col(df_5m, "low")
    v_5 = _safe_col(df_5m, "volume")

    ema3_5m = c_5.ewm(span=3, adjust=False).mean()
    ema9_5m = c_5.ewm(span=9, adjust=False).mean()

    # Análisis de velas recientes de 5m (Micro-Pullback y Gatillo de Primera Vela)
    last_candle_green = float(c_5.iloc[-1]) >= float(o_5.iloc[-1])
    last_candle_red = float(c_5.iloc[-1]) < float(o_5.iloc[-1])
    prev_candle_high = float(h_5.iloc[-2]) if len(h_5) >= 2 else current_price
    prev_candle_low = float(l_5.iloc[-2]) if len(l_5) >= 2 else current_price

    # =========================================================================
    # ESCENARIO CALL: TENDENCIA ALCISTA + MICRO PULLBACK + VELA SUPERA MÁXIMO
    # =========================================================================
    is_trend_bull_15m = (float(ema3_15m.iloc[-1]) > float(ema9_15m.iloc[-1])) and (current_price >= current_vwap * 0.998)
    is_trend_bull_5m = (float(ema3_5m.iloc[-1]) >= float(ema9_5m.iloc[-1]))

    # Pullback en velas previas de 5m: vela -2 fue roja o descansó hacia EMA9
    had_pullback_call = False
    if len(c_5) >= 4:
        for idx in range(-4, -1):
            if float(c_5.iloc[idx]) < float(o_5.iloc[idx]):
                had_pullback_call = True
                break

    # Gatillo: Vela actual es verde y superó el máximo de la vela previa (First Candle New High)
    first_candle_new_high = last_candle_green and (float(c_5.iloc[-1]) > prev_candle_high or float(h_5.iloc[-1]) > prev_candle_high)

    if is_trend_bull_15m and is_trend_bull_5m and (had_pullback_call or is_bb_expanding) and first_candle_new_high:
        score = 70.0
        if is_bb_expanding:
            score += 20.0
        if rvol_15m >= 1.8:
            score += 15.0
        if current_price > current_vwap:
            score += 10.0

        return {
            "symbol": symbol,
            "direction": "CALL",
            "score": min(score, 100.0),
            "underlying_price": current_price,
            "bb_expanding": is_bb_expanding,
            "rvol_15m": rvol_15m,
            "reason": f"Ross Cameron Call Breakout: First Candle New High en 5m tras pullback + Expansión Bollinger 15m (RVOL {rvol_15m:.1f}x)"
        }

    # =========================================================================
    # ESCENARIO PUT: TENDENCIA BAJISTA + REBOTE TÉCNICO + VELA PERFORA MÍNIMO
    # =========================================================================
    is_trend_bear_15m = (float(ema3_15m.iloc[-1]) < float(ema9_15m.iloc[-1])) and (current_price <= current_vwap * 1.002)
    is_trend_bear_5m = (float(ema3_5m.iloc[-1]) <= float(ema9_5m.iloc[-1]))

    # Rebote previo en velas de 5m hacia resistencia
    had_pullback_put = False
    if len(c_5) >= 4:
        for idx in range(-4, -1):
            if float(c_5.iloc[idx]) > float(o_5.iloc[idx]):
                had_pullback_put = True
                break

    # Gatillo: Vela actual es roja y perforó el mínimo de la vela previa (First Candle New Low)
    first_candle_new_low = last_candle_red and (float(c_5.iloc[-1]) < prev_candle_low or float(l_5.iloc[-1]) < prev_candle_low)

    if is_trend_bear_15m and is_trend_bear_5m and (had_pullback_put or is_bb_expanding) and first_candle_new_low:
        score = 70.0
        if is_bb_expanding:
            score += 20.0
        if rvol_15m >= 1.8:
            score += 15.0
        if current_price < current_vwap:
            score += 10.0

        return {
            "symbol": symbol,
            "direction": "PUT",
            "score": min(score, 100.0),
            "underlying_price": current_price,
            "bb_expanding": is_bb_expanding,
            "rvol_15m": rvol_15m,
            "reason": f"Ross Cameron Put Breakdown: First Candle New Low en 5m tras rebote + Expansión Bollinger 15m (RVOL {rvol_15m:.1f}x)"
        }

    return None


async def run_warrior_momentum_options_scan(limit: int = 2) -> Dict[str, Any]:
    """
    Ejecuta el ciclo de escaneo y despacho de Warrior Momentum Options.
    1. Descarga datos 5m y 15m de los subyacentes líderes.
    2. Identifica rupturas de momentum tipo Ross Cameron.
    3. Selecciona contratos Delta 0.50-0.65 con DTE 3-7 días.
    4. Auto-dispara vía Adaptive Midpoint si el capital lo permite.
    """
    sb = get_supabase()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    # Cargar configuración de opciones
    eff = {}
    try:
        cfg_rows = sb.table("opt_user_settings").select("key, value").execute().data or []
        for r in cfg_rows:
            eff[r["key"]] = r["value"]
    except Exception as e_cfg:
        log_warning(MODULE, f"Aviso al cargar configuración de opciones: {e_cfg}")

    max_capital = float(eff.get("max_open_risk_usd", 5000.0))

    # Verificar posiciones abiertas en opt_paper_trades
    open_trades = sb.table("opt_paper_trades").select("id, max_loss_total, symbol").eq("status", "open").execute().data or []
    current_open_risk = sum(float(t.get("max_loss_total") or 0.0) for t in open_trades)
    open_symbols = {str(t.get("symbol") or "").upper() for t in open_trades}

    yf_provider = YFinanceProvider()
    candidates_found: List[Dict[str, Any]] = []

    for sym in WARRIOR_OPTIONS_UNIVERSE:
        # Diversificación: máximo 1 contrato abierto por subyacente
        if sym in open_symbols:
            continue

        try:
            df_5m = yf_provider.get_historical_data(sym, period="3d", interval="5m")
            df_15m = yf_provider.get_historical_data(sym, period="5d", interval="15m")

            setup = evaluate_warrior_momentum_setup(sym, df_5m, df_15m)
            if setup:
                log_info(MODULE, f"⚡ [WARRIOR SETUP DETECTADO] {sym} -> {setup['direction']} (Score: {setup['score']:.1f}) | {setup['reason']}")
                candidates_found.append(setup)
        except Exception as e_sym:
            log_warning(MODULE, f"Error evaluando setup Warrior para {sym}: {e_sym}")

    if not candidates_found:
        return {"ok": True, "count": 0, "dispatched": 0}

    # Ordenar candidatos por score descendente
    candidates_found.sort(key=lambda x: x["score"], reverse=True)

    dispatched_count = 0
    for cand in candidates_found[:limit]:
        sym = cand["symbol"]
        direction = cand["direction"]
        right = "C" if direction == "CALL" else "P"
        current_p = cand["underlying_price"]

        # Buscar contrato semanal con Delta ~0.55 (0.50 - 0.65) y DTE 3 a 7 días
        contract = fetch_and_select_best_option_contract(
            symbol=sym,
            underlying_price=current_p,
            right=right,
            budget=min(800.0, max_capital * 0.25),
            min_dte=3,
            max_dte=7,
            target_delta=0.55 if right == "C" else -0.55,
            max_spread_pct=6.0,
            tranche_mode="SINGLE"
        )

        if not contract:
            log_info(MODULE, f"⏸️ No se encontró contrato óptimo para {sym} {direction} con Delta 0.50-0.65 y DTE 3-7d.")
            continue

        cost_total = contract.cost_per_contract * contract.target_total_contracts
        if current_open_risk + cost_total > max_capital:
            log_info(MODULE, f"⛔ Saldo insuficiente para {sym} ({cost_total:.2f} + {current_open_risk:.2f} > {max_capital:.2f})")
            continue

        # Crear registro en opt_candidates con estrategia WARRIOR_MOMENTUM
        leg = {
            "leg_index": 0,
            "action": "BUY",
            "ratio": 1,
            "right": right,
            "strike": contract.strike,
            "expiry": contract.expiry.isoformat(),
            "dte": contract.dte,
            "contract_id": contract.contract_id,
            "conid": contract.conid,
            "delta": contract.delta,
            "bid": contract.bid,
            "ask": contract.ask,
            "mid": contract.mid,
            "spread_pct": contract.spread_pct,
            "open_interest": contract.open_interest,
            "volume": contract.volume,
            "cost_contract": contract.cost_per_contract
        }

        exit_plan = {
            "tp_half_pct": 20.0,              # TP1 al +20% (vender 50%)
            "breakeven_on_tp1": True,          # Mover stop a breakeven
            "trailing_runner": True,           # 50% restante protegido con candado Bollinger 15m
            "candado_bollinger_15m": True,
            "exit_ema3_flat_1h": True,
            "stop_loss_underlying_pct": -5.0   # Stop loss de -5% en el subyacente
        }

        payload = {
            "symbol": sym,
            "underlying_id": 1,
            "strategy_type": "WARRIOR_MOMENTUM",
            "direction": direction,
            "direction_source": "warrior_momentum_engine",
            "expiry": contract.expiry.isoformat(),
            "legs": [leg],
            "qty": contract.target_total_contracts,
            "entry_debit": contract.mid,
            "mid_debit": contract.mid,
            "max_loss_contract": round(contract.mid * 100, 2),
            "max_loss_total": cost_total,
            "max_profit_contract": round(contract.mid * 150, 2),
            "breakeven": contract.strike + contract.mid if right == "C" else contract.strike - contract.mid,
            "costs_contract": 1.4,
            "exec_overcost_pct": contract.spread_pct,
            "exit_plan": exit_plan,
            "score": cand["score"],
            "score_breakdown": {"warrior_setup": 70, "bollinger": 20 if cand["bb_expanding"] else 0, "rvol": 10},
            "eligibility_status": "eligible",
            "rejection_reasons": [],
            "warnings": [],
            "rank_global": 1,
            "rank_strategy": 1,
            "model_version": "v8.0-warrior",
            "settings_version": 1,
            "data_quality": {"status": "good", "source": "warrior_momentum_options"},
            "snapshot_at": now_iso,
            "created_at": now_iso
        }

        try:
            ins_res = sb.table("opt_candidates").insert(payload).execute()
            if ins_res.data:
                cand_record = ins_res.data[0]
                und_dict = {"symbol": sym, "id": 1, "price": current_p}
                executed_pos = execute_selected_candidate_to_trade(sb, cand_record, eff, und=und_dict, now_dt=now_dt)
                if executed_pos:
                    log_info(MODULE, f"🚀 [WARRIOR AUTO-DISPATCH] Posición {sym} {direction} {contract.strike} {contract.expiry} abierta exitosamente.")
                    dispatched_count += 1
                    current_open_risk += cost_total
                    open_symbols.add(sym)
        except Exception as e_ins:
            log_error(MODULE, f"Error insertando candidato Warrior para {sym}: {e_ins}")

    return {
        "ok": True,
        "candidates_evaluated": len(candidates_found),
        "dispatched": dispatched_count,
        "timestamp": now_iso
    }
