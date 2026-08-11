import asyncio
from app.core.supabase_client import get_supabase
from datetime import datetime, timezone, timedelta
import pytz

async def check():
    sb = get_supabase()
    lima_tz = pytz.timezone('America/Lima')
    now_lima = datetime.now(lima_tz)
    month_lima = now_lima.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = month_lima.astimezone(timezone.utc)
    start_date_filter = month_start_utc.isoformat()
    
    # Sin limit explícito
    res1 = sb.table('positions').select('id', count='exact').eq('status', 'closed').gte('closed_at', start_date_filter).execute()
    print("Total exact count for month:", res1.count)
    
    res2 = sb.table('positions').select('id').eq('status', 'closed').gte('closed_at', start_date_filter).execute()
    print("Rows returned without limit:", len(res2.data))
    
    res3 = sb.table('positions').select('id').eq('status', 'closed').gte('closed_at', start_date_filter).limit(5000).execute()
    print("Rows returned with limit(5000):", len(res3.data))

if __name__ == '__main__':
    asyncio.run(check())
