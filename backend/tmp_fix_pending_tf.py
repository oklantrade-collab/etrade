from app.core.supabase_client import get_supabase
import asyncio

async def fix_pending_timeframes():
    sb = get_supabase()
    # Buscar pending_orders con timeframe 'TRAP'
    res = sb.table('pending_orders').select('id, created_at').eq('timeframe', 'TRAP').execute()
    print(f"Found {len(res.data)} pending orders with 'TRAP' timeframe")
    
    for o in res.data:
        # Por ahora asumimos 15m para los TRAP segun los ultimos logs
        sb.table('pending_orders').update({'timeframe': '15m'}).eq('id', o['id']).execute()
        print(f"Fixed PendingOrder {o['id']} to 15m")

if __name__ == "__main__":
    asyncio.run(fix_pending_timeframes())
