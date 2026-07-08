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

from app.core.logger import log_info, log_error, log_warning, log_debug
from app.core.supabase_client import get_supabase
from app.strategy.proactive_exit import evaluate_proactive_exit
from app.strategy.dynamic_sl_manager import evaluate_sl_action
from app.analysis.fibonacci_utils import calculate_fibonacci_zone
from app.stocks.stocks_adaptive_tp_v2 import evaluate_stock_tp_v2


MODULE = "position_monitor"
MIN_HOLDING_MINUTES = 6.0  # Esperar al menos 6 min (1 vela de 5m + margen) antes de evaluar salidas



def safe_float(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except (ValueError, TypeError):
        return default

class PositionMonitor:
    """Monitors active stock positions and manages exits."""

    async def check_all_positions(self):
        """Main cycle: check every active position."""
        sb = get_supabase()
        
        # Load global stocks config
        config_res = sb.table("stocks_config").select("key, value").execute()
        stocks_config = {r["key"]: r["value"] for r in (config_res.data or [])}

        active = sb.table("stocks_positions")\
            .select("*")\
            .eq("status", "open")\
            .execute()

        if not active.data:
            return

        log_info(MODULE, f"Monitoring {len(active.data)} active positions...")

        for trade in active.data:
            await self._check_position(trade, stocks_config)

    async def _check_position(self, trade: dict, stocks_config: dict):
        """Check a single position for exit conditions."""
        ticker = trade["ticker"]
        
        try:
            # Get real-time price from IB first, fallback to YFinance
            current_price = 0.0
            try:
                from app.data.ib_provider import IBProvider
                ib_prov = IBProvider()
                await ib_prov.connect()
                current_price = await ib_prov.get_current_price(ticker)
            except Exception as e:
                log_warning(MODULE, f"IB price fallback for {ticker}: {e}")

            if current_price <= 0:
                from app.data.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                info = await provider.get_ticker_info(ticker)
                
                if not info:
                    log_warning(MODULE, f"Cannot get price for {ticker}")
                    return

                current_price = safe_float(info.get("current_price"))

            if current_price <= 0:
                return

            entry_price = safe_float(trade.get("avg_price") or trade.get("entry_price"))
            stop_loss = safe_float(trade.get("stop_loss"))
            target_price = safe_float(trade.get("take_profit"))
            shares = int(safe_float(trade.get("shares", 0)))

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

            # ── EREP Integration ──
            if trade.get('erep_active') or trade.get('erep_phase', 0) > 0:
                log_info(MODULE, f"Bypassing normal exits for {ticker} because EREP is active (phase: {trade.get('erep_phase')})")
                return

            # ── Cálculo de Antigüedad de la Posición ──
            entry_time_str = trade.get("first_buy_at") or trade.get("entry_time")
            age_mins = 0.0
            if entry_time_str:
                try:
                    # Normalizar ISO string para comparación
                    entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                    age_mins = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
                except Exception as age_e:
                    log_debug(MODULE, f"Error calculando age para {ticker}: {age_e}")

            # ── Cierre Proactivo AaPX51/BbPX51 ──
            closed = await self.check_proactive_exit_stocks(ticker, trade, current_price, pnl_pct, sb)
            if closed:
                return

            # ── NUEVO: Stop Loss Dinámico y Trailing Stop ──
            # Reutilizamos el motor SIPV adaptado para Stocks
            import yfinance as yf
            t_obj = yf.Ticker(ticker)
            hist_1h = t_obj.history(period="15d", interval="1h")
            hist_1d = t_obj.history(period="30d", interval="1d")
            hist_4h = None
            if not hist_1h.empty:
                try:
                    hist_4h = hist_1h.resample('4h').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                except Exception as e_resample:
                    log_error(MODULE, f"Error resampling 1h to 4h for {ticker}: {e_resample}")
                    hist_4h = hist_1h.copy()

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
                df_4h=hist_1h,
                df_1d=hist_1d,
                market_type='stocks_spot'
            )

            sl_action = sl_res['action']

            if sl_action == 'close_backstop':
                log_warning(MODULE, f"🔴 BACKSTOP HIT: {ticker} @ ${current_price:.2f}. Routing to EREP Phase 1...")
                sb.table("stocks_positions").update({
                    "erep_phase": 1,
                    "erep_p1_price": entry_price,
                    "erep_q1": safe_float(trade.get("shares_remaining")) or safe_float(trade.get("shares")) or shares,
                    "erep_market_type": "stocks_spot",
                }).eq("id", trade["id"]).execute()
                return

            if sl_action == 'trigger_dynamic_sl':
                log_warning(MODULE, f"🔴 DYNAMIC SL HIT: {ticker} @ ${current_price:.2f} (SIPV). Routing to EREP Phase 1...")
                sb.table("stocks_positions").update({
                    "erep_phase": 1,
                    "erep_p1_price": entry_price,
                    "erep_q1": safe_float(trade.get("shares_remaining")) or safe_float(trade.get("shares")) or shares,
                    "erep_market_type": "stocks_spot",
                }).eq("id", trade["id"]).execute()
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

            # ── NUEVO: FLASH EXIT PARA SCALPING (HOT) ──
            group = str(trade.get("group_name", "")).upper()
            if "HOT" in group or "SCALPING" in group:
                db_highest = trade.get("highest_price_reached")
                highest = safe_float(db_highest or current_price)
                if db_highest is None or current_price > highest:
                    highest = current_price
                    sb.table("stocks_positions").update({"highest_price_reached": highest}).eq("id", trade["id"]).execute()
                
                # Ajuste: Retroceso de 1.5% y Profit Mínimo de 0.8% para Scalping
                pullback = ((highest - current_price) / highest) * 100
                if pullback >= 1.5 and pnl_pct >= 0.8:
                    log_warning(MODULE, f"⚡ FLASH EXIT: {ticker} retroceso de {pullback:.1f}% detectado con profit de {pnl_pct:.2f}%. Cerrando.")
                    await self._close_position(trade, current_price, "hot_pullback_exit")
                    return

            # ── NUEVO: BLUE PROACTIVE EXIT (Salidas Rápidas 5m para APEX AZUL) ──
            rule_code_pos = str(trade.get("rule_code", "") or trade.get("strategy", "") or "")
            if rule_code_pos.startswith("BLUE_"):
                try:
                    hist_5m_blue = t_obj.history(period="2d", interval="5m")

                    if not hist_5m_blue.empty and len(hist_5m_blue) >= 20:
                        import pandas as pd
                        last_5m = hist_5m_blue.iloc[-1]
                        close_5m = float(last_5m['Close'])
                        high_5m = float(last_5m['High'])

                        # EMAs 5m
                        c5 = hist_5m_blue['Close'].astype(float)
                        ema3_5m = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])
                        ema9_5m = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])

                        # RSI 5m
                        delta = c5.diff()
                        gain = delta.clip(lower=0).rolling(14).mean()
                        loss = (-delta.clip(upper=0)).rolling(14).mean()
                        rs = gain / loss.replace(0, 1e-10)
                        rsi_5m = float((100 - 100 / (1 + rs)).iloc[-1])

                        # Bollinger 5m
                        sma20_5m = float(c5.rolling(20).mean().iloc[-1])
                        std20_5m = float(c5.rolling(20).std().iloc[-1])
                        bb_upper_5m = sma20_5m + 2 * std20_5m

                        # Fibonacci zone 5m
                        atr_5m = float((hist_5m_blue['High'] - hist_5m_blue['Low']).rolling(14).mean().iloc[-1])
                        fib_zone_5m = calculate_fibonacci_zone(current_price, sma20_5m, atr_5m)

                        # Señales externas
                        pine_sig = str(snap_val.get('pinescript_signal', '') or '').upper()
                        sipv_15m = str(snap_val.get('sipv_signal_15m', '') or snap_val.get('sipv_signal', '') or '')

                        exit_reason = None

                        # A. HIGH >= UPPER_6 (Fibonacci zona extrema)
                        if fib_zone_5m >= 6:
                            exit_reason = f"BLUE_EXIT_UPPER6: Fib zone {fib_zone_5m} >= 6 (Overextended)"

                        # B. RSI_5m >= 80 (Agotamiento)
                        elif rsi_5m >= 80:
                            exit_reason = f"BLUE_EXIT_RSI80: RSI_5m={rsi_5m:.1f} >= 80 (Exhaustion)"

                        # C. SIPV 15m Reversión Bajista
                        elif 'revers' in sipv_15m.lower() and 'bajist' in sipv_15m.lower():
                            exit_reason = f"BLUE_EXIT_SIPV_REV: SIPV_15m={sipv_15m}"

                        # D. Pine SELL + EMA3 < EMA9
                        elif pine_sig == 'SELL' and ema3_5m < ema9_5m:
                            exit_reason = f"BLUE_EXIT_PINE_EMA: SELL + EMA3={ema3_5m:.2f} < EMA9={ema9_5m:.2f}"

                        # E. Pine SELL + HIGH >= BB_UPPER
                        elif pine_sig == 'SELL' and high_5m >= bb_upper_5m:
                            exit_reason = f"BLUE_EXIT_PINE_BB: SELL + HIGH={high_5m:.2f} >= BB={bb_upper_5m:.2f}"

                        # F. Pine SELL + CLOSE < EMA3
                        elif pine_sig == 'SELL' and close_5m < ema3_5m:
                            exit_reason = f"BLUE_EXIT_PINE_EMA3: SELL + CLOSE={close_5m:.2f} < EMA3={ema3_5m:.2f}"

                        if exit_reason:
                            log_warning(MODULE, f"🔵 BLUE EXIT: {ticker} @ ${current_price:.2f} | {exit_reason}")
                            await self._close_position(trade, current_price, exit_reason.split(":")[0])
                            from app.core.telegram_notifier import send_telegram
                            await send_telegram(
                                f'🔵 CIERRE BLUE EXIT [{ticker}]\n'
                                f'P&L: {pnl_pct:+.2f}%\n'
                                f'Razón: {exit_reason}'
                            )
                            return

                except Exception as blue_e:
                    log_error(MODULE, f"Error en BLUE EXIT {ticker}: {blue_e}")

            # ── NUEVO: Adaptive TP v2 (Stocks) ──
            try:
                hist_15m = t_obj.history(period="5d", interval="15m")
                hist_5m = t_obj.history(period="2d", interval="5m")
                
                # Fetch recent RVOL (simplified)
                rvol = 1.0
                if not hist_15m.empty:
                    vol_ema = hist_15m['Volume'].rolling(20).mean().iloc[-1]
                    cur_vol = hist_15m['Volume'].iloc[-1]
                    if vol_ema > 0: rvol = cur_vol / vol_ema

                tp_res = evaluate_stock_tp_v2(
                    ticker=ticker,
                    position=trade,
                    current_price=current_price,
                    snap=snap_val,
                    df_15m=hist_15m,
                    df_5m=hist_5m,
                    df_1h=hist_1h,
                    df_4h=hist_4h,
                    rvol=rvol,
                    sar_15m=snap_val.get('sar_trend_15m', 1)
                )

                # Actualizar indicadores en DB (NUEVOS CAMPOS)
                debug = tp_res.get('debug_indicators', {})
                ema_info = debug.get('ema', {})
                sipv15 = debug.get('sipv_15m', {})
                sipv4h = debug.get('sipv_4h', {})
                fib_info = debug.get('fib', {})

                sb.table("stocks_positions").update({
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", trade["id"]).execute()

                if tp_res['action'] == 'close_total':
                    log_warning(MODULE, f"🎯 TP V2 CLOSE TOTAL: {ticker} @ ${current_price:.2f} | Reason: {tp_res['reason']}")
                    await self._close_position(trade, current_price, f"tp_v2_total_{tp_res.get('trigger', 'signal')}")
                    return

                if tp_res['action'] in ['close_block1', 'close_block2', 'close_block3']:
                    block_name = tp_res['action'].replace('close_', '')
                    log_info(MODULE, f"🎯 TP V2 PARTIAL: {ticker} {block_name.upper()} @ ${current_price:.2f} | Reason: {tp_res['reason']}")
                    await self._execute_partial_close(trade, current_price, tp_res['shares'], block_name, tp_res['reason'])
                    # No retornamos aquí porque la posición sigue abierta (parcialmente)
                else:
                    log_debug(MODULE, f"Skipping adaptive TP for {ticker}: age {age_mins:.1f} < {MIN_HOLDING_MINUTES}")

            except Exception as tp_e:
                log_error(MODULE, f"Error en Adaptive TP V2 para {ticker}: {tp_e}")

            log_info(MODULE, f"  {ticker}: ${current_price:.2f} | P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)")

        except Exception as e:
            log_error(MODULE, f"Error monitoring {ticker}: {e}")

    async def check_proactive_exit_stocks(self, ticker: str, position: dict, current_price: float, pnl_pct: float, sb) -> bool:
        """ Evalúa AaPX51/BbPX51 para posiciones de Stocks. """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist_1h = t.history(period="15d", interval="1h")
            
            if hist_1h.empty or len(hist_1h) < 3:
                return False

            import pandas as pd
            df_4h = pd.DataFrame()
            df_4h['open'] = hist_1h['Open']
            df_4h['high'] = hist_1h['High']
            df_4h['low'] = hist_1h['Low']
            df_4h['close'] = hist_1h['Close']

            # ── NUEVO: Análisis de velas 5m/15m para Salida en Zonas Extremas ──
            hist_15m = t.history(period="5d", interval="15m")
            hist_5m = t.history(period="2d", interval="5m")

            # Recuperar snapshot de base de datos
            snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).execute()
            snap = snap_res.data[0] if snap_res.data else {}
            
            # CALCULAR ZONA EN TIEMPO REAL (Evita delay del scanner de 5 min)
            basis = float(snap.get('basis') or current_price)
            atr = 0.0
            try:
                # Intentar obtener ATR del snapshot o de technical_scores (si existe)
                atr = float(snap.get('atr') or 0)
                if atr <= 0:
                    # Fallback: estimación basada en 2% del precio (volatilidad promedio)
                    atr = current_price * 0.02
            except:
                atr = current_price * 0.02
            
            fib_zone = calculate_fibonacci_zone(current_price, basis, atr)
            log_debug(MODULE, f"Real-time Fib Zone for {ticker}: {fib_zone}")

            position_std = {
                'symbol':          ticker,
                'side':            'long', # Default to long in spot
                'avg_entry_price': safe_float(position.get('avg_price') or position.get('entry_price')),
                'size':            safe_float(position.get('shares'), 1),
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
        entry_price = safe_float(trade.get("entry_price") or trade.get("avg_price"))
        shares = int(safe_float(trade.get("shares")))

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
                "entry_date": trade.get("entry_time") or trade.get("first_buy_at"),
                "exit_date": now,
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "result": result,
                "exit_reason": exit_reason,
                "trade_type": trade.get("strategy") or trade.get("rule_code") or "V5_INDUSTRIAL"
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
            
            # 3. Registrar profit en capital acumulado
            try:
                from app.core.capital_manager import register_realized_pnl
                register_realized_pnl('stocks', pnl_usd)
            except Exception as cap_e:
                log_error(MODULE, f"Error registrando profit acumulado: {cap_e}")

            emoji = "🟢" if result == "win" else "🔴"
            log_info(MODULE, f"{emoji} CLOSED: {ticker} | {exit_reason} | "
                             f"P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)")

            # 4. Send Telegram notification
            await self._notify_close(ticker, result, pnl_usd, pnl_pct, exit_reason)

        except Exception as e:
            log_error(MODULE, f"Error closing position {ticker}: {e}")

    async def _execute_partial_close(self, trade: dict, exit_price: float, shares_to_close: int, block_name: str, reason: str):
        """Executes a partial close for a block (B1, B2, B3)."""
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()
        ticker = trade["ticker"]
        entry_price = safe_float(trade.get("avg_price") or trade.get("entry_price"))
        
        # Calculate P&L for this block
        pnl_usd = round((exit_price - entry_price) * shares_to_close, 2)
        pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0
        
        try:
            # 1. Update Position
            update_data = {
                f"tp_{block_name}_executed": True,
                f"tp_{block_name}_price": exit_price,
                f"tp_{block_name}_pnl": pnl_usd,
                "shares_remaining": int(trade.get("shares_remaining", trade["shares"])) - shares_to_close,
                "updated_at": now
            }
            
            # If it was the last block or if remaining shares <= 0, close it
            if update_data["shares_remaining"] <= 0:
                await self._close_position(trade, exit_price, f"partial_finish_{block_name}")
                return

            sb.table("stocks_positions").update(update_data).eq("id", trade["id"]).execute()
            
            # 2. Record in journal (as partial)
            journal_entry = {
                "ticker": ticker,
                "shares": shares_to_close,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "entry_date": trade.get("entry_time") or trade.get("first_buy_at"),
                "exit_date": now,
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "result": "win" if pnl_usd > 0 else "loss",
                "exit_reason": f"partial_{block_name}_{reason}",
                "trade_type": trade.get("strategy") or trade.get("rule_code") or "V5_INDUSTRIAL"
            }
            sb.table("trades_journal").insert(journal_entry).execute()

            # 3. Notify
            from app.core.telegram_notifier import send_telegram
            emoji = "🎯"
            msg = (f"{emoji} *STOCK PARTIAL CLOSE ({block_name.upper()})*\n"
                   f"Ticker: `{ticker}`\n"
                   f"Shares: {shares_to_close}\n"
                   f"P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)\n"
                   f"Reason: {reason}")
            await send_telegram(msg)
            
        except Exception as e:
            log_error(MODULE, f"Error executing partial close for {ticker}: {e}")

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
                price = safe_float(info.get("current_price")) or safe_float(trade.get("avg_price"))
                await self._close_position(trade, price, reason)
                results.append({"ticker": trade["ticker"], "status": "closed"})
            except Exception as e:
                results.append({"ticker": trade["ticker"], "status": "error", "error": str(e)})

        return results
