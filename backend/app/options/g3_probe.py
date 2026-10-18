"""Sonda y Evaluador del Gate G3 (Sprint 7).
Criterios de aceptacion del Gate G3 (§17.2 y §18):
  1. Duracion minima en shadow paper: >= 4 semanas (28 dias).
  2. Volumen minimo de operaciones: >= 60 operaciones simuladas (umbral ajustado con el usuario).
  3. Expectancy neta positiva: PnL medio por operacion > 0 bajo ejecucion conservadora y slippage.
  4. Tolerancia de calibracion: error maximo por tramo de probabilidad <= +-10 puntos porcentuales.
  5. Max drawdown controlado: sin breach de parada catastrofica.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.options import calibration as cal
from app.options import performance as perf
from app.options import settings_defaults as sd

MODEL_VERSION = "v1.0-s7"


def evaluate_gate_g3(trades: list[dict[str, Any]],
                     eff: dict[str, Any],
                     shadow_start_date: date | None = None,
                     now: datetime | None = None) -> dict[str, Any]:
    """Evalua si la cartera paper en shadow cumple los requisitos del Gate G3."""
    now_dt = now or datetime.now(timezone.utc)
    today = now_dt.date()

    # Requisitos configurables
    min_weeks = float(eff.get("g3_min_weeks") or 4.0)
    min_trades = int(eff.get("g3_min_trades") or 60)
    cal_tol_pts = float(eff.get("g3_calibration_tol_pts") or 10.0)

    # 1. Duracion en shadow
    earliest_trade_date: date | None = None
    if trades:
        dates = []
        for t in trades:
            d_str = str(t.get("entry_time") or t.get("created_at") or "")[:10]
            if d_str:
                dates.append(date.fromisoformat(d_str))
        if dates:
            earliest_trade_date = min(dates)

    start_dt = shadow_start_date or earliest_trade_date or today
    days_in_shadow = max(0, (today - start_dt).days)
    weeks_in_shadow = round(days_in_shadow / 7.0, 1)
    duration_ok = weeks_in_shadow >= min_weeks

    # 2. Volumen de operaciones
    n_trades = len(trades)
    volume_ok = n_trades >= min_trades

    # 3. Metricas de performance y expectancy
    p_metrics = perf.calculate_performance(trades)
    expectancy = p_metrics["expectancy_usd"]
    expectancy_ok = expectancy > 0.0

    # 4. Calibracion de probabilidad
    cal_metrics = cal.compute_binned_calibration(trades)
    max_cal_error = cal_metrics["max_calibration_error_pts"]
    calibration_ok = max_cal_error <= cal_tol_pts

    # 5. Drawdown
    max_dd = p_metrics["max_drawdown_usd"]
    dd_limit = float(eff.get("daily_stop_usd") or 50.0) * 3.0  # max 3 stops
    drawdown_ok = max_dd <= dd_limit

    # Criterios consolidados
    criteria = [
        {
            "id": "C-1",
            "name": "Duración en Shadow",
            "required": f">= {min_weeks} semanas ({int(min_weeks * 7)} días)",
            "current": f"{weeks_in_shadow} semanas ({days_in_shadow} días)",
            "passed": duration_ok,
            "status": "PASS" if duration_ok else "PENDING",
        },
        {
            "id": "C-2",
            "name": "Volumen de Operaciones",
            "required": f">= {min_trades} operaciones",
            "current": f"{n_trades} operaciones",
            "passed": volume_ok,
            "status": "PASS" if volume_ok else "PENDING",
        },
        {
            "id": "C-3",
            "name": "Expectancy Neta",
            "required": "> $0.00 / operación",
            "current": f"${expectancy:+.2f} / operación",
            "passed": expectancy_ok,
            "status": "PASS" if expectancy_ok else ("FAIL" if volume_ok else "PENDING"),
        },
        {
            "id": "C-4",
            "name": "Calibración de Probabilidad",
            "required": f"Error máx <= ±{cal_tol_pts:.1f} pts",
            "current": f"Error máx ±{max_cal_error:.1f} pts",
            "passed": calibration_ok,
            "status": "PASS" if calibration_ok else ("FAIL" if volume_ok else "PENDING"),
        },
        {
            "id": "C-5",
            "name": "Control de Drawdown",
            "required": f"<= ${dd_limit:.2f}",
            "current": f"${max_dd:.2f}",
            "passed": drawdown_ok,
            "status": "PASS" if drawdown_ok else "FAIL",
        },
    ]

    all_passed = duration_ok and volume_ok and expectancy_ok and calibration_ok and drawdown_ok
    any_failed = not drawdown_ok or (volume_ok and (not expectancy_ok or not calibration_ok))

    if all_passed:
        verdict = "GO"
    elif any_failed:
        verdict = "NO-GO"
    else:
        verdict = "PENDING"

    recommendations = []
    if not duration_ok:
        recommendations.append(f"Continuar ejecución en shadow: faltan {max(0, int(min_weeks * 7 - days_in_shadow))} días.")
    if not volume_ok:
        recommendations.append(f"Acumular más operaciones simuladas: faltan {max(0, min_trades - n_trades)} trades para el objetivo de {min_trades}.")
    if not expectancy_ok and volume_ok:
        recommendations.append("Expectancy neta negativa: revisar filtros de selección o reducir slippage de entrada.")
    if not calibration_ok and volume_ok:
        recommendations.append(f"Calibración de probabilidad fuera de tolerancia (±{max_cal_error:.1f} > ±{cal_tol_pts:.1f} pts): ajustar alpha o parámetros de volatilidad.")

    return {
        "verdict": verdict,
        "all_passed": all_passed,
        "criteria": criteria,
        "summary": {
            "weeks_in_shadow": weeks_in_shadow,
            "required_weeks": min_weeks,
            "trades_count": n_trades,
            "required_trades": min_trades,
            "expectancy_usd": expectancy,
            "net_pnl_usd": p_metrics["net_pnl_usd"],
            "win_rate_pct": p_metrics["win_rate_pct"],
            "profit_factor": p_metrics["profit_factor"],
            "max_drawdown_usd": max_dd,
            "max_calibration_error_pts": max_cal_error,
            "brier_score": cal_metrics["brier_score"],
        },
        "recommendations": recommendations,
        "model_version": MODEL_VERSION,
        "evaluated_at": now_dt.isoformat(),
    }


def main():
    import sys
    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    trades = sb.table("opt_paper_trades").select("*, opt_candidates(*)").eq("status", "closed").execute().data or []
    eff = sd.effective_settings(None)
    res = evaluate_gate_g3(trades, eff)
    print("=" * 60)
    print(f"EVALUACION GATE G3: {res['verdict']}")
    print("=" * 60)
    for c in res["criteria"]:
        print(f"[{c['status']}] {c['name']}: {c['current']} (Req: {c['required']})")
    print("-" * 60)
    for r in res["recommendations"]:
        print(f"  * {r}")


if __name__ == "__main__":
    main()
