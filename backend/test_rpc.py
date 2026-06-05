import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def test():
    sb = get_supabase()
    
    # Try different RPC names and parameter names
    options = [
        ('exec_sql', 'sql_query'),
        ('exec_sql', 'query'),
        ('exec_sql', 'sql'),
        ('exec_sql', 'query_text'),
        ('exec_sql', 'sql_text'),
        ('exec_sql_return', 'sql_query'),
        ('exec_sql_return', 'query'),
        ('execute_sql', 'sql'),
        ('run_sql', 'sql'),
        ('query_db', 'query')
    ]
    
    for rpc_name, param_name in options:
        try:
            print(f"Trying rpc('{rpc_name}', {{{param_name}: 'SELECT 1;'}})...")
            res = sb.rpc(rpc_name, {param_name: 'SELECT 1;'}).execute()
            print(f"  SUCCESS! Result: {res.data}")
            return rpc_name, param_name
        except Exception as e:
            print(f"  Failed: {e}")
            
    print("\nAll options failed.")
    return None

if __name__ == "__main__":
    test()
