
from app.core.supabase_client import get_supabase
import pandas as pd
import sys

def run_diagnostics():
    sb = get_supabase()
    print("--- INICIANDO DIAGNÓSTICO DE PROTECCIÓN ---")
    
    # Obtener todas las posiciones cerradas de Crypto
    try:
        raw = sb.table('positions').select('symbol, realized_pnl, opened_at, closed_at, close_reason').eq('status', 'closed').execute()
        if not raw.data:
            print("No hay datos de posiciones cerradas para analizar.")
            return

        df = pd.DataFrame(raw.data)
        df['opened_at'] = pd.to_datetime(df['opened_at'])
        df['closed_at'] = pd.to_datetime(df['closed_at'])
        df['duration_min'] = (df['closed_at'] - df['opened_at']).dt.total_seconds() / 60
        
        # Filtro para SL
        sl_df = df[df['close_reason'].str.lower().str.contains('sl|stop_loss', na=False)]
        
        # Reporte 1: Destrucción por Símbolo
        if not sl_df.empty:
            report1 = sl_df.groupby('symbol').agg(
                sl_activaciones=('realized_pnl', 'count'),
                total_perdido_usd=('realized_pnl', 'sum'),
                promedio_pnl=('realized_pnl', 'mean'),
                minutos_promedio_abierta=('duration_min', 'mean')
            ).sort_values('total_perdido_usd').reset_index()
            print('\n--- REPORTE 1: DESTRUCCIÓN POR SÍMBOLO ---')
            print(report1.to_string(index=False))
        else:
            print("\nNo se encontraron activaciones de SL.")

        # Reporte 2: Efectividad por Razón de Cierre
        report2 = df.groupby('close_reason').agg(
            trades=('realized_pnl', 'count'),
            avg_pnl=('realized_pnl', 'mean'),
            minutos_promedio=('duration_min', 'mean'),
            win_rate=('realized_pnl', lambda x: (x > 0).sum() * 100.0 / len(x))
        ).sort_values('avg_pnl', ascending=False).reset_index()
        print('\n--- REPORTE 2: EFECTIVIDAD POR RAZÓN DE CIERRE ---')
        print(report2.to_string(index=False))

        # Reporte 3: Peores SL Activados
        if not sl_df.empty:
            report3 = sl_df.sort_values('realized_pnl').head(10)[['symbol', 'realized_pnl', 'opened_at', 'closed_at']]
            print('\n--- REPORTE 3: PEORES SL ACTIVADOS ---')
            print(report3.to_string(index=False))

    except Exception as e:
        print(f"Error en diagnóstico: {e}")

if __name__ == "__main__":
    run_diagnostics()
