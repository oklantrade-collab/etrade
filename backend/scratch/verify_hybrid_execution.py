import sys
import os
import asyncio
sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase
from app.core.position_monitor import check_signal_reversal

async def test_hybrid():
    print("="*60)
    print("=== VERIFICATION OF HYBRID EXECUTION PLAN ===")
    print("="*60)
    
    # 1. Test Smart LIMIT calculation logic
    current_price = 0.1975
    side_long = 'long'
    side_short = 'short'
    
    limit_px_long = round(current_price * 0.9998, 4)
    limit_px_short = round(current_price * 1.0002, 4)
    
    print(f"1. ENTRADAS SMART LIMIT (Maker Fee 0.020%):")
    print(f"   LONG  ADAUSDT @ ${current_price} -> Order Limit @ ${limit_px_long:.4f} (Colocada en Bid)")
    print(f"   SHORT ADAUSDT @ ${current_price} -> Order Limit @ ${limit_px_short:.4f} (Colocada en Ask)")
    
    # 2. Test Emergency / Reversal Exit (MARKET URGENTE)
    dummy_pos_long = {'side': 'LONG', 'entry_price': 0.1900, 'symbol': 'ADAUSDT'}
    cfg = {'min_profit_exit_pct': 0.25, 'exit_on_signal_reversal': True}
    
    # Mock snap with EMA3 < EMA9 (reversal)
    mock_snap_reversal = {'ema_3': 0.1970, 'ema_9': 0.1975}
    res = await check_signal_reversal(dummy_pos_long, 0.5, 0.1975, cfg, snap=mock_snap_reversal)
    
    print(f"\n2. CIERRE POR REVERSIÓN EN CONTRA (EMA3 < EMA9):")
    print(f"   ¿Gatilla salida? {res.get('should_exit')}")
    print(f"   Tipo de ejecución: {res.get('exit_execution_type')}")
    print(f"   Detalle: {res.get('detail')}")

if __name__ == "__main__":
    asyncio.run(test_hybrid())
