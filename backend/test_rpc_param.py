from app.core.supabase_client import get_supabase
sb = get_supabase()
try:
    res = sb.rpc('exec_sql', {'sql_query': 'SELECT 1;'}).execute()
    print("✅ Success with sql_query!")
except Exception as e:
    print(f"❌ Error with sql_query: {e}")
