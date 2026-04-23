
from app.core.supabase_client import get_supabase
import asyncio

async def cleanup():
    supabase = get_supabase()
    print("--- Iniciando Limpieza de Posiciones Distorsionadas ---")
    
    # 1. Limpieza de Forex
    fx_res = supabase.table('forex_positions').select('*').eq('status', 'open').execute()
    if fx_res.data:
        for pos in fx_res.data:
            # Eliminamos todas las abiertas para resetear el monitor y que entren limpias con las nuevas reglas
            supabase.table('forex_positions').delete().eq('id', pos['id']).execute()
            print(f"Eliminada posición Forex: {pos['symbol']} {pos['side']} ID: {pos['id']}")
    
    # 2. Limpieza de Cripto
    crypto_res = supabase.table('positions').select('*').eq('status', 'open').execute()
    if crypto_res.data:
        for pos in crypto_res.data:
            supabase.table('positions').delete().eq('id', pos['id']).execute()
            print(f"Eliminada posición Crypto: {pos['symbol']} ID: {pos['id']}")

    print("--- Limpieza Completada con Éxito ---")

if __name__ == "__main__":
    asyncio.run(cleanup())
