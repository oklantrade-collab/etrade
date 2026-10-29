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
MIN_HOLDING_MINUTES = 15.0  # Mínimo 15 min (3 velas de 5m) para filtrar ruido intradía antes de evaluar salidas técnicas/proactivas



def safe_float(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_col(df, col_name: str):
    if df is None: return None
    if col_name in df.columns: return df[col_name].astype(float)
    if col_name.capitalize() in df.columns: return df[col_name.capitalize()].astype(float)
    if col_name.upper() in df.columns: return df[col_name.upper()].astype(float)
    return None


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

    async def check_fast_tick_positions(self):
        """
        Sub-ciclo rápido (cada 15s) para monitoreo intraminuto de Regla 2d-3, 2a, 2b y Trailing Stop
        en posiciones ALPHA_RUNNER o cuyo precio haya perforado la Banda Superior de Bollinger.
        """
        sb = get_supabase()
        active = sb.table("stocks_positions").select("*").eq("status", "open").execute()
        if not active.data:
            return

        config_res = sb.table("stocks_config").select("key, value").execute()
        stocks_config = {r["key"]: r["value"] for r in (config_res.data or [])}

        for trade in active.data:
            # Universal: monitorear TODAS las posiciones abiertas sin sesgo de filtros para ejecutar salidas intraminuto
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

            # ── 1. PROTECCIÓN EOD GOLDEN HOUR (15:00 a 15:55 ET) & CIERRE DURO (15:50 ET) ──
            from app.core.market_hours import get_nyc_now
            from datetime import time as dt_time
            nyc_now = get_nyc_now()
            is_weekday = nyc_now.weekday() < 5
            cur_t = nyc_now.time()

            # 1.1 HARD-EXIT INCONDICIONAL 15:50+ ET (Cero Retención Nocturna)
            is_eod_window = is_weekday and (nyc_now.hour > 15 or (nyc_now.hour == 15 and nyc_now.minute >= 50))
            if is_eod_window:
                allow_ah = str(stocks_config.get("allow_after_hours", "false")).lower() == "true"
                if not allow_ah or pnl_pct >= 0 or pnl_pct < 0 or trade.get('erep_active'):
                    log_warning(MODULE, f"⏰ EOD HARD-EXIT (15:50+ ET): {ticker} cerrando al 100% para evitar riesgo nocturno. PnL: {pnl_pct:+.2f}%")
                    await self._close_position(trade, current_price, "eod_hard_exit_1550")
                    return

            # 1.2 GOLDEN HOUR HARVEST (15:00 a 15:50 ET) PARA POSICIONES CON GANANCIA >= +5.0%
            if is_weekday and pnl_pct >= 5.0 and dt_time(15, 0) <= cur_t < dt_time(15, 50):
                gh_tp_done = bool(trade.get("golden_hour_tp_executed") or trade.get("tp_block1_executed"))
                if dt_time(15, 0) <= cur_t < dt_time(15, 30) and not gh_tp_done:
                    shares_total = int(safe_float(trade.get("shares") or 0))
                    rem_sh = int(safe_float(trade.get("shares_remaining") or shares_total))
                    shares_to_sell = max(1, int(shares_total * 0.50))
                    if rem_sh - shares_to_sell >= 1:
                        log_warning(MODULE, f"🌅 [GOLDEN HOUR FASE 1] {ticker}: Tomando 50% de ganancia (+{pnl_pct:.2f}% >= +5.0%). Venta de {shares_to_sell} acciones.")
                        await self._execute_partial_close(trade, current_price, shares_to_sell, "golden_hour_tp50", f"Golden Hour 15:00-15:30 ET (+{pnl_pct:.2f}%)")
                        sb.table("stocks_positions").update({
                            "tp_block1_executed": True,
                            "golden_hour_tp_executed": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", trade["id"]).execute()
                        trade["tp_block1_executed"] = True
                        trade["golden_hour_tp_executed"] = True

                elif dt_time(15, 30) <= cur_t < dt_time(15, 50):
                    # Fase 2: liquidar ante debilidad en última media hora
                    import yfinance as yf_gh
                    gh_t = yf_gh.Ticker(ticker)
                    gh_5m = gh_t.history(period="1d", interval="5m")
                    is_weak = False
                    weak_msg = ""
                    if not gh_5m.empty and len(gh_5m) >= 3:
                        c5_gh = _safe_col(gh_5m, 'close')
                        if len(c5_gh) >= 3:
                            e3_5_gh = c5_gh.ewm(span=3, adjust=False).mean()
                            cur_e3 = float(e3_5_gh.iloc[-1])
                            prev_e3 = float(e3_5_gh.iloc[-2])
                            c_last = float(c5_gh.iloc[-1])
                            if cur_e3 <= prev_e3:
                                is_weak = True
                                weak_msg = f"EMA3(5m) descendente/plana (${cur_e3:.2f} <= ${prev_e3:.2f})"
                            elif c_last < cur_e3:
                                is_weak = True
                                weak_msg = f"Close(5m) ${c_last:.2f} < EMA3 ${cur_e3:.2f}"
                    if is_weak:
                        log_warning(MODULE, f"🌅 [GOLDEN HOUR FASE 2] {ticker}: Debilidad ({weak_msg}) con profit +{pnl_pct:.2f}%. Liquidando remanente antes del cierre.")
                        await self._close_position(trade, current_price, "golden_hour_weakness_exit")
                        return

            # ── 1.2 AUTO-REPAIR / AUTO-ESTABLECER PARÁMETROS DE RIESGO SI FALTAN ──
            sl_val = safe_float(trade.get("stop_loss"))
            tsl_val = safe_float(trade.get("trailing_sl_price") or trade.get("tp_trailing_sl") or trade.get("sl_dynamic_price"))
            tp_val = safe_float(trade.get("take_profit") or trade.get("tp_block1_price"))

            repair_needed = False
            repair_updates = {}
            atr_calc = max(0.05, current_price * 0.02)

            if sl_val <= 0:
                sl_val = round(max(0.01, entry_price - (atr_calc * 2.0)), 2)
                repair_updates["stop_loss"] = sl_val
                trade["stop_loss"] = sl_val
                repair_needed = True

            if tsl_val <= 0:
                tsl_val = sl_val
                repair_updates["trailing_sl_price"] = tsl_val
                trade["trailing_sl_price"] = tsl_val
                repair_needed = True

            if tp_val <= 0:
                tp_val = round(entry_price + (atr_calc * 5.0), 2)
                repair_updates["take_profit"] = tp_val
                trade["take_profit"] = tp_val
                repair_needed = True

            if repair_needed:
                repair_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
                try:
                    sb.table("stocks_positions").update(repair_updates).eq("id", trade["id"]).execute()
                    log_info(MODULE, f"🛡️ [AUTO-REPAIR] Parámetros de riesgo auto-reparados para {ticker}: SL=${sl_val:.2f}, TP=${tp_val:.2f}, TSL=${tsl_val:.2f}")
                except Exception as rep_err:
                    log_warning(MODULE, f"Error actualizando auto-repair para {ticker}: {rep_err}")

            # ── 1.5 AUDITORÍA DE SEGURIDAD DIAGNÓSTICA (AUTO-REPARAR, PRESERVAR POSICIÓN) ──
            from app.stocks.diagnostic_validator import build_position_diagnostics
            snap_res = sb.table("market_snapshot").select("*").eq("symbol", ticker).limit(1).execute()
            snap_data = snap_res.data[0] if snap_res.data else None
            diag = build_position_diagnostics(trade, snap_db=snap_data)
            if not diag["is_valid"]:
                missing_str = ", ".join(diag["missing_fields"])
                log_warning(MODULE, f"⚠️ [DIAGNOSTICS] {ticker}: Variables requeridas ausentes ({missing_str}). Parámetros auto-reparados; posición preservada sin liquidación forzada.")

            # ── 2. HARD PANIC CUT INCONDICIONAL (Pérdida Máxima de Pánico Configurable) ──
            panic_threshold_cfg = safe_float(stocks_config.get("sl_wait_threshold") or stocks_config.get("sl_max_loss_hard"), 8.0)
            panic_limit_pct = -abs(panic_threshold_cfg)
            if pnl_pct <= panic_limit_pct:
                log_warning(MODULE, f"🛑 HARD PANIC CUT HIT: {ticker} @ ${current_price:.2f} ({pnl_pct:.2f}% <= {panic_limit_pct:.2f}%). Cortando a mercado incondicionalmente...")
                await self._close_position(trade, current_price, "hard_panic_cut_exit")
                return

            # ── 3. POSICIONES EN GANANCIA vs RESCATE EREP ──
            # Si la posición está en ganancia (pnl_usd >= 0), NUNCA debe ser bloqueada por erep_phase previo
            if pnl_usd < 0 and (trade.get('erep_active') or trade.get('erep_phase', 0) > 0):
                log_info(MODULE, f"EREP activo en pérdida para {ticker} (fase: {trade.get('erep_phase')}).")
                # Continuar flujo para permitir evaluar salidas técnicas o SL si corresponde

            # ── Cálculo de Antigüedad de la Posición ──
            entry_time_str = trade.get("first_buy_at") or trade.get("entry_time")
            age_mins = 0.0
            if entry_time_str:
                try:
                    entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                    age_mins = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
                except Exception as age_e:
                    log_debug(MODULE, f"Error calculando age para {ticker}: {age_e}")

            # ── MODELO DE SALIDA OPT3 (flag GAP_EXIT_MODEL=OPT3, solo posiciones GAP) ──
            # En OPT3 las salidas las gobierna gap_exit_opt3 (SL duro, TSL 15m al cierre, tramos 25/50/25).
            # Se desactivan las capas que no formaron parte del backtest validado (proactiva, escudo de
            # tendencia, ratchets universales, agotamiento 1H, sharp exit).
            try:
                from app.stocks.gap_exit_opt3 import is_opt3_gap_position
                opt3_gap = is_opt3_gap_position(trade)
            except Exception:
                opt3_gap = False

            # ── Cierre Proactivo AaPX51/BbPX51 ──
            # Requiere al menos MIN_HOLDING_MINUTES (15 min) salvo ganancia de clímax >= 2.5%
            if (age_mins >= MIN_HOLDING_MINUTES or pnl_pct >= 2.5) and not opt3_gap:
                closed = await self.check_proactive_exit_stocks(ticker, trade, current_price, pnl_pct, sb)
                if closed:
                    return

            # ── NUEVO: Stop Loss Dinámico y Trailing Stop ──
            # Reutilizamos el motor SIPV adaptado para Stocks
            import yfinance as yf
            t_obj = yf.Ticker(ticker)
            hist_1h = t_obj.history(period="15d", interval="1h")
            hist_1d = t_obj.history(period="30d", interval="1d")
            hist_15m = t_obj.history(period="5d", interval="15m")
            hist_5m = t_obj.history(period="2d", interval="5m")
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

            # ── ANÁLISIS DE RÉGIMEN 1H: PENDIENTE EMA3(1H) Y AGOTAMIENTO BOLLINGER ──
            slope_1h = 0.0
            regime_1h_defensive = False
            bb_1h_exhaustion = False
            l_curr_1h = 0.0

            if hist_1h is not None and len(hist_1h) >= 3:
                c1h_s = _safe_col(hist_1h, 'close')
                h1h_s = _safe_col(hist_1h, 'high')
                l1h_s = _safe_col(hist_1h, 'low')
                if c1h_s is not None and len(c1h_s) >= 3:
                    e3_1h_s = c1h_s.ewm(span=3, adjust=False).mean()
                    e3_curr_1h = float(e3_1h_s.iloc[-1])
                    e3_prev_1h = float(e3_1h_s.iloc[-2])
                    slope_1h = ((e3_curr_1h - e3_prev_1h) / max(1e-6, e3_prev_1h)) * 100.0

                    # Si la pendiente es plana o descendente tras el periodo de gracia
                    if age_mins >= 15.0 and slope_1h <= 0.0:
                        regime_1h_defensive = True
                        log_info(MODULE, f"🛡️ [1H REGIME DEFENSIVE] {ticker}: EMA3 1H plana/descendente ({slope_1h:.3f}% <= 0). Modo Defensivo Activo.")

                # Detección de Agotamiento de Rango en Banda Superior 1H
                if len(hist_1h) >= 20 and h1h_s is not None and l1h_s is not None and c1h_s is not None:
                    bb_up_1h = float(c1h_s.rolling(20).mean().iloc[-1] + 2.0 * c1h_s.rolling(20).std().iloc[-1])
                    h_curr = float(h1h_s.iloc[-1])
                    l_curr_1h = float(l1h_s.iloc[-1])
                    range_curr = h_curr - l_curr_1h
                    h_prev = float(h1h_s.iloc[-2])
                    l_prev = float(l1h_s.iloc[-2])
                    range_prev = h_prev - l_prev
                    if h_curr >= bb_up_1h and range_curr < range_prev and range_prev > 0:
                        bb_1h_exhaustion = True
                        regime_1h_defensive = True
                        log_info(MODULE, f"⚠️ [1H BB EXHAUSTION] {ticker}: High ${h_curr:.2f} >= BB Upper ${bb_up_1h:.2f} con rango comprimido ({range_curr:.2f} < {range_prev:.2f}). Modo Defensivo Activo.")

            # ── ESCUDO DE TENDENCIA INTRADÍA 15M/5M (ANTI SHAKE-OUT) ──
            trend_15m_bullish = False
            ema3_15m_val = 0.0
            ema9_15m_val = 0.0
            if hist_15m is not None and len(hist_15m) >= 10:
                c15_s = _safe_col(hist_15m, 'close')
                if c15_s is not None and len(c15_s) >= 10:
                    e3_15m_s = c15_s.ewm(span=3, adjust=False).mean()
                    e9_15m_s = c15_s.ewm(span=9, adjust=False).mean()
                    ema3_15m_val = float(e3_15m_s.iloc[-1])
                    ema9_15m_val = float(e9_s15 := e9_15m_s.iloc[-1])
                    trend_15m_bullish = ema3_15m_val > ema9_15m_val

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
            if opt3_gap:
                # OPT3: el SL/trailing lo gobierna gap_exit_opt3; se ignora el SL dinámico SIPV.
                sl_action = 'none'

            # Evaluación de Stop Loss con Escudo de Tendencia:
            # Si el precio toca el SL intradía, verificamos si está protegido por el Escudo de Tendencia
            if stop_loss > 0 and current_price <= stop_loss:
                # Si el régimen 1H es defensivo (impulso 1H frenado o en agotamiento) O si la tendencia 15m ya se quebró:
                if opt3_gap or regime_1h_defensive or not trend_15m_bullish:
                    log_warning(MODULE, f"🔴 STOP LOSS CONFIRMADO: {ticker} @ ${current_price:.2f} <= SL ${stop_loss:.2f} con tendencia rota/defensiva (1H slope={slope_1h:.2f}%, 15m bullish={trend_15m_bullish}). Cerrando...")
                    await self._close_position(trade, current_price, "sl_hard_exit_defensive")
                    return
                else:
                    # ESCUDO DE TENDENCIA ACTIVO: EMA3 > EMA9 en 15m y 1H con impulso alcista
                    # No cortar por simple mecha o retroceso de 1 vela si no ha tocado el Hard Panic Cut
                    log_info(MODULE, f"🛡️ [TREND SHIELD ACTIVE] {ticker}: Precio ${current_price:.2f} bajo SL ${stop_loss:.2f}, pero EMA3_15m (${ema3_15m_val:.2f}) > EMA9_15m (${ema9_15m_val:.2f}) y 1H alcista. Evitando corte por sacudida intradía.")

            # Si el precio perforó el Stop Loss o Dynamic SL evaluado técnicamente
            if sl_action in ('close_backstop', 'trigger_dynamic_sl'):
                if opt3_gap or regime_1h_defensive or not trend_15m_bullish:
                    log_warning(MODULE, f"🔴 STOP LOSS HIT: {ticker} @ ${current_price:.2f} ({sl_action}). Ejecutando cierre a mercado...")
                    await self._close_position(trade, current_price, f"sl_{sl_action}")
                    return
                else:
                    log_info(MODULE, f"🛡️ [TREND SHIELD ACTIVE] {ticker}: SL Action ({sl_action}) suspendida por tendencia alcista activa 15m/1H.")

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

            # ── MOTOR UNIVERSAL DE TRAILING STOP Y BLOQUEO BOLLINGER PARA STOCKS ──
            # 1. Rastrear incondicionalmente el máximo alcanzado para TODAS las posiciones
            db_highest = trade.get("highest_price_reached")
            highest = max(safe_float(db_highest or 0), current_price) if db_highest else current_price
            if db_highest is None or current_price > safe_float(db_highest):
                sb.table("stocks_positions").update({"highest_price_reached": highest}).eq("id", trade["id"]).execute()
                trade["highest_price_reached"] = highest

            peak_gain_pct = ((highest - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
            cur_sl = safe_float(trade.get("stop_loss") or 0.0)
            proposed_sl = cur_sl
            ratchet_reason = f"Trailing Ratchet (+{peak_gain_pct:.1f}% pico -> SL ${proposed_sl:.2f})"

            # 2. Protección de Ganancia Escalonada (Ratchet Trailing)
            if peak_gain_pct >= 10.0:
                proposed_sl = max(proposed_sl, round(entry_price * 1.05, 2))  # Bloquea al menos +5%
            if peak_gain_pct >= 25.0:
                proposed_sl = max(proposed_sl, round(entry_price * 1.15, 2))  # Bloquea al menos +15%
            if peak_gain_pct >= 50.0:
                proposed_sl = max(proposed_sl, round(highest * 0.75, 2))      # Bloquea al menos 75% del pico
            if peak_gain_pct >= 100.0:
                proposed_sl = max(proposed_sl, round(highest * 0.80, 2))      # Bloquea al menos 80% del pico

            # 2.5 NUEVO: TRAILING STOP ESCALONADO EN 3 ETAPAS (SECCIÓN B.5 & 2C)
            try:
                from app.stocks.aduana_stocks_exit_engine import calculate_alpha_escalating_trailing_stop
                alpha_tsl_res = calculate_alpha_escalating_trailing_stop(
                    position=trade,
                    current_price=current_price,
                    df_5m=hist_5m,
                    df_15m=hist_15m
                )
                if alpha_tsl_res.get('should_update'):
                    cand_alpha_sl = safe_float(alpha_tsl_res.get('new_sl'))
                    if cand_alpha_sl > proposed_sl and cand_alpha_sl < current_price:
                        proposed_sl = cand_alpha_sl
                        ratchet_reason = alpha_tsl_res.get('reason', ratchet_reason)
            except Exception as e_atsl:
                log_debug(MODULE, f"Error calculando TSL Escalonado B.5 para {ticker}: {e_atsl}")

            # 3. Trailing Estructural 1H (ADUANA: Low[t-1] o EMA9 de 1H)
            if hist_1h is not None and len(hist_1h) >= 5:
                try:
                    from app.stocks.aduana_stocks_exit_engine import calculate_1h_trailing_stop
                    res_1h_trail = calculate_1h_trailing_stop(trade, current_price, hist_1h)
                    if res_1h_trail.get('should_update'):
                        proposed_sl = max(proposed_sl, safe_float(res_1h_trail.get('new_sl')))
                except Exception as e_1h_t:
                    log_debug(MODULE, f"Error calculando trailing 1H {ticker}: {e_1h_t}")

            # 4. Trailing por Ruptura de Bandas de Bollinger (Al perforar BB Upper, elevar piso)
            bb_upper_1h = safe_float(snap_val.get('upper_bollinger') or snap_val.get('upper_5') or 0.0)
            if hist_1h is not None and len(hist_1h) >= 20 and bb_upper_1h <= 0:
                try:
                    c1h = _safe_col(hist_1h, 'close')
                    if c1h is not None:
                        bb_upper_1h = float(c1h.rolling(20).mean().iloc[-1] + 2.0 * c1h.rolling(20).std().iloc[-1])
                except Exception:
                    pass

            if bb_upper_1h > 0 and (highest >= bb_upper_1h * 0.99 or current_price >= bb_upper_1h * 0.99):
                # Si el precio perforó la Banda Bollinger Superior, el Stop Loss DEBE asegurarse
                # al menos al nivel de la banda o un piso protegido
                bb_floor = round(max(entry_price * 1.05, bb_upper_1h * 0.92), 2)
                proposed_sl = max(proposed_sl, bb_floor)

            # 4.5 MODO DEFENSIVO POR RÉGIMEN 1H (Slope <= 0 o Agotamiento BB Upper): Asegurar ganancias
            if regime_1h_defensive and pnl_pct > 0:
                defensive_floor = round(entry_price * 1.002, 2)  # Breakeven + fees
                if bb_1h_exhaustion and l_curr_1h > 0 and l_curr_1h < current_price:
                    defensive_floor = max(defensive_floor, round(l_curr_1h, 2))  # Lock al mínimo de la vela 1H de agotamiento
                if defensive_floor > proposed_sl and defensive_floor < current_price:
                    proposed_sl = defensive_floor
                    ratchet_reason = "1H Defensive Regime Profit Lock"

            # Si el nivel propuesto supera el SL actual y está por debajo del precio actual:
            if opt3_gap:
                # OPT3: gap_exit_opt3 maneja los tramos y ratchets; si hubo un pico explosivo (>=25% o 40%), asegurar al menos el piso protegido
                if peak_gain_pct >= 40.0:
                    proposed_sl = max(cur_sl, round(highest * 0.80, 2))
                elif peak_gain_pct >= 25.0:
                    proposed_sl = max(cur_sl, round(entry_price * 1.15, 2))
                else:
                    proposed_sl = cur_sl
            if proposed_sl > cur_sl and proposed_sl < current_price:
                sb.table("stocks_positions").update({
                    "stop_loss": proposed_sl,
                    "trailing_sl_price": proposed_sl,
                    "highest_price_reached": highest,
                    "sl_type": "trailing_ratchet",
                    "sl_activation_reason": str(ratchet_reason)[:100]
                }).eq("id", trade["id"]).execute()
                trade["stop_loss"] = proposed_sl
                trade["trailing_sl_price"] = proposed_sl
                log_info(MODULE, f"🛡️ TRAILING RATCHET ACTUALIZADO: {ticker} SL ${cur_sl:.2f} -> ${proposed_sl:.2f} ({ratchet_reason})")

            # 5. Salida Protectora si el precio perfora el Trailing Stop en Ganancia
            if trade.get("stop_loss") and current_price <= safe_float(trade["stop_loss"]) and safe_float(trade["stop_loss"]) > entry_price:
                log_warning(MODULE, f"🎯 TRAILING STOP HIT: {ticker} @ ${current_price:.2f} (SL: ${trade['stop_loss']:.2f}). Asegurando ganancia...")
                await self._close_position(trade, current_price, "trailing_profit_lock")
                return

            # ── FLASH EXIT PARA SCALPING (HOT) ──
            group = str(trade.get("group_name", "")).upper()
            if "HOT" in group or "SCALPING" in group:
                pullback = ((highest - current_price) / highest) * 100
                if pullback >= 1.5 and (pnl_pct >= 2.5 or (pnl_pct >= 0.8 and age_mins >= MIN_HOLDING_MINUTES)):
                    log_warning(MODULE, f"⚡ FLASH EXIT: {ticker} retroceso de {pullback:.1f}% detectado con profit de {pnl_pct:.2f}%. Cerrando.")
                    await self._close_position(trade, current_price, "hot_pullback_exit")
                    return

            # ── SALIDA INMEDIATA POR AGOTAMIENTO DE FUERZA COMPRADORA (ALPHA RUNNERS) ──
            # Requerimiento: "cuando agote su fuerza compradora es salir inmediatamente"
            if ("ALPHA" in group or "RUNNER" in group or "FAST" in str(trade.get("rule_code", "")).upper()) and not opt3_gap:
                try:
                    from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
                    live_1h_data = get_live_1h_candle_and_sipv(ticker, current_price)
                    
                    ema3_drop = bool(live_1h_data.get("is_ema3_1h_descending", False))
                    ema3_live = float(live_1h_data.get("ema3_1h_live") or 0.0)
                    
                    # Si la EMA3 de 1H gira a la baja y el precio perfora por debajo de la EMA3 en vivo:
                    if ema3_drop and current_price < ema3_live and (pnl_pct >= 1.0 or (pnl_pct >= 0.0 and age_mins >= 8.0)):
                        log_warning(MODULE, f"⚡ AGOTAMIENTO DE FUERZA COMPRADORA: {ticker} EMA3 1H descendente (${ema3_live:.2f}) con precio ${current_price:.2f}. Salida Inmediata asegurando +{pnl_pct:.2f}%.")
                        await self._close_position(trade, current_price, "buying_force_exhaustion_exit")
                        return
                except Exception as e_bf_exit:
                    log_debug(MODULE, f"Error evaluando agotamiento de fuerza compradora para {ticker}: {e_bf_exit}")

            # ── NUEVO: BLUE PROACTIVE EXIT (Salidas Rápidas 5m para APEX AZUL) ──
            rule_code_pos = str(trade.get("rule_code", "") or trade.get("strategy", "") or "")
            if rule_code_pos.startswith("BLUE_") and not opt3_gap and (age_mins >= MIN_HOLDING_MINUTES or pnl_pct >= 2.5):
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

            # ── EVALUACIÓN MOTOR AGUDO ALPHA RUNNER & CLÍMAX MULTIVARIABLE (SECCIÓN A) ──
            try:
                from app.stocks.aduana_stocks_exit_engine import evaluate_alpha_runner_sharp_exit
                sharp_exit_res = evaluate_alpha_runner_sharp_exit(
                    position=trade,
                    current_price=current_price,
                    df_5m=hist_5m,
                    df_15m=hist_15m,
                    df_1h=hist_1h
                )
                if sharp_exit_res.get('should_close') and not opt3_gap:
                    action = sharp_exit_res.get('action')
                    reason = sharp_exit_res.get('reason')
                    pct = sharp_exit_res.get('pct_to_close', 50)
                    if action == 'CLOSE_TOTAL' or pct >= 100:
                        log_warning(MODULE, f"⚡ SHARP EXIT TOTAL: {ticker} @ ${current_price:.2f} | Reason: {reason}")
                        await self._close_position(trade, current_price, sharp_exit_res.get('rule_code', 'ALPHA_SHARP_TOTAL_EXIT'))
                        return
                    elif action == 'CLOSE_PARTIAL_50' or pct == 50:
                        shares_to_close = sharp_exit_res.get('shares_to_close', max(1, int(trade.get('shares', 0) * 0.5)))
                        log_warning(MODULE, f"🎯 CLÍMAX MULTIVARIABLE PARCIAL 50%: {ticker} {shares_to_close} sh @ ${current_price:.2f} | Reason: {reason}")
                        await self._execute_partial_close(trade, current_price, shares_to_close, "climax_50", reason)
                        sb.table("stocks_positions").update({"tp_block1_executed": True}).eq("id", trade["id"]).execute()
                        trade["tp_block1_executed"] = True
            except Exception as e_sharp:
                log_debug(MODULE, f"Error en evaluate_alpha_runner_sharp_exit para {ticker}: {e_sharp}")

            # ── NUEVO: Adaptive TP v2 (Stocks) ──
            try:
                # Si la posición tiene menos de MIN_HOLDING_MINUTES (15 min) y la ganancia no es clímax (>= 2.5%),
                # omitir la evaluación de TP/Aduana para filtrar ruido intradía
                if age_mins < MIN_HOLDING_MINUTES and pnl_pct < 2.5:
                    log_debug(MODULE, f"Skipping adaptive TP for {ticker}: age {age_mins:.1f} < {MIN_HOLDING_MINUTES} y pnl {pnl_pct:.2f}% < 2.5%")
                else:
                    if hist_15m is None or hist_15m.empty:
                        hist_15m = t_obj.history(period="5d", interval="15m")
                    if hist_5m is None or hist_5m.empty:
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
                        df_1d=hist_1d,
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
        # Tras cierres parciales (tramos TP) solo queda 'shares_remaining' por vender: evita sobre-vender el original.
        _rem = safe_float(trade.get("shares_remaining"))
        if _rem > 0:
            shares = min(shares, int(_rem)) if shares > 0 else int(_rem)

        pnl_usd = round((exit_price - entry_price) * shares, 2)
        pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0
        result = "win" if pnl_usd > 0 else "loss"

        try:
            from app.stocks.stocks_order_executor import is_ib_bridge_alive
            bridge_active = is_ib_bridge_alive()

            if bridge_active:
                # Si el puente IBKR está activo: NO cerrar inmediatamente para evitar cierres ficticios.
                # Se marca 'closing' y se envía la orden 'pending' a TWS. El cierre real en Supabase
                # y en trades_journal se ejecutará cuando el Broker confirme la ejecución.
                sb.table("stocks_positions").update({
                    "status": "closing",
                    "current_price": exit_price,
                    "unrealized_pnl": pnl_usd,
                    "unrealized_pnl_pct": pnl_pct,
                    "sl_close_reason": str(exit_reason)[:50],
                    "updated_at": now
                }).eq("id", trade["id"]).execute()

                sell_rule = "ADUANA_TP_CLOSE" if pnl_usd > 0 else "STOP_LOSS_INITIAL"
                if exit_reason in [
                    "STOP_LOSS_INITIAL", "ADUANA_TP_CLOSE", "EMERGENCY_EXIT",
                    "PRO_CANDLE_SELL", "HOT_CANDLE_SELL", "ADUANA_STRUCTURAL_1H_BREAK_EXIT",
                    "PULLBACK_ZOMBIE_TIME_EXIT", "BOLLINGER_EXPLOSION"
                ]:
                    sell_rule = exit_reason
                elif "tp" in str(exit_reason).lower() or "profit" in str(exit_reason).lower():
                    sell_rule = "ADUANA_TP_CLOSE"
                elif "sl" in str(exit_reason).lower() or "stop" in str(exit_reason).lower() or "loss" in str(exit_reason).lower():
                    sell_rule = "STOP_LOSS_INITIAL"
                else:
                    sell_rule = "EMERGENCY_EXIT"

                # DEDUPLICACIÓN: Comprobar si ya existe una orden de venta pendiente para este ticker
                try:
                    existing_so = sb.table("stocks_orders")\
                        .select("id")\
                        .eq("ticker", ticker)\
                        .eq("direction", "sell")\
                        .in_("status", ["pending", "processing"])\
                        .limit(1)\
                        .execute()
                    if existing_so.data:
                        log_warning(MODULE, f"⛔ [DEDUPLICATE] Orden SELL para {ticker} ya encolada (ID #{existing_so.data[0]['id']}). Omitiendo duplicado.")
                        return
                except Exception:
                    pass

                sb.table("stocks_orders").insert({
                    "ticker": ticker,
                    "group_name": trade.get("group_name", "STOCKS"),
                    "rule_code": sell_rule,
                    "order_type": "market",
                    "direction": "sell",
                    "shares": shares,
                    "market_price": exit_price,
                    "status": "pending",
                    "created_at": now
                }).execute()
                log_info(MODULE, f"📡 [IBKR BRIDGE] Orden SELL enviada a APOLO para liquidar {shares}x {ticker} en TWS Paper (regla: {sell_rule}). Posición en espera de confirmación broker.")

            else:
                # Modo simulación puro (sin puente activo)
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
                    "exit_reason": str(exit_reason)[:50] if exit_reason else "closed",
                    "trade_type": str(trade.get("strategy") or trade.get("rule_code") or "V5_INDUSTRIAL")[:20]
                }
                sb.table("trades_journal").insert(journal_entry).execute()

                sb.table("stocks_positions").update({
                    "status": "closed",
                    "current_price": exit_price,
                    "unrealized_pnl": pnl_usd,
                    "unrealized_pnl_pct": pnl_pct,
                    "updated_at": now
                }).eq("id", trade["id"]).execute()

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
            raw_shares_remaining = trade.get("shares_remaining")
            raw_shares = trade.get("shares")
            current_shares = int(safe_float(raw_shares_remaining) if raw_shares_remaining is not None else safe_float(raw_shares, 0))
            shares_rem = current_shares - int(shares_to_close)

            # Blindaje Matemático: Mover Stop Loss a Breakeven + 1.0% para proteger el remanente
            cur_sl = safe_float(trade.get("stop_loss", 0.0))
            be_sl = round(entry_price * 1.01, 2)
            new_sl = max(cur_sl, be_sl) if entry_price > 0 else cur_sl

            update_data = {
                f"tp_{block_name}_executed": True,
                f"tp_{block_name}_price": exit_price,
                f"tp_{block_name}_pnl": pnl_usd,
                "shares_remaining": shares_rem,
                "stop_loss": new_sl,
                "sl_type": "breakeven_plus_1pct"[:20],
                "sl_activation_reason": f"Blindaje tras parcial {block_name} (+1.0% garantizado @ ${new_sl:.2f})"[:100],
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
                "exit_reason": f"partial_{block_name}_{reason}"[:50],
                "trade_type": str(trade.get("strategy") or trade.get("rule_code") or "V5_INDUSTRIAL")[:20]
            }
            sb.table("trades_journal").insert(journal_entry).execute()

            # 2.5 Si el puente IBKR está activo en APOLO, despachar orden SELL parcial a TWS Paper
            try:
                from app.stocks.stocks_order_executor import is_ib_bridge_alive
                if is_ib_bridge_alive():
                    partial_rule = "FT_PARTIAL_SELL" if ("FT" in str(reason).upper() or "FAST" in str(trade.get("rule_code", "")).upper() or "CLIMAX" in str(reason).upper()) else "ADUANA_TP_CLOSE"
                    sb.table("stocks_orders").insert({
                        "ticker": ticker,
                        "group_name": trade.get("group_name", "STOCKS"),
                        "rule_code": partial_rule,
                        "order_type": "market",
                        "direction": "sell",
                        "shares": int(shares_to_close),
                        "market_price": exit_price,
                        "status": "pending",
                        "created_at": now
                    }).execute()
                    log_info(MODULE, f"📡 [IBKR BRIDGE] Orden SELL Parcial enviada a APOLO ({shares_to_close}x {ticker}) en TWS Paper.")
            except Exception as ib_err:
                log_error(MODULE, f"Error despachando SELL parcial a IB Bridge: {ib_err}")

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
