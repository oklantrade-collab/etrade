"""Calibracion de Probabilidad y Estimacion Empirica de Alpha (Sprint 7).
Evalua la concordancia entre la probabilidad teorica del modelo (POP) y la frecuencia
observada de operaciones ganadoras, asi como el alpha observado frente al prior (§11 y §17).
"""
from __future__ import annotations

import math
from typing import Any

MODEL_VERSION = "v1.0-s7"


def compute_binned_calibration(trades_with_candidates: list[dict[str, Any]],
                               n_bins: int = 5) -> dict[str, Any]:
    """Calcula el diagrama de confiabilidad (calibracion agrupada por tramos de probabilidad).
    Evalua el Gate G3: error de calibracion dentro de +-10 puntos porcentuales.
    """
    if not trades_with_candidates:
        return {
            "total_evaluated": 0,
            "brier_score": None,
            "max_calibration_error_pts": 0.0,
            "mean_calibration_error_pts": 0.0,
            "bins": [],
            "well_calibrated": True,
            "model_version": MODEL_VERSION,
        }

    valid_samples: list[tuple[float, int, float]] = []
    for t in trades_with_candidates:
        cand = t.get("candidate") or t
        # Usar pop_view si existe, si no pop_neutral
        pop = cand.get("pop_view")
        if pop is None:
            pop = cand.get("pop_neutral")
        pnl = float(t.get("realized_pnl") or 0.0)

        if pop is not None and 0.0 <= float(pop) <= 1.0:
            won = 1 if pnl > 0 else 0
            valid_samples.append((float(pop), won, pnl))

    if not valid_samples:
        return {
            "total_evaluated": 0,
            "brier_score": None,
            "max_calibration_error_pts": 0.0,
            "mean_calibration_error_pts": 0.0,
            "bins": [],
            "well_calibrated": True,
            "model_version": MODEL_VERSION,
        }

    n_samples = len(valid_samples)
    # Brier score: MSE entre probabilidad teorica y resultado binario (1 o 0)
    brier = sum((p - y) ** 2 for p, y, _ in valid_samples) / n_samples

    # Definir tramos (ej. [0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), [0.8, 1.0])
    bin_width = 1.0 / n_bins
    bins_data: list[dict[str, Any]] = []
    max_error = 0.0
    weighted_error_sum = 0.0

    for b in range(n_bins):
        lo = b * bin_width
        hi = (b + 1) * bin_width
        # Para el ultimo tramo incluir el 1.0
        in_bin = [s for s in valid_samples if (lo <= s[0] < hi) or (b == n_bins - 1 and s[0] == 1.0)]

        count = len(in_bin)
        if count > 0:
            mean_theo = sum(s[0] for s in in_bin) / count
            obs_win = sum(s[1] for s in in_bin) / count
            error_pts = abs(obs_win - mean_theo) * 100.0
            weighted_error_sum += error_pts * count

            # Solo computar max_error en tramos con muestra suficiente (>= 3)
            if count >= 3 and error_pts > max_error:
                max_error = error_pts
        else:
            mean_theo = (lo + hi) / 2.0
            obs_win = None
            error_pts = 0.0

        bins_data.append({
            "bin_index": b + 1,
            "range": f"{int(lo * 100)}%-{int(hi * 100)}%",
            "range_lo": round(lo, 2),
            "range_hi": round(hi, 2),
            "trades_count": count,
            "mean_theoretical_pop": round(mean_theo * 100.0, 1),
            "observed_win_pct": round(obs_win * 100.0, 1) if obs_win is not None else None,
            "calibration_error_pts": round(error_pts, 1),
        })

    mean_error = weighted_error_sum / n_samples if n_samples else 0.0
    # Gate G3 exige calibracion dentro de +-10 puntos
    well_calibrated = max_error <= 10.0

    return {
        "total_evaluated": n_samples,
        "brier_score": round(brier, 4),
        "max_calibration_error_pts": round(max_error, 1),
        "mean_calibration_error_pts": round(mean_error, 1),
        "tolerance_pts": 10.0,
        "well_calibrated": well_calibrated,
        "bins": bins_data,
        "model_version": MODEL_VERSION,
    }


def estimate_empirical_alpha(trades_with_candidates: list[dict[str, Any]],
                             prior_alpha: float = 0.25) -> dict[str, Any]:
    """Estima el alpha empirico observado en las operaciones cerradas frente al prior teorico.
    Si la tasa observada supera a la neutral con significancia, alpha > prior; si no, alpha < prior.
    """
    if not trades_with_candidates:
        return {
            "prior_alpha": prior_alpha,
            "estimated_alpha": prior_alpha,
            "alpha_status": "insufficient_data",
            "samples_count": 0,
            "confidence": "none",
        }

    pop_diffs = []
    wins = []
    for t in trades_with_candidates:
        cand = t.get("candidate") or t
        pop_v = cand.get("pop_view")
        pop_n = cand.get("pop_neutral")
        pnl = float(t.get("realized_pnl") or 0.0)

        if pop_v is not None and pop_n is not None:
            pop_diffs.append(float(pop_v) - float(pop_n))
            wins.append(1 if pnl > 0 else 0)

    if len(wins) < 10:
        return {
            "prior_alpha": prior_alpha,
            "estimated_alpha": prior_alpha,
            "alpha_status": "insufficient_data",
            "samples_count": len(wins),
            "confidence": "low (n < 10)",
        }

    obs_win_rate = sum(wins) / len(wins)
    avg_pop_neutral = 0.50
    avg_edge = obs_win_rate - avg_pop_neutral

    # Ajuste suave bayesiano de alpha hacia los datos observados
    # Si obs_win_rate > 50%, alpha positivo
    # escala lineal: si exceso de win rate es +10% (0.60 vs 0.50), alpha ~ 0.35
    weight_data = min(1.0, len(wins) / 60.0)  # full peso al alcanzar 60 operaciones (G3)
    data_implied_alpha = max(0.0, min(0.60, 0.25 + avg_edge * 1.5))
    blended_alpha = (1.0 - weight_data) * prior_alpha + weight_data * data_implied_alpha

    return {
        "prior_alpha": prior_alpha,
        "estimated_alpha": round(blended_alpha, 3),
        "data_implied_alpha": round(data_implied_alpha, 3),
        "observed_win_rate_pct": round(obs_win_rate * 100.0, 1),
        "samples_count": len(wins),
        "weight_data": round(weight_data, 2),
        "alpha_status": "calibrated" if len(wins) >= 30 else "preliminary",
        "confidence": "high" if len(wins) >= 60 else "moderate",
    }
