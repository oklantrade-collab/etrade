"""
Shared UTC timestamp parsing utilities compatible with Python 3.10 and PostgREST.

PostgREST frequently serializes fractional seconds with 1 to 5 digits (e.g.,
``2026-11-18T16:12:41.77588+00:00``), which raises ``ValueError`` in Python 3.10's
``datetime.fromisoformat()``. ``parse_iso_utc()`` normalizes fractional digits and
timezone suffixes deterministically so TTL, cooldown, and reconciliation guards
never fail silently.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_FRACTIONAL_RE = re.compile(r"\.(\d+)")


def parse_iso_utc(ts: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp or ``datetime`` into a timezone-aware UTC ``datetime``.

    Returns ``None`` if ``ts`` is empty or cannot be parsed.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc) if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)

    raw = str(ts).strip()
    if not raw:
        return None

    # Normalize trailing Z and space separator before timezone normalization
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)

    # Python 3.10 datetime.fromisoformat requires 3 or 6 fractional digits; pad/truncate to 6
    def _norm_frac(match: re.Match[str]) -> str:
        digits = match.group(1)
        if len(digits) < 6:
            return "." + digits.ljust(6, "0")
        return "." + digits[:6]

    normalized = _FRACTIONAL_RE.sub(_norm_frac, raw, count=1)

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def seconds_since_iso(ts: Any, now_dt: datetime | None = None) -> float | None:
    """Return elapsed seconds from ``ts`` to ``now_dt`` (or current UTC time), or ``None``."""
    parsed = parse_iso_utc(ts)
    if parsed is None:
        return None
    ref = parse_iso_utc(now_dt) if now_dt is not None else datetime.now(timezone.utc)
    if ref is None:
        ref = datetime.now(timezone.utc)
    return (ref - parsed).total_seconds()
