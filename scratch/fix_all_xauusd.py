import asyncio
from app.core.supabase_client import get_supabase

async def fix():
    sb = get_supabase()
    # Fetch all closed XAUUSD positions
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').eq('status', 'closed').execute()
    for row in res.data:
        entry = row['entry_price']
        close = row['current_price']
        lots = row['lots']
        # If entry is somehow None, skip
        if not entry or not close or not lots: continue
        
        # Calculate correct PnL
        if str(row.get('side')).lower() in ['short', 'sell']:
            correct_pnl = round((entry - close) * lots, 4)
        else:
            correct_pnl = round((close - entry) * lots, 4)
            
        current_pnl = row.get('pnl_usd')
        
        # If the difference is significant (e.g. because of the bug where entry was considered 0)
        if current_pnl is not None and abs(current_pnl - correct_pnl) > 0.1:
            print(f'Fixing ID {row["id"]} from {current_pnl} to {correct_pnl} (Entry: {entry}, Close: {close})')
            sb.table('forex_positions').update({'pnl_usd': correct_pnl}).eq('id', row['id']).execute()

if __name__ == "__main__":
    asyncio.run(fix())
