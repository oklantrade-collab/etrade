import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.core.supabase_client import get_supabase

sb = get_supabase()

print("=" * 70)
print("6. COLUMNAS: forex_positions")
print("=" * 70)
test_cols = ['sl_type', 'sl_dynamic_price', 'stop_loss', 'take_profit', 'take_profit_price', 
             'dca_executed', 'recovery_activated', 'realized_pnl_pct']
for col in test_cols:
    try:
        sb.table('forex_positions').select(col).limit(1).execute()
        print(f"  [OK] forex_positions.{col} EXISTS")
    except Exception as e:
        err = str(e)
        if '42703' in err or 'does not exist' in err or 'PGRST204' in err or 'schema cache' in err:
            print(f"  [MISS] forex_positions.{col} DOES NOT EXIST")
        else:
            print(f"  [WARN] forex_positions.{col} ERROR: {err[:80]}")

print("\n" + "=" * 70)
print("7. COLUMNAS: positions (crypto)")
print("=" * 70)
for col in test_cols:
    try:
        sb.table('positions').select(col).limit(1).execute()
        print(f"  [OK] positions.{col} EXISTS")
    except Exception as e:
        err = str(e)
        if '42703' in err or 'does not exist' in err or 'PGRST204' in err or 'schema cache' in err:
            print(f"  [MISS] positions.{col} DOES NOT EXIST")
        else:
            print(f"  [WARN] positions.{col} ERROR: {err[:80]}")

print("\n" + "=" * 70)
print("8. Posiciones ANTI-LOSS atrapadas (detalle)")
print("=" * 70)
res = sb.table('positions').select('id, symbol, opened_at, sl_type, erep_active, rule_code, entry_price, current_price, unrealized_pnl').eq('status', 'open').execute()
for p in res.data:
    if p.get('sl_type') == 'susp_neg_protect':
        print(f"  ATRAPADA: {p['symbol']} | opened={p.get('opened_at','?')[:16]} | entry={p.get('entry_price')} | current={p.get('current_price')} | upnl={p.get('unrealized_pnl')}")

print("\n" + "=" * 70)
print("9. Verificacion: frontend deberia mostrar estas cerradas")
print("=" * 70)
res = sb.table('positions').select('symbol, closed_at, close_reason, realized_pnl').eq('status', 'closed').order('closed_at', desc=True).limit(20).execute()
for p in res.data:
    ca = p.get('closed_at', '?')
    print(f"  {ca[:19] if ca else '?'} | {p['symbol']:12s} | {p.get('close_reason','?'):22s} | PnL: {p.get('realized_pnl')}")

print("\nDiagnostico completo")
