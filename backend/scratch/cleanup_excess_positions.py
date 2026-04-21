from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

sb = get_supabase()
symbol = 'XAUUSD'
limit = 4

res = sb.table('forex_positions').select('*').eq('symbol', symbol).eq('status', 'open').order('opened_at', desc=False).execute()
positions = res.data or []

print(f"Total open for {symbol}: {len(positions)}")

if len(positions) > limit:
    to_close = positions[limit:]
    print(f"Closing {len(to_close)} excess positions...")
    for p in to_close:
        sb.table('forex_positions').update({
            'status': 'closed',
            'close_reason': 'excess_limit_cleanup',
            'closed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', p['id']).execute()
        print(f"Closed ID: {p['id']} - Rule: {p['rule_code']}")
else:
    print("No excess positions found.")
