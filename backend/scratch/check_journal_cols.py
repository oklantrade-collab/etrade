from app.core.supabase_client import get_supabase
import logging

def check():
    try:
        sb = get_supabase()
        res = sb.table('trades_journal').select('*').limit(1).execute()
        if res.data:
            print(f"Columns in trades_journal: {list(res.data[0].keys())}")
        else:
            # If no data, try to get columns from schema
            print("No data in trades_journal, cannot determine columns from data.")
    except Exception as e:
        print(f"Error checking columns: {e}")

if __name__ == "__main__":
    check()
