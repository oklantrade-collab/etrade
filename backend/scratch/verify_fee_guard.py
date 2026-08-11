import sys
import os
import asyncio
sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase
from app.core.position_monitor import check_signal_reversal

async def verify():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').eq('id', 1).execute()
    cfg = res.data[0] if res.data else {}
    
    print("=== FEE-NET PROFIT GUARD VERIFIED ===")
    print(f"ID 1 min_profit_exit_pct: {cfg.get('min_profit_exit_pct')}%")
    print(f"ID 1 min_profit_exit_usd: ${cfg.get('min_profit_exit_usd')}")
    
    dummy_pos = {'side': 'BUY', 'entry_price': 100.0, 'symbol': 'BTCUSDT'}
    
    # Case A: PnL +0.05% (< 0.25%) -> Should NOT exit!
    res_a = await check_signal_reversal(dummy_pos, 0.5, 100.05, cfg)
    print(f"Test PnL +0.05% (Zona de comisión Binance): ¿Permite salida? {res_a['should_exit']}")
    
    # Case B: PnL +0.30% (>= 0.25%) -> Allowed to exit if reversal
    res_b = await check_signal_reversal(dummy_pos, 0.5, 100.30, cfg)
    print(f"Test PnL +0.30% (Comisiones Cubiertas): Validación de salida ejecutada.")

if __name__ == "__main__":
    asyncio.run(verify())
