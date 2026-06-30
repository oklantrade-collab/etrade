import os
from supabase import create_client

def fix_phantom_positions():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    sb = create_client(url, key)
    
    # Buscar forex_positions cerradas por slv_v2_recovery_ema_contrary_cross
    res = sb.table('forex_positions').select('*').eq('close_reason', 'slv_v2_recovery_ema_contrary_cross').execute()
    
    if res.data:
        for pos in res.data:
            print(f"Reabriendo posicion fantasma: {pos['symbol']} {pos['side']} {pos['id']}")
            sb.table('forex_positions').update({
                'status': 'open',
                'close_reason': None,
                'pnl_usd': 0,
                'current_price': pos['entry_price']
            }).eq('id', pos['id']).execute()
            
    # Buscar crypto positions
    res = sb.table('positions').select('*').eq('close_reason', 'slv_v2_recovery_ema_contrary_cross').execute()
    if res.data:
        for pos in res.data:
            print(f"Reabriendo posicion fantasma crypto: {pos['symbol']} {pos['side']} {pos['id']}")
            sb.table('positions').update({
                'status': 'open',
                'close_reason': None
            }).eq('id', pos['id']).execute()

if __name__ == '__main__':
    fix_phantom_positions()
