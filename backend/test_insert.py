import traceback
from app.core.supabase_client import get_supabase

def test_insert():
    sb = get_supabase()
    row = {
        'ticker': 'TESTDUMMY',
        'fib_level': 'undefined',
        'mtf_confirmed': False,
        'technical_score': 0,
        'signals_json': {}
    }
    try:
        sb.table('technical_scores').insert(row).execute()
        print('INSERT SUCCESS')
    except Exception as e:
        print(f"INSERT ERROR: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    test_insert()
