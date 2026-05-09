import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def generate_report():
    sb = get_supabase()
    
    # Forex
    forex_res = sb.table('forex_positions').select('pnl_usd').eq('status', 'closed').execute()
    total_forex_pnl = sum(float(p['pnl_usd'] or 0) for p in (forex_res.data or []))
    
    # Crypto
    crypto_res = sb.table('paper_trades').select('total_pnl_usd').not_.is_('closed_at', 'null').execute()
    total_crypto_pnl = sum(float(p['total_pnl_usd'] or 0) for p in (crypto_res.data or []))
    
    # Stocks
    stocks_res = sb.table('stocks_positions').select('unrealized_pnl').eq('status', 'closed').execute()
    total_stocks_pnl = sum(float(p.get('unrealized_pnl') or 0) for p in (stocks_res.data or []))
    
    print(f"REPORT_DATA:")
    print(f"FOREX_PNL: {total_forex_pnl:.2f}")
    print(f"CRYPTO_PNL: {total_crypto_pnl:.2f}")
    print(f"STOCKS_PNL: {total_stocks_pnl:.2f}")

    # Check config for models
    try:
        cfg = sb.table('trading_config').select('*').eq('id', 1).single().execute()
        print(f"CONFIG: {cfg.data}")
    except:
        pass

if __name__ == "__main__":
    asyncio.run(generate_report())
