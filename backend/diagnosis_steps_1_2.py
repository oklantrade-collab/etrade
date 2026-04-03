import os
from dotenv import load_dotenv
from supabase import create_client
import json

load_dotenv('c:/Fuentes/eTrade/backend/.env')

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

def run_query(step_name, query_description, table_name, select_cols, filters=None, order_by=None, limit=None):
    print(f"\n--- {step_name}: {query_description} ---")
    query = supabase.table(table_name).select(select_cols)
    if filters:
        for f in filters:
            if f[1] == 'ilike':
                query = query.ilike(f[0], f[2])
            elif f[1] == 'gte':
                query = query.gte(f[0], f[2])
            elif f[1] == 'eq':
                query = query.eq(f[0], f[2])
    if order_by:
        query = query.order(order_by, desc=True)
    if limit:
        query = query.limit(limit)
    
    result = query.execute()
    if hasattr(result, 'data'):
        print(json.dumps(result.data, indent=2))
    else:
        print(result)

# PASO 1: Ver los logs del scheduler para ETH y SOL
run_query(
    "PASO 1", 
    "Logs del scheduler para ETH/SOL/Error", 
    "system_logs", 
    "message, context, created_at",
    filters=[
        ('module', 'eq', 'SCHEDULER'),
        ('created_at', 'gte', '2026-03-20T19:00:00+00:00')
    ],
    order_by='created_at',
    limit=20
)

# PASO 2: Verificar si el símbolo se guarda correctamente en market_snapshot
run_query(
    "PASO 2a",
    "Símbolos en market_snapshot",
    "market_snapshot",
    "symbol",
    order_by='symbol'
)

run_query(
    "PASO 2b",
    "Símbolos en positions (status=open)",
    "positions",
    "symbol",
    filters=[('status', 'eq', 'open')],
    order_by='symbol'
)
