"""
eTrader v4.5 — Order Executor (Capa 6)
Converts trade_opportunities → IB Bracket Orders or Paper Orders.

Flow:
  1. Reads pending trade_opportunities from DB
  2. Validates risk parameters (position sizing, drawdown)
  3. Places bracket order on IB TWS (if connected) or records paper trade
  4. Updates opportunity status and creates trades_active entry

Paper Trading Mode:
  - Records simulated entries at current market price
  - Tracks P&L against real-time data
  - Mirrors IB bracket structure for realistic simulation
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.data.ib_provider import get_ib_connection, IB_AVAILABLE

MODULE = "order_executor"


class OrderExecutor:
    """Executes trade opportunities as real IB orders or paper trades."""

    def __init__(self):
        self.ib = get_ib_connection() if IB_AVAILABLE else None
        self.paper_mode = True  # Default safety

    async def load_config(self):
        """Load execution config from Supabase."""
        sb = get_supabase()
        try:
            res = sb.table("stocks_config").select("key, value").execute()
            cfg = {r["key"]: r["value"] for r in (res.data or [])}
            self.paper_mode = cfg.get("paper_mode_active", "true") == "true"
            self.kill_switch = cfg.get("kill_switch_active", "false") == "true"
            self.total_capital = float(cfg.get("total_capital_usd", "5000"))
            self.max_risk_pct = float(cfg.get("max_risk_per_trade_pct", "1.0"))
            self.max_positions = int(cfg.get("max_concurrent_positions", "5"))
            self.max_daily_loss = float(cfg.get("max_daily_loss_usd", "100"))
        except Exception as e:
            log_warning(MODULE, f"Config load error, using defaults: {e}")
            self.paper_mode = True
            self.kill_switch = False
            self.total_capital = 5000
            self.max_risk_pct = 1.0
            self.max_positions = 5
            self.max_daily_loss = 100

    async def execute_pending_opportunities(self) -> list[dict]:
        """
        Main entry point: process all pending trade_opportunities.
        Returns list of execution results.
        """
        await self.load_config()

        if self.kill_switch:
            log_warning(MODULE, "🛑 KILL SWITCH ACTIVE — no orders will be placed")
            return []

        sb = get_supabase()
        results = []

        # 1. Check current positions count
        active_res = sb.table("trades_active").select("id").eq("status", "active").execute()
        active_count = len(active_res.data or [])
        if active_count >= self.max_positions:
            log_warning(MODULE, f"Max positions reached ({active_count}/{self.max_positions})")
            return []

        # 2. Check daily loss
        daily_loss = await self._get_daily_pnl()
        if abs(daily_loss) >= self.max_daily_loss:
            log_warning(MODULE, f"🛑 Daily loss limit reached: ${daily_loss:.2f} / ${self.max_daily_loss}")
            return []

        # 3. Fetch pending opportunities
        pending = sb.table("trade_opportunities")\
            .select("*")\
            .eq("status", "pending")\
            .order("meta_score", desc=True)\
            .limit(self.max_positions - active_count)\
            .execute()

        if not pending.data:
            log_info(MODULE, "No pending opportunities to execute")
            return []

        for opp in pending.data:
            result = await self._execute_single(opp)
            results.append(result)

        return results

    async def _execute_single(self, opp: dict) -> dict:
        """Execute a single trade opportunity."""
        ticker = opp["ticker"]
        opp_id = opp["id"]
        log_info(MODULE, f"{'📝 PAPER' if self.paper_mode else '🔴 LIVE'} Executing: {ticker}")

        try:
            # Position sizing
            entry_price = float(opp.get("entry_zone_high") or opp.get("entry_zone_low") or 0)
            stop_loss = float(opp.get("stop_loss") or 0)
            target_1 = float(opp.get("target_1") or 0)

            if entry_price <= 0 or stop_loss <= 0:
                # Fetch current price from yfinance as fallback
                from app.data.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                info = await provider.get_ticker_info(ticker)
                if info:
                    entry_price = float(info.get("current_price", 0))
                    if entry_price > 0:
                        atr_est = entry_price * 0.015  # 1.5% ATR estimate
                        stop_loss = round(entry_price - (atr_est * 2), 2)
                        target_1 = round(entry_price + (atr_est * 3), 2)

            if entry_price <= 0:
                return await self._mark_failed(opp_id, "Invalid entry price")

            # Calculate shares
            risk_per_share = abs(entry_price - stop_loss)
            if risk_per_share <= 0:
                return await self._mark_failed(opp_id, "Invalid risk calculation")

            max_risk_usd = self.total_capital * (self.max_risk_pct / 100)
            calculated_shares = int(max_risk_usd / risk_per_share)
            max_allowed_shares = int(self.total_capital * 0.2 / entry_price)  # Cap: max 20% of total capital
            
            shares = min(calculated_shares, max_allowed_shares)

            if shares <= 0:
                return await self._mark_failed(opp_id, f"Capital/Risk constraints limit shares to 0. Min required for 1 share safe exposure: ${entry_price:.2f}")

            if self.paper_mode:
                return await self._paper_execute(opp_id, ticker, entry_price, stop_loss, target_1, shares)
            else:
                return await self._ib_execute(opp_id, ticker, entry_price, stop_loss, target_1, shares)

        except Exception as e:
            log_error(MODULE, f"Execution failed for {ticker}: {e}")
            return await self._mark_failed(opp_id, str(e))

    async def _notify_open(self, ticker: str, mode: str, shares: int, entry: float, sl: float, tp: float):
        """Send Telegram notification on trade execution."""
        try:
            from app.core.telegram_notifier import send_telegram
            mode_badge = "📝 PAPER" if mode == "paper" else "🔴 LIVE"
            msg = (f"🚀 *STOCK TRADE OPENED* ({mode_badge})\n"
                   f"Ticker: `{ticker}`\n"
                   f"Shares: {shares}\n"
                   f"Entry Price: ${entry:.2f}\n"
                   f"Stop Loss: ${sl:.2f}\n"
                   f"Take Profit: ${tp:.2f}")
            await send_telegram(msg)
        except Exception as e:
            log_warning(MODULE, f"Telegram notification failed: {e}")

    async def _paper_execute(self, opp_id, ticker, entry, sl, tp, shares) -> dict:
        """Simulate order execution in paper mode."""
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()

        # Create active trade (paper)
        trade = {
            "ticker": ticker,
            "shares": shares,
            "entry_price": entry,
            "stop_loss": sl,
            "target_1": tp,
            "entry_time": now,
            "status": "active",
            "opportunity_id": opp_id,
            "unrealized_pnl": 0.0,
        }

        try:
            res = sb.table("trades_active").insert(trade).execute()
            trade_id = res.data[0]["id"] if res.data else None

            # Update opportunity status
            sb.table("trade_opportunities").update({
                "status": "executed",
                "updated_at": now,
            }).eq("id", opp_id).execute()

            log_info(MODULE, f"📝 PAPER TRADE: {ticker} BUY {shares}x @ ${entry:.2f} "
                             f"SL=${sl:.2f} TP=${tp:.2f} (trade_id={trade_id})")

            # Fire telegram alert
            await self._notify_open(ticker, "paper", shares, entry, sl, tp)

            return {
                "status": "paper_executed",
                "ticker": ticker,
                "trade_id": trade_id,
                "shares": shares,
                "entry": entry,
                "sl": sl,
                "tp": tp,
            }
        except Exception as e:
            log_error(MODULE, f"Paper trade insert failed: {e}")
            return {"status": "error", "ticker": ticker, "error": str(e)}

    async def _ib_execute(self, opp_id, ticker, entry, sl, tp, shares) -> dict:
        """Execute real bracket order on IB TWS."""
        if not self.ib or not self.ib.connected:
            log_warning(MODULE, f"IB not connected, falling back to paper for {ticker}")
            return await self._paper_execute(opp_id, ticker, entry, sl, tp, shares)

        try:
            result = self.ib.place_bracket_order(
                ticker=ticker,
                action="BUY",
                qty=shares,
                entry_price=entry,
                stop_price=sl,
                target_price=tp,
            )

            if "error" in result:
                return await self._mark_failed(opp_id, result["error"])

            # Record live trade
            sb = get_supabase()
            now = datetime.now(timezone.utc).isoformat()

            trade = {
                "ticker": ticker,
                "shares": shares,
                "entry_price": entry,
                "stop_loss": sl,
                "target_1": tp,
                "entry_time": now,
                "status": "active",
                "opportunity_id": opp_id,
                "ib_parent_id": result["parent_id"],
                "ib_stop_id": result["stop_id"],
                "ib_target_id": result["target_id"],
            }

            res = sb.table("trades_active").insert(trade).execute()
            trade_id = res.data[0]["id"] if res.data else None

            sb.table("trade_opportunities").update({
                "status": "executed",
                "updated_at": now,
            }).eq("id", opp_id).execute()

            log_info(MODULE, f"🔴 LIVE TRADE: {ticker} BUY {shares}x @ ${entry:.2f} "
                             f"IB Orders: {result['parent_id']}/{result['stop_id']}/{result['target_id']}")

            # Fire telegram alert
            await self._notify_open(ticker, "live", shares, entry, sl, tp)

            return {
                "status": "live_executed",
                "ticker": ticker,
                "trade_id": trade_id,
                "ib_orders": result,
            }

        except Exception as e:
            log_error(MODULE, f"IB execution failed for {ticker}: {e}")
            return await self._paper_execute(opp_id, ticker, entry, sl, tp, shares)

    async def _mark_failed(self, opp_id, reason: str) -> dict:
        sb = get_supabase()
        sb.table("trade_opportunities").update({
            "status": "rejected",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", opp_id).execute()
        log_warning(MODULE, f"Opportunity {opp_id} rejected: {reason}")
        return {"status": "rejected", "reason": reason}

    async def _get_daily_pnl(self) -> float:
        """Calculate today's realized P&L from journal."""
        sb = get_supabase()
        try:
            from datetime import date
            today = date.today().isoformat()
            res = sb.table("trades_journal")\
                .select("pnl_usd")\
                .gte("exit_date", today)\
                .execute()
            return sum(float(r.get("pnl_usd", 0) or 0) for r in (res.data or []))
        except:
            return 0.0
