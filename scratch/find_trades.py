import asyncio
from app.core.supabase_client import get_supabase

async def find_trades():
    sb = get_supabase()
    print('--- FOREX POSITIONS ---')
    res = sb.table('forex_positions').select('*').in_('symbol', ['GBPUSD', 'EURUSD']).eq('status', 'closed').order('closed_at', desc=True).limit(10).execute()
    for row in res.data:
        print(f"{row['symbol']} | {row['side']} | {row['opened_at']} | {row['close_reason']} | PnL: {row.get('pnl_usd')} | ID: {row['id']}")

    print('\n--- PAPER TRADES ---')
    res_paper = sb.table('paper_trades').select('*').in_('symbol', ['GBPUSD', 'EURUSD']).order('closed_at', desc=True).limit(10).execute()
    for row in res_paper.data:
        print(f"{row['symbol']} | {row['side']} | {row['closed_at']} | {row['close_reason']} | PnL: {row.get('pnl_usd')} | ID: {row['id']}")

asyncio.run(find_trades())
