"""
Test completo de la regla de Confirmación de Estructura de Mercado.
Ejecutar: python test_structure_4h.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.analysis.parabolic_sar import analyze_structure
from app.core.config import STRUCTURE_CONFIG
import pandas as pd

cfg = STRUCTURE_CONFIG


def make_test_df(highs, lows, sar_trends):
    df = pd.DataFrame({
        'high':      highs,
        'low':       lows,
        'sar_trend': sar_trends,
        'close':     [(h+l)/2 for h, l in zip(highs, lows)],
        'open':      [(h+l)/2 for h, l in zip(highs, lows)],
    })
    return df


# TEST 1 — SAR+ 2 Higher Lows → LONG confirmado
df = make_test_df(
    highs      = [74000, 75000, 76000],
    lows       = [70000, 70300, 70600],
    sar_trends = [1, 1, 1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']   == 'confirmed', f"Expected 'confirmed', got '{r['structure']}'"
assert r['allow_long']  == True
assert r['allow_short'] == False
print("TEST 1 PASSED — 2 Higher Lows: LONG ✅")


# TEST 2 — SAR+ 2 Lower Lows → SHORT autorizado
df = make_test_df(
    highs      = [74000, 73500, 73000],
    lows       = [70000, 69700, 69390],
    sar_trends = [1, 1, 1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']       == 'weakened', f"Expected 'weakened', got '{r['structure']}'"
assert r['allow_short']     == True
assert r['reverse_signal']  == True
print("TEST 2 PASSED — 2 Lower Lows: SHORT ✅")


# TEST 3 — SAR+ 1 Lower Low (umbral no cumple) → NO es estructura debilitada
df = make_test_df(
    highs      = [74000, 73500, 73000],
    lows       = [70000, 69999, 69990],  # cambio < 0.3%
    sar_trends = [1, 1, 1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure'] != 'weakened', f"Expected NOT 'weakened', got '{r['structure']}'"
print("TEST 3 PASSED — Cambio < 0.3%: ignorado ✅")


# TEST 4 — SAR- 2 Lower Highs → SHORT confirmado
df = make_test_df(
    highs      = [73000, 72700, 72390],
    lows       = [68000, 67500, 67000],
    sar_trends = [-1, -1, -1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']   == 'confirmed', f"Expected 'confirmed', got '{r['structure']}'"
assert r['allow_short'] == True
assert r['allow_long']  == False
print("TEST 4 PASSED — 2 Lower Highs: SHORT ✅")


# TEST 5 — SAR- 2 Higher Highs → LONG autorizado
df = make_test_df(
    highs      = [72000, 72300, 72610],
    lows       = [68000, 68200, 68400],
    sar_trends = [-1, -1, -1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']       == 'weakened', f"Expected 'weakened', got '{r['structure']}'"
assert r['allow_long']      == True
assert r['reverse_signal']  == True
print("TEST 5 PASSED — 2 Higher Highs: LONG ✅")


# TEST 6 — Datos insuficientes
df = make_test_df(
    highs      = [74000],
    lows       = [70000],
    sar_trends = [1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure'] == 'unknown'
print("TEST 6 PASSED — Datos insuficientes: unknown ✅")


# TEST 7 — SAR neutral
df = make_test_df(
    highs      = [74000, 74500, 75000],
    lows       = [70000, 70300, 70600],
    sar_trends = [0, 0, 0]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']   == 'neutral'
assert r['allow_long']  == True
assert r['allow_short'] == True
print("TEST 7 PASSED — SAR neutral: sin restricción ✅")


# TEST 8 — SAR+ sin confirmación clara → neutral (mantener LONG)
df = make_test_df(
    highs      = [74000, 74100, 74200],
    lows       = [70000, 70050, 70100],  # cambio < 0.3%, no higher_lows ni lower_lows
    sar_trends = [1, 1, 1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']   == 'neutral'
assert r['allow_long']  == True
assert r['allow_short'] == False  # SAR+ neutral → solo LONG
print("TEST 8 PASSED — SAR+ sin confirmación: neutral LONG ✅")


# TEST 9 — SAR- sin confirmación clara → neutral (mantener SHORT)
df = make_test_df(
    highs      = [73000, 72990, 72980],  # cambio < 0.3%, no lower_highs ni higher_highs
    lows       = [68000, 67990, 67980],
    sar_trends = [-1, -1, -1]
)
r = analyze_structure(
    df, n_confirm=2,
    umbral_low=0.003, umbral_high=0.003
)
assert r['structure']   == 'neutral'
assert r['allow_long']  == False  # SAR- neutral → solo SHORT
assert r['allow_short'] == True
print("TEST 9 PASSED — SAR- sin confirmación: neutral SHORT ✅")


# TEST 10 — Verificar que STRUCTURE_CONFIG existe correctamente
assert cfg['umbral_lower_low']   == 0.003
assert cfg['umbral_higher_high'] == 0.003
assert cfg['velas_confirmacion'] == 2
assert cfg['require_profit_to_reverse'] == True
assert cfg['structure_ref']['5m']  == '15m'
assert cfg['structure_ref']['15m'] == '4h'
print("TEST 10 PASSED — STRUCTURE_CONFIG correctamente definido ✅")


# TEST con datos REALES (intenta cargar, si no disponible, skip)
print("\n--- DATOS REALES ---")
try:
    from app.core.memory_store import MEMORY_STORE
    from app.analysis.parabolic_sar import calculate_parabolic_sar

    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']:
        for tf in ['15m', '4h']:
            mem = MEMORY_STORE.get(symbol, {}).get(tf, {})
            df_real = mem.get('df')
            if df_real is not None and not df_real.empty:
                df_real = calculate_parabolic_sar(df_real.copy())
                r = analyze_structure(
                    df_real,
                    n_confirm  = cfg['velas_confirmacion'],
                    umbral_low = cfg['umbral_lower_low'],
                    umbral_high= cfg['umbral_higher_high']
                )
                emoji = (
                    '✅' if r['structure'] == 'confirmed'
                    else '⚠️' if r['structure'] == 'weakened'
                    else '➖'
                )
                print(
                    f"{symbol}/{tf}: {emoji} "
                    f"{r['structure']:10} | "
                    f"LONG={r['allow_long']} "
                    f"SHORT={r['allow_short']} | "
                    f"{r['reason'][:60]}"
                )
            else:
                print(f"{symbol}/{tf}: (no data in MEMORY_STORE)")
except Exception as e:
    print(f"(Real data test skipped: {e})")


print("\n" + "="*50)
print("TODOS LOS TESTS PASARON ✅")
print("="*50)
