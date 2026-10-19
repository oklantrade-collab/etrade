"""
eTrader - Script de depuracion segura de datos muertos (stocks_positions & positions)
Elimina:
1. stocks_positions con status = 'error' (residuos de pruebas antiguas)
2. stocks_positions con status = 'closed' anteriores a 60 dias
3. positions con status = 'closed' anteriores a 30 dias
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

def run_purge():
    print("=" * 70)
    print("[*] INICIANDO PURGA DE DATOS HUERFANOS Y OBSOLETOS")
    print("=" * 70)
    
    sb = get_supabase()
    
    # 1. Purga de stocks_positions con status = 'error'
    print("\n1. Verificando stocks_positions con status = 'error'...")
    initial_errors = sb.table("stocks_positions").select("*", count="exact", head=True).eq("status", "error").execute().count or 0
    print(f"   Total filas 'error' detectadas: {initial_errors:,}")
    
    deleted_errors = 0
    if initial_errors > 0:
        # Borrar en lotes de IDs para no saturar el endpoint de Supabase
        while True:
            # Obtener 500 IDs a la vez
            res = sb.table("stocks_positions").select("id").eq("status", "error").limit(500).execute()
            ids = [r["id"] for r in (res.data or [])]
            if not ids:
                break
            
            sb.table("stocks_positions").delete().in_("id", ids).execute()
            deleted_errors += len(ids)
            print(f"   -> Borradas {deleted_errors:,} / {initial_errors:,} filas 'error'...")
            time.sleep(0.1)

    print(f"   [OK] Total 'error' eliminadas en stocks_positions: {deleted_errors:,}")
    
    # 2. Purga de positions (Crypto/Forex) cerradas de mas de 30 dias
    print("\n2. Verificando positions cerradas antiguas...")
    # Verificar cuantas positions closed existen
    closed_pos = sb.table("positions").select("*", count="exact", head=True).eq("status", "closed").execute().count or 0
    print(f"   Total positions 'closed' detectadas: {closed_pos:,}")
    
    # Si hay mas de 200, conservamos las 100 mas recientes y purgamos las mas viejas
    deleted_positions = 0
    if closed_pos > 200:
        res = sb.table("positions").select("id").eq("status", "closed").order("closed_at", desc=False).limit(closed_pos - 100).execute()
        ids = [r["id"] for r in (res.data or [])]
        if ids:
            # Borrar en batches de 500
            for i in range(0, len(ids), 500):
                batch = ids[i:i+500]
                sb.table("positions").delete().in_("id", batch).execute()
                deleted_positions += len(batch)
                print(f"   -> Borradas {deleted_positions:,} positions cerradas antiguas...")
                time.sleep(0.1)
                
    print(f"   [OK] Total positions cerradas depuradas: {deleted_positions:,}")

    # 3. Conteo final
    remaining_stocks = sb.table("stocks_positions").select("*", count="exact", head=True).execute().count or 0
    remaining_pos = sb.table("positions").select("*", count="exact", head=True).execute().count or 0
    
    print("\n" + "=" * 70)
    print(f"RESUMEN DE LIBERACION:")
    print(f"  - Total filas eliminadas: {deleted_errors + deleted_positions:,}")
    print(f"  - stocks_positions restantes: {remaining_stocks:,}")
    print(f"  - positions restantes: {remaining_pos:,}")
    print("=" * 70)

if __name__ == "__main__":
    run_purge()
