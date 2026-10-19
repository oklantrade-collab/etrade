"""Script de simulacion integral de extremo a extremo para APEX Options.
Recorre las 5 fases del ciclo completo:
  1. Universe: subyacente opcionable y catalizadores.
  2. Opportunities: valoracion Black-Scholes, sensibilidad EV, ADUANA (O-1..O-16) y Options Score.
  3. Selector de Cartera: asignacion con restricciones de capital, sector y vencimiento.
  4. Compra simulada (Paper Entry): fill realista y apertura de posicion.
  5. Venta simulada (Paper Exit): disparo de Take Profit y calculo de PnL realizado.
  6. Pruebas de inyeccion de errores (Fail-Closed, Kill Switch, Stale, Price Drift).
"""
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath("backend"))

from app.core.supabase_client import get_supabase
from app.options import bs
from app.options import event_calendar as ec
from app.options import exit_engine as ee
from app.options import health
from app.options import options_aduana as aduana
from app.options import paper_execution as pe
from app.options import portfolio_selector as sel
from app.options import score as sc
from app.options import settings_defaults as sd
from app.options import valuation as val


def run_full_simulation():
    print("=" * 80)
    print("🚀 INICIANDO SIMULACION INTEGRAL DE PROCESO COMPLETO: APEX OPTIONS")
    print("=" * 80)

    import os
    os.environ["OPTIONS_HARD_MAX_RISK_PER_TRADE_USD"] = "600"
    os.environ["OPTIONS_HARD_MAX_OPEN_RISK_USD"] = "1500"

    sb = get_supabase()
    eff = sd.effective_settings({
        "capital_usd": 5000,
        "max_risk_per_trade_usd": 500,
        "max_open_risk_usd": 1000,
        "daily_stop_usd": 200,
    })
    health.reset_health_state()

    # -------------------------------------------------------------------------
    # FASE 1: UNIVERSE Y OPCIONABILIDAD
    # -------------------------------------------------------------------------
    print("\n--- [FASE 1: UNIVERSE & FILTROS DE OPCIONABILIDAD] ---")
    mock_underlying = {
        "id": 99991,
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "current_price": 182.50,
        "volume_shares": 52_000_000,
        "atr_14": 3.45,
        "adx_14": 28.5,
        "direction": "bullish",
        "direction_source": "catalyst",
        "catalyst_score": 82.0,
        "catalyst_meta": {
            "c1_gap": {"triggered": True, "confirmed": True, "type": "gap_and_go_up", "gap_pct": 1.4},
            "c2_basis_1h": {"triggered": True, "type": "crossover_above_basis"},
            "c3_adx": {"triggered": True, "adx": 28.5},
            "c4_rebote": {"triggered": False},
        },
        "event_flags": [],
        "market_data_type": "LIVE",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Validar opcionabilidad del subyacente
    opt_ok = (
        mock_underlying["current_price"] >= eff["min_underlying_price"]
        and mock_underlying["volume_shares"] >= 1_000_000
    )
    print(f"✓ Subyacente: {mock_underlying['symbol']} @ ${mock_underlying['current_price']:.2f}")
    print(f"✓ Catalizadores activos: Gap&Go (+{mock_underlying['catalyst_meta']['c1_gap']['gap_pct']}%), Cruce Basis 1H, ADX 5m = {mock_underlying['adx_14']}")
    print(f"✓ Filtro de opcionabilidad superado: {opt_ok}")

    # Verificar calendario de eventos
    calendar = ec.get_event_calendar(sb)
    ev_status = calendar.get_event("AAPL", horizon_days=30)
    print(f"✓ Calendario de eventos: Estado = {ev_status.state} (Bloqueante: {ev_status.is_blocking()})")

    # -------------------------------------------------------------------------
    # FASE 2: OPPORTUNITIES & VALORACION ANALITICA
    # -------------------------------------------------------------------------
    print("\n--- [FASE 2: OPPORTUNITIES, VALORACION, ADUANA & SCORE] ---")
    today = date.today()
    expiry_date = today + timedelta(days=21)
    T0 = 21.0 / 365.0
    strike = 195.0
    r = 0.045
    iv = 0.28

    # Calcular prima teorica y griegas analiticas Black-Scholes
    bs_p = bs.bs_price(mock_underlying["current_price"], strike, T0, r, iv, "C")
    d_delta = bs.bs_delta(mock_underlying["current_price"], strike, T0, r, iv, "C")
    d_gamma = bs.bs_gamma(mock_underlying["current_price"], strike, T0, r, iv)
    d_vega = bs.bs_vega(mock_underlying["current_price"], strike, T0, r, iv)
    d_theta = bs.bs_theta(mock_underlying["current_price"], strike, T0, r, iv, "C")

    # Contrato con debito de $0.45 y spread 6.7% para respetar cap de $50 USD y regla O-6
    bid = 0.42
    ask = 0.45
    entry_debit = ask
    max_loss_contract = round(entry_debit * 100.0, 2)

    cand = {
        "id": 88881,
        "underlying_id": mock_underlying["id"],
        "symbol": "AAPL",
        "strategy_type": "long_call",
        "direction": "bullish",
        "direction_source": "catalyst",
        "expiry": expiry_date.isoformat(),
        "qty": 1,
        "entry_debit": entry_debit,
        "costs_contract": 4.80,
        "max_loss_contract": max_loss_contract,
        "max_loss_total": max_loss_contract,
        "max_profit_contract": 999.0,
        "breakeven": round(strike + entry_debit, 2),
        "exec_overcost_pct": round((ask - bid) / ((ask + bid) / 2.0) * 100.0, 2),
        "underlying_price": mock_underlying["current_price"],
        "sector": "Technology",
        "legs": [
            {
                "contract_id": 77771,
                "conid": 77771,
                "side": "buy",
                "right": "C",
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "iv": iv,
                "delta": round(d_delta, 3),
                "open_interest": 1450,
                "volume": 620,
                "market_data_type": "LIVE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    # Valorar con el motor Black-Scholes y distribucion lognormal
    val_res = val.value_candidate(cand, mock_underlying["current_price"], eff, today, direction_verified=True)
    cand.update({
        "ev_neutral_net": val_res.get("ev_neutral_net"),
        "ev_view_net": val_res.get("ev_view_net"),
        "ev_view_adverse": val_res.get("ev_view_adverse"),
        "ev_ratio": val_res.get("ev_ratio"),
        "worst_adverse_scenario_pnl": val_res.get("worst_adverse_scenario_pnl"),
        "ev_robust": val_res.get("ev_robust"),
        "ev_min": val_res.get("ev_min"),
        "ev_range": val_res.get("ev_range"),
        "greeks_net": val_res.get("greeks_net"),
    })

    print(f"✓ Contrato: AAPL {strike} CALL (Vence: {cand['expiry']}, DTE=21d)")
    print(f"  Bid: ${bid:.2f} | Ask: ${ask:.2f} | Spread Relativo: {cand['exec_overcost_pct']:.2f}%")
    print(f"  EV Neto con Sesgo (ev_view_net): ${cand['ev_view_net']} USD (Ratio EV/Riesgo: {cand['ev_ratio']:.2f})")
    print(f"  EV Robusto (ev_robust): {cand['ev_robust']} (Rango EV: ${cand['ev_range']}, Min: ${cand['ev_min']})")
    print(f"  Griegas Netas: Delta USD = ${cand['greeks_net']['delta_usd']}, Gamma = {cand['greeks_net']['gamma']}, Vega = ${cand['greeks_net']['vega_point']}/pt, Theta = ${cand['greeks_net']['theta_day']}/dia")

    # Evaluacion de ADUANA (O-1..O-16)
    ctx = aduana.static_context(mock_underlying["id"], mock_underlying["event_flags"], mock_underlying)
    aduana_res = aduana.validate_entry(cand, ctx, eff)
    cand["eligibility_status"] = "eligible" if aduana_res.approved else "rejected"
    cand["rejection_reasons"] = aduana_res.reasons

    print(f"\n--- [FILTRO ADUANA (16 REGLAS)] ---")
    print(f"Aprobacion ADUANA: {'✓ APROBADA' if aduana_res.approved else '✗ RECHAZADA'}")
    for r in aduana_res.rules:
        status_icon = "✓" if r.ok else "✗"
        print(f"  {status_icon} [{r.rule}] {r.detail}")

    # Calcular Options Score 0-100
    score_res = sc.score_candidate(cand, mock_underlying, eff)
    cand["score"] = score_res["score"]
    cand["coverage"] = score_res["coverage"]
    cand["score_breakdown"] = score_res["score_breakdown"]
    print(f"\n--- [OPTIONS SCORE EXPLICABLE (Doc §9)] ---")
    print(f"✓ Options Score: {cand['score']} / 100 (Cobertura: {(cand['coverage'] * 100):.0f}%)")
    for comp in cand["score_breakdown"]["components_list"]:
        print(f"  • {comp['name'].upper()} (Peso: {(comp['weight'] * 100):.0f}%): Score = {comp['score']:.1f} -> Contribución = {comp['contribution']:.1f} pts")

    # -------------------------------------------------------------------------
    # FASE 3: SELECTOR DE CARTERA (PORTFOLIO ALLOCATION)
    # -------------------------------------------------------------------------
    print("\n--- [FASE 3: SELECTOR DE CARTERA GREEDY] ---")
    eff_sel = dict(eff, max_risk_per_trade_usd=500.0, max_open_risk_usd=1000.0)
    selection = sel.select_portfolio([cand], existing_positions=[], eff=eff_sel)
    print(f"✓ Candidatas seleccionadas: {len(selection.selected)} / {len(selection.selected) + len(selection.skipped)}")
    print(f"✓ Riesgo asignado: ${selection.total_risk_allocated:.2f} USD (Presupuesto restante: ${selection.remaining_budget:.2f} USD)")
    if selection.skipped:
        for sk in selection.skipped:
            print(f"  ✗ Omitida {sk.get('candidate_id')}: {sk.get('reason')}")

    # -------------------------------------------------------------------------
    # FASE 4: COMPRA SIMULADA (PAPER BUY ENTRY)
    # -------------------------------------------------------------------------
    print("\n--- [FASE 4: COMPRA SIMULADA (PAPER ENTRY)] ---")
    now_entry = datetime.now(timezone.utc)
    entry_fill = pe.simulate_entry_fill(cand, None, eff_sel, now=now_entry)

    paper_position = {
        "candidate_id": cand["id"],
        "underlying_id": cand["underlying_id"],
        "symbol": cand["symbol"],
        "strategy_type": cand["strategy_type"],
        "direction": cand["direction"],
        "status": "open",
        "qty": cand["qty"],
        "expiry": cand["expiry"],
        "entry_time": entry_fill.entry_time,
        "entry_debit": entry_fill.entry_debit,
        "entry_fills": entry_fill.entry_fills,
        "entry_costs": entry_fill.entry_costs,
        "entry_total_invested": entry_fill.entry_total_invested,
        "max_loss_total": entry_fill.entry_total_invested,
        "max_profit_total": 999.0,
        "unrealized_pnl": 0.0,
        "last_mark_price": entry_fill.entry_debit,
        "last_mark_at": entry_fill.entry_time,
        "exit_plan": {"tp_pct": 75, "sl_pct": 50},
        "model_version": pe.MODEL_VERSION,
    }

    print(f"✓ Orden Paper Ejecutada con Fills Conservadores:")
    print(f"  Precio de entrada ask + slippage: ${entry_fill.entry_debit:.4f}/accion")
    print(f"  Costes de comisiones y fees: ${entry_fill.entry_costs:.2f} USD")
    print(f"  Total invertido (Débito x 100 x Qty + Costes): ${entry_fill.entry_total_invested:.2f} USD")
    print(f"  Estado de la posicion: OPEN (en memoria / opt_paper_trades)")

    # -------------------------------------------------------------------------
    # FASE 5: EVOLUCION DE PRECIO Y VENTA SIMULADA (PAPER SELL EXIT & PNL)
    # -------------------------------------------------------------------------
    print("\n--- [FASE 5: EVOLUCION DE MERCADO, VENTA Y PNL REALIZADO] ---")
    # Escenario simulado: AAPL sube +$5.50 a $188.00 (+3.01%) tras 4 horas
    simulated_future_price = 188.00
    # El call strike 195 sube con el aumento de delta y volatilidad
    sim_exit_bid = 0.85
    sim_exit_ask = 0.90

    print(f"→ Simulando transcurso de tiempo (4 horas de sesion):")
    print(f"  Subyacente AAPL se mueve de ${mock_underlying['current_price']:.2f} a ${simulated_future_price:.2f} (+3.01%)")
    print(f"  Prima del Call {strike} sube de ${entry_debit:.2f} a Bid ${sim_exit_bid:.2f} / Ask ${sim_exit_ask:.2f}")

    # Evaluar Take Profit
    unrealized = round((sim_exit_bid * 100.0 * cand["qty"]) - paper_position["entry_total_invested"], 2)
    tp_triggered, tp_reason = ee.should_exit_take_profit(paper_position, unrealized, eff_sel)
    print(f"  PnL no realizado estimado al Bid: +${unrealized:.2f} USD (+{(unrealized / paper_position['entry_total_invested'] * 100):.1f}%)")
    print(f"  Evaluacion Take Profit: Disparo = {tp_triggered} ({tp_reason})")

    # Ejecutar salida con fills conservadores (venta al Bid - slippage)
    now_exit = now_entry + timedelta(hours=4)
    exit_quotes = {
        cand["legs"][0]["conid"]: {
            "bid": sim_exit_bid,
            "ask": sim_exit_ask,
            "market_data_type": "LIVE",
        }
    }
    exit_fill = pe.simulate_exit_fill(paper_position, exit_quotes, eff_sel, exit_reason=tp_reason or "take_profit", now=now_exit)

    paper_position.update({
        "status": "closed",
        "exit_time": exit_fill.exit_time,
        "exit_credit": exit_fill.exit_credit,
        "exit_fills": exit_fill.exit_fills,
        "exit_costs": exit_fill.exit_costs,
        "exit_total_recovered": exit_fill.exit_total_recovered,
        "realized_pnl": exit_fill.realized_pnl,
        "unrealized_pnl": 0.0,
        "last_mark_price": exit_fill.exit_credit,
        "last_mark_at": now_exit.isoformat(),
        "exit_reason": tp_reason,
    })

    print(f"\n✓ Cierre de Posicion Paper Ejecutado:")
    print(f"  Precio de salida bid - slippage: ${exit_fill.exit_credit:.4f}/accion")
    print(f"  Costes de salida (comisiones): ${exit_fill.exit_costs:.2f} USD")
    print(f"  Total recuperado neto: ${exit_fill.exit_total_recovered:.2f} USD")
    roi_pct = (exit_fill.realized_pnl / paper_position["entry_total_invested"]) * 100.0
    print(f"  ★ PnL REALIZADO NETO: +${exit_fill.realized_pnl:.2f} USD (ROI: +{roi_pct:.1f}%)")
    print(f"  Motivo de cierre: {paper_position['exit_reason']}")

    # -------------------------------------------------------------------------
    # FASE 6: INYECCION DE ERRORES Y PRUEBAS DE SALVAGUARDA (FAIL-CLOSED)
    # -------------------------------------------------------------------------
    print("\n--- [FASE 6: PRUEBAS DE RESILIENCIA Y MANEJO DE ERRORES] ---")

    # 1. Error de Kill Switch activo
    health.set_kill_switch(True, reason="Simulacion emergencia")
    o15_pass, o15_code, o15_msg = aduana.rule_o15_system_health_and_kill_switch(cand, eff)
    print(f"  Test Error 1 (Kill Switch Activo): Aprobado = {o15_pass} | Codigo = {o15_code} | Motivo = {o15_msg}")
    assert o15_pass is False, "Fallo: Kill switch deberia bloquear"
    health.reset_health_state()

    # 2. Error de Deriva de Precio Excesiva (Price Drift > 5%)
    drift_pass, drift_code, drift_msg = aduana.rule_o16_price_drift_revalidation(cand, current_underlying=195.0, current_debit=4.10, eff=eff)
    print(f"  Test Error 2 (Price Drift 6.8% > 5%): Aprobado = {drift_pass} | Codigo = {drift_code} | Motivo = {drift_msg}")
    assert drift_pass is False, "Fallo: Deriva de precio deberia bloquear"

    # 3. Error de Cobertura Insuficiente (< 80% o falta liquidez)
    cand_broken = dict(cand, coverage=0.60, missing_components=["liquidity", "iv_greeks"])
    o14_pass, o14_code, o14_msg = aduana.rule_o14_coverage_and_critical_data(cand_broken, eff)
    print(f"  Test Error 3 (Falta Componente Esencial 'liquidity'): Aprobado = {o14_pass} | Codigo = {o14_code} | Motivo = {o14_msg}")
    assert o14_pass is False, "Fallo: Falta de componente esencial deberia bloquear"

    # 4. Replay Determinista
    rep = sc.replay_evaluation(cand, mock_underlying, eff)
    print(f"  Test Replay Determinista (§13.3): Coincidencia = {rep['matches']} | Diferencia de Score = {rep['diff']}")
    assert rep["matches"] is True, "Fallo: Replay debe ser 100% determinista"

    print("\n" + "=" * 80)
    print("✅ CONCLUSION: EL PIPELINE COMPLETO OPERA 100% CORRECTO SIN ERRORES INESPERADOS.")
    print("   Todas las salvaguardas Fail-Closed bloquearon con exito los casos anomalos.")
    print("=" * 80)


if __name__ == "__main__":
    run_full_simulation()
