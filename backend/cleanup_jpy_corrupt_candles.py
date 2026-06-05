import asyncio
import os
import sys

# Add root directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.core.supabase_client import get_supabase

async def cleanup():
    sb = get_supabase()
    try:
        print("=== INICIANDO LIMPIEZA DE BASE DE DATOS ===")
        
        # 1. Identificar y eliminar velas corruptas de GBPUSD (donde el precio close > 5.0)
        res_gbp = sb.table('market_candles').select('*').eq('symbol', 'GBPUSD').eq('timeframe', '15m').gt('close', 5.0).execute()
        gbp_count = len(res_gbp.data or [])
        print(f"Encontradas {gbp_count} velas corruptas de GBPUSD (close > 5.0).")
        if gbp_count > 0:
            del_gbp = sb.table('market_candles').delete().eq('symbol', 'GBPUSD').eq('timeframe', '15m').gt('close', 5.0).execute()
            print(f"Eliminadas {gbp_count} velas de GBPUSD.")

        # 2. Identificar y eliminar velas corruptas de XAUUSD (donde el precio close < 1000.0)
        res_xau = sb.table('market_candles').select('*').eq('symbol', 'XAUUSD').eq('timeframe', '15m').lt('close', 1000.0).execute()
        xau_count = len(res_xau.data or [])
        print(f"Encontradas {xau_count} velas corruptas de XAUUSD (close < 1000.0).")
        if xau_count > 0:
            del_xau = sb.table('market_candles').delete().eq('symbol', 'XAUUSD').eq('timeframe', '15m').lt('close', 1000.0).execute()
            print(f"Eliminadas {xau_count} velas de XAUUSD.")

        # 3. Restaurar accumulated_profit_forex a 0 en trading_config
        config_res = sb.table('trading_config').select('accumulated_profit_forex').eq('id', 1).single().execute()
        if config_res and config_res.data:
            current_profit = config_res.data.get('accumulated_profit_forex')
            print(f"Capital acumulado Forex actual: ${current_profit}")
            sb.table('trading_config').update({'accumulated_profit_forex': 0.0}).eq('id', 1).execute()
            print("accumulated_profit_forex restaurado a 0.0 en trading_config.")
        else:
            print("No se encontró el registro de trading_config (id=1) para restaurar el capital acumulado.")

        print("=== LIMPIEZA COMPLETADA CON ÉXITO ===")

    except Exception as e:
        print(f"Error durante la limpieza de la base de datos: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup())
