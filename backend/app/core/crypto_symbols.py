"""
Canonical crypto spot symbols for DB and Binance (no slash), e.g. SOLUSDT.
"""
from __future__ import annotations

from typing import Any, Mapping


def normalize_crypto_symbol(symbol: str) -> str:
    """BTC/USDT, BTCUSDT, btcusdt -> BTCUSDT."""
    return (symbol or "").strip().upper().replace("/", "")


def crypto_symbol_match_variants(symbol: str) -> list[str]:
    """
    Values that may exist in legacy rows (SOLUSDT vs SOL/USDT).
    Use with .in_('symbol', variants) when querying positions/orders.
    """
    norm = normalize_crypto_symbol(symbol)
    out = {norm}
    if norm.endswith("USDT") and len(norm) > 4:
        base = norm[:-4]
        out.add(f"{base}/USDT")
    return list(out)


def resolve_crypto_position_quantity(sb, pos: Mapping[str, Any]) -> float:
    """
    Effective quantity for PnL. Falls back to linked orders.quantity if positions.size is missing/zero.
    """
    try:
        s = float(pos.get("size") or 0)
    except (TypeError, ValueError):
        s = 0.0
    if s > 0:
        return s
    oid = pos.get("order_id")
    if not oid:
        return 0.0
    try:
        r = sb.table("orders").select("quantity").eq("id", str(oid)).maybe_single().execute()
        if r.data:
            q = float(r.data.get("quantity") or 0)
            if q > 0:
                return q
    except Exception:
        pass
    return 0.0
