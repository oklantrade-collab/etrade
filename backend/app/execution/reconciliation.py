"""
eTrade v3 — Reconciliation + Rate Limiter Utilities
Compares bot state vs Binance state and updates Supabase.
Runs every 3 cycles of 15m (= 45 minutes).
"""
from datetime import datetime, timezone
from typing import Optional

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.strategy.risk_controls import rate_limiter

MODULE = "reconciliation"


async def reconcile_positions(
    symbols: list[str],
    data_provider=None,
    supabase_client=None,
) -> list[dict]:
    """
    Compare bot state in Supabase with real positions on Binance.
    Supabase is updated with the real state (Binance = source of truth).

    Parameters
    ----------
    symbols : list of symbols to reconcile
    data_provider : DataProvider instance for exchange queries
    supabase_client : Supabase client

    Returns
    -------
    list of discrepancy dicts
    """
    if supabase_client is None:
        supabase_client = get_supabase()

    discrepancies = []

    for symbol in symbols:
        try:
            # Wait for rate limit token
            rate_limiter.wait_for_token()

            # Get real position from exchange
            if data_provider:
                real_pos = await data_provider.get_position(symbol)
            else:
                real_pos = {"symbol": symbol, "side": None, "size": 0}

            # Get bot state from Supabase
            internal_sym = symbol if "/" in symbol else f"{symbol[:3]}/{symbol[3:]}"
            bot_result = (
                supabase_client.table("positions")
                .select("*")
                .eq("symbol", internal_sym)
                .eq("status", "open")
                .execute()
            )
            bot_positions = bot_result.data or []

            # Compare
            real_has_position = real_pos.get("size", 0) > 0
            bot_has_position = len(bot_positions) > 0

            if real_has_position != bot_has_position:
                discrepancy = {
                    "symbol": symbol,
                    "bot_has_position": bot_has_position,
                    "real_has_position": real_has_position,
                    "bot_count": len(bot_positions),
                    "real_side": real_pos.get("side"),
                    "real_size": real_pos.get("size", 0),
                    "action": "supabase_updated",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
                discrepancies.append(discrepancy)

                log_warning(
                    MODULE,
                    f"Discrepancy detected for {symbol}: "
                    f"bot={'open' if bot_has_position else 'flat'} vs "
                    f"real={'open' if real_has_position else 'flat'}",
                )

                # If Binance has no position but bot thinks it does
                if not real_has_position and bot_has_position:
                    for pos in bot_positions:
                        supabase_client.table("positions").update(
                            {
                                "status": "closed",
                                "close_reason": "reconciliation_flat",
                                "closed_at": datetime.now(
                                    timezone.utc
                                ).isoformat(),
                            }
                        ).eq("id", pos["id"]).execute()

        except Exception as e:
            log_error(MODULE, f"Reconciliation failed for {symbol}: {e}")
            discrepancies.append(
                {
                    "symbol": symbol,
                    "error": str(e),
                    "action": "failed",
                }
            )

    if discrepancies:
        log_warning(
            MODULE,
            f"Reconciliation found {len(discrepancies)} discrepancies",
        )
    else:
        log_info(MODULE, f"Reconciliation clean — {len(symbols)} symbols checked")

    return discrepancies


# Track cycle count for reconciliation interval
_cycle_counter = 0
RECONCILE_EVERY_N_CYCLES = 3  # Every 3 × 15m = 45 minutes


def should_reconcile() -> bool:
    """Check if this cycle should run reconciliation."""
    global _cycle_counter
    _cycle_counter += 1
    if _cycle_counter >= RECONCILE_EVERY_N_CYCLES:
        _cycle_counter = 0
        return True
    return False
