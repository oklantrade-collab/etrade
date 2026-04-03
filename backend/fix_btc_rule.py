import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def update_btc_rule():
    print("Corrección 1: Actualizando rule_code para BTC...")
    res = sb.table('paper_trades').update({'rule_code': 'Aa22'})\
        .eq('symbol', 'BTCUSDT')\
        .eq('close_reason', 'sl')\
        .is_('rule_code', 'null')\
        .gte('closed_at', '2026-03-22 00:00:00+00')\
        .execute()
    
    if res.data:
        print(f"Éxito: {len(res.data)} filas actualizadas.")
    else:
        print("No se encontraron filas que coincidan con el criterio.")

    print("\nVerificación:")
    check = sb.table('paper_trades').select('symbol, rule_code, close_reason, closed_at')\
        .gte('closed_at', '2026-03-22 00:00:00+00')\
        .order('closed_at', desc=True).execute()
    for row in check.data:
        print(row)

if __name__ == "__main__":
    update_btc_rule()
