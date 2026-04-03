import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

import psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute("ALTER TABLE pending_orders ADD COLUMN IF NOT EXISTS sizing_pct NUMERIC(4,2) DEFAULT 1.00;")
cur.execute("ALTER TABLE pending_orders ADD COLUMN IF NOT EXISTS timeframe VARCHAR(5) DEFAULT '4h';")
conn.commit()
cur.close()
conn.close()
print("PATCH APLICADO EXTOSAMENTE EN DB")
