import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.position_sizing import (
    can_open_short,
    get_bearish_action
)

def run_tests():
    print("Iniciando tests de Market Type y Short logic...\n")

    # TEST 1 — Futures permite SHORT
    assert can_open_short('crypto_futures') == True
    assert can_open_short('forex_futures')  == True
    assert can_open_short('futures')        == True
    print("TEST 1 PASSED — Futures permite SHORT")

    # TEST 2 — Spot NO permite SHORT
    assert can_open_short('crypto_spot')    == False
    assert can_open_short('stocks_spot')    == False
    print("TEST 2 PASSED — Spot no permite SHORT")

    # TEST 3 — Spot con LONG abierto → cerrar LONG
    action = get_bearish_action(
        market_type   = 'crypto_spot',
        has_long_open = True
    )
    assert action == 'close_long'
    print("TEST 3 PASSED — Spot cierra LONG")

    # TEST 4 — Spot sin posición → no action
    action = get_bearish_action(
        market_type   = 'crypto_spot',
        has_long_open = False
    )
    assert action == 'no_action'
    print("TEST 4 PASSED — Spot sin posición: no action")

    # TEST 5 — Futures con señal bajista → SHORT
    action = get_bearish_action(
        market_type   = 'crypto_futures',
        has_long_open = False
    )
    assert action == 'open_short'
    print("TEST 5 PASSED — Futures abre SHORT")

    # TEST 6 — Futures con LONG abierto → SHORT igualmente
    # (En cobertura o porque el exchange permite hedge mode o simplemente abre short)
    action = get_bearish_action(
        market_type   = 'crypto_futures',
        has_long_open = True
    )
    assert action == 'open_short'
    print("TEST 6 PASSED — Futures abre SHORT aunque hay LONG")

    print("\n✅ TODOS LOS TESTS PASARON EXITOSAMENTE")

if __name__ == "__main__":
    run_tests()
