import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_cleanup_and_checks():
    print("--- TEMA 1: Limpiar trade artificial BTC ---")
    res1 = sb.table('paper_trades').delete()\
        .eq('symbol', 'BTCUSDT')\
        .eq('mode', 'paper')\
        .eq('entry_price', 71146.00)\
        .eq('close_reason', 'sl')\
        .execute()
    
    if res1.data:
        print(f"Éxito: {len(res1.data)} trade artificial de BTC eliminado.")
    else:
        print("No se encontró el trade artificial de BTC.")

    print("\n--- TEMA 2: Estado posición original BTC ($70,934) ---")
    res2 = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').order('updated_at', desc=True).limit(3).execute()
    if res2.data:
        for row in res2.data:
            print(f"Status: {row['status']} | Entry: {row.get('avg_entry_price')} | Reason: {row.get('close_reason')} | Closed At: {row.get('closed_at')}")
    else:
        print("No se encontró la posición original de BTC.")

    print("\n--- VERIFICACIÓN FINAL: Sistema limpio ---")
    print("Trades en papel:")
    res_trades = sb.table('paper_trades').select('symbol, close_reason, total_pnl_usd, closed_at').eq('mode', 'paper').order('closed_at', desc=True).execute()
    for row in res_trades.data:
        print(row)
    
    print("\nPosiciones abiertas:")
    res_pos = sb.table('positions').select('symbol, status, avg_entry_price').eq('status', 'open').execute()
    if not res_pos.data:
        print("0 filas (sistema limpio)")
    else:
        for row in res_pos.data: print(row)

if __name__ == "__main__":
    run_cleanup_and_checks()
