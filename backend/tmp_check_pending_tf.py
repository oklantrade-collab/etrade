from app.core.supabase_client import get_supabase
import asyncio

async def check_pending_timeframes():
    sb = get_supabase()
    res = sb.table('pending_orders').select('id, symbol, rule_code, timeframe, trade_type').eq('status', 'pending').execute()
    for o in res.data:
        print(f"ID: {o['id']}, Symbol: {o['symbol']}, Rule: {o['rule_code']}, Timeframe: {o['timeframe']}, TradeType: {o['trade_type']}")

if __name__ == "__main__":
    asyncio.run(check_pending_timeframes())
