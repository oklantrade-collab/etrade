import os
from supabase import create_client

url = "https://dfrsccxkhicyhkprpsqt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw"
sb = create_client(url, key)

print("\n--- PILOT DIAGNOSTICS ---")
res2 = sb.table("pilot_diagnostics").select("*").eq("symbol", "BTCUSDT").order("id", desc=True).limit(50).execute()
for r in res2.data:
    print(r.get('id'), r.get('symbol'), r.get('action'), r.get('reason'))
