"""
eTrader v5.0 — Interactive Brokers Bridge Worker (APOLO Local Bridge)
=====================================================================
Este worker corre localmente en tu computadora "APOLO" para enlazar
Interactive Brokers TWS (Paper Trading, puerto 7497) con Supabase y Vercel.

¿Por qué corre en APOLO?
1. IBKR exige autenticación diaria y 2FA en Trader Workstation (TWS).
2. TWS abre un socket local en 127.0.0.1:7497.
3. Como APOLO tiene IP dinámica, este worker hace conexión SALIENTE hacia
   Supabase, eliminando la necesidad de IP fija, puertos abiertos o DDNS.
"""
import os
import sys
import time
import asyncio
from datetime import datetime, timezone

# Añadir raíz de backend al PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.data.ib_provider import get_ib_connection, IB_AVAILABLE

MODULE = "ib_bridge"

# Mapa local para relacionar orderId de IB con id de Supabase
# { ib_order_id: supabase_order_row }
PENDING_IB_ORDERS = {}
ACTIVE_BRIDGE = None


def send_telegram_alert(message: str):
    """Envío seguro de alertas Telegram."""
    try:
        from app.workers.alerts_service import send_telegram_message
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(message))
        except RuntimeError:
            asyncio.run(send_telegram_message(message))
    except Exception:
        pass


def on_ib_order_status(order_id: int, status_info: dict):
    """Callback invocado por IB TWS cuando una orden cambia de estado."""
    status = status_info.get("status")
    filled = status_info.get("filled", 0)
    avg_price = status_info.get("avg_fill_price", 0.0)

    log_info(MODULE, f"🔔 TWS Callback: Order #{order_id} -> Estado={status.upper()} (Filled={filled} @ ${avg_price:.2f})")

    if order_id not in PENDING_IB_ORDERS:
        return

    order_ctx = PENDING_IB_ORDERS[order_id]
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = order_ctx.get("ticker", "UNKNOWN")
    direction = order_ctx.get("direction", "buy").lower()
    shares = int(order_ctx.get("shares", filled or 1))

    target_b = str(order_ctx.get("target_band") or "").strip().upper()
    ticker_u = str(ticker or "").strip().upper()
    group_u = str(order_ctx.get("group_name") or "").strip().upper()
    is_opt_order = (
        ":OPT:" in ticker_u or ticker_u.startswith("OPT:") or
        ":OPT:" in target_b or target_b.startswith("OPT:") or "OPT:" in target_b or
        group_u in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS")
    )

    # Si la orden fue completada (FILLED)
    if status == "filled":
        exec_price = avg_price if avg_price > 0 else float(order_ctx.get("market_price") or 0)
        target_price = float(order_ctx.get("limit_price") or order_ctx.get("market_price") or exec_price)
        slippage_usd = round(exec_price - target_price, 4) if direction == "buy" else round(target_price - exec_price, 4)
        slippage_pct = round((slippage_usd / target_price * 100.0), 2) if target_price > 0 else 0.0

        log_info(MODULE, f"📊 Fills Reconciliation: Ticker={ticker} {direction.upper()} | Exec=${exec_price:.2f} Target=${target_price:.2f} | Slippage=${slippage_usd:+.2f} ({slippage_pct:+.2f}%)")

        # 1. Actualizar orden en stocks_orders
        try:
            try:
                sb.table("stocks_orders").update({
                    "status": "filled",
                    "filled_price": exec_price,
                    "slippage_usd": slippage_usd,
                    "slippage_pct": slippage_pct,
                    "filled_at": now_iso
                }).eq("id", order_ctx["id"]).execute()
            except Exception:
                sb.table("stocks_orders").update({
                    "status": "filled",
                    "filled_price": exec_price,
                    "filled_at": now_iso
                }).eq("id", order_ctx["id"]).execute()
        except Exception as e:
            log_error(MODULE, f"Error actualizando orden {order_ctx['id']} en Supabase: {e}")

        # 2. Si fue BUY: Crear o actualizar posición en stocks_positions (o opt_paper_trades si es opción)
        if direction == "buy":
            try:
                if is_opt_order:
                    try:
                        und_sym = ticker_u.split(":")[0].replace("OPT", "").strip(":")
                        exp_d = "20261026"
                        strike_num = 0.0
                        is_call = True
                        if "OPT:" in target_b:
                            parts = target_b.split(":")
                            if len(parts) == 4 and parts[0] == "OPT":
                                exp_d = parts[1]
                                strike_num = float(parts[2])
                                is_call = parts[3].upper() == "C"
                            elif len(parts) >= 5:
                                und_sym = parts[0] if parts[0] != "OPT" else parts[1]
                                exp_d = parts[2]
                                strike_num = float(parts[3])
                                is_call = parts[4].upper() == "C"
                        elif ":OPT:" in ticker_u or ticker_u.startswith("OPT:"):
                            parts = ticker_u.split(":")
                            if len(parts) >= 5:
                                und_sym = parts[0] if parts[0] != "OPT" else parts[1]
                                exp_d = parts[2]
                                strike_num = float(parts[3])
                                is_call = parts[-1].upper() == "C"

                        formatted_exp = f"{exp_d[:4]}-{exp_d[4:6]}-{exp_d[6:8]}" if len(exp_d) == 8 else exp_d
                        existing_opt = sb.table("opt_paper_trades").select("*").eq("symbol", und_sym).eq("status", "open").execute().data
                        if not existing_opt:
                            cid = None
                            conid = None
                            try:
                                c_res = sb.table("opt_contracts").select("id, conid").eq("expiry", formatted_exp).eq("strike", strike_num).eq("right", "C" if is_call else "P").limit(1).execute()
                                if c_res.data:
                                    cid = c_res.data[0].get("id")
                                    conid = c_res.data[0].get("conid")
                            except Exception:
                                pass

                            u_id = 1
                            try:
                                u_res = sb.table("opt_underlyings").select("id").eq("symbol", und_sym).limit(1).execute()
                                if u_res.data:
                                    u_id = u_res.data[0]["id"]
                            except Exception:
                                pass

                            fills = [{
                                "contract_id": cid,
                                "conid": conid,
                                "side": "buy",
                                "closing_side": "sell",
                                "right": "C" if is_call else "P",
                                "strike": strike_num,
                                "bid": exec_price,
                                "ask": exec_price,
                                "fill_price": exec_price,
                                "slippage_applied": 0.0,
                                "market_data_type": "DELAYED",
                                "fee_usd": 0.0,
                            }]

                            sb.table("opt_paper_trades").insert({
                                "underlying_id": u_id,
                                "symbol": und_sym,
                                "strategy_type": "long_call" if is_call else "long_put",
                                "direction": "bullish" if is_call else "bearish",
                                "status": "open",
                                "qty": shares,
                                "expiry": formatted_exp,
                                "entry_time": now_iso,
                                "entry_debit": exec_price,
                                "entry_fills": fills,
                                "last_mark_price": exec_price,
                                "unrealized_pnl": 0.0,
                                "entry_total_invested": round(shares * exec_price * 100, 2),
                                "max_loss_total": round(shares * exec_price * 100, 2),
                                "max_profit_total": 9999.0,
                                "breakeven": round(strike_num + exec_price, 2) if is_call else round(strike_num - exec_price, 2),
                                "model_version": "ib_live_paper",
                                "created_at": now_iso,
                                "updated_at": now_iso
                            }).execute()
                            log_info(MODULE, f"✅ Trade de opción registrado en opt_paper_trades para {und_sym}")
                    except Exception as opt_err:
                        log_warning(MODULE, f"No se pudo guardar en opt_paper_trades: {opt_err}")
                else:
                    # Verificar si ya existe posición abierta para acciones
                    pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
                    if pos_res.data:
                        pos = pos_res.data[0]
                        old_shares = int(pos.get("shares") or 0)
                        old_avg = float(pos.get("avg_price") or 0)
                        total_shares = old_shares + shares
                        new_avg = ((old_avg * old_shares) + (exec_price * shares)) / total_shares if total_shares > 0 else exec_price

                        sb.table("stocks_positions").update({
                            "shares": total_shares,
                            "avg_price": round(new_avg, 4),
                            "total_cost": round(total_shares * new_avg, 2),
                            "current_price": exec_price,
                            "updated_at": now_iso
                        }).eq("id", pos["id"]).execute()
                        log_info(MODULE, f"✅ Posición DCA actualizada para {ticker}: {total_shares} acc @ ${new_avg:.2f}")
                    else:
                        atr_fb = exec_price * 0.02
                        sl_p = round(exec_price - (atr_fb * 2.0), 2)
                        tp_p = round(exec_price + (atr_fb * 5.0), 2)

                        sb.table("stocks_positions").insert({
                            "ticker": ticker,
                            "direction": "long",
                            "shares": shares,
                            "avg_price": exec_price,
                            "total_cost": round(shares * exec_price, 2),
                            "current_price": exec_price,
                            "stop_loss": sl_p,
                            "trailing_sl_price": sl_p,
                            "highest_price_reached": exec_price,
                            "take_profit": tp_p,
                            "group_name": order_ctx.get("group_name", "IB_PAPER"),
                            "first_buy_at": now_iso,
                            "status": "open",
                            "updated_at": now_iso
                        }).execute()
                        log_info(MODULE, f"✅ Nueva posición creada en Supabase para {ticker}: {shares} acc @ ${exec_price:.2f} (SL: ${sl_p:.2f}, TP: ${tp_p:.2f})")

            except Exception as pos_e:
                log_error(MODULE, f"Error creando/actualizando posición para {ticker}: {pos_e}")

        # 3. Si fue SELL: Ejecutar cierre parcial o total confirmado con el broker
        elif direction == "sell":
            try:
                if is_opt_order:
                    # Cierre de opción confirmado con datos reales del broker
                    try:
                        und_sym = ticker_u.split(":")[0].replace("OPT", "").strip(":")
                        opt_pos_res = sb.table("opt_paper_trades").select("*").eq("symbol", und_sym).eq("status", "open").execute()
                        for opos in (opt_pos_res.data or []):
                            entry_debit = float(opos.get("entry_debit") or 0.0)
                            qty = int(opos.get("qty") or 1)
                            total_inv = float(opos.get("entry_total_invested") or (entry_debit * 100 * qty))
                            fee = 0.70 * qty
                            recovered = round((exec_price * 100 * qty) - fee, 2)
                            realized = round(recovered - total_inv, 2)

                            sb.table("opt_paper_trades").update({
                                "status": "closed",
                                "exit_time": now_iso,
                                "exit_credit": exec_price,
                                "exit_costs": fee,
                                "exit_total_recovered": recovered,
                                "realized_pnl": realized,
                                "unrealized_pnl": 0.0,
                                "last_mark_price": exec_price,
                                "last_mark_at": now_iso,
                                "exit_reason": "take_profit" if realized >= 0 else "stop_loss",
                                "updated_at": now_iso,
                                "exit_fills": [{
                                    "side": "buy",
                                    "closing_side": "sell",
                                    "fill_price": exec_price,
                                    "bid": exec_price,
                                    "ask": exec_price,
                                    "fee_usd": fee,
                                    "market_data_type": "LIVE"
                                }]
                            }).eq("id", opos["id"]).execute()
                            log_info(MODULE, f"opt_paper_trades ID {opos['id']} ({und_sym}) cerrado confirmado por Broker a ${exec_price:.2f} (PnL: ${realized:.2f})")
                    except Exception as opt_close_e:
                        log_warning(MODULE, f"Error actualizando opt_paper_trades en SELL: {opt_close_e}")
                else:
                    pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).in_("status", ["open", "closing"]).execute()
                    for pos in (pos_res.data or []):
                        entry_p = float(pos.get("avg_price") or 0)
                        pos_sh = int(pos.get("shares") or 0)
                        rem_sh = pos_sh - shares

                        if rem_sh > 0:
                            # Venta PARCIAL confirmada por el broker
                            pnl_usd = round((exec_price - entry_p) * shares, 2)
                            pnl_pct = round(((exec_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0
                            sb.table("stocks_positions").update({
                                "shares": rem_sh,
                                "shares_remaining": rem_sh,
                                "current_price": exec_price,
                                "status": "open",
                                "updated_at": now_iso
                            }).eq("id", pos["id"]).execute()
                            log_info(MODULE, f"✅ Venta PARCIAL confirmada por Broker para {ticker}: {shares} vendidas, quedan {rem_sh}")
                        else:
                            # Cierre TOTAL confirmado por el broker
                            pnl_usd = round((exec_price - entry_p) * pos_sh, 2)
                            pnl_pct = round(((exec_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0
                            sb.table("trades_journal").insert({
                                "ticker": ticker,
                                "shares": pos_sh,
                                "entry_price": entry_p,
                                "exit_price": exec_price,
                                "entry_date": pos.get("first_buy_at") or now_iso,
                                "exit_date": now_iso,
                                "pnl_usd": pnl_usd,
                                "pnl_pct": pnl_pct,
                                "result": "win" if pnl_usd >= 0 else "loss",
                                "exit_reason": "IB_BROKER_CONFIRMED_SELL",
                                "trade_type": pos.get("group_name") or "STOCKS_IB"
                            }).execute()

                            # Propuesta #3: Registrar cierre en Disyuntor Diario
                            try:
                                from app.core.circuit_breaker import record_trade_completion
                                record_trade_completion(ticker, pnl_usd)
                            except Exception as cb_err:
                                log_warning(MODULE, f"Aviso registrando disyuntor en broker fill: {cb_err}")
                            sb.table("stocks_positions").update({
                                "status": "closed",
                                "shares": 0,
                                "shares_remaining": 0,
                                "current_price": exec_price,
                                "unrealized_pnl": pnl_usd,
                                "unrealized_pnl_pct": pnl_pct,
                                "sl_close_reason": "broker_confirmed_sell",
                                "updated_at": now_iso
                            }).eq("id", pos["id"]).execute()
                            log_info(MODULE, f"✅ Cierre TOTAL confirmado por Broker para {ticker} en Supabase")
            except Exception as close_e:
                log_error(MODULE, f"Error procesando SELL {ticker} en Supabase: {close_e}")

        # Notificar por Telegram
        send_telegram_alert(
            f"🎯 [IBKR PAPER] ORDEN EJECUTADA\n"
            f"Ticker: {ticker} ({direction.upper()})\n"
            f"Acciones: {shares}\n"
            f"Precio Ejecución: ${exec_price:.2f}\n"
            f"IB Order ID: #{order_id}"
        )

        # Descontar del libro de in-flight sells si fue venta
        if ACTIVE_BRIDGE and hasattr(ACTIVE_BRIDGE, '_in_flight_sells') and direction == "sell":
            cur_inf = ACTIVE_BRIDGE._in_flight_sells.get(ticker.upper(), 0)
            ACTIVE_BRIDGE._in_flight_sells[ticker.upper()] = max(0, cur_inf - shares)

        # Limpiar de seguimiento activo
        PENDING_IB_ORDERS.pop(order_id, None)

        # Confirmación y reconciliación inmediata con el Broker
        if ACTIVE_BRIDGE:
            try:
                ACTIVE_BRIDGE.reconcile_broker_portfolio()
            except Exception as r_err:
                log_warning(MODULE, f"Error en reconciliación post-fill: {r_err}")

    elif status in ["cancelled", "inactive"]:
        try:
            sb.table("stocks_orders").update({
                "status": "cancelled",
            }).eq("id", order_ctx["id"]).execute()
        except Exception:
            pass
        PENDING_IB_ORDERS.pop(order_id, None)


import socket

def get_default_ib_host() -> str:
    hostname = socket.gethostname().upper()
    # Si este script corre directamente en APOLO, conectar por localhost
    if "APOLO" in hostname:
        return "127.0.0.1"
    # Si corre desde otra máquina, buscar variable o apuntar a APOLO en la LAN
    env_host = os.getenv("IB_HOST")
    if env_host:
        return env_host
    return "192.168.1.102"


class IBBridgeWorker:
    """Worker permanente para el puente APOLO <-> IBKR TWS <-> Supabase."""

    def __init__(self, host=None, port=None, client_id=None):
        global ACTIVE_BRIDGE
        self.host = host or get_default_ib_host()
        self.port = port or int(os.getenv("IB_PORT", "7497"))
        self.client_id = client_id or int(os.getenv("IB_CLIENT_ID", "25"))
        self.ib = None
        self.running = True
        ACTIVE_BRIDGE = self

    def initialize_ib(self) -> bool:
        """Establece conexión inicial con TWS en el puerto 7497."""
        if not IB_AVAILABLE:
            log_error(MODULE, "❌ La librería 'ibapi' no está instalada en este entorno.")
            return False

        try:
            self.ib = get_ib_connection()
            self.ib.set_order_callback(on_ib_order_status)
            log_info(MODULE, f"🔌 Intentando conectar a TWS en {self.host}:{self.port} (Client ID: {self.client_id})...")
            connected = self.ib.connect_tws(host=self.host, port=self.port, client_id=self.client_id)
            if connected:
                log_info(MODULE, f"✅ ¡Conexión exitosa con Interactive Brokers TWS! (Cuentas: {self.ib.accounts or 'Detectando...'})")
                self._start_micro_pullback_scalper_if_needed()
                return True
            else:
                log_warning(MODULE, "⚠️ No se pudo conectar a TWS. Asegúrate de que TWS esté abierto en modo PAPER (puerto 7497).")
                return False
        except Exception as e:
            log_error(MODULE, f"❌ Error conectando a TWS: {e}")
            return False

    def _start_micro_pullback_scalper_if_needed(self):
        """Inicia el escáner y motor de micro-pullbacks en APOLO (hilo con event loop dedicado)."""
        if getattr(self, "_scalp_scanner_started", False):
            return
        self._scalp_scanner_started = True

        import threading

        def _run_scanner_loop():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                from app.stocks.micro_pullback_scanner import get_micro_pullback_scanner
                scanner = get_micro_pullback_scanner()
                scanner.start()
                log_info(MODULE, "⚡ Motor In-Memory Micro-Pullback ACTIVADO en APOLO (TWS Local).")
                loop.run_forever()
            except Exception as e:
                log_error(MODULE, f"Error en thread de Micro-Pullback Scalper: {e}")

        th = threading.Thread(target=_run_scanner_loop, daemon=True, name="micro-pullback-apolo")
        th.start()

    def update_heartbeat(self):
        """Actualiza el estado de vida del puente en Supabase."""
        try:
            sb = get_supabase()
            is_connected = bool(self.ib and self.ib.connected)
            accounts_str = ",".join(self.ib.accounts) if (self.ib and self.ib.accounts) else "Paper-Session"
            payload = {
                "connected": is_connected,
                "host_name": "APOLO",
                "tws_port": self.port,
                "mode": "PAPER",
                "accounts": accounts_str,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            # Upsert en stocks_config con on_conflict='key'
            sb.table("stocks_config").upsert({
                "key": "ib_bridge_heartbeat",
                "value": str(payload),
                "description": "Estado en tiempo real del agente IBKR Bridge en APOLO",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }, on_conflict="key").execute()
        except Exception as e:
            log_warning(MODULE, f"Error reportando heartbeat a Supabase: {e}")

    def process_pending_orders(self):
        """Busca órdenes pendientes en Supabase y las despacha a TWS."""
        if not self.ib or not self.ib.connected:
            return

        try:
            sb = get_supabase()
            # Buscar órdenes que requieran ejecución por el broker
            res = sb.table("stocks_orders")\
                .select("*")\
                .eq("status", "pending")\
                .order("created_at", desc=False)\
                .limit(10)\
                .execute()

            orders = res.data or []
            for order in orders:
                order_id = order["id"]
                ticker = order["ticker"]
                direction = order.get("direction", "buy").lower()
                order_type = order.get("order_type", "market").lower()
                shares = int(order.get("shares") or 5)
                price = float(order.get("limit_price") or order.get("market_price") or 0.0)
                trigger_price = float(order.get("trigger_price") or price or 0.0)

                # Marcar inmediatamente en proceso para evitar envíos duplicados
                sb.table("stocks_orders").update({"status": "processing"}).eq("id", order_id).execute()

                log_info(MODULE, f"🚀 Enviando orden a TWS: {direction.upper()} {shares}x {ticker} ({order_type.upper()})")

                try:
                    from ibapi.order import Order

                    # Reconocer si es un contrato de opción (CALL/PUT) o acción
                    contract = None
                    is_option = False
                    target_b = str(order.get("target_band") or "").strip().upper()
                    ticker_u = str(ticker or "").strip().upper()
                    group_u = str(order.get("group_name") or "").strip().upper()

                    is_option_candidate = (
                        ":OPT:" in ticker_u or ticker_u.startswith("OPT:") or
                        ":OPT:" in target_b or target_b.startswith("OPT:") or "OPT:" in target_b or
                        group_u in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS")
                    )

                    if is_option_candidate:
                        try:
                            # 1. Intentar target_band si contiene OPT
                            if "OPT:" in target_b:
                                parts = target_b.split(":")
                                if len(parts) == 4 and parts[0] == "OPT":
                                    # Formato: OPT:YYYYMMDD:STRIKE:RIGHT
                                    sym_p = ticker_u.split(":")[0]
                                    exp_p = parts[1]
                                    strike_p = float(parts[2])
                                    right_p = parts[3]
                                    contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                                    is_option = True
                                elif len(parts) >= 5:
                                    sym_p = parts[0] if parts[0] != "OPT" else parts[1]
                                    exp_p = parts[2]
                                    strike_p = float(parts[3])
                                    right_p = parts[4]
                                    contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                                    is_option = True

                            # 2. Si no se obtuvo de target_band, intentar ticker
                            if not contract and ("OPT:" in ticker_u or ":OPT:" in ticker_u):
                                parts = ticker_u.split(":")
                                if len(parts) >= 5:
                                    sym_p = parts[0] if parts[0] != "OPT" else parts[1]
                                    exp_p = parts[2]
                                    strike_p = float(parts[3])
                                    right_p = parts[4]
                                    contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                                    is_option = True

                            if contract:
                                log_info(MODULE, f"🎯 Contrato de OPCIÓN identificado: {contract.symbol} {contract.lastTradeDateOrContractMonth} Strike ${contract.strike} Right={contract.right}")
                        except Exception as opt_parse_err:
                            log_warning(MODULE, f"Aviso al parsear contrato de opción ({ticker_u}, target={target_b}): {opt_parse_err}")

                    # Si era candidata de opción pero no se pudo construir el contrato, cancelar para evitar operar acciones por error
                    if is_option_candidate and not contract:
                        msg = f"⚠️ [OPTION PARSE GUARD] Orden {order_id} ({ticker_u}, target={target_b}) no pudo resolver contrato de opción. Cancelando orden para evitar operar acciones por error."
                        log_warning(MODULE, msg)
                        sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                        continue

                    # ── GUARDIA DE MERCADO PARA OPCIONES ──
                    if is_option:
                        from app.core.market_hours import is_options_market_open
                        is_opt_open, opt_reason = is_options_market_open()
                        if not is_opt_open:
                            log_warning(MODULE, f"⏸️ [MARKET GATE] Mercado de opciones cerrado ({opt_reason}). Orden {ticker_u} ({direction}) no despachada a TWS para evitar rechazo del broker.")
                            continue

                    # ── BLOQUEO ANTI-SHORT PARA ACCIONES (NUNCA APLICA A OPCIONES) ──
                    if not is_option and not contract:
                        if direction == "sell":
                            self.ib.request_broker_positions(timeout=3.0)
                            broker_pos = self.ib._positions.get(ticker.upper())

                            confirmed_shares = float(broker_pos.get("shares", 0.0)) if broker_pos else 0.0
                            if not hasattr(self, '_in_flight_sells'):
                                self._in_flight_sells = {}
                            already_in_flight = self._in_flight_sells.get(ticker.upper(), 0)
                            available_shares = max(0, int(confirmed_shares) - already_in_flight)

                            if available_shares <= 0:
                                msg = f"⛔ [ANTI-SHORT SHIELD] Orden SELL para {ticker} ({shares} acc) CANCELADA: Broker tiene {confirmed_shares} acc y ya hay {already_in_flight} en proceso de venta. Cero acciones disponibles."
                                log_warning(MODULE, msg)
                                sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                                send_telegram_alert(msg)
                                continue

                            if shares > available_shares:
                                log_warning(MODULE, f"⚠️ [CLAMP SHARES] Ajustando venta de {ticker} de {shares} a {available_shares} acc para no entrar en corto.")
                                shares = available_shares

                            self._in_flight_sells[ticker.upper()] = already_in_flight + shares

                        contract = self.ib.us_stock_contract(ticker)

                    # ── BLINDAJE ANTI-SHORT Y TIPO DE ORDEN PARA OPCIONES ──
                    if is_option:
                        if direction == "sell":
                            # Verificar que realmente tengamos la opción en TWS antes de enviar SELL
                            self.ib.request_broker_positions(timeout=3.0)
                            held_opt_qty = 0
                            for pk, pv in (self.ib._positions or {}).items():
                                if pv.get("sec_type") == "OPT" and str(pv.get("underlying") or "").upper() == contract.symbol.upper():
                                    if str(pv.get("expiry") or "").replace("-", "") == str(contract.lastTradeDateOrContractMonth or "").replace("-", ""):
                                        if abs(float(pv.get("strike") or 0) - float(contract.strike or 0)) <= 0.05 and str(pv.get("right") or "").upper() == str(contract.right or "").upper():
                                            held_opt_qty = int(round(float(pv.get("shares") or 0)))
                                            break
                            if held_opt_qty <= 0:
                                log_warning(MODULE, f"⛔ [OPTION ANTI-SHORT] Orden SELL {ticker_u} ({target_b}) cancelada: 0 contratos abiertos en TWS.")
                                sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                                continue
                            if shares > held_opt_qty:
                                shares = held_opt_qty
                            # Para cierres SELL de opciones: usar MKT para garantizar salida inmediata en TWS
                            order_type = "market"
                        else:
                            eff_price = price if price > 0 else float(order.get("limit_price") or order.get("market_price") or 0.0)
                            if eff_price <= 0:
                                log_warning(MODULE, f"⚠️ Orden BUY de opción {ticker_u} sin precio límite válido. Cancelando.")
                                sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                                continue
                            order_type = "limit"
                            price = eff_price

                    ib_ord = Order()
                    ib_ord.eTradeOnly = False
                    ib_ord.firmQuoteOnly = False
                    ib_ord.action = direction.upper()
                    ib_ord.totalQuantity = shares
                    
                    if order_type in ("stop", "stp", "buy_stop") and trigger_price > 0:
                        ib_ord.orderType = "STP"
                        ib_ord.auxPrice = round(trigger_price, 2)
                    elif order_type in ("stop_limit", "stp_lmt") and trigger_price > 0:
                        ib_ord.orderType = "STP LMT"
                        ib_ord.auxPrice = round(trigger_price, 2)
                        ib_ord.lmtPrice = round(price if price > 0 else (trigger_price * 1.005), 2)
                    elif order_type == "limit" and price > 0:
                        ib_ord.orderType = "LMT"
                        ib_ord.lmtPrice = round(price, 2)
                    else:
                        ib_ord.orderType = "MKT"

                    ib_ord.transmit = True
                    ib_order_id = self.ib.get_next_order_id()

                    # Guardar referencia para el callback
                    PENDING_IB_ORDERS[ib_order_id] = order

                    # Colocar la orden en TWS
                    self.ib.placeOrder(ib_order_id, contract, ib_ord)
                    log_info(MODULE, f"📋 Orden enviada con éxito a TWS con ID #{ib_order_id}")

                except Exception as ord_err:
                    log_error(MODULE, f"Error despachando orden {order_id} a TWS: {ord_err}")
                    sb.table("stocks_orders").update({"status": "failed"}).eq("id", order_id).execute()

        except Exception as e:
            log_error(MODULE, f"Error revisando órdenes pendientes: {e}")

    def reconcile_broker_portfolio(self):
        """
        Consulta las posiciones reales en Interactive Brokers TWS (Paper)
        y reconcilia la tabla stocks_positions en Supabase para que predomine
        el Broker sobre cualquier estado local ("El Broker es la verdad absoluta").
        """
        if not self.ib or not self.ib.connected:
            return

        try:
            sb = get_supabase()
            broker_positions = self.ib.request_broker_positions(timeout=6.0)
            if not getattr(self.ib, "_positions_sync_ok", True) and not broker_positions:
                log_warning(MODULE, "⏸️ Omitiendo reconciliación: TWS no confirmó positionEnd y snapshot está vacío.")
                return
            now_iso = datetime.now(timezone.utc).isoformat()

            # Guardar el snapshot del portfolio real en stocks_config
            try:
                sb.table("stocks_config").upsert({
                    "key": "ib_broker_portfolio",
                    "value": str(broker_positions),
                    "description": "Cartera de posiciones reales en Interactive Brokers TWS",
                    "updated_at": now_iso
                }, on_conflict="key").execute()
            except Exception:
                pass

            # ── 1. SEPARAR EN STOCKS Y OPTIONS ──
            broker_stocks = {}
            broker_options = {}
            for sym, b_data in broker_positions.items():
                qty = float(b_data.get("shares") or 0)
                if qty == 0:
                    continue
                sec_type = str(b_data.get("sec_type") or "").upper()
                if sec_type == "OPT" or ":OPT:" in sym or b_data.get("right") or b_data.get("strike"):
                    broker_options[sym] = b_data
                else:
                    broker_stocks[sym] = b_data

            # ── 2. RECONCILIAR STOCKS_POSITIONS (SÓLO ACCIONES REALES) ──
            sb_pos_res = sb.table("stocks_positions").select("*").in_("status", ["open", "closing"]).execute()
            sb_open_stocks = {}
            
            # Identificar símbolos de opciones abiertas en el broker
            broker_opt_symbols = {str(opt_b.get("underlying") or k.split(":")[0]).upper() for k, opt_b in broker_options.items()}

            for p in (sb_pos_res.data or []):
                p_ticker = str(p.get("ticker", "")).upper()
                # Si una opción se coló en stocks_positions (o su subyacente como SPY cuando solo es opción):
                is_opt = p.get("group_name") in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS") or ":OPT:" in p_ticker or p_ticker.startswith("OPT:") or "OPT:" in str(p.get("target_band") or "")
                is_opt_underlying_only = (p_ticker in broker_opt_symbols and p_ticker not in broker_stocks)

                if is_opt or is_opt_underlying_only:
                    sb.table("stocks_positions").delete().eq("id", p["id"]).execute()
                    log_info(MODULE, f"🧹 [LIMPIEZA] Opción/Subyacente {p_ticker} eliminada de stocks_positions.")
                else:
                    sb_open_stocks[p["ticker"]] = p

            for sym, b_data in broker_stocks.items():
                qty = int(b_data["shares"])
                if qty <= 0:
                    continue
                avg_cost = float(b_data["avg_cost"])

                cur_p = self.ib._prices.get(sym, avg_cost) if hasattr(self.ib, '_prices') else avg_cost
                if cur_p <= 0:
                    cur_p = avg_cost

                atr_fb = max(0.05, cur_p * 0.02)
                sl_calc = round(max(0.01, avg_cost - (atr_fb * 2.0)), 2)
                tp_calc = round(avg_cost + (atr_fb * 5.0), 2)
                pnl_usd = round((cur_p - avg_cost) * qty, 2)
                pnl_pct = round(((cur_p - avg_cost) / avg_cost * 100), 2) if avg_cost > 0 else 0.0

                if sym in sb_open_stocks:
                    existing_pos = sb_open_stocks[sym]
                    old_shares = int(existing_pos.get("shares") or 0)
                    old_avg = float(existing_pos.get("avg_price") or 0)
                    if old_shares != qty or abs(old_avg - avg_cost) > 0.01 or existing_pos.get("status") == "closing":
                        update_payload = {
                            "status": "open",
                            "shares": qty,
                            "shares_remaining": qty,
                            "avg_price": round(avg_cost, 4),
                            "total_cost": round(qty * avg_cost, 2),
                            "current_price": cur_p,
                            "unrealized_pnl": pnl_usd,
                            "unrealized_pnl_pct": pnl_pct,
                            "updated_at": now_iso
                        }
                        if not existing_pos.get("stop_loss") or float(existing_pos.get("stop_loss")) <= 0:
                            update_payload["stop_loss"] = sl_calc
                            update_payload["trailing_sl_price"] = sl_calc
                        if not existing_pos.get("take_profit") or float(existing_pos.get("take_profit")) <= 0:
                            update_payload["take_profit"] = tp_calc

                        sb.table("stocks_positions").update(update_payload).eq("id", existing_pos["id"]).execute()
                        log_info(MODULE, f"🔄 [SYNC STOCKS] Posición ajustada para {sym}: {old_shares} -> {qty} acc @ ${avg_cost:.2f}")
                else:
                    # HEALING: Comprobar si existía una posición cerrada prematuramente por simulación local
                    recent_closed = sb.table("stocks_positions")\
                        .select("*")\
                        .eq("ticker", sym)\
                        .order("updated_at", desc=True)\
                        .limit(1)\
                        .execute()
                    
                    if recent_closed.data:
                        # Reactivar la fila existente en lugar de duplicar y dejar basura en CLOSED HISTORY
                        target_id = recent_closed.data[0]["id"]
                        heal_payload = {
                            "status": "open",
                            "shares": qty,
                            "shares_remaining": qty,
                            "avg_price": round(avg_cost, 4),
                            "total_cost": round(qty * avg_cost, 2),
                            "current_price": cur_p,
                            "unrealized_pnl": pnl_usd,
                            "unrealized_pnl_pct": pnl_pct,
                            "sl_close_reason": None,
                            "exit_triggered_by": None,
                            "updated_at": now_iso
                        }
                        sb.table("stocks_positions").update(heal_payload).eq("id", target_id).execute()
                        
                        # Eliminar entradas ficticias del trades_journal para este ticker
                        try:
                            sb.table("trades_journal").delete().eq("ticker", sym).execute()
                        except Exception:
                            pass
                        log_info(MODULE, f"♻️ [HEALING] Posición {sym} reabierta en Supabase (validada con broker: {qty} acc @ ${avg_cost:.2f})")
                    else:
                        new_pos = {
                            "ticker": sym,
                            "direction": "long",
                            "shares": qty,
                            "shares_remaining": qty,
                            "avg_price": round(avg_cost, 4),
                            "total_cost": round(qty * avg_cost, 2),
                            "current_price": cur_p,
                            "unrealized_pnl": pnl_usd,
                            "unrealized_pnl_pct": pnl_pct,
                            "stop_loss": sl_calc,
                            "trailing_sl_price": sl_calc,
                            "highest_price_reached": max(avg_cost, cur_p),
                            "take_profit": tp_calc,
                            "group_name": "IB_PAPER",
                            "first_buy_at": now_iso,
                            "status": "open",
                            "updated_at": now_iso
                        }
                        sb.table("stocks_positions").insert(new_pos).execute()
                        log_info(MODULE, f"📥 [SYNC STOCKS] Acción del Broker agregada a Supabase: {sym} {qty} acc @ ${avg_cost:.2f}")

            # CONFIRMACIÓN BROKER: Cerrar en stocks_positions cualquier acción que el broker confirme que ya NO existe
            for sym, p_data in sb_open_stocks.items():
                if sym not in broker_stocks:
                    try:
                        fb_str = p_data.get("first_buy_at") or p_data.get("updated_at")
                        if fb_str:
                            fb_dt = datetime.fromisoformat(str(fb_str).replace("Z", "+00:00"))
                            if (datetime.now(timezone.utc) - fb_dt).total_seconds() < 90.0:
                                continue
                        inflight_buy = sb.table("stocks_orders").select("id").eq("ticker", sym).eq("direction", "buy").in_("status", ["pending", "processing"]).limit(1).execute()
                        if inflight_buy.data:
                            continue
                    except Exception:
                        pass

                    real_exit_time = now_iso
                    real_exit_price = p_data.get("current_price") or p_data.get("avg_price")
                    sell_rule = "broker_sync"
                    try:
                        sell_ord = sb.table("stocks_orders")\
                            .select("filled_at, filled_price, rule_code")\
                            .eq("ticker", sym)\
                            .eq("direction", "sell")\
                            .eq("status", "filled")\
                            .order("filled_at", desc=True)\
                            .limit(1)\
                            .execute()
                        if sell_ord.data and sell_ord.data[0].get("filled_at"):
                            real_exit_time = sell_ord.data[0]["filled_at"]
                            if sell_ord.data[0].get("filled_price"):
                                real_exit_price = float(sell_ord.data[0]["filled_price"])
                            if sell_ord.data[0].get("rule_code"):
                                sell_rule = sell_ord.data[0]["rule_code"]
                    except Exception as ord_e:
                        log_warning(MODULE, f"No se pudo consultar orden sell para {sym}: {ord_e}")

                    entry_p = float(p_data.get("avg_price") or 0.0)
                    pos_sh = int(float(p_data.get("shares") or 0))
                    pnl_usd = round((real_exit_price - entry_p) * pos_sh, 2)
                    pnl_pct = round(((real_exit_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0

                    sb.table("stocks_positions").update({
                        "status": "closed",
                        "current_price": real_exit_price,
                        "unrealized_pnl": pnl_usd,
                        "unrealized_pnl_pct": pnl_pct,
                        "sl_close_reason": sell_rule,
                        "updated_at": real_exit_time
                    }).eq("id", p_data["id"]).execute()

                    # Registrar permanentemente en trades_journal para Closed History
                    try:
                        sb.table("trades_journal").insert({
                            "ticker": sym,
                            "shares": pos_sh,
                            "entry_price": entry_p,
                            "exit_price": real_exit_price,
                            "entry_date": p_data.get("first_buy_at") or real_exit_time,
                            "exit_date": real_exit_time,
                            "pnl_usd": pnl_usd,
                            "pnl_pct": pnl_pct,
                            "result": "win" if pnl_usd >= 0 else "loss",
                            "exit_reason": sell_rule,
                            "trade_type": p_data.get("group_name") or "STOCKS_IB"
                        }).execute()
                    except Exception as tj_err:
                        log_warning(MODULE, f"Aviso insertando en trades_journal para {sym}: {tj_err}")

                    log_info(MODULE, f"📤 [SYNC STOCKS] Acción cerrada en Supabase sincronizada con orden real ({real_exit_time}): {sym} (PnL: ${pnl_usd:.2f})")

            # ── 3. RECONCILIAR OPT_PAPER_TRADES (SINCRONIZACIÓN BIDIRECCIONAL CON BROKER TWS) ──
            try:
                opt_open_res = sb.table("opt_paper_trades").select("*").eq("status", "open").execute()
                open_opt_rows = opt_open_res.data or []

                def _fmt_exp(raw_e: str) -> str:
                    s = str(raw_e or "").strip().replace("-", "")
                    if len(s) == 8 and s.isdigit():
                        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
                    return str(raw_e or "")[:10]

                def _row_contract_key(row_d: dict) -> tuple:
                    sym_u = str(row_d.get("symbol") or "").upper()
                    exp_s = _fmt_exp(row_d.get("expiry") or "")
                    fills = row_d.get("entry_fills") or []
                    stk_f = float(fills[0].get("strike") or 0.0) if fills else 0.0
                    rgt_s = str(fills[0].get("right") or ("C" if "call" in str(row_d.get("strategy_type") or "").lower() else "P")).upper() if fills else ("C" if "call" in str(row_d.get("strategy_type") or "").lower() else "P")
                    return (sym_u, exp_s, round(stk_f, 2), rgt_s)

                sb_open_by_key = {}
                for r in open_opt_rows:
                    ck = _row_contract_key(r)
                    if ck not in sb_open_by_key:
                        sb_open_by_key[ck] = r
                    else:
                        sb.table("opt_paper_trades").delete().eq("id", r["id"]).execute()

                active_broker_keys = set()
                for opt_key, b_data in broker_options.items():
                    qty = int(round(float(b_data.get("shares") or 0)))
                    if qty <= 0:
                        continue
                    und_sym = str(b_data.get("underlying") or opt_key.split(":")[0]).upper()
                    exp_iso = _fmt_exp(b_data.get("expiry") or "")
                    strike_v = round(float(b_data.get("strike") or 0.0), 2)
                    right_v = str(b_data.get("right") or "C").upper()
                    strat_v = "long_call" if right_v == "C" else "long_put"
                    dir_v = "bullish" if right_v == "C" else "bearish"
                    avg_cost_contract = float(b_data.get("avg_cost") or 0.0)
                    entry_debit = round(avg_cost_contract / 100.0, 4) if avg_cost_contract > 0 else 0.01
                    total_invested = round(avg_cost_contract * qty, 2) if avg_cost_contract > 0 else round(entry_debit * 100.0 * qty, 2)
                    conid_v = b_data.get("conid")

                    ck = (und_sym, exp_iso, strike_v, right_v)
                    active_broker_keys.add(ck)

                    if ck in sb_open_by_key:
                        ex_row = sb_open_by_key[ck]
                        if int(ex_row.get("qty") or 0) != qty or abs(float(ex_row.get("entry_debit") or 0) - entry_debit) > 0.02:
                            sb.table("opt_paper_trades").update({
                                "qty": qty,
                                "entry_debit": entry_debit,
                                "entry_total_invested": total_invested,
                                "max_loss_total": total_invested,
                                "updated_at": now_iso
                            }).eq("id", ex_row["id"]).execute()
                            log_info(MODULE, f"🔄 [SYNC OPTIONS] Contrato ajustado en opt_paper_trades: {und_sym} {exp_iso} {strike_v}{right_v} -> {qty}x @ ${entry_debit:.2f}")
                    else:
                        uid = 1
                        try:
                            u_res = sb.table("opt_underlyings").select("id").eq("symbol", und_sym).limit(1).execute()
                            if u_res.data:
                                uid = u_res.data[0]["id"]
                            else:
                                ins_u = sb.table("opt_underlyings").insert({"symbol": und_sym, "optionable": True, "data_state": "LIVE"}).execute()
                                if ins_u.data:
                                    uid = ins_u.data[0]["id"]
                        except Exception:
                            pass

                        leg_fill = [{
                            "conid": conid_v,
                            "side": "buy",
                            "closing_side": "sell",
                            "right": right_v,
                            "strike": strike_v,
                            "bid": entry_debit,
                            "ask": entry_debit,
                            "fill_price": entry_debit,
                            "slippage_applied": 0.0,
                            "market_data_type": "LIVE",
                            "fee_usd": 0.70,
                        }]

                        recent_opt = sb.table("opt_paper_trades")\
                            .select("*")\
                            .eq("symbol", und_sym)\
                            .eq("strategy_type", strat_v)\
                            .order("id", desc=True)\
                            .limit(5)\
                            .execute()
                        target_heal = None
                        for cand_r in (recent_opt.data or []):
                            if _row_contract_key(cand_r) == ck:
                                target_heal = cand_r
                                break

                        if target_heal:
                            sb.table("opt_paper_trades").update({
                                "status": "open",
                                "qty": qty,
                                "expiry": exp_iso,
                                "entry_debit": entry_debit,
                                "entry_fills": leg_fill,
                                "entry_total_invested": total_invested,
                                "max_loss_total": total_invested,
                                "exit_time": None,
                                "exit_credit": None,
                                "exit_fills": [],
                                "exit_reason": None,
                                "realized_pnl": None,
                                "updated_at": now_iso
                            }).eq("id", target_heal["id"]).execute()
                            log_info(MODULE, f"♻️ [HEALING OPTIONS] Opción {und_sym} {exp_iso} {strike_v}{right_v} reabierta en opt_paper_trades ({qty}x @ ${entry_debit:.2f})")
                        else:
                            sb.table("opt_paper_trades").insert({
                                "underlying_id": uid,
                                "symbol": und_sym,
                                "strategy_type": strat_v,
                                "direction": dir_v,
                                "status": "open",
                                "qty": qty,
                                "expiry": exp_iso,
                                "entry_time": now_iso,
                                "entry_debit": entry_debit,
                                "entry_fills": leg_fill,
                                "entry_costs": round(0.70 * qty, 2),
                                "entry_total_invested": total_invested,
                                "max_loss_total": total_invested,
                                "max_profit_total": round(total_invested * 2.0, 2),
                                "breakeven": round(strike_v + entry_debit, 2) if right_v == "C" else round(strike_v - entry_debit, 2),
                                "unrealized_pnl": 0.0,
                                "last_mark_price": entry_debit,
                                "last_mark_at": now_iso,
                                "exit_plan": {"trailing_sl_type": "INITIAL", "highest_premium_seen": entry_debit},
                                "model_version": "v1.0-tws-sync",
                                "settings_version": 1,
                                "updated_at": now_iso
                            }).execute()
                            log_info(MODULE, f"📥 [SYNC OPTIONS] Opción del Broker agregada a opt_paper_trades: {und_sym} {exp_iso} {strike_v}{right_v} ({qty}x @ ${entry_debit:.2f})")

                # Cerrar o limpiar en opt_paper_trades cualquier posición que NO esté en el broker
                for ck, opt_t in sb_open_by_key.items():
                    if ck not in active_broker_keys:
                        sym = opt_t["symbol"]
                        try:
                            et_str = opt_t.get("entry_time") or opt_t.get("updated_at")
                            if et_str:
                                et_dt = datetime.fromisoformat(str(et_str).replace("Z", "+00:00"))
                                if (datetime.now(timezone.utc) - et_dt).total_seconds() < 90.0:
                                    inflight_opt = sb.table("stocks_orders").select("id").eq("ticker", sym).eq("direction", "buy").in_("status", ["pending", "processing"]).limit(1).execute()
                                    if inflight_opt.data:
                                        continue
                        except Exception:
                            pass

                        exp_c = ck[1].replace("-", "")
                        tb_match = f"OPT:{exp_c}:{ck[2]}:{ck[3]}"
                        filled_buy = sb.table("stocks_orders").select("id").eq("ticker", sym).eq("direction", "buy").eq("status", "filled").limit(1).execute()
                        if not filled_buy.data:
                            sb.table("opt_paper_trades").delete().eq("id", opt_t["id"]).execute()
                            log_info(MODULE, f"🧹 [CLEAN OPTIONS] Opción no ejecutada en TWS eliminada de opt_paper_trades: {sym} {tb_match}")
                        else:
                            sb.table("opt_paper_trades").update({
                                "status": "closed",
                                "exit_reason": "manual_simulated",
                                "exit_time": now_iso,
                                "updated_at": now_iso
                            }).eq("id", opt_t["id"]).execute()
                            log_info(MODULE, f"📤 [SYNC OPTIONS] Opción {sym} cerrada en opt_paper_trades por no existir en TWS.")
            except Exception as opt_sync_e:
                log_warning(MODULE, f"Error reconciliando opt_paper_trades: {opt_sync_e}")

        except Exception as sync_e:
            log_error(MODULE, f"Error en reconciliación con el broker: {sync_e}")

    def run_loop(self):
        """Bucle principal de ejecución del puente."""
        print("=" * 65)
        print("  eTrade v5.0 — Interactive Brokers Bridge (Host: APOLO)")
        print("  Modalidad: PAPER TRADING (Puerto: 7497)")
        print("=" * 65)

        self.initialize_ib()

        last_heartbeat = 0
        last_reconcile = 0
        last_reconnect_attempt = time.time()
        reconnect_cooldown = 15  # Intentar reconectar a TWS cada 15 segundos
        initial_mtime = os.path.getmtime(os.path.abspath(__file__))

        while self.running:
            try:
                # Auto-reload si el archivo fue actualizado en disco
                try:
                    if os.path.getmtime(os.path.abspath(__file__)) > initial_mtime + 1.0:
                        log_info(MODULE, "🔄 Código de ib_bridge_worker actualizado en disco. Reiniciando proceso...")
                        if self.ib:
                            self.ib.disconnect_tws()
                        sys.exit(0)
                except SystemExit:
                    raise
                except Exception:
                    pass
                # 1. Comprobar salud de conexión con TWS (con cooldown para no saturar)
                if not self.ib or not self.ib.connected:
                    now = time.time()
                    if now - last_reconnect_attempt >= reconnect_cooldown:
                        last_reconnect_attempt = now
                        log_warning(MODULE, "TWS no conectado. Reintentando conexión con TWS (puerto 7497)...")
                        self.initialize_ib()

                # 2. Heartbeat cada 15 segundos hacia Supabase
                if time.time() - last_heartbeat > 15:
                    self.update_heartbeat()
                    last_heartbeat = time.time()

                # 2.5 Reconciliación continua con el Broker cada 30 segundos
                if self.ib and self.ib.connected and (time.time() - last_reconcile > 30):
                    self.reconcile_broker_portfolio()
                    last_reconcile = time.time()

                # 3. Procesar órdenes pendientes si estamos conectados
                if self.ib and self.ib.connected:
                    self.process_pending_orders()

                time.sleep(2)

            except KeyboardInterrupt:
                print("\nDeteniendo IB Bridge Worker de manera ordenada...")
                self.running = False
                if self.ib:
                    self.ib.disconnect_tws()
                break
            except Exception as e:
                log_error(MODULE, f"Error imprevisto en loop del bridge: {e}")
                time.sleep(5)


if __name__ == "__main__":
    bridge = IBBridgeWorker()
    bridge.run_loop()
