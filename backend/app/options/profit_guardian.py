"""
Agente Guardián de Ganancias (Profit Guardian) para Opciones.

Proporciona una escalera continua de Trailing Ratchet basada en el pico de prima
alcanzado (`highest_premium_seen` / `peak_pnl_pct`), eliminando:
1. El falso Breakeven prematuro al +5% que cerraba en pérdida por ruido de spread.
2. El hueco sin protección entre +5% y +25% de ganancia.
3. La devolución excesiva de ganancias en picos >= +35% y >= +50%.
"""
from __future__ import annotations

from typing import Any, Dict


def evaluate_option_profit_ratchet(
    entry_premium: float,
    current_premium: float,
    highest_premium_seen: float,
    peak_pnl_pct: float = 0.0,
    is_otm_momentum: bool = False,
    und_pnl_pct: float = 0.0,
    prev_floor_premium: float = 0.0,
) -> Dict[str, Any]:
    """
    Evalúa si el retroceso desde el pico perforó el piso garantizado de ganancia.

    Curva continua y estrictamente ascendente desde +10% de pico:
    - Pico >= +50%: garantiza 75% de la ganancia pico (`OPT_GAP_TRAIL_TIER3`)
    - Pico +25% .. +49.9%: interpola continuamente de +15% a +37.5% (`OPT_GAP_TRAIL_TIER2`)
    - Pico +10% .. +24.9%: interpola continuamente de +2.0% a +15.0% (`OPT_GAP_BE_LOCK_PLUS_1PCT`)
    - Subyacente >= +5% (CALL/PUT): garantiza al menos +1% en prima si no aplica tier mayor
    Monotonicidad estricta: el piso nunca retrocede respecto a `prev_floor_premium`.
    """
    entry_p = float(entry_premium or 0.0)
    cur_p = float(current_premium or 0.0)
    hi_p = max(entry_p, cur_p, float(highest_premium_seen or 0.0))
    prev_floor = float(prev_floor_premium or 0.0)

    if entry_p <= 0.0 or cur_p <= 0.0:
        return {"should_exit": False, "floor_pct": 0.0, "floor_premium": prev_floor if prev_floor > 0.0 else 0.0, "peak_pct": 0.0}

    calc_peak_pct = ((hi_p - entry_p) / entry_p) * 100.0
    eff_peak_pct = max(float(peak_pnl_pct or 0.0), calc_peak_pct)
    # Solo conservar pisos previos que realmente protegen ganancia (>= entry_p); los Hard SL iniciales (< entry_p) no son profit locks.
    prev_profit_floor = prev_floor if prev_floor >= entry_p else 0.0

    floor_pct = 0.0
    rule_code = None
    tier_label = "NONE"

    if eff_peak_pct >= 50.0:
        floor_pct = round(eff_peak_pct * 0.75, 2)
        rule_code = "OPT_GAP_TRAIL_TIER3"
        tier_label = "TIER_3_75PCT_PEAK"
    elif eff_peak_pct >= 25.0:
        floor_pct = round(15.0 + (eff_peak_pct - 25.0) * (22.5 / 25.0), 2)
        rule_code = "OPT_GAP_TRAIL_TIER2"
        tier_label = "TIER_2_CONTINUOUS"
    elif eff_peak_pct >= 10.0:
        floor_pct = round(2.0 + (eff_peak_pct - 10.0) * (13.0 / 15.0), 2)
        rule_code = "OPT_GAP_BE_LOCK_PLUS_1PCT"
        tier_label = "TIER_1_CONTINUOUS"
    elif (not is_otm_momentum) and und_pnl_pct >= 5.0:
        floor_pct = 1.0
        rule_code = "OPT_GAP_BE_LOCK_PLUS_1PCT"
        tier_label = "BE_UNDERLYING_5PCT"

    calc_floor_prem = round(entry_p * (1.0 + floor_pct / 100.0), 4) if floor_pct > 0.0 else 0.0
    floor_premium = max(prev_profit_floor, calc_floor_prem)

    if floor_premium <= 0.0:
        return {
            "should_exit": False,
            "floor_pct": 0.0,
            "floor_premium": 0.0,
            "peak_pct": round(eff_peak_pct, 2),
            "tier": tier_label,
        }

    eff_floor_pct = round(((floor_premium - entry_p) / entry_p) * 100.0, 2) if entry_p > 0 else floor_pct
    if cur_p <= floor_premium:
        if rule_code is None:
            rule_code = "OPT_GAP_TRAIL_TIER3" if eff_floor_pct >= 37.5 else ("OPT_GAP_TRAIL_TIER2" if eff_floor_pct >= 15.0 else "OPT_GAP_BE_LOCK_PLUS_1PCT")
        if rule_code == "OPT_GAP_TRAIL_TIER3":
            reason = (
                f"Tier 3 Ratchet activado: Prima (${cur_p:.2f}) perfora blindaje del 75% pico "
                f"(${floor_premium:.2f}, +{eff_floor_pct:.1f}% neto desde pico +{eff_peak_pct:.1f}%)"
            )
        elif rule_code == "OPT_GAP_TRAIL_TIER2":
            reason = (
                f"Tier 2 Ratchet activado: Prima (${cur_p:.2f}) perfora piso garantizado de "
                f"+{eff_floor_pct:.1f}% (${floor_premium:.2f}, pico +{eff_peak_pct:.1f}%)"
            )
        else:
            reason = (
                f"Breakeven Lock (+{eff_floor_pct:.1f}% Protegido): Ganancia previa alcanzó +{eff_peak_pct:.1f}% "
                f"(subyacente +{und_pnl_pct:.2f}%). Prima ${cur_p:.2f} <= piso ${floor_premium:.2f}"
            )
        return {
            "should_exit": True,
            "exit_type": "trailing_stop",
            "rule_code": rule_code,
            "floor_pct": eff_floor_pct,
            "floor_premium": floor_premium,
            "peak_pct": round(eff_peak_pct, 2),
            "tier": tier_label,
            "reason": reason,
        }

    return {
        "should_exit": False,
        "floor_pct": eff_floor_pct,
        "floor_premium": floor_premium,
        "peak_pct": round(eff_peak_pct, 2),
        "tier": tier_label,
    }


def compute_dynamic_underlying_trailing_sl(
    entry_underlying: float,
    current_underlying: float,
    current_sl: float = 0.0,
    atr_15m: float = 0.0,
    is_put: bool = False,
    lowest_underlying_seen: float = 0.0,
    highest_underlying_seen: float = 0.0,
) -> Dict[str, Any]:
    """
    Calcula Trailing Stop continuo y estrictamente monotónico sobre el precio subyacente
    para opciones PUT (techo descendente según `lowest_underlying_seen`) y CALL (piso ascendente
    según `highest_underlying_seen`). Sin zona muerta entre 0% y ±5% y con colchón mínimo sobre el precio vivo.
    """
    cur_u = float(current_underlying or 0.0)
    cur_sl_r = round(float(current_sl or 0.0), 2)
    if cur_u <= 0.0:
        return {
            "stop_loss_underlying": cur_sl_r,
            "updated": False,
            "trailing_sl_type": "",
            "lowest_underlying_seen": float(lowest_underlying_seen or 0.0),
            "highest_underlying_seen": float(highest_underlying_seen or 0.0),
            "peak_move_pct": 0.0,
        }

    entry_u = float(entry_underlying or 0.0) or cur_u
    atr_pct = (float(atr_15m) / cur_u) if (atr_15m and float(atr_15m) > 0.0) else 0.0

    def _trail_band(peak_move_pct: float) -> float:
        if peak_move_pct < 1.0:
            return min(0.030, max(0.020, 1.5 * atr_pct)) if atr_pct > 0.0 else 0.025
        if peak_move_pct < 3.0:
            return 0.020
        if peak_move_pct < 5.0:
            return 0.015
        return 0.012

    if is_put:
        lo_base = float(lowest_underlying_seen or 0.0)
        lo = min(lo_base, cur_u) if lo_base > 0.0 else min(entry_u, cur_u)
        lo_r = round(lo, 4)
        peak_move_pct = ((entry_u - lo) / entry_u) * 100.0 if entry_u > 0.0 else 0.0

        if peak_move_pct < 0.5:
            if cur_sl_r <= 0.0:
                init_sl = round(max(entry_u, cur_u) * 1.03, 2)
                return {
                    "stop_loss_underlying": init_sl,
                    "updated": True,
                    "trailing_sl_type": "INITIAL_PUT_SL",
                    "lowest_underlying_seen": lo_r,
                    "highest_underlying_seen": float(highest_underlying_seen or 0.0),
                    "peak_move_pct": round(peak_move_pct, 2),
                }
            return {
                "stop_loss_underlying": cur_sl_r,
                "updated": False,
                "trailing_sl_type": "",
                "lowest_underlying_seen": lo_r,
                "highest_underlying_seen": float(highest_underlying_seen or 0.0),
                "peak_move_pct": round(peak_move_pct, 2),
            }

        trail_pct = _trail_band(peak_move_pct)
        raw_cand = lo * (1.0 + trail_pct)
        if peak_move_pct >= 5.0:
            profit_ceiling = min(entry_u * 0.99, entry_u * (1.0 - (peak_move_pct * 0.60) / 100.0))
            raw_cand = min(raw_cand, profit_ceiling)

        min_allowed = round(cur_u * 1.003, 2)
        cand = round(max(raw_cand, min_allowed), 2)
        if (cur_sl_r <= 0.0 or cand < cur_sl_r) and cand > cur_u:
            sl_type = (
                "BE_LOCK_PLUS_1PCT"
                if (peak_move_pct >= 5.0 and cand <= round(entry_u * 0.99, 2))
                else "TRAIL_PUT_CONTINUOUS"
            )
            return {
                "stop_loss_underlying": cand,
                "updated": True,
                "trailing_sl_type": sl_type,
                "lowest_underlying_seen": lo_r,
                "highest_underlying_seen": float(highest_underlying_seen or 0.0),
                "peak_move_pct": round(peak_move_pct, 2),
            }

        return {
            "stop_loss_underlying": cur_sl_r,
            "updated": False,
            "trailing_sl_type": "",
            "lowest_underlying_seen": lo_r,
            "highest_underlying_seen": float(highest_underlying_seen or 0.0),
            "peak_move_pct": round(peak_move_pct, 2),
        }

    # CALL: piso estrictamente ascendente
    hi_base = float(highest_underlying_seen or 0.0)
    hi = max(hi_base, cur_u) if hi_base > 0.0 else max(entry_u, cur_u)
    hi_r = round(hi, 4)
    peak_move_pct = ((hi - entry_u) / entry_u) * 100.0 if entry_u > 0.0 else 0.0

    if peak_move_pct < 0.5:
        if cur_sl_r <= 0.0:
            init_sl = round(min(entry_u, cur_u) * 0.97, 2)
            return {
                "stop_loss_underlying": init_sl,
                "updated": True,
                "trailing_sl_type": "INITIAL_CALL_SL",
                "lowest_underlying_seen": float(lowest_underlying_seen or 0.0),
                "highest_underlying_seen": hi_r,
                "peak_move_pct": round(peak_move_pct, 2),
            }
        return {
            "stop_loss_underlying": cur_sl_r,
            "updated": False,
            "trailing_sl_type": "",
            "lowest_underlying_seen": float(lowest_underlying_seen or 0.0),
            "highest_underlying_seen": hi_r,
            "peak_move_pct": round(peak_move_pct, 2),
        }

    trail_pct = _trail_band(peak_move_pct)
    raw_cand = hi * (1.0 - trail_pct)
    if peak_move_pct >= 5.0:
        profit_floor = max(entry_u * 1.01, entry_u * (1.0 + (peak_move_pct * 0.60) / 100.0))
        raw_cand = max(raw_cand, profit_floor)

    max_allowed = round(cur_u * 0.997, 2)
    cand = round(min(raw_cand, max_allowed), 2)
    if (cur_sl_r <= 0.0 or cand > cur_sl_r) and cand < cur_u:
        sl_type = (
            "BE_LOCK_PLUS_1PCT"
            if (peak_move_pct >= 5.0 and cand >= round(entry_u * 1.01, 2))
            else "TRAIL_CALL_CONTINUOUS"
        )
        return {
            "stop_loss_underlying": cand,
            "updated": True,
            "trailing_sl_type": sl_type,
            "lowest_underlying_seen": float(lowest_underlying_seen or 0.0),
            "highest_underlying_seen": hi_r,
            "peak_move_pct": round(peak_move_pct, 2),
        }

    return {
        "stop_loss_underlying": cur_sl_r,
        "updated": False,
        "trailing_sl_type": "",
        "lowest_underlying_seen": float(lowest_underlying_seen or 0.0),
        "highest_underlying_seen": hi_r,
        "peak_move_pct": round(peak_move_pct, 2),
    }
