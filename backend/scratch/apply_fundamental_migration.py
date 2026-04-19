import os
import requests
from dotenv import load_dotenv

load_dotenv('.env')

sql_path = 'sql/add_fundamental_columns.sql'
sql = open(sql_path).read()
key = os.getenv('SUPABASE_SERVICE_KEY')
url = os.getenv('SUPABASE_URL')
headers = {
    'apikey': key,
    'Authorization': 'Bearer ' + key,
    'Content-Type': 'application/json'
}

raw_queries = [q.strip() for q in sql.split(';') if q.strip()]
for query in raw_queries:
    full_query = query + ';'
    print(f"Ejecutando: {full_query[:50]}...")
    res = requests.post(
        f"{url}/rest/v1/rpc/exec_sql", 
        json={'sql_query': full_query}, 
        headers=headers
    )
    print(f"Status: {res.status_code}, Body: {res.text}")
