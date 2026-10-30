"""
playbook_gate.py — Gate previo al disparo de compra (Ross Cameron Playbook + Velocidad)

Se ejecuta ANTES de enviar la orden BUY a TWS en el MicroPullbackEngine:
  1. Gate de velocidad: el ticker debe conservar un Velocity Score mínimo vigente.
  2. Régimen de mercado (frío/normal): SPY/QQQ en rojo → lote reducido (30%; 10% viernes frío).
  3. WarriorPlaybookEngine.evaluate_live_opportunity → reglas BLOCK_* / stop ceñido.

Modos (stocks_config.playbook_gate_mode):
  - "enforce": bloquea y aplica tamaño.
  - "observe": solo registra lo que HUBIERA hecho (no bloquea ni cambia tamaño).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.logger import log_info, log_warning
from app.stocks.velocity_ranking import get_recorded_velocity

MODULE = "PLAYBOOK_GATE"

COLD_MARKET_SIZE_MULT = 0.30
WILD_CARD_FRIDAY_SIZE_MULT = 0.10
TOPPING_TAIL_MIN_UPPER_WICK = 0.40

_GATE_CFG_CACHE: Dict[str, Any] = {"ts": 0.0, "cfg": None}
_GATE_CFG_TTL = 120.0
_MARKET_CACHE: Dict[str, Any] = {"ts": 0.0, "cold": False, "detail": ""}
_MARKET_TTL = 60.0

DEFAULT_GATE_CFG = {
    "playbook_gate_mode": "enforce",
    "velocity_gate_min_score": 10.0,
    "cold_market_spy_pct": -0.3,
}


@dataclass
class GateDecision:
    allow: bool = True
    size_multiplier: float = 1.0
    fixed_stop_cents: Optional[float] = None
    action: str = "ALLOW"
    reasoning: str = ""
    mode: str = "enforce"
    would_block: bool = False       # en modo observe: el gate habría bloqueado
    market_cold: bool = False
    notes: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────
def load_gate_config_cached(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and _GATE_CFG_CACHE["cfg"] is not None and (now - _GATE_CFG_CACHE["ts"]) < _GATE_CFG_TTL:
        return _GATE_CFG_CACHE["cfg"]
    cfg = dict(DEFAULT_GATE_CFG)
    try:
        from app.core.supabase_client import get_supabase

        res = get_supabase().table("stocks_config").select("key, value").execute()
        raw = {r["key"]: r["value"] for r in (res.data or []) if r.get("key") in DEFAULT_GATE_CFG}
        mode = str(raw.get("playbook_gate_mode", cfg["playbook_gate_mode"])).strip().lower()
        cfg["playbook_gate_mode"] = mode if mode in ("enforce", "observe") else "enforce"
        for k in ("velocity_gate_min_score", "cold_market_spy_pct"):
            if k in raw:
                try:
                    cfg[k] = float(raw[k])
                except (TypeError, ValueError):
                    pass
        _GATE_CFG_CACHE["cfg"] = cfg
        _GATE_CFG_CACHE["ts"] = now
    except Exception:
        if _GATE_CFG_CACHE["cfg"] is not None:
            return _GATE_CFG_CACHE["cfg"]
    return cfg


# ─────────────────────────────────────────────────────────────
# Régimen de mercado frío (SPY / QQQ)
# ─────────────────────────────────────────────────────────────
def _fetch_index_change_pct(symbol: str) -> Optional[float]:
    try:
        import yfinance as yf

        fi = yf.Ticker(symbol).fast_info
        last = float(fi["last_price"])
        prev = float(fi["previous_close"])
        if prev > 0:
            return (last - prev) / prev * 100.0
    except Exception:
        return None
    return None


def is_cold_market(threshold_pct: float = -0.3) -> bool:
    """Mercado frío: SPY o QQQ cotizan por debajo del umbral en el día. Caché de 60s."""
    now = time.time()
    if (now - _MARKET_CACHE["ts"]) < _MARKET_TTL:
        return bool(_MARKET_CACHE["cold"])
    spy = _fetch_index_change_pct("SPY")
    qqq = _fetch_index_change_pct("QQQ")
    vals = [v for v in (spy, qqq) if v is not None]
    cold = bool(vals) and any(v < threshold_pct for v in vals)
    _MARKET_CACHE.update({
        "ts": now,
        "cold": cold,
        "detail": f"SPY={spy if spy is None else round(spy, 2)}% QQQ={qqq if qqq is None else round(qqq, 2)}%",
    })
    if cold:
        log_info(MODULE, f"🧊 Mercado FRÍO detectado ({_MARKET_CACHE['detail']} < {threshold_pct}%)")
    return cold


# ─────────────────────────────────────────────────────────────
# Detectores de patrón sobre barras de 5s
# ─────────────────────────────────────────────────────────────
def has_topping_tail(bars: List[dict], lookback: int = 2) -> bool:
    """Alguna de las últimas barras tiene mecha superior > 40% del rango (rechazo)."""
    for b in bars[-lookback:]:
        if float(b.get("upper_wick_ratio", 0.0) or 0.0) >= TOPPING_TAIL_MIN_UPPER_WICK:
            return True
    return False


def detect_flat_top(bars: List[dict], tol: float = 0.003, min_touches: int = 3, window: int = 24) -> bool:
    """Techo plano: ≥3 máximos dentro de 0.3% del máximo reciente y precio pegado al techo."""
    recent = bars[-window:]
    if len(recent) < 6:
        return False
    top = max(float(b["high"]) for b in recent)
    if top <= 0:
        return False
    touches = sum(1 for b in recent if (top - float(b["high"])) / top <= tol)
    last_close = float(recent[-1]["close"])
    return touches >= min_touches and (top - last_close) / top <= tol * 1.5


# ─────────────────────────────────────────────────────────────
# Evaluación principal
# ─────────────────────────────────────────────────────────────
def _build_playbook_context(ticker: str, price: float, bars: List[dict], snap: Dict[str, Any],
                            vel: Optional[Dict[str, Any]], cold: bool, is_friday: bool,
                            rule_code: str = "SCALP_MICRO_PULLBACK") -> Dict[str, Any]:
    change_pct = float((vel or {}).get("change_pct") or 0.0)
    # La regla MACD negativo (AMOD) aplica a compras INICIALES. En un Buy-the-Dip la estructura
    # ya fue validada por EMA3>EMA9 en 5m y el MACD suele estar corrigiendo: no se aplica.
    macd_hist = 0.0 if rule_code == "SCALP_BUY_THE_DIP" else float(snap.get("macd_hist_5m") or 0.0)
    ctx: Dict[str, Any] = {
        "ticker": ticker,
        "price": price,
        "change_pct": change_pct,
        "vwap": float(snap.get("vwap_intraday") or 0.0),
        "ema_9": float(snap.get("ema9_5m") or 0.0) or None,
        "macd_histogram": macd_hist,
        "is_running_up": change_pct >= 30.0,
        "macro_is_red": cold,
        "is_cold_market": cold,
        "is_wild_card_friday": bool(is_friday),
        "has_topping_tail": has_topping_tail(bars),
        "is_flat_top_squeeze": detect_flat_top(bars),
        "has_positive_news": bool((vel or {}).get("has_news", False)),
        "candle_is_red": False,
    }
    if vel and vel.get("volume"):
        ctx["volume"] = float(vel["volume"])
    if vel and vel.get("shares"):
        ctx["float_shares"] = float(vel["shares"])
    return ctx


def evaluate_entry_gate(ticker: str, price: float, bars: List[dict], rule_code: str = "SCALP_MICRO_PULLBACK",
                        snap: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> GateDecision:
    """Evalúa si se debe disparar la compra y con qué tamaño. Nunca lanza excepción."""
    cfg = load_gate_config_cached()
    mode = cfg["playbook_gate_mode"]
    decision = GateDecision(mode=mode)
    snap = snap or {}
    now = now or datetime.now()

    try:
        # 1. Gate de velocidad
        vel = get_recorded_velocity(ticker)
        if vel is not None:
            score = float(vel.get("velocity_score") or 0.0)
            if score < cfg["velocity_gate_min_score"]:
                decision.would_block = True
                decision.action = "BLOCK_LOW_VELOCITY"
                decision.reasoning = f"Velocity Score {score:.1f} < mínimo {cfg['velocity_gate_min_score']:.1f}"

        # 2. Régimen de mercado
        cold = is_cold_market(cfg["cold_market_spy_pct"])
        decision.market_cold = cold
        is_friday = now.weekday() == 4

        # 3. Playbook Ross Cameron
        if not decision.would_block:
            from app.stocks.warrior_playbook_engine import warrior_playbook

            ctx = _build_playbook_context(ticker, price, bars, snap, vel, cold, is_friday, rule_code)
            result = warrior_playbook.evaluate_live_opportunity(ctx)
            action = str(result.recommended_action or "")
            is_block = (
                str(result.action_type) == "BLOCK_ENTRY"
                or action.startswith("BLOCK_")
                or action == "DEFENSIVE_CUT_TOPPING_TAIL"
            )
            if is_block:
                decision.would_block = True
                decision.action = action
                decision.reasoning = f"{result.historical_trade_ref}: {result.reasoning}"[:400]
            else:
                params = result.execution_params or {}
                res_mult = params.get("position_size_multiplier")
                if res_mult is not None:
                    decision.size_multiplier = float(res_mult)
                if action == "USE_TIGHT_MICRO_STOP_10_CENTS" and params.get("fixed_stop_cents"):
                    decision.fixed_stop_cents = float(params["fixed_stop_cents"])
                decision.action = action or "ALLOW"
                decision.reasoning = result.reasoning[:300] if result.reasoning else ""

        # 4. Tamaño por régimen de mercado (el más conservador gana)
        if cold:
            cold_mult = WILD_CARD_FRIDAY_SIZE_MULT if is_friday else COLD_MARKET_SIZE_MULT
            decision.size_multiplier = min(decision.size_multiplier, cold_mult)
            decision.notes.append(f"cold_market_size={cold_mult}")
    except Exception as e:
        log_warning(MODULE, f"Gate falló para {ticker} ({e}); se permite la operación (fail-open).")
        return GateDecision(mode=mode)

    # Aplicación según modo
    if mode == "enforce":
        decision.allow = not decision.would_block
    else:
        decision.allow = True
        decision.size_multiplier = 1.0
        decision.fixed_stop_cents = None
        if decision.would_block or decision.notes:
            log_info(MODULE, f"👁️ [OBSERVE] {ticker} {rule_code}: habría {'BLOQUEADO' if decision.would_block else 'ajustado tamaño'} "
                             f"({decision.action}) {decision.reasoning} {decision.notes}")
    return decision
