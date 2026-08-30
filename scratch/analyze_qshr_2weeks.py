import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

SUPABASE_URL = 'https://dfrsccxkhicyhkprpsqt.supabase.co'
SUPABASE_SERVICE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw'

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def run_analysis():
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    print(f"=== ANALISIS DE DATOS DESDE: {cutoff} ===")
    
    # 1. Check all positions
    res = sb.table('positions').select('*').gte('created_at', cutoff).order('created_at', desc=True).execute()
    df = pd.DataFrame(res.data)
    print(f"\nTotal posiciones (ultimas 2 semanas): {len(df)}")
    
    if not df.empty:
        # Convert numeric columns
        for col in ['pnl', 'realized_pnl', 'unrealized_pnl', 'entry_price', 'exit_price', 'lots', 'quantity']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        print("\n--- DISTRIBUCION POR MERCADO Y ESTRATEGIA ---")
        summary = df.groupby(['market_type', 'strategy']).agg(
            total=('id', 'count'),
            ganadoras=('pnl', lambda x: (x > 0).sum()),
            perdedoras=('pnl', lambda x: (x < 0).sum()),
            pnl_total=('pnl', 'sum'),
            pnl_promedio=('pnl', 'mean'),
            pnl_max=('pnl', 'max'),
            pnl_min=('pnl', 'min')
        )
        summary['win_rate_%'] = (summary['ganadoras'] / summary['total'] * 100).round(1)
        print(summary.to_string())
        
        # Filtro específico QSHR
        qshr_df = df[df['strategy'].str.contains('QSHR|qshr|Bb33_QSHR|Aa33_QSHR', case=False, na=False)]
        print(f"\n=======================================================")
        print(f"--- DETALLE DE POSICIONES QSHR ({len(qshr_df)}) ---")
        print(f"=======================================================")
        if not qshr_df.empty:
            cols_show = ['id', 'symbol', 'side', 'strategy', 'market_type', 'status', 'entry_price', 'exit_price', 'pnl', 'exit_reason', 'created_at', 'closed_at']
            cols_avail = [c for c in cols_show if c in qshr_df.columns]
            print(qshr_df[cols_avail].to_string())
            
            print("\n--- QSHR AGRUPADO POR MONEDA / ACTIVO ---")
            qshr_sym = qshr_df.groupby(['market_type', 'symbol']).agg(
                total=('id', 'count'),
                ganadas=('pnl', lambda x: (x > 0).sum()),
                perdidas=('pnl', lambda x: (x < 0).sum()),
                pnl_total=('pnl', 'sum'),
                pnl_promedio=('pnl', 'mean')
            )
            qshr_sym['win_rate_%'] = (qshr_sym['ganadas'] / qshr_sym['total'] * 100).round(1)
            print(qshr_sym.to_string())
            
            print("\n--- QSHR AGRUPADO POR SUB-REGLA ---")
            qshr_strat = qshr_df.groupby('strategy').agg(
                total=('id', 'count'),
                ganadas=('pnl', lambda x: (x > 0).sum()),
                perdidas=('pnl', lambda x: (x < 0).sum()),
                pnl_total=('pnl', 'sum'),
                pnl_promedio=('pnl', 'mean')
            )
            qshr_strat['win_rate_%'] = (qshr_strat['ganadas'] / qshr_strat['total'] * 100).round(1)
            print(qshr_strat.to_string())

            print("\n--- QSHR AGRUPADO POR RAZÓN DE SALIDA ---")
            print(qshr_df.groupby('exit_reason').agg(
                total=('id', 'count'),
                pnl_total=('pnl', 'sum'),
                pnl_promedio=('pnl', 'mean')
            ).to_string())

    # 2. Check signals for QSHR
    res_sig = sb.table('signals').select('*').gte('created_at', cutoff).order('created_at', desc=True).execute()
    df_sig = pd.DataFrame(res_sig.data)
    print(f"\n\nTotal señales registradas (ultimas 2 semanas): {len(df_sig)}")
    if not df_sig.empty:
        qshr_sig = df_sig[df_sig['strategy'].str.contains('QSHR|qshr|Bb33|Aa33', case=False, na=False)]
        print(f"Total señales QSHR: {len(qshr_sig)}")
        if not qshr_sig.empty:
            print("\n--- SEÑALES QSHR POR ACTIVO / MONEDA ---")
            print(qshr_sig.groupby(['symbol', 'strategy', 'direction']).size().to_string())

    # 3. Check forex_positions or other forex specific tables
    for tbl in ['forex_positions', 'market_snapshot', 'app_logs', 'system_logs']:
        try:
            r = sb.table(tbl).select('*').limit(5).execute()
            print(f"\nTabla {tbl}: disponible ({len(r.data)} filas de muestra)")
        except Exception as e:
            pass

if __name__ == '__main__':
    run_analysis()
