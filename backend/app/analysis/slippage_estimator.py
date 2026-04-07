"""
eTrader v4.5 — Slippage Estimator & Liquidity Scorer
Estimates execution slippage and assigns a Liquidity Score (0-10).

Slippage is the hidden cost of trading. For stocks $1-$50 with 500K+ daily volume,
typical slippage ranges from 0.02% to 0.5%. Trades exceeding 0.5% slippage are rejected.

Liquidity Score Components:
  - Average daily volume (weight: 40%)
  - Bid-ask spread estimate (weight: 30%)
  - Market cap tier (weight: 20%)
  - Time-of-day factor (weight: 10%)
"""
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.core.logger import log_info, log_warning

MODULE = "slippage_estimator"


def estimate_slippage(
    avg_daily_volume: int,
    order_shares: int,
    current_price: float,
    spread_pct: float | None = None,
) -> dict:
    """
    Estimate execution slippage for a stock trade.

    Parameters
    ----------
    avg_daily_volume : Average daily trading volume (shares)
    order_shares     : Number of shares in our order
    current_price    : Current stock price
    spread_pct       : Estimated bid-ask spread as % (if known)

    Returns
    -------
    dict: {
        slippage_pct: float,      # Estimated slippage as %
        slippage_usd: float,      # Estimated slippage in USD
        impact_ratio: float,      # Our order as % of avg volume
        acceptable: bool,         # True if slippage < 0.5%
        risk_level: str           # 'low' | 'medium' | 'high'
    }
    """
    if avg_daily_volume <= 0 or order_shares <= 0 or current_price <= 0:
        return {
            "slippage_pct": 1.0,
            "slippage_usd": 0.0,
            "impact_ratio": 1.0,
            "acceptable": False,
            "risk_level": "high",
        }

    # Market impact: our order as fraction of daily volume
    impact_ratio = order_shares / avg_daily_volume

    # Base slippage from market impact (square root model)
    # Standard model: slippage ≈ spread/2 + k × σ × √(V/ADV)
    # Simplified: impact_slippage = 0.1 × impact_ratio^0.5 × 100 (%)
    impact_slippage = 0.1 * np.sqrt(impact_ratio) * 100

    # Spread component
    if spread_pct is None:
        # Estimate spread based on price and volume
        spread_pct = _estimate_spread(current_price, avg_daily_volume)

    spread_slippage = spread_pct / 2  # We pay half the spread

    # Total slippage estimate
    total_slippage_pct = round(impact_slippage + spread_slippage, 4)
    total_slippage_usd = round(total_slippage_pct / 100 * current_price * order_shares, 2)

    # Risk classification
    if total_slippage_pct < 0.1:
        risk_level = "low"
    elif total_slippage_pct < 0.3:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {
        "slippage_pct":  total_slippage_pct,
        "slippage_usd":  total_slippage_usd,
        "impact_ratio":  round(impact_ratio, 6),
        "spread_pct":    round(spread_pct, 4),
        "acceptable":    total_slippage_pct < 0.5,  # Hard limit from spec
        "risk_level":    risk_level,
    }


def _estimate_spread(price: float, volume: int) -> float:
    """
    Estimate bid-ask spread based on price and volume.
    
    Empirical model:
    - Penny stocks ($1-$5): 0.3% - 1.0% spread
    - Mid-range ($5-$20): 0.05% - 0.3%
    - Established ($20-$50): 0.02% - 0.1%
    
    Higher volume = tighter spreads.
    """
    # Base spread from price tier
    if price <= 5:
        base = 0.5
    elif price <= 10:
        base = 0.15
    elif price <= 20:
        base = 0.08
    elif price <= 35:
        base = 0.05
    else:
        base = 0.03

    # Volume adjustment: high volume tightens spread
    if volume > 5_000_000:
        vol_factor = 0.5
    elif volume > 1_000_000:
        vol_factor = 0.7
    elif volume > 500_000:
        vol_factor = 0.85
    else:
        vol_factor = 1.0

    return round(base * vol_factor, 4)


def calculate_liquidity_score(
    avg_daily_volume: int,
    current_price: float,
    market_cap: int | None = None,
    spread_pct: float | None = None,
) -> int:
    """
    Calculate Liquidity Score (0-10) for a stock.

    Components:
      - Volume tier (40% weight)
      - Spread estimate (30% weight)
      - Market cap tier (20% weight)
      - Dollar volume (10% weight)

    Returns
    -------
    int: Liquidity score 0-10 (10 = most liquid)
    """
    score = 0.0

    # ── Volume tier (40%) — max 4.0 points ──
    if avg_daily_volume >= 10_000_000:
        vol_score = 4.0
    elif avg_daily_volume >= 5_000_000:
        vol_score = 3.5
    elif avg_daily_volume >= 2_000_000:
        vol_score = 3.0
    elif avg_daily_volume >= 1_000_000:
        vol_score = 2.5
    elif avg_daily_volume >= 500_000:
        vol_score = 2.0
    elif avg_daily_volume >= 200_000:
        vol_score = 1.0
    else:
        vol_score = 0.5
    score += vol_score

    # ── Spread (30%) — max 3.0 points ──
    if spread_pct is None:
        spread_pct = _estimate_spread(current_price, avg_daily_volume)

    if spread_pct <= 0.03:
        spread_score = 3.0
    elif spread_pct <= 0.05:
        spread_score = 2.5
    elif spread_pct <= 0.10:
        spread_score = 2.0
    elif spread_pct <= 0.20:
        spread_score = 1.5
    elif spread_pct <= 0.50:
        spread_score = 1.0
    else:
        spread_score = 0.5
    score += spread_score

    # ── Market cap tier (20%) — max 2.0 points ──
    if market_cap:
        if market_cap >= 10_000_000_000:    # $10B+
            cap_score = 2.0
        elif market_cap >= 2_000_000_000:   # $2B+
            cap_score = 1.5
        elif market_cap >= 500_000_000:     # $500M+
            cap_score = 1.0
        elif market_cap >= 300_000_000:     # $300M+
            cap_score = 0.5
        else:
            cap_score = 0.0
    else:
        cap_score = 1.0  # Default if unknown
    score += cap_score

    # ── Dollar volume (10%) — max 1.0 point ──
    dollar_volume = avg_daily_volume * current_price
    if dollar_volume >= 100_000_000:       # $100M+/day
        dv_score = 1.0
    elif dollar_volume >= 20_000_000:      # $20M+/day
        dv_score = 0.7
    elif dollar_volume >= 5_000_000:       # $5M+/day
        dv_score = 0.5
    else:
        dv_score = 0.2
    score += dv_score

    return min(round(score), 10)
