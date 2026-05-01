
import asyncio
from app.core.supabase_client import get_supabase

async def check_cleanup():
    sb = get_supabase()
    res = sb.table("db_cleanup_log").select("*").order("executed_at", desc=True).limit(5).execute()
    print("Últimos registros de limpieza:")
    for row in res.data or []:
        print(f"- {row['executed_at']}: {row['total_deleted']} filas eliminadas (Status: {row['status']})")
    
    # También chequear tamaños de tablas si la función RPC existe
    try:
        size_res = sb.rpc("get_db_size_report").execute()
        print("\nTamaño de tablas:")
        for row in size_res.data or []:
            print(f"- {row['table_name']}: {row['row_count']} filas, {row['total_size']}")
    except:
        print("\nNo se pudo obtener el reporte de tamaño (RPC missing).")

if __name__ == "__main__":
    asyncio.run(check_cleanup())
