"""
velocity_ranking.py — Ranking por Velocidad de Movimiento Inmediata (Velocity Score)

Fuente única de verdad para ordenar candidatos tanto en la pantalla (Opportunities)
como en el escáner del robot (micro_pullback_scanner).

Idea: lo que importa para Scalping/Day Trading no es cuánto subió la acción esta
mañana, sino con qué ENERGÍA se mueve ahora mismo:
  - RVOL            (anomalía de volumen)
  - ADX 5m + DMI    (fuerza direccional de la tendencia corta)
  - ΔP 5m           (cuánto avanzó el precio en los últimos minutos)
  - Volumen         (liquidez / profundidad real)

Módulo puro (sin I/O) → totalmente testeable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────
# Configuración por defecto (se sobreescribe con stocks_config)
# ─────────────────────────────────────────────────────────────
DEFAULT_VELOCITY_CONFIG: Dict[str, float] = {
    "scanner_min_change_pct": 3.0,
    "scanner_min_rvol": 1.5,
    "scanner_min_adx_5m": 20.0,
    "scanner_min_volume": 300_000.0,
    "scanner_min_dp5m_pct": 0.0,
    "velocity_w_rvol": 0.35,
    "velocity_w_adx": 0.25,
    "velocity_w_dp5m": 0.30,
    "velocity_w_vol": 0.10,
    "scanner_refresh_seconds": 60.0,
}

# Rangos de normalización [lo, hi] → 0..1
RVOL_RANGE = (1.0, 10.0)
ADX_RANGE = (15.0, 50.0)
DP5M_RANGE = (0.0, 4.0)        # % de avance en la ventana de 5 min
LOG_VOL_RANGE = (5.0, 8.0)     # log10(volumen): 100k .. 100M

# Factor direccional: si -DI domina, el ADX alto es una tendencia BAJISTA
ADX_ADVERSE_DI_FACTOR = 0.30


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "" or value == "N/A":
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _norm(x: float, lo: float, hi: float) -> float:
    """Normaliza x al rango [0, 1] con saturación."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def parse_velocity_config(raw_config: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """
    Convierte el dict crudo de stocks_config (valores string) en config numérica
    con defaults seguros. Los pesos se re-normalizan para que sumen 1.0.
    """
    cfg = dict(DEFAULT_VELOCITY_CONFIG)
    raw_config = raw_config or {}
    for key, default in DEFAULT_VELOCITY_CONFIG.items():
        if key in raw_config:
            cfg[key] = _to_float(raw_config.get(key), default)

    w_keys = ("velocity_w_rvol", "velocity_w_adx", "velocity_w_dp5m", "velocity_w_vol")
    total = sum(max(0.0, cfg[k]) for k in w_keys)
    if total <= 0:
        for k in w_keys:
            cfg[k] = DEFAULT_VELOCITY_CONFIG[k]
    else:
        for k in w_keys:
            cfg[k] = max(0.0, cfg[k]) / total
    # Refresco mínimo razonable (evita saturar yfinance)
    cfg["scanner_refresh_seconds"] = max(15.0, cfg["scanner_refresh_seconds"])
    return cfg


# Registro en memoria del último Velocity Score calculado por ticker (compartido entre
# el escáner de pantalla, el escáner del robot y el gate previo al disparo).
_VELOCITY_REGISTRY: Dict[str, Dict[str, Any]] = {}
_REGISTRY_FIELDS = (
    "change_pct", "volume", "rvol", "has_news", "shares", "market_cap",
    "adx_5m", "delta_p_5m_pct", "is_ema3_above_ema9_5m",
)


def record_velocity(ticker: str, item: Dict[str, Any], score: float) -> None:
    import time as _time

    sym = str(ticker or "").upper().strip()
    if not sym:
        return
    entry = {k: item.get(k) for k in _REGISTRY_FIELDS if k in item}
    entry["velocity_score"] = score
    entry["ts"] = _time.time()
    _VELOCITY_REGISTRY[sym] = entry


def get_recorded_velocity(ticker: str, max_age_seconds: float = 180.0) -> Optional[Dict[str, Any]]:
    """Último snapshot de velocidad del ticker o None si no existe / está obsoleto."""
    import time as _time

    entry = _VELOCITY_REGISTRY.get(str(ticker or "").upper().strip())
    if not entry:
        return None
    if _time.time() - float(entry.get("ts", 0.0)) > max_age_seconds:
        return None
    return entry


_CFG_CACHE: Dict[str, Any] = {"ts": 0.0, "cfg": None}
CONFIG_CACHE_TTL_SECONDS = 120.0


def load_velocity_config_cached(force: bool = False) -> Dict[str, float]:
    """
    Lee las claves de velocidad desde stocks_config (Supabase) con caché en memoria.
    Ante cualquier error devuelve la última config válida o los defaults.
    """
    import time as _time

    now = _time.time()
    if not force and _CFG_CACHE["cfg"] is not None and (now - _CFG_CACHE["ts"]) < CONFIG_CACHE_TTL_SECONDS:
        return _CFG_CACHE["cfg"]
    try:
        from app.core.supabase_client import get_supabase

        sb = get_supabase()
        res = sb.table("stocks_config").select("key, value").execute()
        raw = {r["key"]: r["value"] for r in (res.data or []) if r.get("key") in DEFAULT_VELOCITY_CONFIG}
        cfg = parse_velocity_config(raw)
        _CFG_CACHE["cfg"] = cfg
        _CFG_CACHE["ts"] = now
        return cfg
    except Exception:
        if _CFG_CACHE["cfg"] is not None:
            return _CFG_CACHE["cfg"]
        return parse_velocity_config(None)


@dataclass
class VelocityResult:
    score: float
    components: Dict[str, float] = field(default_factory=dict)
    is_descending: bool = False


def compute_velocity_score(item: Dict[str, Any], cfg: Optional[Dict[str, float]] = None) -> VelocityResult:
    """
    Calcula el Velocity Score (0..100) de un candidato.

    Campos leídos de `item` (todos opcionales, con defaults neutros):
      rvol, adx_5m, plus_di_5m, minus_di_5m, delta_p_5m_pct (o delta_p_5m),
      volume, is_ema3_above_ema9_5m
    """
    cfg = cfg or parse_velocity_config(None)

    rvol = _to_float(item.get("rvol"), 1.0)
    adx = _to_float(item.get("adx_5m"), 0.0)
    plus_di = _to_float(item.get("plus_di_5m"), 0.0)
    minus_di = _to_float(item.get("minus_di_5m"), 0.0)
    dp5m = _to_float(item.get("delta_p_5m_pct", item.get("delta_p_5m")), 0.0)
    volume = max(0.0, _to_float(item.get("volume"), 0.0))

    # Dirección del ADX: +DI > -DI → tendencia alcista real
    dir_factor = 1.0 if plus_di >= minus_di else ADX_ADVERSE_DI_FACTOR

    n_rvol = _norm(rvol, *RVOL_RANGE)
    n_adx = _norm(adx, *ADX_RANGE) * dir_factor
    n_dp5m = _norm(dp5m, *DP5M_RANGE)
    n_vol = _norm(math.log10(volume), *LOG_VOL_RANGE) if volume > 0 else 0.0

    score = 100.0 * (
        cfg["velocity_w_rvol"] * n_rvol
        + cfg["velocity_w_adx"] * n_adx
        + cfg["velocity_w_dp5m"] * n_dp5m
        + cfg["velocity_w_vol"] * n_vol
    )

    # Acción descendente: cae en los últimos 5 min Y EMA3<=EMA9 en 5m
    ema5_bull = item.get("is_ema3_above_ema9_5m")
    is_descending = bool(
        dp5m < cfg["scanner_min_dp5m_pct"] and (ema5_bull is False)
    )

    return VelocityResult(
        score=round(min(100.0, max(0.0, score)), 1),
        components={
            "rvol": round(rvol, 2),
            "adx_5m": round(adx, 1),
            "dir_factor": dir_factor,
            "delta_p_5m_pct": round(dp5m, 2),
            "volume": int(volume),
            "n_rvol": round(n_rvol, 3),
            "n_adx": round(n_adx, 3),
            "n_dp5m": round(n_dp5m, 3),
            "n_vol": round(n_vol, 3),
        },
        is_descending=is_descending,
    )


def passes_velocity_minimums(item: Dict[str, Any], cfg: Optional[Dict[str, float]] = None) -> Tuple[bool, str]:
    """
    Aplica los mínimos configurables de Settings/STOCKS.
    Retorna (pasa, motivo_de_rechazo).
    """
    cfg = cfg or parse_velocity_config(None)

    chg = _to_float(item.get("change_pct"), 0.0)
    if chg < cfg["scanner_min_change_pct"]:
        return False, f"change {chg:.1f}% < min {cfg['scanner_min_change_pct']:.1f}%"

    rvol = _to_float(item.get("rvol"), 1.0)
    if rvol < cfg["scanner_min_rvol"]:
        return False, f"rvol {rvol:.2f} < min {cfg['scanner_min_rvol']:.2f}"

    vol = _to_float(item.get("volume"), 0.0)
    if vol < cfg["scanner_min_volume"]:
        return False, f"volume {int(vol)} < min {int(cfg['scanner_min_volume'])}"

    adx = _to_float(item.get("adx_5m"), 0.0)
    if adx < cfg["scanner_min_adx_5m"]:
        return False, f"adx_5m {adx:.1f} < min {cfg['scanner_min_adx_5m']:.1f}"

    return True, ""


def rank_by_velocity(
    items: Iterable[Dict[str, Any]],
    cfg: Optional[Dict[str, float]] = None,
    apply_minimums: bool = True,
    keep_penalized: bool = True,
) -> List[Dict[str, Any]]:
    """
    Enriquece cada item con `velocity_score`, `velocity_components`, `is_velocity_descending`
    y devuelve la lista ordenada de mayor a menor velocidad.

    - apply_minimums: descarta los que no superan los mínimos de configuración.
    - Las acciones DESCENDENTES se excluyen siempre (caso: dos acciones del Top con
      movimiento 1D descendente y EMA3<EMA9).
    - keep_penalized: si True, los items marcados como penalizados (blocked, trap, deep bear...)
      se conservan pero al final; si False se eliminan.
    """
    cfg = cfg or parse_velocity_config(None)
    ranked: List[Dict[str, Any]] = []

    for it in items:
        vr = compute_velocity_score(it, cfg)
        it["velocity_score"] = vr.score
        it["velocity_components"] = vr.components
        it["is_velocity_descending"] = vr.is_descending
        record_velocity(it.get("ticker"), it, vr.score)

        if vr.is_descending:
            continue
        if apply_minimums:
            ok, reason = passes_velocity_minimums(it, cfg)
            if not ok:
                it["velocity_reject_reason"] = reason
                continue
        ranked.append(it)

    def _is_penalized(x: Dict[str, Any]) -> bool:
        return bool(
            str(x.get("status") or "").lower() == "blocked"
            or str(x.get("queue_status") or "").lower() == "blocked"
            or x.get("is_deep_bear_excluded")
            or x.get("is_trap")
        )

    if not keep_penalized:
        ranked = [x for x in ranked if not _is_penalized(x)]

    ranked.sort(key=lambda x: (1 if _is_penalized(x) else 0, -float(x.get("velocity_score") or 0.0)))
    return ranked
