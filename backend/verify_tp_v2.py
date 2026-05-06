import os
import sys
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def run_verification():
    sb = get_supabase()
    
    print("--------------------------------------------------")
    print("Decisiones de TP v2 por trigger:")
    
    # Fetch orders
    orders_res = sb.table('stocks_orders').select('*').ilike('rule_code', 'tp_%').eq('status', 'filled').execute()
    orders = orders_res.data or []
    
    # Fetch positions
    pos_res = sb.table('stocks_positions').select('*').execute()
    positions = pos_res.data or []
    
    if not orders:
        print("No tp_ orders found.")
    else:
        df_orders = pd.DataFrame(orders)
        df_pos = pd.DataFrame(positions)
        
        if not df_pos.empty:
            merged = pd.merge(df_orders, df_pos, left_on='ticker', right_on='ticker', suffixes=('_o', '_p'))
            merged['ganancia_usd'] = merged['filled_price'] - merged['avg_price']
            
            agg = merged.groupby('rule_code').agg(
                activaciones=('id_o', 'count'),
                avg_ganancia_usd=('ganancia_usd', 'mean'),
                shares_total=('shares_o', 'sum')
            ).reset_index().rename(columns={'rule_code': 'trigger'}).sort_values(by='activaciones', ascending=False)
            
            print(agg.to_string(index=False))
        else:
            print("No positions found.")

    print("\n--------------------------------------------------")
    print("Estado actual de posiciones con EMA:")
    open_pos_res = sb.table('stocks_positions').select('*').eq('status', 'open').execute()
    open_pos = open_pos_res.data or []
    
    if not open_pos:
        print("No open positions found.")
    else:
        df_op = pd.DataFrame(open_pos)
        df_op['entry'] = pd.to_numeric(df_op['avg_price']).round(2)
        df_op['price'] = pd.to_numeric(df_op['current_price']).round(2)
        df_op['gain_pct'] = ((df_op['price'] - df_op['entry']) / df_op['entry'] * 100).round(2)
        if 'mid_band_price' in df_op.columns:
            df_op['mid_band'] = pd.to_numeric(df_op['mid_band_price']).round(2)
        else:
            df_op['mid_band'] = 0.0

        cols = ['ticker', 'entry', 'price', 'gain_pct', 'ema_trend_15m', 'current_fib_band', 'mid_band', 
                'tp_block1_executed', 'tp_block2_executed', 'tp_block3_executed']
        
        # Ensure columns exist
        for c in cols:
            if c not in df_op.columns:
                df_op[c] = None
                
        df_op = df_op.rename(columns={
            'ema_trend_15m': 'ema_trend',
            'current_fib_band': 'fib_band',
            'tp_block1_executed': 'b1',
            'tp_block2_executed': 'b2',
            'tp_block3_executed': 'b3'
        }).sort_values(by='gain_pct', ascending=False)
        
        print(df_op[['ticker', 'entry', 'price', 'gain_pct', 'ema_trend', 'fib_band', 'mid_band', 'b1', 'b2', 'b3']].to_string(index=False))

if __name__ == "__main__":
    run_verification()
