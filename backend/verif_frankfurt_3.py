from app.core.supabase_client import get_supabase
from datetime import datetime, timedelta, timezone

def verification_3():
    sb = get_supabase()
    time_limit = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    
    res = sb.table('pilot_diagnostics')\
            .select('symbol, cycle_type, timestamp')\
            .gt('timestamp', time_limit)\
            .execute()
            
    data = res.data
    stats = {}
    for r in data:
        key = (r['symbol'], r['cycle_type'])
        if key not in stats:
            stats[key] = {'count': 0, 'latest': r['timestamp']}
        else:
            stats[key]['count'] += 1
            if r['timestamp'] > stats[key]['latest']:
                stats[key]['latest'] = r['timestamp']
                
    print(f"{'SYMBOL':<10} | {'CYCLE':<5} | {'COUNT':<5} | {'LATEST'}")
    print("-" * 50)
    for (sym, cyc), val in sorted(stats.items()):
        print(f"{sym:<10} | {cyc:<5} | {val['count']:<5} | {val['latest']}")

if __name__ == "__main__":
    verification_3()
