"""
Run Adaptive TP migration:
  - PASO 0: Initialize shares_remaining
  - PASO 1: Add adaptive TP columns
  - VERIFICACION: Show current positions
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    
    print("═" * 60)
    print("PASO 0 — Inicializar shares_remaining")
    print("═" * 60)
    
    # First check current state
    open_pos = sb.table('stocks_positions') \
        .select('ticker, shares, shares_remaining') \
        .eq('status', 'open') \
        .execute()
    
    print(f"\nPosiciones abiertas: {len(open_pos.data or [])}")
    for p in (open_pos.data or []):
        print(f"  {p['ticker']}: shares={p['shares']}, shares_remaining={p.get('shares_remaining')}")
    
    # Initialize shares_remaining where NULL
    needs_init = [p for p in (open_pos.data or []) if p.get('shares_remaining') is None]
    if needs_init:
        for p in needs_init:
            sb.table('stocks_positions').update({
                'shares_remaining': p['shares']
            }).eq('ticker', p['ticker']).eq('status', 'open').execute()
            print(f"  ✅ {p['ticker']}: shares_remaining = {p['shares']}")
    else:
        print("  ✅ Todas las posiciones ya tienen shares_remaining")
    
    print("\n" + "═" * 60)
    print("PASO 1 — Agregar columnas para TP Adaptativo")
    print("═" * 60)
    
    # Use RPC to run raw SQL for ALTER TABLE
    # Since Supabase client doesn't support ALTER TABLE directly,
    # we try to update with the new columns — if they don't exist yet,
    # we need to run the SQL via Supabase Dashboard or psql.
    # For now, let's verify if the columns exist by trying a select.
    
    new_columns = [
        'tp_adaptive_mode', 'tp_highest_band', 'tp_rejection_count',
        'tp_rejection_band', 'tp_exhaustion_score', 'tp_macro_score',
        'tp_adaptive_b1', 'tp_adaptive_b2', 'tp_last_evaluated',
        'tp_exit_signal', 'macro_vix', 'macro_spy_change', 'macro_ndx_change'
    ]
    
    try:
        test = sb.table('stocks_positions') \
            .select(','.join(new_columns)) \
            .limit(1) \
            .execute()
        print("  ✅ Todas las columnas adaptativas ya existen")
    except Exception as e:
        print(f"  ⚠️ Las columnas adaptativas NO existen aún.")
        print(f"     Error: {e}")
        print()
        print("  EJECUTAR ESTE SQL EN SUPABASE DASHBOARD > SQL Editor:")
        print("  " + "-" * 50)
        print("""
  ALTER TABLE stocks_positions
  ADD COLUMN IF NOT EXISTS tp_adaptive_mode    BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS tp_highest_band     INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_rejection_count  INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_rejection_band   INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_exhaustion_score NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_macro_score      NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_adaptive_b1      NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_adaptive_b2      NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_last_evaluated   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS tp_exit_signal      VARCHAR(50),
  ADD COLUMN IF NOT EXISTS macro_vix           NUMERIC,
  ADD COLUMN IF NOT EXISTS macro_spy_change    NUMERIC,
  ADD COLUMN IF NOT EXISTS macro_ndx_change    NUMERIC;
        """)
        return

    print("\n" + "═" * 60)
    print("VERIFICACIÓN — Estado de posiciones con TP")
    print("═" * 60)
    
    verify = sb.table('stocks_positions') \
        .select(
            'ticker, shares, shares_remaining, avg_price, current_price, '
            'tp_highest_band, tp_exhaustion_score, tp_buy_strength, '
            'tp_block1_price, tp_block1_executed, tp_block1_pnl, '
            'tp_block2_executed, tp_block3_executed, macro_vix'
        ) \
        .eq('status', 'open') \
        .execute()
    
    if verify.data:
        print(f"\n{'Ticker':<8} {'Shares':>6} {'Rem':>4} {'Entry':>8} {'Price':>8} {'Gain%':>7} {'Band':>4} {'Exh':>4} {'Fuerza':<10} {'VIX':>5} {'B1':>8} {'B1✓':>3}")
        print("-" * 100)
        for p in verify.data:
            entry = float(p.get('avg_price') or 0)
            price = float(p.get('current_price') or 0)
            gain = ((price - entry) / entry * 100) if entry > 0 else 0
            print(
                f"{p['ticker']:<8} "
                f"{p.get('shares', 0):>6} "
                f"{p.get('shares_remaining', '?'):>4} "
                f"{entry:>8.2f} "
                f"{price:>8.2f} "
                f"{gain:>7.2f} "
                f"{p.get('tp_highest_band', 0):>4} "
                f"{float(p.get('tp_exhaustion_score') or 0):>4.1f} "
                f"{p.get('tp_buy_strength', 'N/A'):<10} "
                f"{float(p.get('macro_vix') or 0):>5.1f} "
                f"{float(p.get('tp_block1_price') or 0):>8.2f} "
                f"{'✅' if p.get('tp_block1_executed') else '❌':>3}"
            )
    else:
        print("  No hay posiciones abiertas")
    
    # Orders verification
    print("\n" + "═" * 60)
    print("VERIFICACIÓN — Órdenes TP recientes")
    print("═" * 60)
    
    try:
        orders = sb.table('stocks_orders') \
            .select('ticker, rule_code, shares, filled_price, created_at') \
            .like('rule_code', 'TP_%') \
            .order('created_at', desc=True) \
            .limit(20) \
            .execute()
        
        if orders.data:
            print(f"\n{'Ticker':<8} {'Rule':<20} {'Shares':>6} {'Price':>8} {'Date'}")
            print("-" * 70)
            for o in orders.data:
                print(
                    f"{o['ticker']:<8} "
                    f"{o.get('rule_code', 'N/A'):<20} "
                    f"{o.get('shares', 0):>6} "
                    f"{float(o.get('filled_price') or 0):>8.2f} "
                    f"{o.get('created_at', 'N/A')}"
                )
        else:
            print("  No hay órdenes TP registradas aún")
    except Exception as e:
        print(f"  Error consultando órdenes: {e}")

    print("\n✅ Migración completada exitosamente")


if __name__ == '__main__':
    main()
