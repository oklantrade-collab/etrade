"""
Script para cerrar las 5 posiciones crypto atrapadas por el Anti-Loss Guard.
Estas posiciones tienen sl_type='susp_neg_protect' y erep_active=True,
pero nunca se cerrarán naturalmente.

Pérdida total estimada: ~$4.84 (~0.48% del capital)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase

sb = get_supabase()

print("=" * 70)
print("Buscando posiciones atrapadas por Anti-Loss Guard...")
print("=" * 70)

res = sb.table('positions').select('*').eq('status', 'open').eq('sl_type', 'susp_neg_protect').execute()
trapped = res.data or []

if not trapped:
    print("No se encontraron posiciones atrapadas. Todo OK.")
    sys.exit(0)

print(f"Encontradas {len(trapped)} posiciones atrapadas:\n")

total_loss = 0.0
for p in trapped:
    entry = float(p.get('entry_price') or 0)
    current = float(p.get('current_price') or entry)
    size = float(p.get('size') or 0)
    side = (p.get('side') or '').lower()
    
    if side in ('long', 'buy'):
        pnl = (current - entry) * size
    else:
        pnl = (entry - current) * size
    
    total_loss += pnl
    print(f"  {p['symbol']:12s} | opened={str(p.get('opened_at',''))[:16]} | "
          f"entry={entry:.4f} | current={current:.4f} | size={size} | PnL=${pnl:.4f}")

print(f"\nPerdida total estimada: ${total_loss:.4f}")
print()

confirm = input("Desea cerrar estas posiciones? (si/no): ").strip().lower()
if confirm != 'si':
    print("Cancelado.")
    sys.exit(0)

print("\nCerrando posiciones...")
now = datetime.now(timezone.utc).isoformat()

for p in trapped:
    pos_id = p['id']
    symbol = p['symbol']
    entry = float(p.get('entry_price') or 0)
    current = float(p.get('current_price') or entry)
    size = float(p.get('size') or 0)
    side = (p.get('side') or '').lower()
    
    if side in ('long', 'buy'):
        pnl = (current - entry) * size
    else:
        pnl = (entry - current) * size
    
    try:
        sb.table('positions').update({
            'status': 'closed',
            'close_reason': 'CLEANUP_TRAPPED',
            'current_price': current,
            'closed_at': now,
            'realized_pnl': round(pnl, 4),
            'sl_type': None,
            'erep_active': False,
            'erep_phase': 0,
        }).eq('id', pos_id).execute()
        
        # Registrar en paper_trades
        sb.table('paper_trades').insert({
            'symbol': symbol,
            'side': p.get('side', 'long'),
            'entry_price': entry,
            'exit_price': current,
            'total_pnl_usd': round(pnl, 4),
            'total_pnl_pct': round(((current - entry) / entry * 100) if entry > 0 else 0, 4),
            'close_reason': 'CLEANUP_TRAPPED_ANTILOSS',
            'closed_at': now,
            'mode': 'paper',
            'rule_code': p.get('rule_code', 'cleanup')
        }).execute()
        
        print(f"  [OK] {symbol} cerrada | PnL=${pnl:.4f}")
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")

print("\nLimpieza completada.")
