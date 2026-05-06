import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from app.core.crypto_symbols import crypto_symbol_match_variants

async def test_limit_query():
    sb = get_supabase()
    symbol = "ADAUSDT"
    variants = crypto_symbol_match_variants(symbol)
    print(f"Testing for {symbol}, variants={variants}")
    try:
        res = sb.table('positions').select('id, rule_code, opened_at', count='exact').in_('symbol', variants).eq('status', 'open').execute()
        print(f"Count from res.count: {res.count}")
        print(f"Length of res.data: {len(res.data)}")
        for r in res.data:
            print(f"  {r}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_limit_query())
