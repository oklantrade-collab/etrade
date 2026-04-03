"""
eTrade v3 — Position Manager
Handles position lifecycle: entries, sizing, SL/TP, break-even, partial closes.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase

MODULE = "position_manager"

BINANCE_MIN_ORDER = 15.0  # USD minimum on Binance


@dataclass
class PositionEntry:
    trade_n: int
    price: float
    usd_amount: float
    timestamp: datetime
    rule_code: str


@dataclass
class Position:
    symbol: str
    side: str  # 'long' | 'short'
    entries: list  # list of PositionEntry
    sl_price: float
    tp_upper5: float  # upper_5 or lower_5 (partial close)
    tp_upper6: float  # upper_6 or lower_6 (full close)
    is_open: bool = True
    breakeven_active: bool = False

    def sync_to_supabase(self):
        """Symmetry rule: Memory first, DB immediate sync for WARM data."""
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        data = {
            "symbol": self.symbol,
            "side": self.side,
            "avg_entry_price": float(self.avg_entry_price),
            "total_usd": float(self.total_usd),
            "sl_price": float(self.sl_price),
            "tp_partial": float(self.tp_upper5),
            "tp_full": float(self.tp_upper6),
            "is_open": self.is_open,
            "breakeven_active": self.breakeven_active,
            "entries": [
                {
                    "trade_n": e.trade_n,
                    "price": float(e.price),
                    "usd_amount": float(e.usd_amount),
                    "timestamp": e.timestamp.isoformat(),
                    "rule_code": e.rule_code
                } for e in self.entries
            ],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        sb.table('bot_state').upsert(data).execute()
        
        # ALSO sync to 'positions' table (which the frontend/dashboard uses)
        # We update by symbol and status='open'
        try:
            pos_update = {
                "sl_price": float(self.sl_price),
                "avg_entry_price": float(self.avg_entry_price),
                "tp_partial_price": float(self.tp_upper5),
                "tp_full_price": float(self.tp_upper6),
                "breakeven_activated": self.breakeven_active,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            sb.table('positions').update(pos_update).eq('symbol', self.symbol).eq('status', 'open').execute()
        except Exception as e:
            log_warning(MODULE, f"Failed to sync Position {self.symbol} to 'positions' table: {e}")

        log_info(MODULE, f"WARM sync: Position {self.symbol} persisted to Supabase (bot_state & positions).")

    @property
    def avg_entry_price(self) -> float:
        total_usd = sum(e.usd_amount for e in self.entries)
        weighted = sum(e.price * e.usd_amount for e in self.entries)
        return weighted / total_usd if total_usd > 0 else 0.0

    @property
    def total_usd(self) -> float:
        return sum(e.usd_amount for e in self.entries)

    def add_entry(self, entry: PositionEntry):
        self.entries.append(entry)
        # Immediate sync after new entry (Requirement 1)
        self.sync_to_supabase()

    def update_sl_after_new_entry(self, atr: float, atr_mult: float):
        avg = self.avg_entry_price
        if self.side == "long":
            self.sl_price = avg - (atr * atr_mult)
        else:
            self.sl_price = avg + (atr * atr_mult)
        # Immediate sync after SL update (Requirement 1)
        self.sync_to_supabase()

    def check_breakeven(self, current_price: float, fee_pct: float = 0.001) -> bool:
        if self.breakeven_active: return False
        avg = self.avg_entry_price
        risk = abs(avg - self.sl_price)
        be_target = avg + risk if self.side == "long" else avg - risk

        if (self.side == "long" and current_price >= be_target) or \
           (self.side == "short" and current_price <= be_target):
            self.sl_price = avg * (1 + fee_pct if self.side == "long" else 1 - fee_pct)
            self.breakeven_active = True
            # Immediate sync after break-even activation (Requirement 1)
            self.sync_to_supabase()
            return True
        return False

    def close(self, reason: str, exit_price: float):
        self.is_open = False
        # Last sync to set is_open=false (Requirement 1)
        self.sync_to_supabase()
        # Also log to audit history (COLD)
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        # ROIs and PnL calculation...
        log_info(MODULE, f"COLD log: Position {self.symbol} closed. Reason: {reason}.")


def calculate_position_sizes(
    capital_operativo: float,
    n_trades_config: int,
    regime: str,
    confluence_score: int,
) -> list[dict]:
    """
    Calculate the USD amount for each entry.

    Confluence adjustment:
      3 TFs aligned → full sizing (×1.00)
      2 TFs aligned → reduced (×0.85)
      1 TF aligned  → reduced (×0.70)
    """
    max_by_regime = {"alto_riesgo": 1, "riesgo_medio": 3, "bajo_riesgo": 5}
    effective_n = min(n_trades_config, max_by_regime.get(regime, 3))

    distributions = {
        1: [1.00],
        2: [0.40, 0.60],
        3: [0.20, 0.30, 0.50],
        4: [0.15, 0.20, 0.30, 0.35],
        5: [0.10, 0.15, 0.20, 0.25, 0.30],
    }

    sizing_mult = {1: 0.70, 2: 0.85, 3: 1.00}.get(confluence_score, 0.70)
    dist = distributions.get(effective_n, [1.00])
    result = []

    for i, pct in enumerate(dist, start=1):
        usd = round(capital_operativo * pct * sizing_mult, 2)
        if usd < BINANCE_MIN_ORDER:
            continue
        result.append(
            {
                "trade_n": i,
                "usd": usd,
                "pct": round(pct * 100, 1),
                "price_cond_long": None
                if i == 1
                else f"close < trade_{i-1}_price",
                "price_cond_short": None
                if i == 1
                else f"close > trade_{i-1}_price",
            }
        )

    return result


def get_max_trades_for_capital(capital_operativo: float) -> int:
    """Determine max allowed trades based on operating capital."""
    if capital_operativo < 30:
        return 1
    elif capital_operativo < 60:
        return 2
    elif capital_operativo < 150:
        return 3
    elif capital_operativo < 300:
        return 4
    else:
        return 5


def evaluate_take_profit_full(
    df: pd.DataFrame,
    position: Position,
    regime: str,
) -> dict:
    """
    Full close logic based on EMA50 vs EMA200 mode.

    EMA50 > EMA200 (trend mode):
      Partial close at upper_5 + full close at Nivel 3 / upper_6

    EMA50 < EMA200 (defensive mode):
      Close as soon as price reaches upper_5 or upper_6
    """
    last = df.iloc[-1]
    current_price = float(last["close"])
    ema50_val = float(last.get("ema4", 0)) if pd.notna(last.get("ema4")) else 0.0
    ema200_val = float(last.get("ema5", 0)) if pd.notna(last.get("ema5")) else 0.0
    trend_mode = ema50_val > ema200_val

    if position.side == "long":
        in_tp_partial = current_price >= position.tp_upper5
        in_tp_full = current_price >= position.tp_upper6

        if trend_mode:
            nivel3_confirmed = (
                str(last.get("ema20_phase", "")) == "nivel_3_long"
                and bool(last.get("vol_decreasing", False))
                and (
                    bool(last.get("is_gravestone", False))
                    or bool(last.get("high_lower_than_prev", False))
                    or (bool(last.get("is_red_candle", False)) and in_tp_full)
                )
            )
            return {
                "close_partial": in_tp_partial,
                "close_full": in_tp_full and nivel3_confirmed,
                "reason": "Nivel 3 + agotamiento volumen + vela reversal"
                if nivel3_confirmed
                else "",
                "mode": "trend",
            }
        else:
            return {
                "close_partial": in_tp_partial,
                "close_full": in_tp_full,
                "reason": "Modo defensivo EMA50 < EMA200",
                "mode": "defensive",
            }
    else:  # short
        in_tp_partial = current_price <= position.tp_upper5
        in_tp_full = current_price <= position.tp_upper6

        if trend_mode:
            nivel3_confirmed = (
                str(last.get("ema20_phase", "")) == "nivel_3_short"
                and bool(last.get("vol_increasing", False))
                and (
                    bool(last.get("is_dragonfly", False))
                    or bool(last.get("low_higher_than_prev", False))
                    or (bool(last.get("is_green_candle", False)) and in_tp_full)
                )
            )
            return {
                "close_partial": in_tp_partial,
                "close_full": in_tp_full and nivel3_confirmed,
                "reason": "Nivel -3 + aumento volumen + vela reversal"
                if nivel3_confirmed
                else "",
                "mode": "trend",
            }
        else:
            return {
                "close_partial": in_tp_partial,
                "close_full": in_tp_full,
                "reason": "Modo defensivo EMA50 < EMA200",
                "mode": "defensive",
            }


def calculate_partial_close_sizes(position: Position) -> dict:
    """
    Determine which trades to close at partial vs full TP.

    With 3 entries:
      Partial (upper_5): close T1 (20%) + T2 (30%) = 50% of position
      Full (upper_6):    close T3 (50%) = largest capital
      → T3 always travels to the most profitable extreme.

    With 1 entry:
      Partial (upper_5): close 40%
      Full (upper_6):    close 60%
    """
    n = len(position.entries)
    if n == 1:
        total = position.entries[0].usd_amount
        return {
            "partial_usd": round(total * 0.40, 2),
            "full_usd": round(total * 0.60, 2),
        }

    sorted_entries = sorted(position.entries, key=lambda e: e.usd_amount)
    half = len(sorted_entries) // 2 + (1 if len(sorted_entries) % 2 else 0)
    partial_entries = sorted_entries[:half]
    full_entries = sorted_entries[half:]

    return {
        "partial_usd": sum(e.usd_amount for e in partial_entries),
        "full_usd": sum(e.usd_amount for e in full_entries),
        "partial_trades": [e.trade_n for e in partial_entries],
        "full_trades": [e.trade_n for e in full_entries],
    }


def process_signal_two_steps(
    new_signal: str,
    current_price: float,
    symbol: str,
    timestamp: datetime,
    open_position: Optional[Position],
    rr_valid: bool,
    sizes: list[dict],
) -> list[dict]:
    """
    Two-step order flow: close opposite position FIRST, then open new.

    Rule: if there's an opposing position open, ALWAYS close first.
    Only open new position if RR is valid.
    If RR not valid: close anyway, stay flat.
    """
    orders = []

    # STEP 1: Close opposing position if exists
    if open_position and open_position.side != new_signal:
        orders.append(
            {
                "step": 1,
                "action": "close",
                "side": open_position.side,
                "symbol": symbol,
                "price": current_price,
                "avg_entry": open_position.avg_entry_price,
                "reason": f"Señal {new_signal.upper()} opuesta — cerrar {open_position.side.upper()}",
                "timestamp": timestamp.isoformat(),
            }
        )

    # STEP 2: Open new position (only if RR valid)
    if rr_valid:
        orders.append(
            {
                "step": len(orders) + 1,
                "action": "open",
                "side": new_signal,
                "symbol": symbol,
                "price": current_price,
                "sizes": sizes,
                "timestamp": timestamp.isoformat(),
            }
        )
    else:
        orders.append(
            {
                "step": len(orders) + 1,
                "action": "flat",
                "reason": f"RR insuficiente para abrir {new_signal.upper()}. Sistema en espera.",
                "timestamp": timestamp.isoformat(),
            }
        )

    return orders


def calculate_real_rr(
    entry: float,
    tp: float,
    sl: float,
    fee_pct: float = 0.001,
) -> float:
    """Risk-Reward ratio adjusted for round-trip fees."""
    eff_entry = entry * (1 + fee_pct)
    eff_tp = tp * (1 - fee_pct)
    eff_sl = sl * (1 - fee_pct)

    denominator = eff_entry - eff_sl
    if abs(denominator) < 1e-10:
        return 0.0

    return round((eff_tp - eff_entry) / denominator, 2)
