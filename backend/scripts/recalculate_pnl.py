import os
import sys
import asyncio
from dotenv import load_dotenv

# Asegurar que el modulo principal se pueda importar
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from app.core.pnl_calculator import calculate_pnl

def recalculate_history():
    print("Recalculando PNL histórico...")
    sb = get_supabase()
    
    # 1. Obtener configuración
    cfg_res = sb.table('trading_config').select('*').eq('id', 1).single().execute()
    config = cfg_res.data or {}

    # 2. Recalcular posiciones Forex cerradas
    print("\n--- FOREX POSITIONS ---")
    forex_res = sb.table('forex_positions').select('*').eq('status', 'closed').execute()
    for pos in forex_res.data:
        symbol = pos.get('symbol', '')
        side = pos.get('side', 'long').lower()
        entry = float(pos.get('entry_price') or 0)
        close = float(pos.get('close_price') or pos.get('current_price') or 0)
        qty = float(pos.get('lots') or pos.get('size') or 0.01)
        
        if entry > 0 and close > 0:
            pnl_usd, pnl_pct = calculate_pnl('forex', side, entry, close, qty, symbol, config=config)
            
            try:
                sb.table('forex_positions').update({
                    'pnl_usd': pnl_usd,
                    'pnl_pct': pnl_pct
                }).eq('id', pos['id']).execute()
            except Exception as e:
                if 'pnl_pct' in str(e):
                    print(f"Warning: La columna 'pnl_pct' no existe en forex_positions. Actualizando solo pnl_usd.")
                    sb.table('forex_positions').update({
                        'pnl_usd': pnl_usd
                    }).eq('id', pos['id']).execute()
            print(f"Forex {pos['id']} ({symbol}): USD {pnl_usd} | {pnl_pct}%")

    # 3. Recalcular posiciones Crypto cerradas
    print("\n--- CRYPTO POSITIONS ---")
    crypto_res = sb.table('positions').select('*').eq('status', 'closed').execute()
    for pos in crypto_res.data:
        symbol = pos.get('symbol', '')
        side = pos.get('side', 'long').lower()
        entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or 0)
        close = float(pos.get('close_price') or pos.get('current_price') or 0)
        qty = float(pos.get('size') or pos.get('quantity') or 0)
        
        if entry > 0 and close > 0:
            pnl_usd, pnl_pct = calculate_pnl('crypto', side, entry, close, qty, symbol, config=config)
            
            try:
                sb.table('positions').update({
                    'realized_pnl': pnl_usd,
                    'pnl_pct': pnl_pct
                }).eq('id', pos['id']).execute()
            except Exception as e:
                if 'pnl_pct' in str(e):
                    print(f"Warning: La columna 'pnl_pct' no existe en positions. Actualizando solo realized_pnl.")
                    sb.table('positions').update({
                        'realized_pnl': pnl_usd
                    }).eq('id', pos['id']).execute()
            print(f"Crypto {pos['id']} ({symbol}): USD {pnl_usd} | {pnl_pct}%")

    print("\n✅ Recálculo completado exitosamente.")

if __name__ == '__main__':
    load_dotenv()
    recalculate_history()
