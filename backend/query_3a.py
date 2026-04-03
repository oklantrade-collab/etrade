import os
from dotenv import load_dotenv
from supabase import create_client
import pandas as pd

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

def run_query_3a():
    # El usuario pidió el query exacto de la instrucción original (PASO 3A)
    # Como no puedo ejecutar SQL crudo arbitrario facilmente sin una funcion RPC 'exec_sql',
    # voy a emular el resultado de esa agregación en Python sobre los datos de paper_trades.
    # Pero el usuario quiere la tabla resultante.
    
    res = supabase.table('paper_trades').select('*').eq('mode', 'backtest').execute()
    df = pd.DataFrame(res.data)
    
    if df.empty:
        print("La tabla paper_trades está vacía. Ejecuta el backtest primero.")
        return

    # Numeric conversion
    columns_to_fix = ['total_pnl_usd', 'total_pnl_pct', 'adx_value']
    for col in columns_to_fix:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Identificar columnas para agrupar (SOLO rule_code y regime como pide el usuario)
    group_cols = ['rule_code', 'regime']
    
    # Agregación corregida (Fórmula económica)
    def aggregate(x):
        trades = len(x)
        wins_mask = x['total_pnl_usd'] > 0
        wins = len(x[wins_mask])
        win_rate = wins / trades
        
        pos = x[wins_mask]['total_pnl_pct']
        avg_win_pct = pos.mean() if not pos.empty else 0
        
        neg = x[~wins_mask]['total_pnl_pct']
        avg_loss_pct = abs(neg.mean()) if not neg.empty else 0
        
        # Fórmula: EV = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)
        ev = round((win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct), 4)
        
        avg_adx = round(x['adx_value'].mean(), 2)
        
        return pd.Series({
            'trades': trades,
            'wins': wins,
            'win_rate': round(win_rate, 4),
            'avg_win': round(avg_win_pct, 4),
            'avg_loss': round(avg_loss_pct, 4),
            'avg_adx': avg_adx,
            'expected_value': ev
        })

    agg = df.groupby(group_cols).apply(aggregate).reset_index()
    
    print("\n" + "="*80)
    print(" RESULTADO DEL QUERY 3A - PERFORMANCE POR REGLA (EMULADO SQL)")
    print("="*80)
    print(agg.sort_values('expected_value', ascending=False).to_string(index=False))
    print("="*80)

if __name__ == "__main__":
    run_query_3a()
