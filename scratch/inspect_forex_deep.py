import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

SUPABASE_URL = 'https://dfrsccxkhicyhkprpsqt.supabase.co'
SUPABASE_SERVICE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw'

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def inspect_all():
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    print(f"Checking forex_positions since {cutoff}...")
    
    # 1. Forex positions table
    try:
        res = sb.table('forex_positions').select('*').execute()
        df = pd.DataFrame(res.data)
        print(f"Total forex_positions count: {len(df)}")
        if not df.empty:
            print("Columns in forex_positions:", df.columns.tolist())
            print(df.tail(20).to_string())
    except Exception as e:
        print("Error reading forex_positions:", e)
        
    # 2. Check all closed positions in 'positions' where market_type = 'forex'
    res_pos = sb.table('positions').select('*').eq('market_type', 'forex').gte('created_at', cutoff).execute()
    df_pos = pd.DataFrame(res_pos.data)
    print(f"\nTotal positions with market_type='forex' in last 14d: {len(df_pos)}")
    if not df_pos.empty:
        print("Columns:", df_pos.columns.tolist())
        print("\nBreakdown by symbol and strategy:")
        print(df_pos.groupby(['symbol', 'strategy', 'side', 'exit_reason']).agg(
            count=('id', 'count'),
            pnl_sum=('pnl', 'sum'),
            pnl_avg=('pnl', 'mean')
        ).to_string())

if __name__ == '__main__':
    inspect_all()
