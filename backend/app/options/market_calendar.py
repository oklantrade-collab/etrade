"""Calendario de mercado NYSE para Options (doc §8): festivos, cierres tempranos, ventanas de entrada/cierre.

Usa pandas_market_calendars (ya en requirements). Si no estuviera disponible, cae a lunes-viernes 9:30-16:00 ET
y lo marca (`FALLBACK_CALENDAR`) para que ADUANA lo registre: no se asume silenciosamente.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
FALLBACK_CALENDAR = False


@lru_cache(maxsize=1)
def _cal():
    global FALLBACK_CALENDAR
    try:
        import pandas_market_calendars as mcal
        return mcal.get_calendar("NYSE")
    except Exception:  # pragma: no cover
        FALLBACK_CALENDAR = True
        return None


@lru_cache(maxsize=512)
def session_bounds(d: date) -> tuple[datetime, datetime] | None:
    """(apertura, cierre) en UTC para la fecha ET `d`, o None si el mercado esta cerrado ese dia."""
    cal = _cal()
    if cal is not None:
        sch = cal.schedule(start_date=d, end_date=d)
        if sch.empty:
            return None
        o, c = sch.iloc[0]["market_open"], sch.iloc[0]["market_close"]
        return o.to_pydatetime().astimezone(timezone.utc), c.to_pydatetime().astimezone(timezone.utc)
    if d.weekday() >= 5:
        return None
    o = datetime.combine(d, time(9, 30), NY).astimezone(timezone.utc)
    c = datetime.combine(d, time(16, 0), NY).astimezone(timezone.utc)
    return o, c


def to_ny(dt: datetime) -> datetime:
    return dt.astimezone(NY)


def current_session(now: datetime) -> tuple[datetime, datetime] | None:
    """Sesion (apertura, cierre) de la fecha ET de `now`, o None si no hay sesion."""
    return session_bounds(to_ny(now).date())


def is_early_close(d: date) -> bool:
    b = session_bounds(d)
    if not b:
        return False
    return to_ny(b[1]).time() < time(16, 0)


def entry_window(now: datetime, start_after_open_min: int, end_before_close_min: int) -> tuple[bool, str]:
    s = current_session(now)
    if not s:
        return False, "mercado cerrado (festivo o fin de semana)"
    o, c = s
    start, end = o + timedelta(minutes=start_after_open_min), c - timedelta(minutes=end_before_close_min)
    if now < start:
        return False, f"antes de la ventana de entrada ({start.astimezone(NY):%H:%M} ET)"
    if now > end:
        return False, f"despues de la ventana de entrada ({end.astimezone(NY):%H:%M} ET)"
    return True, "ok"


def force_close_time(now: datetime, force_close_min_before_close: int) -> datetime | None:
    s = current_session(now)
    return (s[1] - timedelta(minutes=force_close_min_before_close)) if s else None


def market_hours_between(start: datetime, end: datetime) -> float:
    """Horas de mercado (solo sesion regular, cierres tempranos incluidos) entre dos instantes UTC."""
    if end <= start:
        return 0.0
    total = 0.0
    d = to_ny(start).date()
    last = to_ny(end).date()
    while d <= last:
        b = session_bounds(d)
        if b:
            lo, hi = max(start, b[0]), min(end, b[1])
            if hi > lo:
                total += (hi - lo).total_seconds() / 3600.0
        d += timedelta(days=1)
    return total
