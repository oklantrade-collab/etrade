from app.core.supabase_client import get_supabase

def check_trades():
    sb = get_supabase()
    res = sb.table('paper_trades').select('*').eq('rule_code', 'Aa23').order('created_at', desc=True).limit(5).execute()
    print("Recent trades for Aa23:")
    for row in res.data:
        print(f"ID={row['id']}, symbol={row['symbol']}, pnl_usd={row['total_pnl_usd']}, pnl_pct={row['total_pnl_pct']}, created_at={row['created_at']}, closed_at={row['closed_at']}, entry={row['entry_price']}, exit={row['exit_price']}")

if __name__ == '__main__':
    check_trades()
