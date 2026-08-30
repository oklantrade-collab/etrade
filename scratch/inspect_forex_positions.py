import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

SUPABASE_URL = 'https://dfrsccxkhicyhkprpsqt.supabase.co'
SUPABASE_SERVICE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw'

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def inspect_forex():
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    res = sb.table('forex_positions').select('*').gte('created_at', cutoff).execute()
    df = pd.DataFrame(res.data)
    print(f"Total forex_positions in last 14 days: {len(df)}")
    if not df.empty:
        print(df.info())
        print(df.head(10).to_string())
        if 'strategy' in df.columns:
            print(df.groupby('strategy').size())
            
    # Check all signals in table 'signals' for forex symbols
    res_s = sb.table('signals').select('*').in_('symbol', ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'EUR/USD', 'GBP/USD', 'USD/JPY', 'XAU/USD']).gte('created_at', cutoff).execute()
    df_s = pd.DataFrame(res_s.data)
    print(f"\nTotal signals for Forex in last 14d: {len(df_s)}")
    if not df_s.empty:
        print(df_s.groupby(['symbol', 'strategy']).size())

inspect_forex()
