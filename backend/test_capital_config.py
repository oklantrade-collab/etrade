import os
import sys
import asyncio
from dotenv import load_dotenv
from supabase import create_client

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'),
                   os.getenv('SUPABASE_SERVICE_KEY'))

async def test_capital():
    from app.backtesting.backtester import get_capital_config_from_db
    
    cfg = await get_capital_config_from_db(sb)
    
    print(f"capital_total:  ${cfg['capital_total']:,.2f}")
    print(f"capital_op:     ${cfg['capital_op']:,.2f}")
    print(f"capital_t1:     ${cfg['capital_t1']:,.2f}")
    print(f"t1_pct:         {int(cfg['t1_pct']*100)}%")
    print(f"pct_trading:    {int(cfg['pct_trading']*100)}%")
    
    # Formula: total * pct_trading * buffer (0.90) * t1_pct
    expected_t1 = cfg['capital_total'] * cfg['pct_trading'] * 0.90 * cfg['t1_pct']
    
    is_ok = abs(cfg['capital_t1'] - expected_t1) < 0.1
    print(f"\nVerificacion de formula: {'OK' if is_ok else 'ERROR'}")
    print(f"Ejemplo: ${cfg['capital_total']:,.0f} × {int(cfg['pct_trading']*100)}% × 90% × {int(cfg['t1_pct']*100)}% = ${expected_t1:,.2f}")

if __name__ == "__main__":
    asyncio.run(test_capital())
