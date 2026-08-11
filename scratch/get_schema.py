import os
from dotenv import load_dotenv
import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL').replace('https://', '').replace('.supabase.co', '')
pwd = 'Jhon18213546'
conn_str = f'postgresql://postgres.{url}:{pwd}@aws-1-us-west-2.pooler.supabase.com:6543/postgres'

try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM paper_trades WHERE symbol LIKE '%USDT%';")
    print('paper_trades crypto count:', cur.fetchone()[0])
    
    cur.execute("SELECT COUNT(*) FROM trades_active WHERE symbol LIKE '%USDT%';")
    print('trades_active crypto count:', cur.fetchone()[0])
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
