"""Parametros por defecto, rangos y techos duros del modulo Options (doc §17).

Valor efectivo = min(valor en Settings, techo duro del entorno).
Los techos solo se cambian por variables de entorno (deliberado).
"""
from __future__ import annotations

import os
from typing import Any

EXECUTION_MODE = "paper"  # unico modo permitido en V1


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def hard_caps() -> dict[str, float]:
    return {
        "max_risk_per_trade_usd": _env_float("OPTIONS_HARD_MAX_RISK_PER_TRADE_USD", 100),
        "max_open_risk_usd": _env_float("OPTIONS_HARD_MAX_OPEN_RISK_USD", 200),
        "max_daily_selections": _env_float("OPTIONS_HARD_MAX_DAILY_SELECTIONS", 5),
    }


def options_enabled() -> bool:
    return os.getenv("OPTIONS_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def execution_mode_ok() -> bool:
    return os.getenv("OPTIONS_EXECUTION_MODE", EXECUTION_MODE).strip().lower() == EXECUTION_MODE


# key: (default, min, max)  -- max/min None = sin rango numerico (bool/str)
PARAMS: dict[str, tuple[Any, Any, Any]] = {
    # A. Cuenta y riesgo
    "capital_usd": (1000, 100, 50000),
    "max_risk_per_trade_usd": (50, 5, 100),
    "max_open_risk_usd": (100, 5, 200),
    "daily_stop_usd": (50, 5, 200),
    "max_daily_selections": (3, 0, 5),
    "max_open_positions": (3, 1, 5),
    "max_same_direction": (2, 1, 5),
    "commission_per_contract": (0.65, 0, 5),
    "extra_fees_per_contract": (0.05, 0, 1),
    # B. Universo y opcionabilidad
    "max_underlyings": (20, 5, 40),
    "max_candidates_per_direction": (25, 5, 50),
    "min_underlying_price": (5, 1, 100),
    "max_strike_gap_pct": (5, 1, 10),
    "min_atm_open_interest": (300, 50, 5000),
    "pref_atm_volume": (100, 0, 5000),
    "max_atm_spread_pct": (10, 2, 25),
    "block_events_in_dte": (True, None, None),
    "iv_hv_expensive": (1.5, 1.0, 3.0),
    "supplementary_list_enabled": (False, None, None),
    "supplementary_tickers": ("", None, None),
    # C. Contratos y estrategias
    "strat_long_call": (True, None, None),
    "strat_long_put": (True, None, None),
    "strat_bull_call_spread": (True, None, None),
    "strat_bear_put_spread": (True, None, None),
    "dte_min": (7, 0, 60),
    "dte_max": (30, 0, 60),
    "delta_min": (0.25, 0.10, 0.90),
    "delta_max": (0.65, 0.10, 0.90),
    "spread_width_min": (1, 0.5, 10),
    "spread_width_max": (5, 0.5, 10),
    "max_leg_spread_pct": (10, 2, 25),
    "max_exec_overcost_pct": (10, 2, 25),
    "min_contract_oi": (100, 0, 5000),
    "min_contract_volume": (10, 0, 5000),
    # D. Horario y datos
    "entry_start_min_after_open": (15, 0, 60),
    "entry_end_min_before_close": (30, 15, 120),
    "force_close_min_before_close": (15, 5, 60),
    "scanner_freq_min": (15, 5, 60),
    "snapshot_freq_min": (5, 1, 30),
    "snapshot_retention_days": (90, 30, 365),
    "max_quote_age_sec": (15, 2, 120),
    # Fase de prueba con datos gratuitos (retrasados ~15 min). Resultados NO validos para G1/G3 reales.
    "allow_delayed_data": (True, None, None),
    "max_concurrent_quotes": (50, 10, 100),
    # E. Valoracion
    "alpha": (0.25, 0, 1),
    "horizon_hours": (3.0, 0.5, 6.5),           # horas de mercado hasta la salida simulada
    # Fase de prueba: valora con la direccion de la estrategia aunque APEX no la verifique (queda marcado).
    "allow_unverified_direction": (True, None, None),
    "vol_factor_k": (1.0, 0.5, 1.5),
    "slippage_normal": (0.01, 0, 0.25),
    "slippage_adverse": (0.03, 0, 0.25),
    "exit_spread_mult_normal": (1.0, 1, 3),
    "exit_spread_mult_adverse": (1.5, 1, 3),
    "min_ev_ratio": (0.05, 0, 0.5),
    "risk_free_rate_pct": (4.0, 0, 10),
    # F. Score
    "w_expectancy": (30, 0, 100),
    "w_apex_signal": (20, 0, 100),
    "w_liquidity": (20, 0, 100),
    "w_risk": (15, 0, 100),
    "w_iv_greeks": (10, 0, 100),
    "w_context": (5, 0, 100),
    "min_score": (60, 0, 100),
    "ev_anchor": (0.30, 0.1, 1.0),
    # G. Salidas
    "long_tp_pct": (75, 10, 300),
    "long_sl_pct": (50, 10, 100),
    "spread_tp_pct": (60, 10, 100),
    "spread_sl_pct": (50, 10, 100),
    "exit_on_direction_flip": (True, None, None),
    # H. Gates
    "g1_min_sessions": (5, 1, 60),
    "g1_pct_sessions": (60, 10, 100),
    "g1_min_optionable": (3, 1, 20),
    "g1_max_spread_pct": (10, 2, 25),
    "g1_max_risk_usd": (100, 5, 200),
    "g3_min_weeks": (4, 1, 52),
    "g3_min_trades": (60, 10, 500),
    "g3_calibration_tol_pts": (10, 1, 30),
    # I. Catalizadores y Gate O-12
    "catalyst_adx_override": (35.0, 20.0, 60.0),
    "catalyst_min_score": (45.0, 10.0, 100.0),
    "catalyst_ttl_min": (45, 10, 180),
    "gate_enabled": (True, None, None),
    "gate_gap_min_atr": (0.5, 0.1, 3.0),
    "gate_gap_max_atr": (3.0, 1.0, 10.0),
    "gate_adx_min": (18.0, 10.0, 40.0),
    "gate_flow_min": (60.0, 0.0, 100.0),
    "gate_max_age_sec": (330, 60, 900),
}

SCORE_WEIGHT_KEYS = ("w_expectancy", "w_apex_signal", "w_liquidity", "w_risk", "w_iv_greeks", "w_context")
LOCKED = {"execution_mode": "paper", "max_positions_per_underlying": 1, "market_timezone": "America/New_York"}


def default_settings() -> dict[str, Any]:
    return {k: v[0] for k, v in PARAMS.items()}


def validate_settings(values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Valida y normaliza. Devuelve (valores_limpios, errores). Claves desconocidas = error."""
    clean: dict[str, Any] = {}
    errors: list[str] = []
    for key, val in values.items():
        if key not in PARAMS:
            errors.append(f"{key}: parametro desconocido o bloqueado")
            continue
        default, lo, hi = PARAMS[key]
        if isinstance(default, bool):
            if not isinstance(val, bool):
                errors.append(f"{key}: debe ser booleano")
                continue
            clean[key] = val
        elif isinstance(default, str):
            clean[key] = str(val)[:500]
        else:
            try:
                num = float(val)
            except (TypeError, ValueError):
                errors.append(f"{key}: debe ser numerico")
                continue
            if num < lo or num > hi:
                errors.append(f"{key}: fuera de rango [{lo}, {hi}]")
                continue
            clean[key] = int(num) if isinstance(default, int) else num
    return clean, errors


def validate_cross_rules(merged: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if merged["dte_min"] >= merged["dte_max"]:
        errors.append("dte_min debe ser menor que dte_max")
    if merged["delta_min"] >= merged["delta_max"]:
        errors.append("delta_min debe ser menor que delta_max")
    if merged["spread_width_min"] > merged["spread_width_max"]:
        errors.append("spread_width_min no puede superar spread_width_max")
    if sum(merged[k] for k in SCORE_WEIGHT_KEYS) != 100:
        errors.append("los pesos del score deben sumar 100")
    return errors


def effective_settings(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Defaults + guardado, con techos duros aplicados."""
    merged = default_settings()
    if stored:
        clean, _ = validate_settings(stored)
        merged.update(clean)
    caps = hard_caps()
    merged["max_risk_per_trade_usd"] = min(merged["max_risk_per_trade_usd"], caps["max_risk_per_trade_usd"])
    merged["max_open_risk_usd"] = min(merged["max_open_risk_usd"], caps["max_open_risk_usd"])
    merged["max_daily_selections"] = min(merged["max_daily_selections"], int(caps["max_daily_selections"]))
    return merged
