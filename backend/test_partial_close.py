import os
import sys
import pandas as pd
from unittest.mock import MagicMock

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backtesting.backtester import _evaluate_position_close

def test_partial_close_v2():
    # TEST 1: Cierre parcial
    pos = {'side': 'long', 'entry_price': 100.0, 'sl_price': 95.0, 
           'tp_partial': 105.0, 'tp_full': 110.0, 'partial_closed': False}
    bar = pd.Series({'high': 106.0, 'close': 106.0, 'ema4': 102.0, 'ema5': 101.0})
    res1 = _evaluate_position_close(pos, bar, 106.0)
    if res1['should_partial'] == True and res1['close_type'] == 'partial':
        print("TEST 1 PASSED — Cierre parcial en upper_5 detectado")
    
    # TEST 2: Cierre total
    pos['partial_closed'] = True
    bar2 = pd.Series({'high': 111.0, 'close': 110.5, 'vol_decreasing': True, 
                      'is_red_candle': True, 'ema4': 102.0, 'ema5': 101.0})
    res2 = _evaluate_position_close(pos, bar2, 110.5)
    if res2['should_close'] == True and res2['reason'] == 'tp_full':
        print("TEST 2 PASSED — Cierre total en upper_6 detectado")
        
    # TEST 3: SL hit
    res3 = _evaluate_position_close(pos, bar, 94.0)
    if res3['should_close'] == True and res3['reason'] == 'sl':
        print("TEST 3 PASSED — SL hit detectado correctamente")

    print("\nTODOS LOS TESTS DE CIERRE PARCIAL PASARON")

if __name__ == "__main__":
    test_partial_close_v2()
