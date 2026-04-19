"""
eTrader v4.5 — Position Monitor (Capa 7)
Monitors active trades and manages exits.

Responsibilities:
  1. Update unrealized P&L using real-time prices
  2. Check stop-loss / take-profit hits
  3. Apply trailing stops when in profit
  4. Close positions and move to trades_journal
  5. Alert via Telegram on significant events
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.strategy.proactive_exit import evaluate_proactive_exit
from app.strategy.dynamic_sl_manager import evaluate_sl_action


MODULE = "position_monitor"


class PositionMonitor:
    """Monitors active stock positions and manages exits."""

    async def check_all_positions(self):
        """Main cycle: check every active position."""
        sb = get_supabase()
        
        active = sb.table("stocks_positions")\
            .select("*")\
            .eq("status", "open")\
            .execute()

        if not active.data:
            return

        log_info(MODULE, f"Monitoring {len(active.data)} active positions...")

        for trade in active.data:
            await self._check_position(trade)

    async def _check_position(self, trade: dict):
        """Check a single position for exit conditions."""
        ticker = trade["ticker"]
        
        try:
            # Get current price
            from app.data.yfinance_provider import YFinanceProvider
            provider = YFinanceProvider()
            info = await provider.get_ticker_info(ticker)
            
            if not info:
                log_warning(MODULE, f"Cannot get price for {ticker}")
                return

            current_price = float(info.get("current_price", 0))
            if current_price <= 0:
                return

            entry_price = float(trade.get("avg_price", 0))
            # SL/TP are sometimes stored in trade_opportunities, but let's check position first
            stop_loss = float(trade.get("stop_loss", 0)) if trade.get("stop_loss") else 0
            target_price = float(trade.get("take_profit", 0)) if trade.get("take_profit") else 0
            shares = int(trade.get("shares", 0))

            if entry_price <= 0 or shares <= 0:
                return

            # Calculate unrealized P&L
            pnl_usd = (current_price - entry_price) * shares
            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Update unrealized P&L in DB
            sb = get_supabase()
            sb.table("stocks_positions").update({
                "unrealized_pnl": round(pnl_usd, 2),
                "unrealized_pnl_pct": round(pnl_pct, 2),
                "current_price": current_price,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", trade["id"]).execute()

            # ── NUEVO: Cierre Proactivo Aa51/Bb51 ──
            closed = await self.check_proactive_exit_stocks(ticker, trade, current_price, sb)
            if closed:
                return

            # ── NUEVO: Stop Loss Dinámico y Trailing Stop ──
            # Reutilizamos el motor SIPV adaptado para Stocks
            import yfinance as yf
            t_obj = yf.Ticker(ticker)
            hist_4h = t_obj.history(period="15d", interval="1h") # 1h como proxy de 4h para Stocks
            hist_1d = t_obj.history(period="30d", interval="1d")

            # Mapeo a formato estándar para el evaluador
            pos_std = {
                'id': trade['id'],
                'symbol': ticker,
                'side': 'long',
                'avg_entry_price': entry_price,
                'sl_type': trade.get('sl_type', 'backstop'),
                'sl_backstop_price': trade.get('sl_backstop_price') or stop_loss,
                'sl_dynamic_price': trade.get('sl_dynamic_price'),
                'trailing_sl_price': trade.get('trailing_sl_price'),
                'highest_price_reached': trade.get('highest_price_reached', current_price),
                'lowest_price_reached': trade.get('lowest_price_reached', current_price),
                'stop_loss_price': stop_loss
            }

            snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).execute()
            snap_val = snap_res.data[0] if snap_res.data else {}

            sl_res = evaluate_sl_action(
                position=pos_std,
                current_price=current_price,
                snap=snap_val,
                df_4h=hist_4h,
                df_1d=hist_1d,
                market_type='stocks_spot'
            )

            sl_action = sl_res['action']

            if sl_action == 'close_backstop':
                log_warning(MODULE, f"🔴 BACKSTOP HIT: {ticker} @ ${current_price:.2f}")
                await self._close_position(trade, current_price, "backstop_sl")
                return

            if sl_action == 'trigger_dynamic_sl':
                log_warning(MODULE, f"🔴 DYNAMIC SL HIT: {ticker} @ ${current_price:.2f} (SIPV)")
                await self._close_position(trade, current_price, "dynamic_sl")
                return

            if sl_action == 'activate_dynamic_sl':
                new_sl = sl_res['sl_price']
                sb.table("stocks_positions").update({
                    "sl_type": "dynamic",
                    "sl_dynamic_price": new_sl,
                    "stop_loss": new_sl,
                    "sl_activated_at": datetime.now(timezone.utc).isoformat(),
                    "sl_activation_reason": sl_res.get('reason', 'sipv')
                }).eq("id", trade["id"]).execute()
                log_info(MODULE, f"⚡ ACTIVANDO SL DINÁMICO: {ticker} @ ${new_sl:.2f}")

            if sl_action == 'update_trailing':
                new_trailing = sl_res['sl_price']
                sb.table("stocks_positions").update({
                    "trailing_sl_price": new_trailing,
                    "highest_price_reached": sl_res.get('new_max'),
                    "stop_loss": new_trailing # En Stocks protegemos el stop_loss directamente
                }).eq("id", trade["id"]).execute()
                log_info(MODULE, f"📈 TRAILING STOP ACTIVO: {ticker} SL movido a ${new_trailing:.2f}")

            log_info(MODULE, f"  {ticker}: ${current_price:.2f} | P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)")

        except Exception as e:
            log_error(MODULE, f"Error monitoring {ticker}: {e}")

    async def check_proactive_exit_stocks(self, ticker: str, position: dict, current_price: float, sb) -> bool:
        """ Evalúa Aa51/Bb51 para posiciones de Stocks. """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            # Para Stocks usamos velas diarias (1D) o de 1H como equivalente al 4H de Crypto
            # Vamos a usar 1H para velocidad de reacción
            hist = t.history(period="15d", interval="1h")
            
            if hist.empty or len(hist) < 3:
                return False

            import pandas as pd
            df_4h = pd.DataFrame()
            df_4h['open'] = hist['Open']
            df_4h['high'] = hist['High']
            df_4h['low'] = hist['Low']
            df_4h['close'] = hist['Close']

            # Recuperar snapshot de base de datos
            snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).execute()
            snap = snap_res.data[0] if snap_res.data else {}

            position_std = {
                'symbol':          ticker,
                'side':            'long', # Default to long in spot
                'avg_entry_price': float(position.get('avg_price', position.get('entry_price', 0))),
                'size':            float(position.get('shares', 1)),
            }

            result = evaluate_proactive_exit(
                position      = position_std,
                current_price = current_price,
                snap          = snap,
                df_4h         = df_4h,
                market_type   = 'stocks_spot',
            )

            if not result['should_close']:
                return False

            pnl = result['pnl']
            
            # Use normal process to close
            await self._close_position(position, current_price, result['rule_code'])
            
            # Send alert
            from app.core.telegram_notifier import send_telegram
            await send_telegram(
                f'🛡️ CIERRE PROACTIVO STOCKS [{ticker}]\n'
                f'Regla: {result["rule_code"]}\n'
                f'P&L: +{pnl["pnl_pct"]:.3f}% (${pnl["pnl_usd"]:.2f})\n'
                f'Razón: {result["reason"]}'
            )
            return True
        except Exception as e:
            log_error(MODULE, f"Error en proactive exit stocks {ticker}: {e}")
            return False


    async def _close_position(self, trade: dict, exit_price: float, exit_reason: str):
        """Close a position and record in journal."""
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()
        ticker = trade["ticker"]
        entry_price = float(trade.get("entry_price", 0))
        shares = int(trade.get("shares", 0))

        pnl_usd = round((exit_price - entry_price) * shares, 2)
        pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0
        result = "win" if pnl_usd > 0 else "loss"

        try:
            # 1. Insert into trades_journal
            journal_entry = {
                "ticker": ticker,
                "shares": shares,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "entry_date": trade.get("entry_time"),
                "exit_date": now,
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "result": result,
                "exit_reason": exit_reason,
            }
            sb.table("trades_journal").insert(journal_entry).execute()

            # 2. Mark trade as closed
            sb.table("stocks_positions").update({
                "status": "closed",
                "current_price": exit_price,
                "unrealized_pnl": pnl_usd,
                "unrealized_pnl_pct": pnl_pct,
                "updated_at": now
            }).eq("id", trade["id"]).execute()

            emoji = "🟢" if result == "win" else "🔴"
            log_info(MODULE, f"{emoji} CLOSED: {ticker} | {exit_reason} | "
                             f"P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)")

            # 3. Send Telegram notification
            await self._notify_close(ticker, result, pnl_usd, pnl_pct, exit_reason)

        except Exception as e:
            log_error(MODULE, f"Error closing position {ticker}: {e}")

    async def _notify_close(self, ticker, result, pnl_usd, pnl_pct, reason):
        """Send Telegram notification for trade closure."""
        try:
            from app.core.telegram_notifier import send_telegram
            emoji = "🟢" if result == "win" else "🔴"
            msg = (f"{emoji} *STOCK TRADE CLOSED*\n"
                   f"Ticker: `{ticker}`\n"
                   f"Result: {result.upper()}\n"
                   f"P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)\n"
                   f"Reason: {reason}")
            await send_telegram(msg)
        except:
            pass  # Non-critical

    async def force_close_all(self, reason: str = "manual_close"):
        """Emergency: close all active positions at market price."""
        sb = get_supabase()
        active = sb.table("stocks_positions")\
            .select("*")\
            .eq("status", "open")\
            .execute()

        if not active.data:
            log_info(MODULE, "No active positions to close")
            return []

        results = []
        for trade in active.data:
            try:
                from app.data.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                info = await provider.get_ticker_info(trade["ticker"])
                price = float(info.get("current_price", trade.get("entry_price", 0)))
                await self._close_position(trade, price, reason)
                results.append({"ticker": trade["ticker"], "status": "closed"})
            except Exception as e:
                results.append({"ticker": trade["ticker"], "status": "error", "error": str(e)})

        return results
