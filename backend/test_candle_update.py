import pandas as pd
import numpy as np
import os
import sys

# Add backend to sys path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.memory_store import (
    MEMORY_STORE,
    update_current_candle_close
)

def test_candle_update():
    # Simular DataFrame de 4h en memoria para BTC
    symbol = 'BTCUSDT'
    MEMORY_STORE[symbol] = {}
    MEMORY_STORE[symbol]['4h'] = {}

    # Crear vela en curso con precio de hace 4h
    df = pd.DataFrame([{
        'open':   70000.0,
        'high':   71000.0,
        'low':    69500.0,
        'close':  70500.0,  # precio de hace 4h
        'volume': 1000.0,
        'hlc3':   (71000 + 69500 + 70500) / 3
    }])
    MEMORY_STORE[symbol]['4h']['df'] = df

    print(f"ANTES — close 4h: ${df.iloc[-1]['close']:,.2f}")
    print(f"ANTES — high 4h:  ${df.iloc[-1]['high']:,.2f}")
    print(f"ANTES — hlc3 4h:  ${df.iloc[-1]['hlc3']:,.2f}")

    # Simular que el precio subió a $71,200
    update_current_candle_close(
        symbol        = 'BTCUSDT',
        current_price = 71200.0
    )

    df_updated = MEMORY_STORE[symbol]['4h']['df']
    print(f"\nDESPUÉS — close 4h: ${df_updated.iloc[-1]['close']:,.2f}")
    print(f"DESPUÉS — high 4h:  ${df_updated.iloc[-1]['high']:,.2f}")
    print(f"DESPUÉS — hlc3 4h:  ${df_updated.iloc[-1]['hlc3']:,.2f}")

    # Verificaciones
    assert df_updated.iloc[-1]['close'] == 71200.0, "FALLO: close no se actualizó"
    assert df_updated.iloc[-1]['high']  == 71200.0, "FALLO: high no se actualizó (71200 > 71000)"
    assert df_updated.iloc[-1]['low']   == 69500.0, "FALLO: low cambió cuando no debía"

    expected_hlc3 = (71200 + 69500 + 71200) / 3
    assert abs(df_updated.iloc[-1]['hlc3'] - expected_hlc3) < 0.01, "FALLO: hlc3 incorrecto"

    print("\nTEST PASSED — vela actualizada correctamente")
    print(f"hlc3 correcto: ${expected_hlc3:,.2f}")

    # Test 2: precio baja (no debe cambiar high)
    update_current_candle_close(
        symbol        = 'BTCUSDT',
        current_price = 69800.0
    )
    df_updated2 = MEMORY_STORE[symbol]['4h']['df']
    assert df_updated2.iloc[-1]['high'] == 71200.0, "FALLO: high cambió al bajar el precio"
    assert df_updated2.iloc[-1]['low']  == 69500.0, "FALLO: low cambió cuando no debía"
    assert df_updated2.iloc[-1]['close'] == 69800.0, "FALLO: close no se actualizó"

    print("TEST 2 PASSED — high no cambia al bajar")
    print("\nTODOS LOS TESTS PASARON")

if __name__ == "__main__":
    test_candle_update()
