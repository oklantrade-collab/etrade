import asyncio
from datetime import datetime, timedelta
from supabase import create_client
import os

# Configuración de Retención (Días)
RETENTION_DAYS = {
    '5m': 20, '15m': 60, '30m': 90,
    '45m': 120, '4h': 365, '1d': 1095, '1w': 2190
}

async def cleanup():
    # Render debe tener estas variables configuradas
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_SERVICE_KEY')
    
    if not url or not key:
        print("[ERROR] Faltan variables de entorno SUPABASE_URL o SUPABASE_KEY")
        return

    sb = create_client(url, key)
    
    print(f"--- Iniciando limpieza de base de datos eTrade {datetime.utcnow().isoformat()} ---")
    
    for tf, days in RETENTION_DAYS.items():
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        try:
            result = sb.table('market_candles')\
                .delete()\
                .eq('timeframe', tf)\
                .lt('timestamp', cutoff)\
                .execute()
            
            # Nota: Supabase Python client no devuelve el conteo de filas eliminadas fácilmente en delete() sin modificadores
            print(f'[CLEANUP] {tf}: eliminadas velas anteriores a {cutoff}')
        except Exception as e:
            print(f'[ERROR] Falló limpieza de {tf}: {e}')

if __name__ == '__main__':
    asyncio.run(cleanup())
