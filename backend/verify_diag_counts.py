import asyncio
from app.core.supabase_client import get_supabase

async def check_diagnostics():
    sb = get_supabase()
    # Query: count per cycle_type in last 30m
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    
    res = sb.table("pilot_diagnostics")\
        .select("cycle_type, timestamp")\
        .gte("timestamp", cutoff)\
        .execute()
    
    if res.data:
        counts = {}
        for row in res.data:
            ct = row['cycle_type']
            counts[ct] = counts.get(ct, 0) + 1
        
        print("Cycle counts in last 30m:")
        for ct, count in counts.items():
            print(f"  {ct}: {count}")
            
        # Get min/max
        ts = [r['timestamp'] for r in res.data]
        print(f"First cycle: {min(ts)}")
        print(f"Last cycle: {max(ts)}")
    else:
        print("No diagnostic records found in the last 30 minutes.")

if __name__ == "__main__":
    asyncio.run(check_diagnostics())
