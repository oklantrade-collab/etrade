import os
import sys
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

res_crypto = sb.table('positions').select('id, symbol, side, entry_price, current_price, realized_pnl, close_reason, closed_at').eq('status', 'closed').ilike('close_reason', 'profit_capture_%').lt('realized_pnl', 0).execute()
res_forex = sb.table('forex_positions').select('id, symbol, side, entry_price, current_price, pnl_usd, close_reason, closed_at').eq('status', 'closed').ilike('close_reason', 'profit_capture_%').lt('pnl_usd', 0).execute()

crypto_cases = res_crypto.data if res_crypto.data else []
forex_cases = res_forex.data if res_forex.data else []

total = len(crypto_cases) + len(forex_cases)
print(f'TOTAL CASES: {total}')
for c in crypto_cases:
    print(f"Crypto: {c['symbol']} ({c['side']}) | PnL: {c['realized_pnl']} | Reason: {c['close_reason']} | Date: {c['closed_at']}")
for c in forex_cases:
    print(f"Forex: {c['symbol']} ({c['side']}) | PnL: {c['pnl_usd']} | Reason: {c['close_reason']} | Date: {c['closed_at']}")
