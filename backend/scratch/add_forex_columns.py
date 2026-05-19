import os
import sys
from dotenv import load_dotenv
load_dotenv()
from app.core.supabase_client import get_supabase
sb = get_supabase()
queries = [
    "ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS highest_price NUMERIC;",
    "ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS lowest_price NUMERIC;"
]
for query in queries:
    try:
        res = sb.rpc('exec_sql', {'query_text': query}).execute()
        print(f"SUCCESS: {query} -> {res.data}")
    except Exception as e:
        print(f"ERROR for {query}: {e}")
