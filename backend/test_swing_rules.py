from app.analysis.swing_detector import (
    detect_basis_horizontal,
    find_current_band_zone
)
import pandas as pd
import numpy as np

def crear_df_basis_plano(precio_base=68000):
    """BASIS prácticamente sin pendiente."""
    n = 30
    closes = np.random.normal(precio_base, 200, n)
    df = pd.DataFrame({
        'open':   closes * 0.999,
        'high':   closes * 1.002,
        'low':    closes * 0.998,
        'close':  closes,
        'volume': np.random.uniform(1000, 5000, n),
        'basis':  np.full(n, precio_base),  # PLANO
        'lower_3': np.full(n, precio_base * 0.985),
        'lower_4': np.full(n, precio_base * 0.975),
        'lower_5': np.full(n, precio_base * 0.965),
        'lower_6': np.full(n, precio_base * 0.955),
        'upper_3': np.full(n, precio_base * 1.015),
        'upper_4': np.full(n, precio_base * 1.025),
        'upper_5': np.full(n, precio_base * 1.035),
        'upper_6': np.full(n, precio_base * 1.045),
    })
    return df

def crear_df_basis_bajista(precio_base=68000):
    """BASIS con pendiente bajista."""
    n = 30
    basis_vals = np.linspace(
        precio_base, precio_base * 0.95, n
    )  # baja 5%
    closes = basis_vals + np.random.normal(0, 100, n)
    df = pd.DataFrame({
        'open':   closes * 0.999,
        'high':   closes * 1.002,
        'low':    closes * 0.998,
        'close':  closes,
        'volume': np.random.uniform(1000, 5000, n),
        'basis':  basis_vals,
        'lower_4': basis_vals * 0.975,
        'lower_5': basis_vals * 0.965,
        'lower_6': basis_vals * 0.955,
        'upper_4': basis_vals * 1.025,
    })
    return df

if __name__ == "__main__":
    # TEST 1 — BASIS plano → is_flat=True
    df_flat = crear_df_basis_plano()
    result  = detect_basis_horizontal(df_flat)
    assert result['is_flat']           == True
    assert result['direction']         == 'flat'
    print(f"TEST 1 PASSED — BASIS plano: "
          f"slope={result['slope_pct']}%")

    # TEST 2 — BASIS bajista → is_flat=False
    df_trend = crear_df_basis_bajista()
    result   = detect_basis_horizontal(df_trend)
    assert result['is_flat']   == False
    assert result['direction'] == 'down'
    print(f"TEST 2 PASSED — BASIS bajista: "
          f"slope={result['slope_pct']}%")

    # TEST 3 — Con BASIS plano y precio en lower_4
    #          → encuentra extremo
    df = crear_df_basis_plano(68000)
    # Simular que precio tocó lower_4 (68000*0.975=66300)
    df['low'] = df['low'].copy()
    df.iloc[-5, df.columns.get_loc('low')] = 66300
    df.iloc[-1, df.columns.get_loc('close')] = 66350

    band = find_current_band_zone(df, 'long')
    assert band is not None
    assert band['band_level'] >= 4
    print(f"TEST 3 PASSED — Extremo encontrado: "
          f"{band['band_name']} @ {band['band_value']}")

    # TEST 4 — Con BASIS bajista → NO crear Swing
    #          (el proceso principal retorna sin crear)
    df_trend = crear_df_basis_bajista()
    result   = detect_basis_horizontal(df_trend)
    assert not result['is_flat']
    print("TEST 4 PASSED — BASIS bajista no genera Swing")

    # TEST 5 — Con BASIS plano pero precio
    #          NO en extremo → no genera orden
    df_flat2 = crear_df_basis_plano(68000)
    # Precio en el centro, no en extremos
    df_flat2.iloc[-1, df_flat2.columns.get_loc('close')] \
        = 68000  # = basis, no extremo
    band = find_current_band_zone(df_flat2, 'long')
    # No debería encontrar lower_X cerca
    assert band is None or band['band_level'] > 6
    print("TEST 5 PASSED — Precio central no genera Swing")

    print("\nTODOS LOS TESTS PASARON ✅")
    print("Swing solo opera con BASIS HORIZONTAL")
