import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def update_price_limit():
    sb = get_supabase()
    print("Updating max_stock_price config in Supabase to 100...")
    try:
        res = sb.table('stocks_config')\
            .update({'value': '100'})\
            .eq('key', 'max_stock_price')\
            .execute()
        
        print("Success! Response from Supabase:")
        print(res.data)
    except Exception as e:
        print(f"Error updating config: {e}")

if __name__ == "__main__":
    update_price_limit()
