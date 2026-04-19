import asyncio
import os
import sys
import pandas as pd

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from dotenv import load_dotenv
from supabase import create_client
from app.stocks.stocks_rule_engine import StocksRuleEngine
from app.stocks.stocks_order_executor import execute_market_order, place_limit_order

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

sb = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

async def test_example_orders():
    print("=== TEST ÓRDENES STOCKS ===\n")

    engine = StocksRuleEngine.get_instance()
    engine.load_rules()
    print(f"Reglas cargadas: {len(engine.rules)}\n")

    # ── CONTEXTO SIMULADO: AAPL alcista ──────
    context_aapl = {
        'ticker':        'AAPL',
        'price':         175.50,
        'basis':         172.00,
        'fib_zone':      1,
        'movement_type': 'lateral_ascending',
        'signal_bias':   'long_bias',
        'basis_slope_pct': 0.23,
        'ia_score':      8.2,    # >= 7 ✅
        'tech_score':    72.0,   # >= 60 ✅
        'rvol':          2.3,    # > 2.0 ✅
        'pine_signal':   'Buy',  # Pine = B ✅
        'limit_buy_price':  173.25,  # lower_1
        'limit_sell_price': 179.80,  # upper_1
        'limit_buy_band':   'lower_1',
        'limit_sell_band':  'upper_1',
        'limit_buy_quality': 'high',
        'limit_sell_quality': 'medium',
    }

    print("TICKER: AAPL — Lateral Ascendente")
    print(f"Precio: ${context_aapl['price']}")
    print(f"IA: {context_aapl['ia_score']}/10")
    print(f"Tech: {context_aapl['tech_score']}/100")
    print(f"Pine: {context_aapl['pine_signal']}\n")

    # ── EVALUAR TODAS LAS REGLAS ─────────────
    results = engine.evaluate_all(
        context    = context_aapl,
        group_name = 'inversiones_pro',
        direction  = 'buy',
    )

    print("--- EVALUACION DE REGLAS PRO BUY ---")
    for r in results:
        status = 'TRIGGERED ' if r['triggered'] else 'FAILED    '
        print(f"[{status}] {r['rule_code']:15s} ({r['order_type']:6s}): {r['reason'][:60]}")
    print()

    # --- EJECUTAR ORDEN MARKET ─────────────────
    market_rule = engine.rules.get('PRO_BUY_MKT')
    if market_rule:
        market_result = engine.evaluate_rule(market_rule, context_aapl)
        if market_result['triggered']:
            print("--- EJECUTANDO ORDEN MARKET BUY ---")
            try:
                order = execute_market_order(
                    ticker    = 'AAPL',
                    direction = 'buy',
                    rule_code = 'PRO_BUY_MKT',
                    context   = context_aapl,
                    rule      = market_rule,
                )
                if order.get('success'):
                    print(f"OK MARKET ORDER: {order['direction'].upper()} {order['shares']} shares AAPL @ ${order['price']:.2f}")
                    print(f"   Paper mode: {order['paper']}")
                else:
                    print(f"FAIL MARKET: {order.get('reason')}")
            except Exception as e:
                print(f"Error executing market order: {e}")
    else:
        print("Regla PRO_BUY_MKT no encontrada en BD. Asegúrese de correr el SQL.")
    print()

    # --- COLOCAR ORDEN LIMIT ───────────────────
    limit_rule = engine.rules.get('PRO_BUY_LMT')

    if limit_rule:
        # Simular que el precio está 0.3% cerca del estimado (< 0.5% → trigger)
        context_limit = context_aapl.copy()
        context_limit['price'] = 173.77  # 0.3% sobre lower_1

        # Recalcular distancia
        dist = abs(context_limit['price'] - context_limit['limit_buy_price']) / context_limit['limit_buy_price']
        print(f"--- COLOCANDO ORDEN LIMIT BUY ---")
        print(f"Precio actual: ${context_limit['price']:.2f}")
        print(f"Precio estimado: ${context_limit['limit_buy_price']:.2f}")
        print(f"Distancia: {dist*100:.2f}% (trigger: 0.5%)")

        limit_result = engine.evaluate_rule(limit_rule, context_limit)
        if limit_result['triggered']:
            try:
                order = place_limit_order(
                    ticker    = 'AAPL',
                    direction = 'buy',
                    rule_code = 'PRO_BUY_LMT',
                    context   = context_limit,
                    rule      = limit_rule,
                )
                if order.get('success'):
                    print(f"OK LIMIT ORDER colocada: ${order['limit_price']:.2f} en {order['band']}")
                    print(f"   Trigger activo en: ${order['trigger_price']:.2f}")
                else:
                    print(f"FAIL LIMIT: {order.get('reason')}")
            except Exception as e:
                print(f"Error placing limit order: {e}")
        else:
            print(f"FAIL Limit no activada: {limit_result['reason']}")
    else:
        print("Regla PRO_BUY_LMT no encontrada en BD.")

    print()
    print("--- VERIFICAR EN SUPABASE ---")
    
    print("\n[Ver reglas configuradas]")
    rules = sb.table("stocks_rules").select("rule_code, name, direction, order_type, enabled").order("group_name").order("direction").order("order_type").execute()
    for r in rules.data:
        print(f"{r['rule_code']:15s} | {r['direction']:4s} | {r['order_type']:6s} | {r['enabled']} | {r['name'][:50]}")

    print("\n[Ver órdenes del test]")
    orders = sb.table("stocks_orders").select("ticker, order_type, direction, status, market_price, limit_price, rule_code, created_at").order("created_at", desc=True).limit(10).execute()
    for o in orders.data:
        lmt = f"{float(o['limit_price']):.2f}" if o.get('limit_price') else "NULL"
        print(f"{o['ticker']:5s} | {o['order_type']:6s} | {o['direction']:4s} | {o['status']:8s} | Mkt: {o['market_price']} | Lmt: {lmt} | Rule: {o['rule_code']}")

    print("\n[Ver posiciones abiertas]")
    pos = sb.table("stocks_positions").select("ticker, shares, avg_price, dca_count, status").eq("status", "open").order("ticker").execute()
    if not pos.data:
        print("No hay posiciones abiertas.")
    for p in pos.data:
        print(f"{p['ticker']:5s} | Shares: {p['shares']} | Avg: {p['avg_price']} | DCA: {p['dca_count']} | Status: {p['status']}")

    print("\n=== TEST COMPLETADO ===")

if __name__ == "__main__":
    asyncio.run(test_example_orders())
