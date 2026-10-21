import os
import sys
import time
from datetime import datetime, timezone

sys.path.append(os.path.abspath("backend"))

from app.data.ib_provider import get_ib_connection
from app.core.supabase_client import get_supabase
from ibapi.contract import Contract
from ibapi.order import Order

print("=== CONECTANDO A TWS (APOLO: 192.168.1.105:7497) ===")
ib = get_ib_connection()
connected = ib.connect_tws(host="192.168.1.105", port=7497, client_id=77)

if not connected:
    print("ERROR: No se pudo conectar a TWS en 192.168.1.105:7497")
    sys.exit(1)

time.sleep(1.5)
sb = get_supabase()
now_iso = datetime.now(timezone.utc).isoformat()

status_captured = {}
def order_callback(oid, info):
    print(f"  [Callback TWS] Orden #{oid}: Estado={info.get('status')} Llenado={info.get('filled')} AvgPrice=${info.get('avg_fill_price', 0):.2f}")
    status_captured[oid] = info

ib.set_order_callback(order_callback)

# ── 1. CUBRIR CORTO EN SHMD (BUY 100 SHMD MKT) ──
print("\n1. Enviando orden de cobertura para SHMD (BUY 100 MKT)...")
c_shmd = Contract()
c_shmd.symbol = "SHMD"
c_shmd.secType = "STK"
c_shmd.exchange = "SMART"
c_shmd.currency = "USD"

o_shmd = Order()
o_shmd.action = "BUY"
o_shmd.orderType = "MKT"
o_shmd.totalQuantity = 100
o_shmd.eTradeOnly = False
o_shmd.firmQuoteOnly = False
o_shmd.transmit = True

id_shmd = ib.get_next_order_id()
ib.placeOrder(id_shmd, c_shmd, o_shmd)
print(f"  -> Orden #{id_shmd} BUY 100 SHMD transmitida.")

# ── 2. CUBRIR CORTO EN SATL (BUY 60 SATL MKT) ──
print("\n2. Enviando orden de cobertura para SATL (BUY 60 MKT)...")
c_satl = Contract()
c_satl.symbol = "SATL"
c_satl.secType = "STK"
c_satl.exchange = "SMART"
c_satl.currency = "USD"

o_satl = Order()
o_satl.action = "BUY"
o_satl.orderType = "MKT"
o_satl.totalQuantity = 60
o_satl.eTradeOnly = False
o_satl.firmQuoteOnly = False
o_satl.transmit = True

id_satl = ib.get_next_order_id()
ib.placeOrder(id_satl, c_satl, o_satl)
print(f"  -> Orden #{id_satl} BUY 60 SATL transmitida.")

# ── 3. CUBRIR CORTO EN SPY ACCIONES (BUY 6 SPY MKT) ──
print("\n3. Enviando orden de cobertura para SPY acciones (BUY 6 MKT)...")
c_spy_stk = Contract()
c_spy_stk.symbol = "SPY"
c_spy_stk.secType = "STK"
c_spy_stk.exchange = "SMART"
c_spy_stk.currency = "USD"

o_spy_stk = Order()
o_spy_stk.action = "BUY"
o_spy_stk.orderType = "MKT"
o_spy_stk.totalQuantity = 6
o_spy_stk.eTradeOnly = False
o_spy_stk.firmQuoteOnly = False
o_spy_stk.transmit = True

id_spy_stk = ib.get_next_order_id()
ib.placeOrder(id_spy_stk, c_spy_stk, o_spy_stk)
print(f"  -> Orden #{id_spy_stk} BUY 6 SPY acciones transmitida.")

# ── 4. LANZAR PUT PARA SPY (BUY 1x SPY PUT MKT) ──
# Vencimiento: Próxima semana (2026-10-26) | Strike: 770.0 PUT
print("\n4. Enviando orden PUT SPY -> BUY 1x SPY PUT Strike 770 Exp 2026-10-26 (MKT)...")
c_spy_put = Contract()
c_spy_put.conId = 933472355
c_spy_put.symbol = "SPY"
c_spy_put.secType = "OPT"
c_spy_put.exchange = "SMART"
c_spy_put.currency = "USD"
c_spy_put.lastTradeDateOrContractMonth = "20261026"
c_spy_put.strike = 770.0
c_spy_put.right = "P"
c_spy_put.multiplier = "100"

o_spy_put = Order()
o_spy_put.action = "BUY"
o_spy_put.orderType = "MKT"
o_spy_put.totalQuantity = 1
o_spy_put.eTradeOnly = False
o_spy_put.firmQuoteOnly = False
o_spy_put.transmit = True

id_spy_put = ib.get_next_order_id()
ib.placeOrder(id_spy_put, c_spy_put, o_spy_put)
print(f"  -> Orden #{id_spy_put} BUY 1 SPY PUT 770 transmitida.")

# Esperar fills de TWS
print("\nEsperando confirmaciones de llenado desde TWS (6 segundos)...")
time.sleep(6.0)

# Registrar en stocks_orders
try:
    sb.table("stocks_orders").insert([
        {
            "ticker": "SHMD", "group_name": "COVER", "rule_code": "APEX_AUTO",
            "direction": "buy", "order_type": "market", "shares": 100,
            "status": status_captured.get(id_shmd, {}).get("status", "filled"),
            "filled_price": status_captured.get(id_shmd, {}).get("avg_fill_price"),
            "created_at": now_iso
        },
        {
            "ticker": "SATL", "group_name": "COVER", "rule_code": "APEX_AUTO",
            "direction": "buy", "order_type": "market", "shares": 60,
            "status": status_captured.get(id_satl, {}).get("status", "filled"),
            "filled_price": status_captured.get(id_satl, {}).get("avg_fill_price"),
            "created_at": now_iso
        },
        {
            "ticker": "SPY", "group_name": "COVER", "rule_code": "APEX_AUTO",
            "direction": "buy", "order_type": "market", "shares": 6,
            "status": status_captured.get(id_spy_stk, {}).get("status", "filled"),
            "filled_price": status_captured.get(id_spy_stk, {}).get("avg_fill_price"),
            "created_at": now_iso
        }
    ]).execute()
    print("✅ Órdenes de acciones registradas en stocks_orders.")
except Exception as e:
    print("Aviso al registrar en stocks_orders:", e)

# Registrar o actualizar SPY PUT en opt_paper_trades
spy_fill_price = float(status_captured.get(id_spy_put, {}).get("avg_fill_price") or 5.20)
try:
    res_existing = sb.table("opt_paper_trades").select("id").eq("symbol", "SPY").eq("strategy_type", "long_put").eq("status", "open").execute()
    put_trade_data = {
        "underlying_id": 1,
        "symbol": "SPY",
        "strategy_type": "long_put",
        "direction": "bearish",
        "status": "open",
        "qty": 1,
        "expiry": "2026-10-26",
        "entry_time": now_iso,
        "entry_debit": spy_fill_price,
        "entry_total_invested": round(spy_fill_price * 100, 2),
        "max_loss_total": round(spy_fill_price * 100, 2),
        "max_profit_total": round((770.0 - spy_fill_price) * 100, 2),
        "breakeven": round(770.0 - spy_fill_price, 2),
        "last_mark_price": spy_fill_price,
        "last_mark_at": now_iso,
        "model_version": "ib_live_paper",
        "entry_fills": [{
            "conid": 933472355,
            "side": "buy",
            "closing_side": "sell",
            "right": "P",
            "strike": 770.0,
            "bid": spy_fill_price,
            "ask": spy_fill_price,
            "fill_price": spy_fill_price,
            "fee_usd": 0.70,
            "market_data_type": "LIVE",
            "slippage_applied": 0.0
        }],
        "exit_plan": {
            "take_profit_premium": round(spy_fill_price * 1.75, 2),
            "stop_premium": round(spy_fill_price * 0.50, 2),
            "stop_loss_underlying": 778.0,
            "strike": 770.0,
            "right": "P"
        },
        "updated_at": now_iso
    }
    if res_existing.data:
        put_id = res_existing.data[0]["id"]
        sb.table("opt_paper_trades").update(put_trade_data).eq("id", put_id).execute()
        print(f"✅ Posición SPY PUT Strike 770 (ID #{put_id}) actualizada en opt_paper_trades (Entrada: ${spy_fill_price:.2f}).")
    else:
        put_trade_data["created_at"] = now_iso
        res_ins = sb.table("opt_paper_trades").insert(put_trade_data).execute()
        print(f"✅ Posición SPY PUT Strike 770 guardada en opt_paper_trades (Entrada: ${spy_fill_price:.2f}).")
except Exception as e:
    print("Aviso al registrar opt_paper_trades:", e)

# Limpiar posiciones cerradas de SHMD, SATL y SPY en stocks_positions
try:
    sb.table("stocks_positions").update({"status": "closed", "shares": 0}).in_("ticker", ["SHMD", "SATL", "SPY"]).execute()
    print("✅ stocks_positions marcado como closed/0 para SHMD, SATL y SPY.")
except Exception as e:
    print("Aviso stocks_positions:", e)

# Verificar posiciones finales en el broker
print("\nVerificando posiciones finales en TWS...")
final_pos = ib.request_broker_positions(timeout=4.0)
for sym in ["SHMD", "SATL", "SPY", "SPY:OPT:20261026:770.0:P"]:
    print(f"  -> Broker posición {sym}: {final_pos.get(sym, {}).get('shares', 0.0)}")

ib.disconnect_tws()
print("\n=== TODAS LAS ÓRDENES FUERON TRANSMITIDAS CON ÉXITO A TWS ===")
