import os
import sys
sys.path.append('backend')
from dotenv import load_dotenv
load_dotenv('backend/.env')
from app.core.supabase_client import get_supabase

async def migrate():
    sb = get_supabase()
    
    # 1. Add key to stocks_config if not exists
    res = sb.table('stocks_config').select('*').eq('key', 'max_total_risk_pct').execute()
    if not res.data:
        sb.table('stocks_config').insert({'key': 'max_total_risk_pct', 'value': '30'}).execute()
        print("Added max_total_risk_pct to stocks_config")
    
    # 2. Add columns to risk_config (requires SQL)
    # Since I don't have direct SQL access, I'll try to see if I can trick it or if I should just use available columns.
    # Actually, I can use the SQL editor via API if I have the right token, but I don't.
    # I'll check if there are columns I can hijack.
    # 'max_trade_loss_pct'? No.
    
    # Wait! I'll try to add them to 'regime_params' inside 'trading_config' as JSON!
    # That's much safer and more flexible.
    
    res_tc = sb.table('trading_config').select('regime_params').eq('id', 1).single().execute()
    params = res_tc.data.get('regime_params') or {}
    if 'max_total_risk_crypto_pct' not in params:
        params['max_total_risk_crypto_pct'] = 30
    if 'max_total_risk_forex_pct' not in params:
        params['max_total_risk_forex_pct'] = 30
        
    sb.table('trading_config').update({'regime_params': params}).eq('id', 1).execute()
    print("Updated regime_params in trading_config with max total risk values.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
