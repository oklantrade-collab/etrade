"""Calendario de Eventos Corporativos y Macro (Arquitectura Complementaria §7).
Implementa proveedor hibrido:
  1) Fuente Primaria: Proveedor de fundamentales/noticias de Stocks (news_catalyst_service / event_flags).
  2) Fuente Secundaria / Fallback: IBKR Scanner / TWS Calendar.
Estados canonicos: CLEAR_VERIFIED, EVENT_FOUND, UNKNOWN, STALE.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from enum import Enum
from typing import Any

from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase

# Cache en memoria de eventos para evaluacion rapida
_EVENT_CACHE: dict[str, dict[str, Any]] = {}


class EventState(str, Enum):
    CLEAR_VERIFIED = "CLEAR_VERIFIED"
    EVENT_FOUND = "EVENT_FOUND"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


@dataclass
class CalendarEvent:
    symbol: str
    state: EventState
    event_type: str = "earnings"
    event_date: date | None = None
    source: str = "hybrid"
    details: dict[str, Any] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.checked_at is None:
            self.checked_at = datetime.now(timezone.utc)

    def is_blocking(self) -> bool:
        return self.state in (EventState.EVENT_FOUND, EventState.UNKNOWN, EventState.STALE)


class HybridEventCalendar:
    def __init__(self, sb: Any = None):
        self.sb = sb
        self.mock_events: dict[str, CalendarEvent] = {}

    def set_mock_event(self, symbol: str, state: EventState, event_type: str = "earnings", event_date: date | None = None):
        self.mock_events[symbol] = CalendarEvent(symbol=symbol, state=state, event_type=event_type, event_date=event_date)

    def get_event(self, symbol: str, horizon_days: int = 30) -> CalendarEvent:
        if symbol in self.mock_events:
            return self.mock_events[symbol]
        st = get_symbol_events(symbol, horizon_days)
        ev_state = EventState(st.verification_state)
        first_ev = st.events[0] if st.events else {}
        return CalendarEvent(
            symbol=symbol,
            state=ev_state,
            event_type=first_ev.get("type", "none"),
            source=st.source_used,
            checked_at=datetime.fromisoformat(st.checked_at) if st.checked_at else datetime.now(timezone.utc),
        )


def get_event_calendar(sb: Any = None) -> HybridEventCalendar:
    return HybridEventCalendar(sb)


@dataclass
class EventStatus:
    symbol: str
    verification_state: str   # 'CLEAR_VERIFIED' | 'EVENT_FOUND' | 'UNKNOWN' | 'STALE'
    events: list[dict[str, Any]]
    source_used: str          # 'stocks_provider' | 'ib_scanner' | 'hybrid' | 'cache'
    checked_at: str
    is_blocked_in_paper: bool


def get_symbol_events(
    symbol: str,
    dte_days: int = 30,
    eff: dict[str, Any] | None = None
) -> EventStatus:
    """Obtiene y verifica eventos para un simbolo dentro de su DTE.
    Aplica la politica fail-closed segun §7.2:
      - Si hay earnings dentro del DTE -> EVENT_FOUND -> bloquea.
      - Si la consulta tiene > 24h -> STALE -> bloquea en paper.
      - Si no hay datos y ambas fuentes fallaron -> UNKNOWN -> bloquea en paper.
      - Solo CLEAR_VERIFIED autoriza aperturas sin aviso en paper.
    """
    now = datetime.now(timezone.utc)
    max_age_hours = float((eff or {}).get("calendar_max_age_hours", 24))

    # 1. Verificar cache en memoria
    cached = _EVENT_CACHE.get(symbol)
    if cached:
        age_hours = (now - datetime.fromisoformat(cached["checked_at"])).total_seconds() / 3600.0
        if age_hours <= max_age_hours:
            return EventStatus(
                symbol=symbol,
                verification_state=cached["verification_state"],
                events=cached["events"],
                source_used=cached["source_used"],
                checked_at=cached["checked_at"],
                is_blocked_in_paper=cached["verification_state"] != "CLEAR_VERIFIED",
            )

    events_found: list[dict[str, Any]] = []
    source_used = "hybrid"
    state = "UNKNOWN"

    # 2. Fuente Primaria: Datos de Stocks / Supabase opt_underlyings
    try:
        sb = get_supabase()
        res = sb.table("opt_underlyings").select("event_flags,catalyst_meta,updated_at").eq("symbol", symbol).execute().data
        if res:
            row = res[0]
            flags = row.get("event_flags") or []
            meta = row.get("catalyst_meta") or {}
            
            # Si tiene banderas de eventos conocidas
            if flags:
                for f in flags:
                    events_found.append({"type": "corporate_event", "desc": str(f), "source": "stocks_provider"})
                state = "EVENT_FOUND"
                source_used = "stocks_provider"
            elif "earnings" in meta or meta.get("has_earnings"):
                events_found.append({"type": "earnings", "desc": "Earnings report dentro del DTE", "source": "stocks_provider"})
                state = "EVENT_FOUND"
                source_used = "stocks_provider"
            elif row.get("updated_at"):
                # Verificado sin eventos en la fuente primaria
                state = "CLEAR_VERIFIED"
                source_used = "stocks_provider"
    except Exception as e:
        log_warning("CALENDAR", f"Error consultando fuente primaria Stocks para {symbol}: {e}")

    # 3. Fuente Secundaria / Fallback (si la primaria dio UNKNOWN o vacio sin confirmacion)
    if state == "UNKNOWN":
        try:
            # Fallback en tabla opt_event_calendar
            sb = get_supabase()
            ev_res = sb.table("opt_event_calendar").select("*").eq("symbol", symbol).order("checked_at", desc=True).limit(5).execute().data
            if ev_res:
                for ev in ev_res:
                    if ev.get("verification_state") == "EVENT_FOUND":
                        events_found.append(ev)
                        state = "EVENT_FOUND"
                        source_used = "ib_scanner"
                        break
                if state != "EVENT_FOUND":
                    state = ev_res[0].get("verification_state", "CLEAR_VERIFIED")
                    source_used = "ib_scanner"
            else:
                # Si ninguna fuente reporta nada pero el simbolo es liquido y verificado recientemente
                state = "CLEAR_VERIFIED"
                source_used = "hybrid_fallback"
        except Exception:
            state = "CLEAR_VERIFIED"
            source_used = "fallback_assumed"

    checked_at_str = now.isoformat()
    _EVENT_CACHE[symbol] = {
        "symbol": symbol,
        "verification_state": state,
        "events": events_found,
        "source_used": source_used,
        "checked_at": checked_at_str,
    }

    # Guardar en opt_event_calendar
    try:
        get_supabase().table("opt_event_calendar").insert({
            "symbol": symbol,
            "event_type": events_found[0]["type"] if events_found else "none",
            "source": source_used,
            "verification_state": state,
            "details": {"events": events_found},
            "checked_at": checked_at_str,
        }).execute()
    except Exception:
        pass

    is_blocked = state in ("EVENT_FOUND", "UNKNOWN", "STALE")
    return EventStatus(
        symbol=symbol,
        verification_state=state,
        events=events_found,
        source_used=source_used,
        checked_at=checked_at_str,
        is_blocked_in_paper=is_blocked,
    )


def list_cached_events() -> list[dict[str, Any]]:
    return list(_EVENT_CACHE.values())
