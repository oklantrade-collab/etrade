import json
from app.core.supabase_client import get_supabase

sb = get_supabase()

# 1. Consultar exactamente las posiciones de la captura de pantalla
print("=" * 70)
print("POSICIONES CON close_reason = 'ctrader_rejected_by_broker'")
print("=" * 70)
res = sb.table('forex_positions').select('*').eq('close_reason', 'ctrader_rejected_by_broker').order('opened_at', desc=True).limit(50).execute()

print(f"Total encontradas: {len(res.data)}")
for p in res.data:
    print("-" * 50)
    print(f"ID: {p.get('id')}")
    print(f"Symbol: {p.get('symbol')} | Side: {p.get('side')} | Lots: {p.get('lots') or p.get('size')}")
    print(f"Entry Price: {p.get('entry_price') or p.get('avg_entry_price')} | Close Price: {p.get('close_price')}")
    print(f"PnL: {p.get('pnl')} | Pips: {p.get('pips_pnl')}")
    print(f"SL: {p.get('sl_price')} | TP: {p.get('tp_price')}")
    print(f"Opened At: {p.get('opened_at')} | Closed At: {p.get('closed_at')}")
    print(f"Rule: {p.get('rule_code')} | Strategy: {p.get('strategy')}")
    print(f"cTrader Pos ID: {p.get('ctrader_pos_id')} | Order ID: {p.get('order_id')}")

# 2. Consultar todas las posiciones abiertas el 13 y 14 de Agosto 2026
print("\n" + "=" * 70)
print("TODAS LAS POSICIONES DEL 13 Y 14 DE AGOSTO 2026")
print("=" * 70)
res_recent = sb.table('forex_positions').select('*').gte('opened_at', '2026-08-13T00:00:00').order('opened_at', desc=True).limit(50).execute()
print(f"Total posiciones recientes: {len(res_recent.data)}")
for p in res_recent.data:
    print(f"[{p.get('opened_at')}] ID={p.get('id')} | {p.get('symbol')} {p.get('side')} {p.get('lots')} lots | Entry={p.get('entry_price')} | Close={p.get('close_price')} | Status={p.get('status')} | Reason={p.get('close_reason')} | cTraderID={p.get('ctrader_pos_id')}")
