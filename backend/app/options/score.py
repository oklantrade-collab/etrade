"""Motor de puntuacion de candidatas APEX Options (Sprint 5).
Escala 0-100 normalizada. Combina 6 factores ponderados configurables en Settings.
Un score alto nunca vuelve elegible una operacion invalida.
"""
from __future__ import annotations

from typing import Any

from app.options.aduana_gap_runner_options import get_asset_class, get_min_gap_threshold

MODEL_VERSION = "v1.0-s5"


def is_gap_runner_opportunity(cand: dict[str, Any], underlying: dict[str, Any] | None = None) -> tuple[bool, str | None, float]:
    """
    Determina si una oportunidad califica como ADUANA GAP RUNNER (CALL para Gap Up, PUT para Gap Down).
    Retorna (is_runner, gap_type, gap_pct).
    """
    if underlying is None:
        underlying = {}

    # 1. Indicadores explícitos en la candidata
    exit_plan = cand.get("exit_plan") or {}
    score_bd = cand.get("score_breakdown") or {}
    if cand.get("is_gap_runner") or exit_plan.get("is_gap_runner") or score_bd.get("is_gap_runner"):
        gtype = cand.get("gap_type") or exit_plan.get("gap_type") or score_bd.get("gap_type") or (
            "OPEN_GAP_UP" if str(cand.get("direction")).upper() in ("CALL", "BULLISH") else "OPEN_GAP_DOWN"
        )
        gpct = float(cand.get("gap_pct") or exit_plan.get("gap_pct") or score_bd.get("gap_pct") or 0.0)
        return True, gtype, gpct

    if cand.get("direction_source") == "gap_runner" or cand.get("strategy_type") in ("gap_runner_call", "gap_runner_put"):
        gtype = "OPEN_GAP_UP" if str(cand.get("direction")).upper() in ("CALL", "BULLISH") else "OPEN_GAP_DOWN"
        return True, gtype, float(cand.get("gap_pct") or 0.0)

    # 2. Indicadores en el subyacente
    sym = (underlying.get("symbol") or cand.get("symbol") or "").upper()
    if not sym:
        return False, None, 0.0

    min_gap = get_min_gap_threshold(sym)
    cand_dir = (cand.get("direction") or underlying.get("direction") or "").lower()
    is_bullish = cand_dir in ("call", "bullish")
    is_bearish = cand_dir in ("put", "bearish")

    # Revisar catalyst_meta o c1_gap en el underlying
    cat_meta = underlying.get("catalyst_meta") or {}
    c1 = cat_meta.get("c1_gap") or {}
    gap_pct = float(c1.get("gap_pct") or underlying.get("gap_pct") or cand.get("gap_pct") or 0.0)

    if is_bullish and gap_pct >= min_gap:
        return True, "OPEN_GAP_UP", gap_pct
    if is_bearish and gap_pct <= -min_gap:
        return True, "OPEN_GAP_DOWN", gap_pct

    return False, None, gap_pct




def classify_options_opportunity_setup(cand: dict[str, Any], underlying: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Clasifica la oportunidad en uno de los 3 arquetipos institucionales de alta probabilidad:
    1. Setup 1: CATALYST_GAP (Gap >= 1.2% / <= -1.2%, noticia/catalizador activo, RVOL >= 1.8x).
    2. Setup 2: VOLUME_IGNITION (RVOL >= 2.5x, Buying Force >= 65 para CALL o <= 35 para PUT).
    3. Setup 3: MEAN_REVERSION_1H (RSI 1H <= 28 para CALL o >= 72 para PUT / giro en extremo).
    
    Aplica el Dead Stock Shield:
    - Si no cumple ninguno de los 3 setups y RVOL < 1.8x, |Gap| < 1.2% y sin noticias -> IS_DEAD_STOCK = True
    """
    if underlying is None:
        underlying = {}

    sym = (cand.get("symbol") or underlying.get("symbol") or "").upper()
    cand_dir = (cand.get("direction") or underlying.get("direction") or "").lower()
    is_bull = cand_dir in ("call", "bullish")
    is_bear = cand_dir in ("put", "bearish")

    # Gap %
    cat_meta = underlying.get("catalyst_meta") or {}
    c1 = cat_meta.get("c1_gap") or {}
    gap_pct = float(
        cand.get("gap_pct")
        or (cand.get("exit_plan") or {}).get("gap_pct")
        or (cand.get("score_breakdown") or {}).get("gap_pct")
        or c1.get("gap_pct")
        or underlying.get("gap_pct")
        or underlying.get("change_pct")
        or 0.0
    )

    # News catalyst
    has_news = bool(
        underlying.get("has_news")
        or cand.get("has_news")
        or underlying.get("news_catalyst")
        or (float(underlying.get("catalyst_score") or 0) >= 60)
        or (cand.get("direction_source") == "catalyst")
    )

    # RVOL (Volumen Relativo)
    rvol = float(
        underlying.get("rvol")
        or cand.get("rvol")
        or (underlying.get("atm_volume", 0) / max(1, underlying.get("atm_oi", 1)))
        or 1.0
    )

    # Buying Force / APEX Signal
    apex_score = float(underlying.get("apex_score") or cand.get("apex_score") or 50.0)
    bf = float(underlying.get("buying_force_5m") or apex_score)

    # 1H RSI
    rsi_1h = float(underlying.get("rsi_1h") or underlying.get("rsi_14") or 50.0)

    # ── EVALUACIÓN DE RÉGIMEN ESTRUCTURAL 1D (EMA 3/9/20/50/200 + VWAP + ATR) ──
    try:
        from app.core.structural_regime_engine import evaluate_structural_regime
        p_val = float(cand.get("price") or underlying.get("price") or 0.0)
        regime = evaluate_structural_regime(sym, p_val)
    except Exception as e_reg:
        regime = {"regime_code": "NEUTRAL", "regime_label": "⚪ NEUTRAL", "is_deep_bear_excluded": False, "key_levels_1d": {}}

    # 1. CANDADO MACRO SECULAR: DEEP BEAR WINTER (Bajo EMA50/200)
    # Evita atrapar capital durante meses en activos en invierno bajista
    if is_bull and regime.get("is_deep_bear_excluded"):
        return {
            "setup_name": "DEEP_BEAR_WINTER",
            "setup_label": regime.get("regime_label") or "⛔ DEEP BEAR WINTER",
            "setup_bonus": -50.0,
            "is_dead_stock": True,
            "is_eligible": False,
            "rejection_reason": "deep_bear_winter: subyacente bajo EMA50/200, riesgo de meses atrapado",
            "structural_regime": regime,
        }

    # 2. SETUP ALCISTA INSTITUCIONAL: BULL_TREND_EXPANSION (Caso DIS)
    if is_bull and regime.get("regime_code") == "BULL_TREND_EXPANSION":
        return {
            "setup_name": "BULL_TREND_EXPANSION",
            "setup_label": regime.get("regime_label") or "🟢 BULL EXPANSION (EMA 3>9>20>50>200)",
            "setup_bonus": 35.0,
            "is_dead_stock": False,
            "is_eligible": True,
            "rejection_reason": None,
            "structural_regime": regime,
        }

    # 3. REBOTE TÁCTICO CONTRATENDENCIA (Caso AAL)
    if regime.get("regime_code") == "COUNTER_TREND_BOUNCE":
        wall = regime.get("target_resistance_wall", 0.0)
        # Si está rozando la EMA20 diaria (< 1.2% de distancia)
        if abs(regime.get("room_to_resistance_pct", 0.0)) <= 1.2:
            if is_bear:
                return {
                    "setup_name": "REJECTION_PUT_EMA20",
                    "setup_label": f"🎯 RECHAZO EN RESISTENCIA EMA20 (${wall:.2f})",
                    "setup_bonus": 30.0,
                    "is_dead_stock": False,
                    "is_eligible": True,
                    "rejection_reason": None,
                    "structural_regime": regime,
                }
            else:
                return {
                    "setup_name": "ROOF_RESISTANCE_BLOCKED",
                    "setup_label": f"⛔ TECHO EN RESISTENCIA EMA20 (${wall:.2f})",
                    "setup_bonus": -35.0,
                    "is_dead_stock": True,
                    "is_eligible": False,
                    "rejection_reason": f"techo_ema20: el subyacente choca contra la EMA20 diaria (${wall:.2f})",
                    "structural_regime": regime,
                }
        else:
            if is_bull and rvol >= 1.8:
                return {
                    "setup_name": "TACTICAL_SCALP_INTRADAY",
                    "setup_label": f"🟡 REBOTE TÁCTICO INTRADÍA (Target EMA20: ${wall:.2f})",
                    "setup_bonus": 20.0,
                    "is_dead_stock": False,
                    "is_eligible": True,
                    "rejection_reason": None,
                    "structural_regime": regime,
                }

    # SETUP 1: CATALYST GAP
    min_gap = get_min_gap_threshold(sym) if sym else 1.2
    is_gap_valid = (is_bull and gap_pct >= min_gap) or (is_bear and gap_pct <= -min_gap)
    if is_gap_valid and has_news and rvol >= 1.8:
        return {
            "setup_name": "CATALYST_GAP",
            "setup_label": f"🚀 SETUP 1: CATALYST GAP ({gap_pct:+.1f}% RVOL {rvol:.1f}x)",
            "setup_bonus": 30.0,
            "is_dead_stock": False,
            "is_eligible": True,
            "rejection_reason": None,
            "structural_regime": regime,
        }

    # SETUP 2: INSTITUTIONAL VOLUME IGNITION
    if rvol >= 2.5:
        if (is_bull and bf >= 65.0) or (is_bear and bf <= 35.0):
            return {
                "setup_name": "VOLUME_IGNITION",
                "setup_label": f"🔥 SETUP 2: IGNICIÓN INSTITUCIONAL (RVOL {rvol:.1f}x)",
                "setup_bonus": 25.0,
                "is_dead_stock": False,
                "is_eligible": True,
                "rejection_reason": None,
            }

    # SETUP 3: 1-HOUR MEAN REVERSION
    if (is_bull and rsi_1h <= 28.0) or (is_bear and rsi_1h >= 72.0):
        return {
            "setup_name": "MEAN_REVERSION_1H",
            "setup_label": f"🎯 SETUP 3: REVERSIÓN 1H (RSI {rsi_1h:.1f})",
            "setup_bonus": 20.0,
            "is_dead_stock": False,
            "is_eligible": True,
            "rejection_reason": None,
            "structural_regime": regime,
        }

    # DEAD STOCK SHIELD
    # Si la acción está dormida sin catalizador ni volumen anormal (ej. AAL)
    is_dead = (rvol < 1.8) and (abs(gap_pct) < 1.2) and (not has_news)
    if is_dead:
        return {
            "setup_name": "DEAD_STOCK",
            "setup_label": "⛔ ACCIÓN DORMIDA / SIN SETUP (DEAD STOCK SHIELD)",
            "setup_bonus": -40.0,
            "is_dead_stock": True,
            "is_eligible": False,
            "rejection_reason": "dead_stock_shield: subyacente sin catalizador de noticias, sin volumen anormal ni reversión 1H",
        }

    # Setup estándar
    return {
        "setup_name": "STANDARD",
        "setup_label": "⚪ SETUP ESTÁNDAR (MONITOREANDO)",
        "setup_bonus": 0.0,
        "is_dead_stock": False,
        "is_eligible": True,
        "rejection_reason": None,
    }


def _clip(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(val)))


def compute_expectancy_score(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 1: Expectativa neta (ev_view_net / max_loss).
    Normalizacion lineal: 0 si <= 0; 100 si >= ev_anchor (default 0.30 = 30%).
    """
    ev_ratio = cand.get("ev_ratio")
    if ev_ratio is None:
        ev = cand.get("ev_view_net")
        loss = cand.get("max_loss_contract") or cand.get("max_loss_total")
        if ev is not None and loss and loss > 0:
            ev_ratio = ev / loss
        else:
            ev_ratio = 0.0

    anchor = float(eff.get("ev_anchor") or 0.30)
    if anchor <= 0:
        anchor = 0.30

    if ev_ratio <= 0:
        score = 0.0
    elif ev_ratio >= anchor:
        score = 100.0
    else:
        score = (ev_ratio / anchor) * 100.0

    return _clip(score), {"ev_ratio": round(ev_ratio, 4), "ev_anchor": anchor, "ev_view_net": cand.get("ev_view_net")}


def compute_apex_signal_score(cand: dict[str, Any], underlying: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 2: Calidad de senal APEX o Catalizador del subyacente.
    Score en escala 0-100. Coherencia direccional obligatoria.
    """
    apex_score = underlying.get("apex_score")
    if apex_score is None:
        apex_score = 50.0
    else:
        apex_score = float(apex_score)

    cand_dir = (cand.get("direction") or "").lower()
    raw_und_dir = underlying.get("direction") or ""
    # Normalizar CALL/PUT o bullish/bearish
    und_dir = "bullish" if raw_und_dir in ("CALL", "bullish") else ("bearish" if raw_und_dir in ("PUT", "bearish") else raw_und_dir.lower())
    cand_norm_dir = "bullish" if cand_dir in ("call", "bullish") else ("bearish" if cand_dir in ("put", "bearish") else cand_dir)

    dir_source = cand.get("direction_source") or underlying.get("direction_source") or "unverified"
    is_runner, gap_type, gap_pct = is_gap_runner_opportunity(cand, underlying)

    if dir_source == "gap_runner" or is_runner:
        score = 100.0
        note = f"🚀 ADUANA GAP RUNNER ({gap_type or 'RUNNER'} {gap_pct:+.2f}%)"
        return _clip(score), {
            "direction_source": "gap_runner",
            "apex_score": 100.0,
            "note": note,
            "is_gap_runner": True,
            "gap_type": gap_type,
            "gap_pct": gap_pct
        }

    if dir_source == "catalyst":
        cat_score = float(underlying.get("catalyst_score") or cand.get("catalyst_score") or 60.0)
        if und_dir and cand_norm_dir and cand_norm_dir != und_dir:
            score = 0.0
            note = f"direccion opuesta al catalizador ({cand_norm_dir} vs {und_dir})"
        else:
            score = cat_score
            note = f"coherente con catalizador ({raw_und_dir})"
        return _clip(score), {"catalyst_score": cat_score, "direction_source": "catalyst", "note": note}

    if dir_source == "apex":
        if und_dir and cand_norm_dir != und_dir:
            score = 0.0
            note = f"direccion opuesta a la senal APEX ({cand_norm_dir} vs {und_dir})"
        else:
            score = apex_score
            note = f"coherente con senal APEX ({und_dir})"
    else:
        # Direccion no verificada: penalizacion del 40% respecto al score base
        score = min(apex_score * 0.60, 50.0)
        note = "direccion no verificada (penalizacion aplicada)"

    return _clip(score), {"apex_score": apex_score, "direction_source": dir_source, "note": note}


def compute_liquidity_score(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 3: Liquidez y calidad de cotizacion.
    Spread relativo (0% -> 100, 10% -> 0), OI/volumen y estado del dato de mercado.
    """
    legs = cand.get("legs") or []
    if not legs:
        return 0.0, {"reason": "sin piernas"}

    spreads = []
    ois = []
    states = []

    for lg in legs:
        bid = lg.get("bid")
        ask = lg.get("ask")
        if bid is not None and ask is not None and (bid + ask) > 0:
            mid = (bid + ask) / 2.0
            rel_spread = (ask - bid) / mid
            spreads.append(rel_spread)
        else:
            spreads.append(1.0)  # max spread si falta cotizacion

        oi = lg.get("open_interest")
        ois.append(float(oi) if oi is not None else 0.0)
        states.append(lg.get("market_data_type") or "UNKNOWN")

    max_spread = max(spreads) if spreads else 1.0
    min_oi = min(ois) if ois else 0.0

    # Spread score: 0% -> 100, 10% (0.10) -> 0
    if max_spread <= 0:
        spread_score = 100.0
    elif max_spread >= 0.10:
        spread_score = 0.0
    else:
        spread_score = (1.0 - (max_spread / 0.10)) * 100.0

    # OI score: >= 500 -> 100, <= 50 -> 20
    if min_oi >= 500:
        oi_score = 100.0
    elif min_oi <= 50:
        oi_score = 20.0
    else:
        oi_score = 20.0 + ((min_oi - 50.0) / (500.0 - 50.0)) * 80.0

    raw_liquidity = 0.60 * spread_score + 0.40 * oi_score

    # Ajuste por estado del dato
    allow_delayed = bool(eff.get("allow_delayed_data"))
    has_delayed = any(s == "DELAYED" for s in states)
    has_bad = any(s in ("STALE", "FROZEN", "UNKNOWN") for s in states)

    if has_bad:
        data_mult = 0.0
        data_note = "cotizaciones stale o frozen"
    elif has_delayed:
        if allow_delayed:
            data_mult = 0.70  # 30% de penalizacion por dato diferido en modo prueba
            data_note = "dato diferido permitido en modo prueba (-30%)"
        else:
            data_mult = 0.0
            data_note = "dato diferido no permitido"
    else:
        data_mult = 1.0
        data_note = "datos LIVE"

    final_score = raw_liquidity * data_mult
    return _clip(final_score), {
        "max_rel_spread_pct": round(max_spread * 100, 2),
        "min_oi": int(min_oi),
        "raw_liquidity": round(raw_liquidity, 1),
        "data_multiplier": data_mult,
        "data_note": data_note,
    }


def compute_risk_score(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 4: Riesgo y escenarios adversos.
    Drawdown en peor escenario simulado vs max_loss y sobrecoste de ejecucion.
    """
    max_loss = cand.get("max_loss_contract") or cand.get("max_loss_total") or 1.0
    worst_pnl = cand.get("worst_adverse_scenario_pnl")
    if worst_pnl is None:
        worst_pnl = -max_loss

    # Preservacion frente a max loss: si el peor escenario pierde menos que el max loss teorico
    # (ej. salida anticipada o spread que acota la perdida)
    loss_ratio = abs(float(worst_pnl)) / float(max_loss) if max_loss > 0 else 1.0
    drawdown_score = _clip((1.0 - min(loss_ratio, 1.0)) * 100.0)

    # Sobrecoste de ejecucion (slippage sobre mid)
    overcost = float(cand.get("exec_overcost_pct") or 0.0)
    max_overcost = float(eff.get("max_exec_overcost_pct") or 25.0)
    if max_overcost <= 0:
        overcost_score = 100.0
    else:
        overcost_score = _clip((1.0 - (overcost / max_overcost)) * 100.0)

    # EV adverso: si la expectativa con ejecucion adversa sigue siendo positiva, da bonus
    ev_adv = cand.get("ev_view_adverse")
    if ev_adv is not None and max_loss > 0:
        ev_adv_ratio = float(ev_adv) / float(max_loss)
        ev_adv_score = _clip(50.0 + (ev_adv_ratio / 0.20) * 50.0)
    else:
        ev_adv_score = 50.0

    final_score = 0.40 * drawdown_score + 0.30 * overcost_score + 0.30 * ev_adv_score
    return _clip(final_score), {
        "drawdown_score": round(drawdown_score, 1),
        "overcost_score": round(overcost_score, 1),
        "ev_adverse_score": round(ev_adv_score, 1),
        "exec_overcost_pct": overcost,
    }


def compute_iv_greeks_score(cand: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 5: IV y griegas.
    Penaliza IV muy alta en estrategias compradas (riesgo de crush);
    premia deltas optimos (0.40-0.60 en piernas largas, delta neto moderado en spreads).
    """
    legs = cand.get("legs") or []
    strategy = cand.get("strategy_type") or ""

    # IV de la pierna larga principal
    ivs = [float(l["iv"]) for l in legs if l.get("iv") is not None]
    avg_iv = sum(ivs) / len(ivs) if ivs else 0.50

    # IV score: IV moderada (20%-40%) es ideal para compras; >80% castigada
    if avg_iv <= 0.35:
        iv_score = 100.0
    elif avg_iv <= 0.60:
        iv_score = 100.0 - ((avg_iv - 0.35) / 0.25) * 30.0  # 100 -> 70
    elif avg_iv <= 1.00:
        iv_score = 70.0 - ((avg_iv - 0.60) / 0.40) * 45.0   # 70 -> 25
    else:
        iv_score = max(0.0, 25.0 - ((avg_iv - 1.00) / 0.50) * 25.0)

    # Delta sweet spot
    long_legs = [l for l in legs if l.get("side") == "buy"]
    if long_legs and long_legs[0].get("delta") is not None:
        delta = abs(float(long_legs[0]["delta"]))
        # punto optimo 0.50 (ATM)
        dist_from_target = abs(delta - 0.50)
        delta_score = _clip((1.0 - (dist_from_target / 0.30)) * 100.0)
    else:
        delta_score = 50.0

    final_score = 0.50 * iv_score + 0.50 * delta_score
    return _clip(final_score), {
        "avg_iv": round(avg_iv, 4),
        "iv_score": round(iv_score, 1),
        "delta_score": round(delta_score, 1),
        "strategy": strategy,
    }


def compute_context_score(cand: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 6: Catalizadores y contexto (eventos dentro del DTE).
    100 si no hay evento binario reportado; 50 si no esta verificado; 0 si hay evento bloqueante.
    """
    event_flags = underlying.get("event_flags")
    warnings = underlying.get("warnings") or []
    is_unverified = any("no verificado" in str(w) for w in warnings) or event_flags is None

    if is_unverified:
        score = 50.0
        note = "eventos no verificados (neutral)"
    elif len(event_flags) == 0:
        score = 100.0
        note = "sin eventos binarios dentro del DTE"
    else:
        # Hay eventos reportados (earnings, etc.)
        if eff.get("block_events_in_dte", True):
            score = 0.0
            note = f"evento presente ({', '.join(event_flags)})"
        else:
            score = 30.0
            note = f"evento presente pero no bloqueado ({', '.join(event_flags)})"

    return _clip(score), {"event_flags": event_flags or [], "note": note}


def compute_potential_benefit_metrics(cand: dict[str, Any], eff: dict[str, Any] | None = None) -> dict[str, float]:
    """Calcula las métricas de beneficio potencial real y ponderado en dólares ($ USD)."""
    eff = eff or {}
    qty = max(1, int(cand.get("qty") or 1))
    loss_tot = float(cand.get("max_loss_total") or 0.0)
    if loss_tot <= 0:
        loss_tot = float(cand.get("max_loss_contract") or 0.0) * qty

    mpc = cand.get("max_profit_contract")
    debit = float(cand.get("entry_debit") or 0.0)
    exit_plan = cand.get("exit_plan") or {}

    if mpc is not None and float(mpc) > 0:
        pot_profit_contract = float(mpc)
    else:
        # Outright Call / Put
        tp_px = float(exit_plan.get("take_profit_premium") or 0.0)
        if tp_px > debit:
            pot_profit_contract = (tp_px - debit) * 100.0
        else:
            tp_pct = float(eff.get("long_tp_pct", 50.0)) / 100.0
            pot_profit_contract = debit * 100.0 * tp_pct

    pot_profit_total = pot_profit_contract * qty
    ev_net = float(cand.get("ev_view_net") or 0.0)
    ev_total = ev_net * qty
    r2r = (pot_profit_total / loss_tot) if loss_tot > 0 else 0.0
    score = float(cand.get("score") or 0.0)

    # Benefit Index: Prioriza beneficio neto esperado en dólares, ganancia potencial máxima y calidad técnica
    benefit_index = (ev_total * 0.40) + (pot_profit_total * 0.30) + (score * 2.0)

    return {
        "pot_profit_total": round(pot_profit_total, 2),
        "ev_total_usd": round(ev_total, 2),
        "reward_to_risk": round(r2r, 2),
        "benefit_index": round(benefit_index, 2),
        "loss_total": round(loss_tot, 2),
    }


def score_candidate(cand: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> dict[str, Any]:
    """Calcula el Options Score total (0-100) y su desglose completo por componentes.
    Pesos configurables en Settings:
      - w_expectancy (30%)
      - w_apex_signal (20%)
      - w_liquidity (20%)
      - w_risk (15%)
      - w_iv_greeks (10%)
      - w_context (5%)
    """
    w_exp = float(eff.get("w_expectancy", 30))
    w_apex = float(eff.get("w_apex_signal", 20))
    w_liq = float(eff.get("w_liquidity", 20))
    w_risk = float(eff.get("w_risk", 15))
    w_iv = float(eff.get("w_iv_greeks", 10))
    w_ctx = float(eff.get("w_context", 5))

    total_w = w_exp + w_apex + w_liq + w_risk + w_iv + w_ctx
    if total_w <= 0:
        total_w = 100.0

    s_exp, d_exp = compute_expectancy_score(cand, eff)
    s_apex, d_apex = compute_apex_signal_score(cand, underlying)
    s_liq, d_liq = compute_liquidity_score(cand, eff)
    s_risk, d_risk = compute_risk_score(cand, eff)
    s_iv, d_iv = compute_iv_greeks_score(cand)
    s_ctx, d_ctx = compute_context_score(cand, underlying, eff)

    weighted_sum = (
        s_exp * w_exp +
        s_apex * w_apex +
        s_liq * w_liq +
        s_risk * w_risk +
        s_iv * w_iv +
        s_ctx * w_ctx
    )
    raw_base_score = round(_clip(weighted_sum / total_w), 1)

    # Detección y Clasificación Institucional de Setups & Dead Stock Shield
    setup_info = classify_options_opportunity_setup(cand, underlying)
    setup_bonus = setup_info["setup_bonus"]
    is_dead_stock = setup_info["is_dead_stock"]

    is_runner, gap_type, gap_pct = is_gap_runner_opportunity(cand, underlying)
    gap_runner_boost = 25.0 if is_runner else 0.0

    # ── MODULACIÓN POR MACRO SENTIMENT (SPY, QQQ, VIX) (Propuesta #1) ──
    macro_regime = "NEUTRAL"
    macro_label = "🟡 Neutral"
    macro_adj = 0.0
    is_call_side = str(cand.get("direction", "")).lower() == "bullish" or "call" in str(cand.get("strategy_type", "")).lower()
    is_put_side = str(cand.get("direction", "")).lower() == "bearish" or "put" in str(cand.get("strategy_type", "")).lower()

    try:
        from app.core.macro_sentiment_engine import evaluate_macro_sentiment
        macro_eval = evaluate_macro_sentiment()
        macro_regime = macro_eval.get("regime", "NEUTRAL")
        macro_label = macro_eval.get("label", "🟡 Neutral")

        if macro_regime == "RISK_OFF":
            if is_call_side:
                macro_adj = -40.0  # Castigo severo a Calls en día de sangría
            elif is_put_side:
                macro_adj = +25.0  # Bonificación a Puts / Spreads bajistas para seguir marea
        elif macro_regime == "RISK_ON":
            if is_call_side:
                macro_adj = +15.0  # Impulso a Calls con viento macro a favor
            elif is_put_side:
                macro_adj = -20.0  # Penalización a Puts en mercado en rally
    except Exception:
        pass

    min_score = float(eff.get("min_score", 60))
    if is_dead_stock:
        final_score = 0.0
        eligible_by_score = False
    else:
        effective_boost = max(setup_bonus, gap_runner_boost)
        final_score = round(max(0.0, min(100.0, raw_base_score + effective_boost + macro_adj)), 1)
        # En RISK_OFF, deshabilitar calls automáticamente
        if macro_regime == "RISK_OFF" and is_call_side:
            eligible_by_score = False
        else:
            eligible_by_score = final_score >= min_score and setup_info["is_eligible"]

    # Check missing components and calculate coverage (§5, §9.1)
    missing_components = []
    # Essential components: expectancy, liquidity, risk
    if cand.get("ev_view_net") is None:
        missing_components.append("expectancy")
    legs = cand.get("legs") or []
    if not legs or any(l.get("bid") is None or l.get("ask") is None for l in legs):
        missing_components.append("liquidity")
    if not (cand.get("max_loss_contract") or cand.get("max_loss_total")):
        missing_components.append("risk")
    if not legs or any(l.get("iv") is None for l in legs):
        missing_components.append("iv_greeks")
    if not (cand.get("direction_source") or underlying.get("direction")):
        missing_components.append("apex_signal")
    if underlying.get("event_flags") is None and not cand.get("event_state"):
        missing_components.append("context")

    total_components_count = 6
    present_count = total_components_count - len(missing_components)
    coverage = round(present_count / total_components_count, 2)

    components_list = [
        {
            "name": "expectancy",
            "weight": round(w_exp / total_w, 2),
            "score": s_exp,
            "contribution": round(s_exp * w_exp / total_w, 2),
            "inputs": d_exp,
            "sub_scores": {"ev_ratio": d_exp.get("ev_ratio")},
            "multiplier": 1.0,
            "notes": [],
        },
        {
            "name": "apex_signal",
            "weight": round(w_apex / total_w, 2),
            "score": s_apex,
            "contribution": round(s_apex * w_apex / total_w, 2),
            "inputs": {"direction_source": d_apex.get("direction_source")},
            "sub_scores": {"raw_score": d_apex.get("apex_score") or d_apex.get("catalyst_score")},
            "multiplier": 1.0,
            "notes": [d_apex.get("note")] if d_apex.get("note") else [],
        },
        {
            "name": "liquidity",
            "weight": round(w_liq / total_w, 2),
            "score": s_liq,
            "contribution": round(s_liq * w_liq / total_w, 2),
            "inputs": {
                "max_rel_spread_pct": d_liq.get("max_rel_spread_pct"),
                "min_oi": d_liq.get("min_oi"),
            },
            "sub_scores": {"raw_liquidity": d_liq.get("raw_liquidity")},
            "multiplier": d_liq.get("data_multiplier", 1.0),
            "notes": [d_liq.get("data_note")] if d_liq.get("data_note") else [],
        },
        {
            "name": "risk",
            "weight": round(w_risk / total_w, 2),
            "score": s_risk,
            "contribution": round(s_risk * w_risk / total_w, 2),
            "inputs": {"exec_overcost_pct": d_risk.get("exec_overcost_pct")},
            "sub_scores": {
                "drawdown": d_risk.get("drawdown_score"),
                "overcost": d_risk.get("overcost_score"),
                "ev_adverse": d_risk.get("ev_adverse_score"),
            },
            "multiplier": 1.0,
            "notes": [],
        },
        {
            "name": "iv_greeks",
            "weight": round(w_iv / total_w, 2),
            "score": s_iv,
            "contribution": round(s_iv * w_iv / total_w, 2),
            "inputs": {"avg_iv": d_iv.get("avg_iv")},
            "sub_scores": {"iv_score": d_iv.get("iv_score"), "delta_score": d_iv.get("delta_score")},
            "multiplier": 1.0,
            "notes": [],
        },
        {
            "name": "context",
            "weight": round(w_ctx / total_w, 2),
            "score": s_ctx,
            "contribution": round(s_ctx * w_ctx / total_w, 2),
            "inputs": {"event_flags": d_ctx.get("event_flags")},
            "sub_scores": {},
            "multiplier": 1.0,
            "notes": [d_ctx.get("note")] if d_ctx.get("note") else [],
        },
    ]

    breakdown = {
        "score_version": "sv-001",
        "code_version": "git:master",
        "config_version": int(eff.get("config_version") or 1),
        "score_total": final_score,
        "final_score": final_score,
        "raw_base_score": raw_base_score,
        "setup_name": setup_info["setup_name"],
        "setup_label": setup_info["setup_label"],
        "setup_bonus": setup_info["setup_bonus"],
        "is_dead_stock": is_dead_stock,
        "dead_stock_shield_reason": setup_info["rejection_reason"],
        "structural_regime": setup_info.get("structural_regime") or {},
        "is_gap_runner": is_runner,
        "gap_runner_boost": gap_runner_boost,
        "gap_type": gap_type,
        "gap_pct": gap_pct,
        "macro_regime": macro_regime,
        "macro_label": macro_label,
        "macro_adjustment": macro_adj,
        "coverage": coverage,
        "missing_components": missing_components,
        "min_score_required": min_score,
        "eligible_by_score": eligible_by_score,
        "potential_benefit": compute_potential_benefit_metrics(cand, eff),
        "weights": {
            "w_expectancy": w_exp, "w_apex_signal": w_apex, "w_liquidity": w_liq,
            "w_risk": w_risk, "w_iv_greeks": w_iv, "w_context": w_ctx,
        },
        "components": {
            "expectancy": {"score": s_exp, "weighted": round(s_exp * w_exp / total_w, 2), "detail": d_exp},
            "apex_signal": {"score": s_apex, "weighted": round(s_apex * w_apex / total_w, 2), "detail": d_apex},
            "liquidity": {"score": s_liq, "weighted": round(s_liq * w_liq / total_w, 2), "detail": d_liq},
            "risk": {"score": s_risk, "weighted": round(s_risk * w_risk / total_w, 2), "detail": d_risk},
            "iv_greeks": {"score": s_iv, "weighted": round(s_iv * w_iv / total_w, 2), "detail": d_iv},
            "context": {"score": s_ctx, "weighted": round(s_ctx * w_ctx / total_w, 2), "detail": d_ctx},
        },
        "components_list": components_list,
        "model_version": MODEL_VERSION,
    }
    return {"score": final_score, "coverage": coverage, "score_breakdown": breakdown}


def replay_evaluation(cand: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> dict[str, Any]:
    """Reejecuta deterministamente la valoracion y score de una candidata (Doc §13.3).
    Comprueba reproducibilidad bit a bit.
    """
    replayed = score_candidate(cand, underlying, eff)
    orig_score = cand.get("score")
    diff = None
    matches = True
    if orig_score is not None:
        diff = round(float(replayed["score"]) - float(orig_score), 4)
        matches = abs(diff) < 0.01

    return {
        "candidate_id": cand.get("id"),
        "original_score": orig_score,
        "replayed_score": replayed["score"],
        "diff": diff,
        "matches": matches,
        "coverage": replayed["coverage"],
        "breakdown": replayed["score_breakdown"],
    }


def rank_and_score_candidates(candidates: list[dict[str, Any]],
                              underlyings_by_id: dict[int, dict[str, Any]],
                              eff: dict[str, Any]) -> list[dict[str, Any]]:
    """Puntua y asigna ranking global y por estrategia a todas las candidatas.
    Devuelve lista ordenada descendentemente por score.
    Determinista y reproducible.
    """
    scored: list[dict[str, Any]] = []
    for c in candidates:
        row = dict(c)
        uid = row.get("underlying_id") or 0
        und = underlyings_by_id.get(uid) or {}
        res = score_candidate(row, und, eff)
        row["score"] = res["score"]
        row["score_breakdown"] = res["score_breakdown"]
        row["is_gap_runner"] = res["score_breakdown"].get("is_gap_runner", False)
        row["gap_type"] = res["score_breakdown"].get("gap_type")
        row["gap_pct"] = res["score_breakdown"].get("gap_pct")
        scored.append(row)

    # Ordenamiento por Máximo Beneficio Potencial ($ USD) y Calidad Técnica:
    # Prioridad 1: Gap Runners
    # Prioridad 2: Benefit Index descendente (pondera $ ganancia neta, $ ganancia potencial y calidad)
    # Prioridad 3: Beneficio Potencial Total en USD descendente
    # Prioridad 4: Valor Esperado Total en USD descendente
    # Prioridad 5: Options Score descendente
    # Prioridad 6: ev_ratio descendente
    # Prioridad 7: id ascendente
    def sort_key(item: dict[str, Any]):
        bd = item.get("score_breakdown") or {}
        is_dead = bd.get("is_dead_stock", False)
        setup_name = bd.get("setup_name", "")
        has_prime_setup = setup_name in ("CATALYST_GAP", "VOLUME_IGNITION", "MEAN_REVERSION_1H")
        is_runner = bool(
            has_prime_setup
            or item.get("is_gap_runner")
            or (item.get("exit_plan") or {}).get("is_gap_runner")
            or bd.get("is_gap_runner")
            or item.get("direction_source") == "gap_runner"
            or item.get("strategy_type") in ("gap_runner_call", "gap_runner_put")
        )
        met = compute_potential_benefit_metrics(item, eff)
        return (
            1 if is_dead else 0,             # Dead stocks van al final absoluto
            0 if is_runner else 1,           # Opciones con setup confirmado van primero
            -round(met["benefit_index"], 2),
            -round(met["pot_profit_total"], 2),
            -round(met["ev_total_usd"], 2),
            -float(item.get("score") or 0.0),
            -float(item.get("ev_ratio") or 0.0),
            int(item.get("id") or 0),
        )

    scored.sort(key=sort_key)

    # Asignar rank global
    for rank, row in enumerate(scored, start=1):
        row["rank_global"] = rank

    # Asignar rank por estrategia
    strat_counters: dict[str, int] = {}
    for row in scored:
        stype = row.get("strategy_type") or "unknown"
        strat_counters[stype] = strat_counters.get(stype, 0) + 1
        row["rank_strategy"] = strat_counters[stype]

    return scored
