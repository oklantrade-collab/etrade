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

    # Si la orden fue completada (FILLED)
    if status == "filled":
        exec_price = avg_price if avg_price > 0 else float(order_ctx.get("market_price") or 0)

        # 1. Actualizar orden en stocks_orders
        try:
            sb.table("stocks_orders").update({
                "status": "filled",
                "filled_price": exec_price,
                "filled_at": now_iso
            }).eq("id", order_ctx["id"]).execute()
        except Exception as e:
            log_error(MODULE, f"Error actualizando orden {order_ctx['id']} en Supabase: {e}")

        # 2. Si fue BUY: Crear o actualizar posición en stocks_positions
        if direction == "buy":
            try:
                # Verificar si ya existe posición abierta
                pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
                if pos_res.data:
                    # DCA: Promediar
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
                    # Nueva posición
                    atr_fb = exec_price * 0.02
                    sl_p = round(exec_price - (atr_fb * 2.0), 2)
                    tp_p = round(exec_price + (atr_fb * 5.0), 2)

                    multiplier = 100 if ":OPT:" in ticker else 1
                    sb.table("stocks_positions").insert({
                        "ticker": ticker,
                        "direction": "long",
                        "shares": shares,
                        "avg_price": exec_price,
                        "total_cost": round(shares * exec_price * multiplier, 2),
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
                    log_info(MODULE, f"✅ Nueva posición creada en Supabase para {ticker}: {shares} {'contratos' if multiplier == 100 else 'acc'} @ ${exec_price:.2f} (SL: ${sl_p:.2f}, TP: ${tp_p:.2f})")

                    # Si es opción, también registrar en opt_paper_trades
                    if ":OPT:" in ticker:
                        try:
                            parts = ticker.split(":")
                            und_sym = parts[0] if parts[0] != "OPT" else parts[1]
                            exp_d = parts[2]
                            formatted_exp = f"{exp_d[:4]}-{exp_d[4:6]}-{exp_d[6:8]}" if len(exp_d) == 8 else exp_d
                            strike_num = float(parts[3])
                            is_call = parts[-1].upper() == "C"

                            # Buscar contrato en opt_contracts para vincular conid/contract_id
                            cid = None
                            conid = None
                            try:
                                c_res = sb.table("opt_contracts").select("id, conid").eq("expiry", formatted_exp).eq("strike", strike_num).eq("right", "C" if is_call else "P").limit(1).execute()
                                if c_res.data:
                                    cid = c_res.data[0].get("id")
                                    conid = c_res.data[0].get("conid")
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

            except Exception as pos_e:
                log_error(MODULE, f"Error creando/actualizando posición para {ticker}: {pos_e}")

        # 3. Si fue SELL: Ejecutar cierre parcial o total confirmado con el broker
        elif direction == "sell":
            try:
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
                return True
            else:
                log_warning(MODULE, "⚠️ No se pudo conectar a TWS. Asegúrate de que TWS esté abierto en modo PAPER (puerto 7497).")
                return False
        except Exception as e:
            log_error(MODULE, f"❌ Error conectando a TWS: {e}")
            return False

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

                # Marcar inmediatamente en proceso para evitar envíos duplicados
                sb.table("stocks_orders").update({"status": "processing"}).eq("id", order_id).execute()

                log_info(MODULE, f"🚀 Enviando orden a TWS: {direction.upper()} {shares}x {ticker} ({order_type.upper()})")

                try:
                    from ibapi.order import Order

                    # Reconocer si es un contrato de opción (CALL/PUT) o acción
                    contract = None
                    is_option = False
                    if ":OPT:" in ticker.upper() or ticker.upper().startswith("OPT:"):
                        parts = ticker.upper().split(":")
                        # Formato: "SPY:OPT:20261120:580:C" -> [SPY, OPT, 20261120, 580, C]
                        # o "OPT:SPY:20261120:580:C" -> [OPT, SPY, 20261120, 580, C]
                        if len(parts) >= 5:
                            sym_p = parts[0] if parts[0] != "OPT" else parts[1]
                            exp_p = parts[2]
                            strike_p = float(parts[3])
                            right_p = parts[4]
                            contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                            is_option = True
                            log_info(MODULE, f"🎯 Contrato de OPCIÓN identificado: {sym_p} {exp_p} Strike ${strike_p} Right={right_p}")
                    elif order.get("target_band") and ":OPT:" in str(order.get("target_band")).upper():
                        parts = str(order.get("target_band")).upper().split(":")
                        sym_p = ticker.upper()
                        exp_p = parts[1]
                        strike_p = float(parts[2])
                        right_p = parts[3]
                        contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                        is_option = True
                        log_info(MODULE, f"🎯 Contrato de OPCIÓN identificado vía target_band: {sym_p} {exp_p} Strike ${strike_p} Right={right_p}")

                    if not contract:
                        contract = self.ib.us_stock_contract(ticker)

                    ib_ord = Order()
                    ib_ord.eTradeOnly = False
                    ib_ord.firmQuoteOnly = False
                    ib_ord.action = direction.upper()
                    ib_ord.totalQuantity = shares
                    
                    if order_type == "limit" and price > 0:
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
                is_opt = p.get("group_name") == "OPTIONS" or ":OPT:" in p_ticker or p_ticker.startswith("OPT:")
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
                    sb.table("stocks_positions").update({"status": "closed", "updated_at": now_iso}).eq("id", p_data["id"]).execute()
                    log_info(MODULE, f"📤 [SYNC STOCKS] Acción cerrada en Supabase porque ya no existe en el Broker: {sym}")

            # ── 3. RECONCILIAR OPT_PAPER_TRADES (SÓLO OPCIONES) ──
            try:
                opt_open_res = sb.table("opt_paper_trades").select("*").eq("status", "open").execute()
                sb_open_opts = {t["symbol"]: t for t in (opt_open_res.data or [])}

                # Simbolos subyacentes con opciones abiertas en el broker
                broker_opt_symbols = set()
                for opt_key, b_data in broker_options.items():
                    und_sym = b_data.get("underlying") or opt_key.split(":")[0]
                    broker_opt_symbols.add(und_sym.upper())

                # Cerrar en opt_paper_trades cualquier posición que NO esté en el broker
                for sym, opt_t in sb_open_opts.items():
                    if sym.upper() not in broker_opt_symbols:
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

        while self.running:
            try:
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
