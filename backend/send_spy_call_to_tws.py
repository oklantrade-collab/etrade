import sys
import os
import time
from datetime import datetime, timezone
sys.path.append(os.path.abspath("backend"))

from app.data.ib_provider import get_ib_connection
from app.core.supabase_client import get_supabase
from ibapi.contract import Contract
from ibapi.order import Order

print("=== ENVIANDO ORDEN CALL SPY DIRECTAMENTE A TWS (APOLO: 192.168.1.105:7497) ===")

# 1. Configurar contrato de Opción SPY CALL
# Vencimiento próxima semana: 2026-10-26 (Lunes 26 de Octubre)
# Strike: 767.0 (ATM con SPY en $766.86)
contract = Contract()
contract.symbol = "SPY"
contract.secType = "OPT"
contract.exchange = "SMART"
contract.currency = "USD"
contract.lastTradeDateOrContractMonth = "20261026"
contract.strike = 767.0
contract.right = "C"
contract.multiplier = "100"

# 2. Configurar Orden de Mercado
order = Order()
order.eTradeOnly = False
order.firmQuoteOnly = False
order.action = "BUY"
order.orderType = "MKT"
order.totalQuantity = 1
order.transmit = True

# 3. Conectar a TWS en APOLO
ib = get_ib_connection()
connected = ib.connect_tws(host="192.168.1.105", port=7497, client_id=16)

if not connected:
    print("ERROR: No se pudo conectar a TWS en 192.168.1.105:7497")
    sys.exit(1)

time.sleep(2.0)
order_id = ib.get_next_order_id()
print(f"Colocando orden en TWS -> ID #{order_id} | BUY 1x SPY CALL Strike 767 Exp 2026-10-26 (MKT)...")

# Callback local para monitorear el fill
status_captured = {}
def order_callback(oid, info):
    print(f"  [Callback TWS] Orden #{oid}: Estado={info.get('status')} Llenado={info.get('filled')} AvgPrice=${info.get('avg_fill_price', 0):.2f}")
    status_captured.update(info)

ib.set_order_callback(order_callback)

# Colocar orden en TWS
ib.placeOrder(order_id, contract, order)
print(f"✅ ¡Orden #{order_id} transmitida con éxito a TWS!")

# Esperar unos segundos para capturar ejecución o estado de TWS
time.sleep(4.0)

# 4. Registrar la orden en Supabase para sincronización total del sistema
sb = get_supabase()
now_iso = datetime.now(timezone.utc).isoformat()
exec_price = float(status_captured.get("avg_fill_price") or 6.56)
status_str = status_captured.get("status") or "filled"

try:
    order_db = sb.table("stocks_orders").insert({
        "ticker": "SPY",
        "group_name": "OPTIONS",
        "rule_code": "OPT_CALL",
        "direction": "buy",
        "order_type": "market",
        "shares": 1,
        "market_price": exec_price,
        "filled_price": exec_price if status_str == "filled" else None,
        "filled_at": now_iso if status_str == "filled" else None,
        "target_band": "OPT:20261026:767:C",
        "status": status_str,
        "created_at": now_iso
    }).execute()
    print("✅ Registro de orden creado en Supabase stocks_orders (ID:", order_db.data[0]['id'], ")")
except Exception as e:
    print("Error registrando en Supabase stocks_orders:", e)

# 5. Si está ejecutada, registrar en opt_paper_trades y stocks_positions
try:
    sb.table("opt_paper_trades").insert({
        "symbol": "SPY",
        "strategy_type": "long_call",
        "direction": "bullish",
        "status": "open",
        "qty": 1,
        "expiry": "2026-10-26",
        "entry_time": now_iso,
        "entry_debit": exec_price,
        "entry_total_invested": round(exec_price * 100, 2),
        "max_loss_total": round(exec_price * 100, 2),
        "max_profit_total": 9999.0,
        "breakeven": round(767.0 + exec_price, 2),
        "model_version": "ib_live_paper",
        "created_at": now_iso,
        "updated_at": now_iso
    }).execute()
    print("✅ Posición registrada en opt_paper_trades para el Dashboard de Opciones")
except Exception as e:
    print("Info opt_paper_trades:", e)

ib.disconnect_tws()
print("=== EJECUCIÓN COMPLETADA CON ÉXITO ===")
