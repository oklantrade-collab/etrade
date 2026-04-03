from app.strategy.rule_engine import (
    evaluate_cc21_long_scalp,
    evaluate_cc11_short_scalp
)

def run_tests():
    # TEST 1 — Cc21 se activa correctamente
    result = evaluate_cc21_long_scalp(
        df     = None,
        snap   = {
            'sar_trend_4h':     1,
            'sar_ini_high_15m': True,
        },
        signal = 'Buy'
    )
    assert result['triggered'] == True, f"Failed Result: {result}"
    assert result['rule_code'] == 'Cc21'
    print("TEST 1 PASSED - Cc21 activa")

    # TEST 2 — Cc21 NO se activa sin señal Buy
    result = evaluate_cc21_long_scalp(
        df     = None,
        snap   = {
            'sar_trend_4h':     1,
            'sar_ini_high_15m': True,
        },
        signal = ''  # sin señal
    )
    assert result['triggered'] == False, f"Failed Result: {result}"
    print("TEST 2 PASSED - Cc21 sin señal no activa")

    # TEST 3 — Cc21 NO se activa si SAR 4h SHORT
    result = evaluate_cc21_long_scalp(
        df     = None,
        snap   = {
            'sar_trend_4h':     -1,  # SHORT
            'sar_ini_high_15m': True,
        },
        signal = 'Buy'
    )
    assert result['triggered'] == False, f"Failed Result: {result}"
    print("TEST 3 PASSED - Cc21 bloqueada por SAR 4h")

    # TEST 4 — Cc11 SHORT se activa
    result = evaluate_cc11_short_scalp(
        df     = None,
        snap   = {
            'sar_trend_4h':    -1,
            'sar_ini_low_15m': True,
        },
        signal = 'Sell'
    )
    assert result['triggered'] == True, f"Failed Result: {result}"
    assert result['rule_code'] == 'Cc11'
    print("TEST 4 PASSED - Cc11 activa")

    # TEST 5 — SAR 15m NO acaba de cambiar
    result = evaluate_cc21_long_scalp(
        df     = None,
        snap   = {
            'sar_trend_4h':     1,
            'sar_ini_high_15m': False,  # no cambió
        },
        signal = 'Buy'
    )
    assert result['triggered'] == False, f"Failed Result: {result}"
    print("TEST 5 PASSED - Sin cambio de SAR 15m no activa")

    print("\nTODOS LOS TESTS PASARON")
    print("Reglas Cc listas para producción")

if __name__ == "__main__":
    run_tests()
