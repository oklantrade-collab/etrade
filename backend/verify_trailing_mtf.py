import os
import pandas as pd
import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

print("=== VERIFICACIÓN 1: Trailing dinámico vs escalonado ===")
res1 = supabase.table('positions').select('*').in_('symbol', ['XAUUSD','GBPUSD']).eq('status', 'closed').execute()
df = pd.DataFrame(res1.data)
if not df.empty:
    df['realized_pnl'] = pd.to_numeric(df['realized_pnl'])
    df['peak_pnl_pct'] = pd.to_numeric(df['peak_pnl_pct'])
    df['opened_at'] = pd.to_datetime(df['opened_at'])
    df['closed_at'] = pd.to_datetime(df['closed_at'])
    df['min_prom'] = (df['closed_at'] - df['opened_at']).dt.total_seconds() / 60.0
    
    df['win'] = (df['realized_pnl'] > 0).astype(int)
    
    grouped = df.groupby(['symbol', 'sl_type']).agg({
        'id': 'count',
        'realized_pnl': 'mean',
        'min_prom': 'mean',
        'win': lambda x: x.sum() * 100.0 / x.count(),
        'peak_pnl_pct': 'mean'
    }).rename(columns={'id': 'trades', 'realized_pnl': 'avg_pnl', 'win': 'win_rate', 'peak_pnl_pct': 'avg_peak_pnl'})
    
    print(grouped.to_string())
else:
    print("No hay posiciones cerradas para XAUUSD/GBPUSD.")

print("\n=== VERIFICACIÓN 2: Entradas bloqueadas por filtro MTF ===")
now = datetime.datetime.utcnow()
past = now - datetime.timedelta(hours=24)
res2 = supabase.table('system_logs').select('module, message, created_at').gte('created_at', past.isoformat()).like('message', '%FILTRO MTF%').order('created_at', desc=True).limit(20).execute()
if res2.data:
    for row in res2.data:
        print(f"[{row['created_at']}] {row['module']}: {row['message']}")
else:
    print("No se encontraron registros de FILTRO MTF en las últimas 24h.")

print("\n=== VERIFICACIÓN 3: Fases del trailing activo ===")
res3 = supabase.table('positions').select('symbol, side, entry_price, current_price, stop_loss, sl_type, peak_pnl_pct').eq('symbol', 'XAUUSD').eq('status', 'open').execute()
if res3.data:
    for row in res3.data:
        if row['entry_price'] is not None and row['current_price'] is not None:
            pnl = round((float(row['current_price']) - float(row['entry_price'])) / 0.01, 1)
        else:
            pnl = 0.0
        print(f"Symbol: {row['symbol']}, Side: {row['side']}, Entry: {row['entry_price']}, Price: {row['current_price']}, SL: {row['stop_loss']}, PnL(pips): {pnl}, Type: {row['sl_type']}, Peak: {row['peak_pnl_pct']}")
else:
    print("No hay posiciones abiertas para XAUUSD.")
