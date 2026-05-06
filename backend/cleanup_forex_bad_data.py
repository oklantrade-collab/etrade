import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

async def cleanup():
    sb = get_supabase()
    try:
        # 1. Identificar registros ficticios (XAUUSD con precio de entrada > 4000)
        res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').gt('entry_price', 4000).execute()
        bad_positions = res.data or []
        count = len(bad_positions)
        total_pnl = sum(float(p.get('pnl_usd', 0) or 0) for p in bad_positions)
        
        print(f"Encontrados {count} registros ficticios con PnL total de ${total_pnl:.2f}")
        
        if count > 0:
            # 2. Corregir el capital acumulado en trading_config
            config_res = sb.table('trading_config').select('accumulated_profit_forex').eq('id', 1).single().execute()
            current_profit = float(config_res.data.get('accumulated_profit_forex') or 0)
            new_profit = current_profit - total_pnl
            
            print(f"Corrigiendo accumulated_profit_forex: ${current_profit:.2f} -> ${new_profit:.2f}")
            sb.table('trading_config').update({'accumulated_profit_forex': round(new_profit, 4)}).eq('id', 1).execute()
            
            # 3. Eliminar los registros de forex_positions
            ids = [p['id'] for p in bad_positions]
            print(f"Eliminando {len(ids)} registros...")
            # Supabase delete doesn't support 'in' directly in some versions via .delete().in_()
            # but we can do it with .in_('id', ids)
            sb.table('forex_positions').delete().in_('id', ids).execute()
            print("Limpieza completada.")
        else:
            print("No se encontraron registros que limpiar.")
            
    except Exception as e:
        print(f"Error durante la limpieza: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup())
