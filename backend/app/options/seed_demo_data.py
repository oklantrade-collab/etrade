"""Script para generar datos de prueba y demostracion del modulo Options.

Puebla Supabase con:
- opt_underlyings (universo de acciones con scores APEX y opcionabilidad)
- opt_contracts y opt_quotes_latest (contratos y cotizaciones)
- opt_candidates (candidatas seleccionadas, elegibles y descartadas con Options Score)
- opt_simulations (matrices de escenarios 5x5 de valoracion BS)
- opt_aduana_decisions (aprobaciones y descartes ADUANA O-1..O-11)
- opt_paper_trades (posiciones abiertas con P&L no realizado y cerradas para performance)
- opt_g1_sessions (historial de avance del Gate G1)
- opt_worker_heartbeat (worker activo en estado ONLINE)

Uso:
  python -m app.options.seed_demo_data
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.logger import log_info
from app.core.supabase_client import get_supabase


def generate_scenario_grid(spot: float, base_debit: float, is_spread: bool = True) -> list[dict[str, Any]]:
    """Genera una cuadricula 5x5 realista (movimiento subyacente x cambio IV)."""
    grid = []
    d_spots = [-0.06, -0.03, 0.0, 0.03, 0.06]
    d_ivs = [-0.10, -0.05, 0.0, 0.05, 0.10]
    for ds in d_spots:
        for div in d_ivs:
            s_scen = spot * (1.0 + ds)
            # Aproximacion de P&L para demo
            pnl_delta = (ds * spot * 15.0) if is_spread else (ds * spot * 40.0)
            pnl_vega = div * 25.0
            pnl_net = round(pnl_delta + pnl_vega - 1.40, 2)
            grid.append({
                "delta_spot_pct": round(ds * 100, 1),
                "delta_iv_pts": round(div * 100, 1),
                "spot": round(s_scen, 2),
                "iv": round(0.25 + div, 4),
                "pnl_net_usd": pnl_net,
                "prob_neutral": round(0.04, 4),
                "prob_view": round(0.05 if ds > 0 else 0.03, 4),
            })
    return grid


def seed():
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    today_date = now.date()

    print("== Generando datos de prueba para el modulo APEX Options ==")

    # 1. opt_worker_heartbeat (para que aparezca ONLINE)
    sb.table("opt_worker_heartbeat").upsert({
        "worker": "options_worker",
        "status": "running",
        "data_state": "DELAYED",
        "detail": {"tws_connected": True, "mode": "demo_seed", "version": "v1.0"},
        "updated_at": now_iso,
    }, on_conflict="worker").execute()
    print("✓ Worker Heartbeat actualizado (ONLINE).")

    # 2. opt_underlyings
    underlyings_data = [
        {"symbol": "SPY", "underlying_conid": 756733, "price": 585.50, "apex_score": 85.0, "direction": "bullish",
         "optionable": True, "atm_spread_pct": 2.1, "atm_oi": 14500, "atm_volume": 8200, "strike_gap_pct": 0.8,
         "data_state": "DELAYED", "updated_at": now_iso},
        {"symbol": "NVDA", "underlying_conid": 265598, "price": 138.40, "apex_score": 82.0, "direction": "bullish",
         "optionable": True, "atm_spread_pct": 2.8, "atm_oi": 9800, "atm_volume": 5400, "strike_gap_pct": 1.2,
         "data_state": "DELAYED", "updated_at": now_iso},
        {"symbol": "AAPL", "underlying_conid": 265598, "price": 232.80, "apex_score": 78.5, "direction": "bullish",
         "optionable": True, "atm_spread_pct": 3.2, "atm_oi": 8500, "atm_volume": 4100, "strike_gap_pct": 1.1,
         "data_state": "DELAYED", "updated_at": now_iso},
        {"symbol": "MSFT", "underlying_conid": 272093, "price": 420.10, "apex_score": 74.0, "direction": "bullish",
         "optionable": True, "atm_spread_pct": 3.5, "atm_oi": 6200, "atm_volume": 3200, "strike_gap_pct": 1.4,
         "data_state": "DELAYED", "updated_at": now_iso},
        {"symbol": "TSLA", "underlying_conid": 76792991, "price": 218.00, "apex_score": 62.0, "direction": "bearish",
         "optionable": True, "atm_spread_pct": 4.2, "atm_oi": 11200, "atm_volume": 7600, "strike_gap_pct": 1.5,
         "data_state": "DELAYED", "updated_at": now_iso},
        {"symbol": "AMD", "underlying_conid": 4391, "price": 155.20, "apex_score": 45.0, "direction": "neutral",
         "optionable": False, "optionable_reason": "spread ATM 16.5% > 15%", "atm_spread_pct": 16.5,
         "atm_oi": 1200, "atm_volume": 450, "strike_gap_pct": 2.2, "data_state": "DELAYED", "updated_at": now_iso},
    ]
    u_map: dict[str, int] = {}
    for u in underlyings_data:
        res = sb.table("opt_underlyings").upsert(u, on_conflict="symbol").execute()
        if res.data:
            u_map[u["symbol"]] = res.data[0]["id"]
    print(f"✓ {len(u_map)} subyacentes creados en opt_underlyings.")

    # 3. opt_g1_sessions (5 sesiones para mostrar avance de factibilidad)
    for i in range(5):
        s_date = (today_date - timedelta(days=5 - i)).isoformat()
        is_pass = (i != 1)  # 4 de 5 pasan (80%)
        sb.table("opt_g1_sessions").upsert({
            "session_date": s_date,
            "symbols_evaluated": 12,
            "optionable_count": 9 if is_pass else 4,
            "viable_candidates": 5 if is_pass else 0,
            "market_data_type": "DELAYED",
            "details": [{"symbol": "SPY", "optionable": True, "viable": True}],
            "session_pass": is_pass,
        }, on_conflict="session_date").execute()
    print("✓ 5 sesiones registradas en opt_g1_sessions (Gate G1: GO/80%).")

    # 4. Limpiar candidatas previas para un reemplazo limpio
    for uid in u_map.values():
        sb.table("opt_candidates").delete().eq("underlying_id", uid).execute()

    # 5. opt_candidates con desgloses realistas
    expiry_nov = (today_date + timedelta(days=34)).isoformat()
    expiry_dec = (today_date + timedelta(days=62)).isoformat()

    cands_data = [
        # 1. SPY Bull Call Spread (Selected, #1)
        {
            "underlying_id": u_map["SPY"], "strategy_type": "bull_call_spread", "direction": "bullish",
            "direction_source": "apex", "expiry": expiry_nov,
            "legs": [{"desc": "+C580 / -C590", "side": "buy", "right": "C", "strike": 580.0},
                     {"desc": "-C590", "side": "sell", "right": "C", "strike": 590.0}],
            "qty": 1, "entry_debit": 3.20, "mid_debit": 3.15, "max_loss_contract": 321.40,
            "max_loss_total": 321.40, "max_profit_contract": 678.60, "breakeven": 583.21,
            "costs_contract": 1.40, "exec_overcost_pct": 1.6, "ev_neutral_net": 18.50,
            "ev_view_net": 58.40, "pop_neutral": 0.48, "pop_view": 0.62, "alpha_used": 0.25,
            "score": 86.5, "rank_global": 1, "rank_strategy": 1, "eligibility_status": "selected",
            "score_breakdown": {
                "score": 86.5, "min_score_required": 60,
                "components": {
                    "expectancy": {"score": 90.0, "weight": 0.30},
                    "asymmetry": {"score": 88.0, "weight": 0.25},
                    "liquidity": {"score": 95.0, "weight": 0.20},
                    "apex_confluence": {"score": 85.0, "weight": 0.15},
                    "maturity": {"score": 80.0, "weight": 0.10},
                }
            },
            "model_version": "v1.0-s5", "created_at": now_iso
        },
        # 2. NVDA Bull Call Spread (Selected, #2)
        {
            "underlying_id": u_map["NVDA"], "strategy_type": "bull_call_spread", "direction": "bullish",
            "direction_source": "apex", "expiry": expiry_nov,
            "legs": [{"desc": "+C135 / -C145", "side": "buy", "right": "C", "strike": 135.0},
                     {"desc": "-C145", "side": "sell", "right": "C", "strike": 145.0}],
            "qty": 1, "entry_debit": 2.80, "mid_debit": 2.75, "max_loss_contract": 281.40,
            "max_loss_total": 281.40, "max_profit_contract": 718.60, "breakeven": 137.81,
            "costs_contract": 1.40, "exec_overcost_pct": 1.8, "ev_neutral_net": 14.20,
            "ev_view_net": 45.20, "pop_neutral": 0.46, "pop_view": 0.59, "alpha_used": 0.25,
            "score": 82.0, "rank_global": 2, "rank_strategy": 2, "eligibility_status": "selected",
            "score_breakdown": {
                "score": 82.0, "min_score_required": 60,
                "components": {
                    "expectancy": {"score": 85.0, "weight": 0.30},
                    "asymmetry": {"score": 92.0, "weight": 0.25},
                    "liquidity": {"score": 82.0, "weight": 0.20},
                    "apex_confluence": {"score": 82.0, "weight": 0.15},
                    "maturity": {"score": 80.0, "weight": 0.10},
                }
            },
            "model_version": "v1.0-s5", "created_at": now_iso
        },
        # 3. AAPL Long Call (Eligible, #3)
        {
            "underlying_id": u_map["AAPL"], "strategy_type": "long_call", "direction": "bullish",
            "direction_source": "apex", "expiry": expiry_dec,
            "legs": [{"desc": "+C235", "side": "buy", "right": "C", "strike": 235.0}],
            "qty": 1, "entry_debit": 4.50, "mid_debit": 4.45, "max_loss_contract": 450.70,
            "max_loss_total": 450.70, "max_profit_contract": None, "breakeven": 239.51,
            "costs_contract": 0.70, "exec_overcost_pct": 1.1, "ev_neutral_net": 12.00,
            "ev_view_net": 32.10, "pop_neutral": 0.42, "pop_view": 0.54, "alpha_used": 0.25,
            "score": 76.2, "rank_global": 3, "rank_strategy": 1, "eligibility_status": "eligible",
            "score_breakdown": {
                "score": 76.2, "min_score_required": 60,
                "components": {
                    "expectancy": {"score": 78.0, "weight": 0.30},
                    "asymmetry": {"score": 75.0, "weight": 0.25},
                    "liquidity": {"score": 80.0, "weight": 0.20},
                    "apex_confluence": {"score": 78.0, "weight": 0.15},
                    "maturity": {"score": 85.0, "weight": 0.10},
                }
            },
            "model_version": "v1.0-s5", "created_at": now_iso
        },
        # 4. MSFT Bull Call Spread (Eligible, #4)
        {
            "underlying_id": u_map["MSFT"], "strategy_type": "bull_call_spread", "direction": "bullish",
            "direction_source": "apex", "expiry": expiry_nov,
            "legs": [{"desc": "+C420 / -C430", "side": "buy", "right": "C", "strike": 420.0},
                     {"desc": "-C430", "side": "sell", "right": "C", "strike": 430.0}],
            "qty": 1, "entry_debit": 3.10, "mid_debit": 3.05, "max_loss_contract": 311.40,
            "max_loss_total": 311.40, "max_profit_contract": 688.60, "breakeven": 423.11,
            "costs_contract": 1.40, "exec_overcost_pct": 1.6, "ev_neutral_net": 10.50,
            "ev_view_net": 28.50, "pop_neutral": 0.47, "pop_view": 0.58, "alpha_used": 0.25,
            "score": 74.8, "rank_global": 4, "rank_strategy": 3, "eligibility_status": "eligible",
            "score_breakdown": {
                "score": 74.8, "min_score_required": 60,
                "components": {
                    "expectancy": {"score": 72.0, "weight": 0.30},
                    "asymmetry": {"score": 85.0, "weight": 0.25},
                    "liquidity": {"score": 76.0, "weight": 0.20},
                    "apex_confluence": {"score": 74.0, "weight": 0.15},
                    "maturity": {"score": 80.0, "weight": 0.10},
                }
            },
            "model_version": "v1.0-s5", "created_at": now_iso
        },
        # 5. TSLA Bear Put Spread (Eligible, #5)
        {
            "underlying_id": u_map["TSLA"], "strategy_type": "bear_put_spread", "direction": "bearish",
            "direction_source": "apex", "expiry": expiry_nov,
            "legs": [{"desc": "+P220 / -P210", "side": "buy", "right": "P", "strike": 220.0},
                     {"desc": "-P210", "side": "sell", "right": "P", "strike": 210.0}],
            "qty": 1, "entry_debit": 3.40, "mid_debit": 3.35, "max_loss_contract": 341.40,
            "max_loss_total": 341.40, "max_profit_contract": 658.60, "breakeven": 216.59,
            "costs_contract": 1.40, "exec_overcost_pct": 1.5, "ev_neutral_net": 8.00,
            "ev_view_net": 24.00, "pop_neutral": 0.45, "pop_view": 0.55, "alpha_used": 0.25,
            "score": 71.0, "rank_global": 5, "rank_strategy": 1, "eligibility_status": "eligible",
            "score_breakdown": {
                "score": 71.0, "min_score_required": 60,
                "components": {
                    "expectancy": {"score": 70.0, "weight": 0.30},
                    "asymmetry": {"score": 80.0, "weight": 0.25},
                    "liquidity": {"score": 74.0, "weight": 0.20},
                    "apex_confluence": {"score": 62.0, "weight": 0.15},
                    "maturity": {"score": 80.0, "weight": 0.10},
                }
            },
            "model_version": "v1.0-s5", "created_at": now_iso
        },
        # 6. AMD Long Call (Rejected por iliquidez)
        {
            "underlying_id": u_map["AMD"], "strategy_type": "long_call", "direction": "bullish",
            "direction_source": "unverified", "expiry": expiry_nov,
            "legs": [{"desc": "+C160", "side": "buy", "right": "C", "strike": 160.0}],
            "qty": 1, "entry_debit": 5.20, "mid_debit": 4.50, "max_loss_contract": 520.70,
            "max_loss_total": 520.70, "max_profit_contract": None, "breakeven": 165.21,
            "costs_contract": 0.70, "exec_overcost_pct": 15.5, "score": 42.0,
            "eligibility_status": "rejected",
            "rejection_reasons": ["O-2: Liquidez insuficiente (spread ATM 16.5% > 12%)", "O-6: Sobre-coste de ejecución 15.5% > 10%"],
            "model_version": "v1.0-s5", "created_at": now_iso
        },
    ]

    saved_cands = []
    for c in cands_data:
        res = sb.table("opt_candidates").insert(c).execute()
        if res.data:
            saved_cands.append(res.data[0])
    print(f"✓ {len(saved_cands)} candidatas creadas en opt_candidates.")

    # 6. opt_simulations y opt_aduana_decisions para cada candidata
    for cand in saved_cands:
        cid = cand["id"]
        spot = 585.5 if "SPY" in str(cand) else (138.4 if "NVDA" in str(cand) else 232.8)
        grid = generate_scenario_grid(spot, float(cand.get("entry_debit") or 3.0))

        # Simulacion BS
        sb.table("opt_simulations").insert({
            "candidate_id": cid,
            "scenario_config": {"horizon_hours": 96, "sigma_h": 0.038, "iv_ref": 0.24, "alpha_used": 0.25, "model": "black_scholes_v1"},
            "scenario_results": {"grid": grid, "worst_adverse_pnl": -280.0, "ev_neutral_adverse": -45.0, "ev_view_adverse": -12.0},
            "cost_assumptions": {"costs_contract": 1.40, "slippage_normal": 0.02, "slippage_adverse": 0.05},
            "pricing_model_version": "v1.0-s5",
        }).execute()

        # Decision ADUANA
        is_rej = cand["eligibility_status"] == "rejected"
        sb.table("opt_aduana_decisions").insert({
            "candidate_id": cid,
            "kind": "entry",
            "approved": not is_rej,
            "rules": {
                "O-1": {"pass": True, "detail": "Riesgo < $100 por contrato"},
                "O-2": {"pass": not is_rej, "detail": "Liquidez y spread ATM validos"},
                "O-3": {"pass": True, "detail": "Ventana DTE entre 14 y 60 dias"},
                "O-4": {"pass": True, "detail": "Sin eventos de earnings en ventana DTE"},
            },
            "warnings": [] if not is_rej else ["Alerta de liquidez en subyacente"],
            "model_version": "v1.0-s5",
        }).execute()
    print("✓ Cuadrículas de simulación y decisiones ADUANA registradas.")

    # 7. opt_paper_trades (2 Abiertas + 4 Cerradas con P&L positivo neto)
    sb.table("opt_paper_trades").delete().neq("id", 0).execute()

    paper_positions = [
        # ABIERTA 1: SPY Bull Call Spread
        {
            "candidate_id": saved_cands[0]["id"], "underlying_id": u_map["SPY"], "symbol": "SPY",
            "strategy_type": "bull_call_spread", "direction": "bullish", "status": "open", "qty": 1,
            "expiry": expiry_nov, "entry_time": (now - timedelta(days=2)).isoformat(),
            "entry_debit": 3.20, "entry_total_invested": 321.40, "max_loss_total": 321.40,
            "breakeven": 583.21, "unrealized_pnl": 65.00, "last_mark_price": 3.85, "last_mark_at": now_iso,
            "exit_plan": {"tp_pct": 50, "sl_pct": 50, "dte_close": 5},
            "model_version": "v1.0-s6",
        },
        # ABIERTA 2: NVDA Bull Call Spread
        {
            "candidate_id": saved_cands[1]["id"], "underlying_id": u_map["NVDA"], "symbol": "NVDA",
            "strategy_type": "bull_call_spread", "direction": "bullish", "status": "open", "qty": 1,
            "expiry": expiry_nov, "entry_time": (now - timedelta(days=1)).isoformat(),
            "entry_debit": 2.80, "entry_total_invested": 281.40, "max_loss_total": 281.40,
            "breakeven": 137.81, "unrealized_pnl": 30.00, "last_mark_price": 3.10, "last_mark_at": now_iso,
            "exit_plan": {"tp_pct": 50, "sl_pct": 50, "dte_close": 5},
            "model_version": "v1.0-s6",
        },
        # CERRADA 1: SPY Bull Call (+145 USD)
        {
            "candidate_id": saved_cands[0]["id"], "underlying_id": u_map["SPY"], "symbol": "SPY",
            "strategy_type": "bull_call_spread", "direction": "bullish", "status": "closed", "qty": 1,
            "expiry": (today_date - timedelta(days=2)).isoformat(),
            "entry_time": (now - timedelta(days=12)).isoformat(), "entry_debit": 3.10, "entry_total_invested": 311.40,
            "max_loss_total": 311.40, "exit_time": (now - timedelta(days=4)).isoformat(), "exit_credit": 4.55,
            "exit_total_recovered": 453.60, "realized_pnl": 142.20, "unrealized_pnl": 0.0,
            "exit_reason": "take_profit", "model_version": "v1.0-s6",
        },
        # CERRADA 2: NVDA Bull Call (+180 USD)
        {
            "candidate_id": saved_cands[1]["id"], "underlying_id": u_map["NVDA"], "symbol": "NVDA",
            "strategy_type": "bull_call_spread", "direction": "bullish", "status": "closed", "qty": 1,
            "expiry": (today_date - timedelta(days=4)).isoformat(),
            "entry_time": (now - timedelta(days=14)).isoformat(), "entry_debit": 2.50, "entry_total_invested": 251.40,
            "max_loss_total": 251.40, "exit_time": (now - timedelta(days=5)).isoformat(), "exit_credit": 4.30,
            "exit_total_recovered": 428.60, "realized_pnl": 177.20, "unrealized_pnl": 0.0,
            "exit_reason": "take_profit", "model_version": "v1.0-s6",
        },
        # CERRADA 3: AAPL Bull Call (+110 USD)
        {
            "candidate_id": saved_cands[2]["id"], "underlying_id": u_map["AAPL"], "symbol": "AAPL",
            "strategy_type": "bull_call_spread", "direction": "bullish", "status": "closed", "qty": 1,
            "expiry": (today_date - timedelta(days=3)).isoformat(),
            "entry_time": (now - timedelta(days=10)).isoformat(), "entry_debit": 2.90, "entry_total_invested": 291.40,
            "max_loss_total": 291.40, "exit_time": (now - timedelta(days=3)).isoformat(), "exit_credit": 4.00,
            "exit_total_recovered": 398.60, "realized_pnl": 107.20, "unrealized_pnl": 0.0,
            "exit_reason": "take_profit", "model_version": "v1.0-s6",
        },
        # CERRADA 4: MSFT Long Call (-85 USD)
        {
            "candidate_id": saved_cands[3]["id"], "underlying_id": u_map["MSFT"], "symbol": "MSFT",
            "strategy_type": "long_call", "direction": "bullish", "status": "closed", "qty": 1,
            "expiry": (today_date - timedelta(days=5)).isoformat(),
            "entry_time": (now - timedelta(days=9)).isoformat(), "entry_debit": 4.20, "entry_total_invested": 420.70,
            "max_loss_total": 420.70, "exit_time": (now - timedelta(days=6)).isoformat(), "exit_credit": 3.35,
            "exit_total_recovered": 334.30, "realized_pnl": -86.40, "unrealized_pnl": 0.0,
            "exit_reason": "stop_loss", "model_version": "v1.0-s6",
        },
    ]

    for p in paper_positions:
        sb.table("opt_paper_trades").insert(p).execute()
    print("✓ 6 posiciones (2 abiertas, 4 cerradas con Win Rate 75%) creadas en opt_paper_trades.")

    print("\n========================================================")
    print("¡Datos de prueba inyectados con éxito en Supabase!")
    print("Vistas listas para explorar en el frontend:")
    print(" - /options               (Dashboard & KPIs generales)")
    print(" - /options/opportunities (Ranking, Scores y Curvas Payoff)")
    print(" - /options/positions     (Posiciones Paper abiertas/cerradas)")
    print(" - /options/performance   (Curva de Equidad, Métricas y Gate G3)")
    print(" - /options/status        (Universo, Datos y Sesiones G1)")
    print("========================================================")


if __name__ == "__main__":
    seed()
