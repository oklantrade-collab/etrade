"""
Diagnóstico: 
1) ¿Hay posiciones crypto cerradas después del 2 de junio en la DB?
2) ¿Hay posiciones "atrapadas" con status='open' que deberían estar cerradas?
3) ¿Hay paper_trades recientes que no aparecen como closed en positions?
4) ¿Qué columnas tiene forex_positions vs positions?
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.core.supabase_client import get_supabase

sb = get_supabase()

print("=" * 70)
print("1. POSICIONES CERRADAS DE CRYPTO (tabla 'positions') - RECIENTES")
print("=" * 70)
try:
    res = sb.table('positions').select('id, symbol, status, closed_at, close_reason, realized_pnl, opened_at').eq('status', 'closed').order('closed_at', desc=True).limit(15).execute()
    for p in res.data:
        print(f"  {p.get('closed_at','?')[:16]} | {p['symbol']:12s} | {p.get('close_reason','?'):22s} | PnL: {p.get('realized_pnl', '?')}")
    print(f"\n  Total mostradas: {len(res.data)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("2. POSICIONES ABIERTAS DE CRYPTO (tabla 'positions', status='open')")
print("=" * 70)
try:
    res = sb.table('positions').select('id, symbol, status, opened_at, erep_active, sl_type, rule_code').eq('status', 'open').execute()
    for p in res.data:
        flags = []
        if p.get('erep_active'): flags.append('EREP')
        if p.get('sl_type') == 'susp_neg_protect': flags.append('ANTI-LOSS')
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {p.get('opened_at','?')[:16]} | {p['symbol']:12s} | rule: {p.get('rule_code','?'):10s}{flag_str}")
    print(f"\n  Total abiertas: {len(res.data)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("3. PAPER TRADES RECIENTES (tabla 'paper_trades') - últimas 15")
print("=" * 70)
try:
    res = sb.table('paper_trades').select('symbol, closed_at, close_reason, total_pnl_usd, mode').order('closed_at', desc=True).limit(15).execute()
    for t in res.data:
        print(f"  {t.get('closed_at','?')[:16]} | {t['symbol']:12s} | {t.get('close_reason','?'):22s} | PnL: ${t.get('total_pnl_usd', 0):.4f}")
    print(f"\n  Total mostradas: {len(res.data)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("4. CONTEO: Closed después del 2 de junio en 'positions'")
print("=" * 70)
try:
    res = sb.table('positions').select('id', count='exact').eq('status', 'closed').gte('closed_at', '2026-06-02T00:00:00').execute()
    print(f"  Posiciones cerradas después del 2 de junio: {res.count}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("5. CONTEO: paper_trades después del 2 de junio")
print("=" * 70)
try:
    res = sb.table('paper_trades').select('id', count='exact').gte('closed_at', '2026-06-02T00:00:00').execute()
    print(f"  Paper trades después del 2 de junio: {res.count}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("6. COLUMNAS: Verificar existencia de columnas en forex_positions")
print("=" * 70)
test_cols = ['sl_type', 'sl_dynamic_price', 'stop_loss', 'take_profit', 'take_profit_price', 
             'dca_executed', 'recovery_activated', 'realized_pnl_pct']
for col in test_cols:
    try:
        sb.table('forex_positions').select(col).limit(1).execute()
        print(f"  ✅ forex_positions.{col} EXISTS")
    except Exception as e:
        err = str(e)
        if 'PGRST204' in err or 'schema cache' in err or 'column' in err.lower():
            print(f"  ❌ forex_positions.{col} DOES NOT EXIST")
        else:
            print(f"  ⚠️ forex_positions.{col} ERROR: {err[:80]}")

print("\n" + "=" * 70)
print("7. COLUMNAS: Verificar existencia de columnas en positions (crypto)")
print("=" * 70)
for col in test_cols:
    try:
        sb.table('positions').select(col).limit(1).execute()
        print(f"  ✅ positions.{col} EXISTS")
    except Exception as e:
        err = str(e)
        if 'PGRST204' in err or 'schema cache' in err or 'column' in err.lower():
            print(f"  ❌ positions.{col} DOES NOT EXIST")
        else:
            print(f"  ⚠️ positions.{col} ERROR: {err[:80]}")

print("\n" + "=" * 70)
print("8. POSICIONES CRYPTO 'ATASCADAS' (status != open y != closed)")
print("=" * 70)
try:
    res = sb.table('positions').select('id, symbol, status, opened_at').neq('status', 'open').neq('status', 'closed').execute()
    if res.data:
        for p in res.data:
            print(f"  {p['symbol']} | status='{p['status']}' | opened={p.get('opened_at','?')}")
    else:
        print("  Ninguna posición con status anormal")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n✅ Diagnóstico completo")
