from app.core.supabase_client import get_supabase

def print_dict():
    sb = get_supabase()
    res = sb.table('paper_trades').select('*').eq('rule_code', 'Aa23').order('created_at', desc=True).limit(1).execute()
    if res.data:
        row = res.data[0]
        for k, v in row.items():
            print(f"{k}: {v}")

if __name__ == '__main__':
    print_dict()
