"""Gestor de Salud del Sistema, Modos de Operacion y Kill Switch (Arquitectura Complementaria §4).
Proporciona politica Fail-Closed, telemetria de latencia de cotizaciones, y auditoria.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import os

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase

# Estado en memoria para persistencia rapida y fallback
_HEALTH_STATE = {
    "status": "NORMAL",             # 'NORMAL' | 'DEGRADED' | 'HALTED'
    "degraded_reasons": [],
    "p95_quote_age_sec": 1.2,
    "stale_quotes_pct": 0.0,
    "ibkr_connected": True,
    "consecutive_errors": 0,
    "last_checked_at": datetime.now(timezone.utc).isoformat(),
}

_KILL_SWITCH = {
    "active": False,
    "reason": "",
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "updated_by": "system",
}


@dataclass
class SystemHealth:
    status: str                     # 'NORMAL' | 'DEGRADED' | 'HALTED'
    degraded_reasons: list[str] = field(default_factory=list)
    p95_quote_age_sec: float = 0.0
    stale_quotes_pct: float = 0.0
    ibkr_connected: bool = True
    consecutive_errors: int = 0
    kill_switch_active: bool = False
    mode: str = "paper"             # 'observation' | 'paper'
    last_checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "degraded_reasons": self.degraded_reasons,
            "p95_quote_age_sec": self.p95_quote_age_sec,
            "stale_quotes_pct": self.stale_quotes_pct,
            "ibkr_connected": self.ibkr_connected,
            "consecutive_errors": self.consecutive_errors,
            "kill_switch_active": self.kill_switch_active,
            "mode": self.mode,
            "last_checked_at": self.last_checked_at or datetime.now(timezone.utc).isoformat(),
        }


def is_kill_switch_active() -> bool:
    return bool(_KILL_SWITCH["active"])


def reset_health_state():
    """Restablece el estado de salud a NORMAL (utilizado en tests y recuperacion)."""
    global _HEALTH_STATE, _KILL_SWITCH
    _HEALTH_STATE["status"] = "NORMAL"
    _HEALTH_STATE["degraded_reasons"] = []
    _HEALTH_STATE["p95_quote_age_sec"] = 1.2
    _HEALTH_STATE["stale_quotes_pct"] = 0.0
    _HEALTH_STATE["ibkr_connected"] = True
    _HEALTH_STATE["consecutive_errors"] = 0
    _HEALTH_STATE["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    _KILL_SWITCH["active"] = False
    _KILL_SWITCH["reason"] = ""


def set_kill_switch(active: bool, reason: str = "Manual toggle", user: str = "CEO") -> dict[str, Any]:
    old_active = _KILL_SWITCH["active"]
    _KILL_SWITCH["active"] = active
    _KILL_SWITCH["reason"] = reason
    _KILL_SWITCH["updated_at"] = datetime.now(timezone.utc).isoformat()
    _KILL_SWITCH["updated_by"] = user

    event_type = "kill_switch_activated" if active else "kill_switch_deactivated"
    payload = {
        "event_type": event_type,
        "old_state": {"active": old_active},
        "new_state": {"active": active},
        "reason": reason,
        "triggered_by": user,
        "created_at": _KILL_SWITCH["updated_at"],
    }

    try:
        get_supabase().table("opt_control_events").insert(payload).execute()
    except Exception as e:
        log_warning("HEALTH", f"No se pudo persistir opt_control_events: {e}")

    log_info("HEALTH", f"Kill switch actualizado a active={active}: {reason} (por {user})")
    return _KILL_SWITCH


def update_health_metrics(
    p95_age: float,
    stale_pct: float,
    ibkr_online: bool,
    consecutive_errors: int,
    eff: dict[str, Any]
) -> SystemHealth:
    """Actualiza y evalua el estado de salud segun los umbrales configurados (§4.2)."""
    global _HEALTH_STATE

    reasons: list[str] = []
    status = "NORMAL"

    # Umbrales
    max_disconnect_sec = float(eff.get("degraded_disconnect_sec", 30))
    max_p95_age = float(eff.get("degraded_quote_age_p95_sec", 10))
    max_stale_pct = float(eff.get("degraded_stale_pct", 30))
    max_db_errors = int(eff.get("halted_consecutive_db_errors", 3))

    if not ibkr_online:
        reasons.append("IBKR desconectado")
        status = "DEGRADED"

    if p95_age > max_p95_age:
        reasons.append(f"Antigüedad p95 de cotizaciones {p95_age:.1f}s > {max_p95_age}s")
        status = "DEGRADED"

    if stale_pct > max_stale_pct:
        reasons.append(f"Candidatas con datos STALE {stale_pct:.1f}% > {max_stale_pct}%")
        status = "DEGRADED"

    if consecutive_errors >= max_db_errors:
        reasons.append(f"Errores consecutivos {consecutive_errors} >= {max_db_errors}")
        status = "HALTED"

    if is_kill_switch_active():
        reasons.append(f"Kill switch activo ({_KILL_SWITCH['reason']})")
        status = "HALTED"

    _HEALTH_STATE["status"] = status
    _HEALTH_STATE["degraded_reasons"] = reasons
    _HEALTH_STATE["p95_quote_age_sec"] = round(p95_age, 2)
    _HEALTH_STATE["stale_quotes_pct"] = round(stale_pct, 2)
    _HEALTH_STATE["ibkr_connected"] = ibkr_online
    _HEALTH_STATE["consecutive_errors"] = consecutive_errors
    _HEALTH_STATE["last_checked_at"] = datetime.now(timezone.utc).isoformat()

    # Opcional: registrar en opt_system_health
    try:
        get_supabase().table("opt_system_health").insert({
            "status": status,
            "degraded_reasons": reasons,
            "p95_quote_age_sec": round(p95_age, 2),
            "stale_quotes_pct": round(stale_pct, 2),
            "ibkr_connected": ibkr_online,
            "consecutive_errors": consecutive_errors,
        }).execute()
    except Exception:
        pass

    mode = str(eff.get("options_mode", "paper")).lower()
    return SystemHealth(
        status=status,
        degraded_reasons=reasons,
        p95_quote_age_sec=round(p95_age, 2),
        stale_quotes_pct=round(stale_pct, 2),
        ibkr_connected=ibkr_online,
        consecutive_errors=consecutive_errors,
        kill_switch_active=is_kill_switch_active(),
        mode=mode,
        last_checked_at=_HEALTH_STATE["last_checked_at"],
    )


def get_current_health(eff: dict[str, Any] | None = None) -> SystemHealth:
    mode = "paper"
    if eff:
        mode = str(eff.get("options_mode", "paper")).lower()
    
    status = _HEALTH_STATE["status"]
    reasons = list(_HEALTH_STATE["degraded_reasons"])
    if is_kill_switch_active():
        status = "HALTED"
        if f"Kill switch activo ({_KILL_SWITCH['reason']})" not in reasons:
            reasons.append(f"Kill switch activo ({_KILL_SWITCH['reason']})")

    return SystemHealth(
        status=status,
        degraded_reasons=reasons,
        p95_quote_age_sec=_HEALTH_STATE["p95_quote_age_sec"],
        stale_quotes_pct=_HEALTH_STATE["stale_quotes_pct"],
        ibkr_connected=_HEALTH_STATE["ibkr_connected"],
        consecutive_errors=_HEALTH_STATE["consecutive_errors"],
        kill_switch_active=is_kill_switch_active(),
        mode=mode,
        last_checked_at=_HEALTH_STATE["last_checked_at"],
    )


def can_open_new_position(eff: dict[str, Any]) -> tuple[bool, str]:
    """Politica Fail-Closed: autoriza nuevas entradas solo si salud es NORMAL y modo es paper."""
    h = get_current_health(eff)
    if h.kill_switch_active:
        return False, "Kill switch activo: nuevas entradas bloqueadas"
    if h.status == "HALTED":
        return False, f"Sistema en estado HALTED: {'; '.join(h.degraded_reasons)}"
    if h.status == "DEGRADED":
        return False, f"Sistema en estado DEGRADED: nuevas entradas en pausa ({'; '.join(h.degraded_reasons)})"
    if h.mode != "paper":
        return False, f"Modo actual '{h.mode}': entradas paper deshabilitadas en modo observation"
    return True, "OK"


class HealthStatus:
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


def record_control_event(sb: Any, event_type: str, reason: str, operator: str = "CEO"):
    payload = {
        "event_type": event_type,
        "old_state": {},
        "new_state": {},
        "reason": reason,
        "triggered_by": operator,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        (sb or get_supabase()).table("opt_control_events").insert(payload).execute()
    except Exception as e:
        log_warning("HEALTH", f"No se pudo persistir opt_control_events: {e}")


def evaluate_system_health(sb: Any = None, eff: dict[str, Any] | None = None,
                           override_divergences: int | None = None,
                           override_delayed_ratio: float | None = None) -> Any:
    """Evalua salud integral del sistema (Doc §4). Compatible con endpoints y tests."""
    eff = eff or {}
    if override_divergences is not None and override_divergences >= 3:
        update_health_metrics(p95_age=2.0, stale_pct=10.0, ibkr_online=True, consecutive_errors=override_divergences, eff=eff)
    elif override_delayed_ratio is not None and override_delayed_ratio > 0.30:
        update_health_metrics(p95_age=2.0, stale_pct=override_delayed_ratio * 100, ibkr_online=True, consecutive_errors=0, eff=eff)

    h = get_current_health(eff)
    allowed, _ = can_open_new_position(eff)

    class HealthEval:
        def __init__(self, h, allowed):
            self.status = h.status
            self.kill_switch_active = h.kill_switch_active
            self.data_state = "LIVE" if h.ibkr_connected else "UNKNOWN"
            self.consecutive_divergences = h.consecutive_errors
            self.delayed_quotes_ratio = round(h.stale_quotes_pct / 100.0, 2)
            self.active_positions_count = 0
            self.can_open_new_position = allowed
            self.reasons = h.degraded_reasons
            self.checked_at = datetime.fromisoformat(h.last_checked_at) if h.last_checked_at else datetime.now(timezone.utc)

    return HealthEval(h, allowed)
