import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_cleanup_and_checks():
    print("--- VERIFICACIÓN FINAL: Sistema limpio ---")
    print("Trades en papel:")
    res_trades = sb.table('paper_trades').select('symbol, close_reason, total_pnl_usd, closed_at').eq('mode', 'paper').order('closed_at', desc=True).execute()
    for row in res_trades.data:
        print(row)
    
    print("\nPosiciones abiertas de BTC:")
    # Usando campo genérico de ordenamiento si existe, sino sin orden
    res_pos = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').execute()
    for row in res_pos.data:
        print(f"Status: {row['status']} | Entry: {row.get('avg_entry_price') or row.get('entry_price')} | Reason: {row.get('close_reason')} | Closed At: {row.get('closed_at')}")

    print("\nPosiciones abiertas totales (status = 'open'):")
    res_open = sb.table('positions').select('symbol, status, avg_entry_price').eq('status', 'open').execute()
    if not res_open.data:
        print("0 filas (sistema limpio)")
    else:
        for row in res_open.data: print(row)

if __name__ == "__main__":
    run_cleanup_and_checks()
