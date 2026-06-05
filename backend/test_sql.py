import os
import sys
from dotenv import load_dotenv

load_dotenv()
from supabase import create_client, Client, ClientOptions

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

options = ClientOptions(postgrest_client_timeout=60)
sb = create_client(url, key, options=options)

sql = """
ALTER TABLE positions
ADD COLUMN IF NOT EXISTS entry_band VARCHAR(20),
ADD COLUMN IF NOT EXISTS entry_band_price NUMERIC,
ADD COLUMN IF NOT EXISTS highest_band_reached VARCHAR(20),
ADD COLUMN IF NOT EXISTS profit_floor_band VARCHAR(20),
ADD COLUMN IF NOT EXISTS profit_floor_price NUMERIC,
ADD COLUMN IF NOT EXISTS basis_crossed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS basis_crossed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS ema3_below_ema9_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS flip_pending BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS exit_triggered_by VARCHAR(50);

ALTER TABLE forex_positions
ADD COLUMN IF NOT EXISTS entry_band VARCHAR(20),
ADD COLUMN IF NOT EXISTS entry_band_price NUMERIC,
ADD COLUMN IF NOT EXISTS highest_band_reached VARCHAR(20),
ADD COLUMN IF NOT EXISTS profit_floor_band VARCHAR(20),
ADD COLUMN IF NOT EXISTS profit_floor_price NUMERIC,
ADD COLUMN IF NOT EXISTS basis_crossed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS basis_crossed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS ema3_below_ema9_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS flip_pending BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS exit_triggered_by VARCHAR(50);

ALTER TABLE stocks_positions
ADD COLUMN IF NOT EXISTS entry_band VARCHAR(20),
ADD COLUMN IF NOT EXISTS entry_band_price NUMERIC,
ADD COLUMN IF NOT EXISTS highest_band_reached VARCHAR(20),
ADD COLUMN IF NOT EXISTS profit_floor_band VARCHAR(20),
ADD COLUMN IF NOT EXISTS profit_floor_price NUMERIC,
ADD COLUMN IF NOT EXISTS basis_crossed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS basis_crossed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS ema3_below_ema9_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS exit_triggered_by VARCHAR(50);
"""

# Try to use rpc exec_sql if exists
try:
    res = sb.rpc('exec_sql', {'query': sql}).execute()
    print("Success:", res)
except Exception as e:
    print("Error:", e)
