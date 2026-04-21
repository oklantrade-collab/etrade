import os
import sys
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase

def to_ts(val):
    if not val: return 0
    if isinstance(val, str):
        try:
            base = val.replace('Z', '').split('.')[0].split('+')[0]
            if 'T' not in base: base = base.replace(' ', 'T')
            dt = datetime.strptime(base[:19], '%Y-%m-%dT%H:%M:%S')
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except Exception as e:
            print(f"Error in to_ts (str): {e}")
            return 0
    try: return int(val.timestamp())
    except: return 0

def test_events(symbol):
    sb = get_supabase()
    symbol_clean = symbol.replace('/', '')
    cutoff = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    
    events = []
    
    print(f"Fetching for {symbol_clean} from {cutoff}")
    # Forex
    try:
        forex_res = sb.table('forex_positions').select('side, opened_at, closed_at, entry_price, current_price, pnl_usd, rule_code, close_reason').eq('symbol', symbol_clean).gte('opened_at', cutoff).execute().data or []
        print(f"Found {len(forex_res)} forex positions")
        for t in forex_res:
            side = 'long' if str(t['side']).lower() in ['long', 'buy'] else 'short'
            events.append({
                'type': 'entry', 'direction': side, 'timestamp': to_ts(t.get('opened_at')),
                'price': float(t['entry_price'] or 0), 'rule_code': t['rule_code']
            })
    except Exception as e:
        print(f"Error in forex section: {e}")

    # Crypto
    try:
        crypto_res = sb.table('paper_trades').select('side, opened_at, closed_at, entry_price, exit_price, rule_code, close_reason').eq('symbol', symbol_clean).gte('opened_at', cutoff).execute().data or []
        print(f"Found {len(crypto_res)} crypto trades")
    except Exception as e:
        print(f"Error in crypto section: {e}")
        
    print(f"Total events: {len(events)}")
    if events:
        events.sort(key=lambda x: x['timestamp'])
    return events

if __name__ == "__main__":
    test_events('XAUUSD')
    test_events('USDJPY')
