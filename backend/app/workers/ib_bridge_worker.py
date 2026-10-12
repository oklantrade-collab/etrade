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
                    sb.table("stocks_positions").insert({
                        "ticker": ticker,
                        "direction": "long",
                        "shares": shares,
                        "avg_price": exec_price,
                        "total_cost": round(shares * exec_price, 2),
                        "current_price": exec_price,
                        "group_name": order_ctx.get("group_name", "IB_PAPER"),
                        "rule_code": order_ctx.get("rule_code", "IB_BRIDGE"),
                        "first_buy_at": now_iso,
                        "status": "open",
                        "updated_at": now_iso
                    }).execute()
                    log_info(MODULE, f"✅ Nueva posición creada en Supabase para {ticker}: {shares} acc @ ${exec_price:.2f}")

            except Exception as pos_e:
                log_error(MODULE, f"Error creando/actualizando posición para {ticker}: {pos_e}")

        # 3. Si fue SELL: Cerrar la posición
        elif direction == "sell":
            try:
                pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).eq("status", "open").execute()
                for pos in (pos_res.data or []):
                    entry_p = float(pos.get("avg_price") or 0)
                    pos_sh = int(pos.get("shares") or 0)
                    pnl_usd = round((exec_price - entry_p) * pos_sh, 2)
                    pnl_pct = round(((exec_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0

                    # Mover a trades_journal
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
                        "exit_reason": "IB_SELL_ORDER",
                        "trade_type": pos.get("group_name") or "STOCKS_IB"
                    }).execute()

                    # Cerrar en stocks_positions
                    sb.table("stocks_positions").update({
                        "status": "closed",
                        "current_price": exec_price,
                        "unrealized_pnl": pnl_usd,
                        "unrealized_pnl_pct": pnl_pct,
                        "updated_at": now_iso
                    }).eq("id", pos["id"]).execute()

                log_info(MODULE, f"✅ Posición cerrada para {ticker} en Supabase")
            except Exception as close_e:
                log_error(MODULE, f"Error cerrando posición {ticker} en Supabase: {close_e}")

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
        self.host = host or get_default_ib_host()
        self.port = port or int(os.getenv("IB_PORT", "7497"))
        self.client_id = client_id or int(os.getenv("IB_CLIENT_ID", "25"))
        self.ib = None
        self.running = True

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
                    contract = self.ib.us_stock_contract(ticker)
                    ib_ord = Order()
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

    def run_loop(self):
        """Bucle principal de ejecución del puente."""
        print("=" * 65)
        print("  eTrade v5.0 — Interactive Brokers Bridge (Host: APOLO)")
        print("  Modalidad: PAPER TRADING (Puerto: 7497)")
        print("=" * 65)

        self.initialize_ib()

        last_heartbeat = 0
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
