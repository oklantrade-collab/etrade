import asyncio
from supabase import create_client
import os
import json

supabase = create_client(
    os.getenv('SUPABASE_URL', 'https://dfrsccxkhicyhkprpsqt.supabase.co'),
    os.getenv('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw')
)

res = supabase.table('forex_positions').select('*').eq('status', 'open').execute()
for p in res.data:
    print(json.dumps(p, indent=2))
