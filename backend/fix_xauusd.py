from app.core.supabase_client import get_supabase

def fix_forex_prices():
    sb = get_supabase()
    
    symbols_to_fix = {
        'XAUUSD': 1000.0,
        'XAGUSD': 1000.0,
        'USDJPY': 1000.0,
        'EURJPY': 1000.0,
        'GBPJPY': 1000.0
    }
    
    for symbol, divisor in symbols_to_fix.items():
        # 1. Fix market_snapshot
        res = sb.table('market_snapshot').select('*').eq('symbol', symbol).execute()
        if res.data:
            snap = res.data[0]
            # Solo dividir si el precio es claramente erroneo (escala alta)
            if snap['price'] > 5000:
                new_snap = {}
                fields_to_divide = [
                    'price', 'basis', 'upper_1', 'upper_2', 'upper_3', 
                    'upper_4', 'upper_5', 'upper_6', 'lower_1', 'lower_2', 
                    'lower_3', 'lower_4', 'lower_5', 'lower_6', 'sar_4h', 'sar_15m'
                ]
                for f in fields_to_divide:
                    if f in snap and snap[f] is not None and snap[f] > 100:
                        new_snap[f] = float(snap[f]) / divisor
                
                if new_snap:
                    sb.table('market_snapshot').update(new_snap).eq('symbol', symbol).execute()
                    print(f'market_snapshot updated for {symbol}')

        # 2. Fix forex_positions
        res = sb.table('forex_positions').select('*').eq('symbol', symbol).eq('status', 'open').execute()
        for pos in res.data:
            if pos['entry_price'] > 5000:
                new_pos = {
                    'entry_price': float(pos['entry_price']) / divisor,
                    'sl_price': float(pos['sl_price']) / divisor if pos['sl_price'] else None,
                    'tp_price': float(pos['tp_price']) / divisor if pos['tp_price'] else None,
                    'slv_price': float(pos['slv_price']) / divisor if pos['slv_price'] else None,
                }
                if pos.get('slv_hard_stop_trigger'):
                     new_pos['slv_hard_stop_trigger'] = float(pos['slv_hard_stop_trigger']) / divisor
                
                sb.table('forex_positions').update(new_pos).eq('id', pos['id']).execute()
                print(f"forex_position {pos['id']} updated for {symbol}")

if __name__ == "__main__":
    fix_forex_prices()
