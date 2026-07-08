import sys
import os
import pandas as pd

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.analysis.fibonacci_bb import extract_fib_levels
from app.core.position_monitor import _execute_paper_open_unlocked
from app.strategy.strategy_engine import StrategyEngine
from app.core.supabase_client import get_supabase
import asyncio

async def test_all():
    sb = get_supabase()
    
    # 1. Test extract_fib_levels copies ATR
    print("--- Testing ATR Propagation in extract_fib_levels ---")
    dummy_df = pd.DataFrame([{
        'basis': 50000.0,
        'close': 50000.0,
        'atr': 150.0,
        **{f"upper_{i}": 50000.0 + i*100 for i in range(1, 7)},
        **{f"lower_{i}": 50000.0 - i*100 for i in range(1, 7)}
    }])
    
    levels = extract_fib_levels(dummy_df)
    print("Extracted Levels dict:", levels)
    assert 'atr' in levels, "ATR was not copied to levels!"
    assert levels['atr'] == 150.0, f"Expected ATR 150.0, got {levels['atr']}"
    print("✅ ATR Propagation Test Passed!")
    
    # 2. Test Stop Loss capping in _execute_paper_open_unlocked
    print("\n--- Testing Stop Loss Capping ---")
    engine = StrategyEngine.get_instance(sb)
    await engine.load()
    
    # Bb30 is a scalp rule, max SL should be capped at 1.0%
    # With entry 58569.7, 1.0% SL is 59155.397 for SHORT
    vel_config = {
        'tp_band': 'lower_6',
        'sl_mult': 2.5,
        'velocity': 'moderado'
    }
    
    # We pass levels with a huge ATR of 2000 (which would normally lead to a >5% SL)
    large_atr_levels = levels.copy()
    large_atr_levels['atr'] = 2000.0
    large_atr_levels['upper_6'] = 60000.0
    
    # Open a SHORT paper position for Bb30
    # Entry price: 58569.7
    res = await _execute_paper_open_unlocked(
        symbol="BTCUSDT",
        side="short",
        price=58569.7,
        size=0.008,
        rule_code="Bb30",
        regime={'category': 'riesgo_medio'},
        levels=large_atr_levels,
        vel_config=vel_config,
        supabase=sb
    )
    
    print("Apertura de posición result:", res)
    if res:
        # Check Stop Loss in database
        pos_id = res.get('id') if isinstance(res, dict) else None
        if pos_id:
            db_pos = sb.table('positions').select('*').eq('id', pos_id).single().execute()
            p = db_pos.data
            print("Posición guardada en DB:", p)
            sl = float(p['stop_loss'])
            entry = float(p['entry_price'])
            sl_pct = (sl - entry) / entry * 100
            print(f"SL: {sl}, Entry: {entry}, SL %: {sl_pct:.2f}%")
            
            # Since Bb30 is a scalp, SL must be exactly capped at 1.0%
            # Entry 58569.7 -> SL capped at 58569.7 * 1.01 = 59155.397
            assert abs(sl_pct - 1.0) < 0.05, f"SL % is {sl_pct}%, not capped at 1.0%!"
            print("✅ Stop Loss Capping Test Passed!")
            
            # Clean up test position
            sb.table('positions').delete().eq('id', pos_id).execute()
            print("Cleaned up test position.")

if __name__ == "__main__":
    asyncio.run(test_all())
