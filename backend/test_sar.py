import pandas as pd
import numpy as np
from app.analysis.parabolic_sar import (
    calculate_parabolic_sar
)

# Crear datos simulados con tendencia clara
# Período alcista luego bajista
np.random.seed(42)
n = 100

# Simular precio subiendo luego bajando
prices_up   = np.cumsum(
    np.random.normal(50, 100, 50)
) + 70000
prices_down = np.cumsum(
    np.random.normal(-50, 100, 50)
) + prices_up[-1]
closes = np.concatenate([prices_up, prices_down])

df = pd.DataFrame({
    'open':   closes * 0.999,
    'high':   closes * 1.002,
    'low':    closes * 0.998,
    'close':  closes,
    'volume': np.random.uniform(1000, 5000, n)
})

df = calculate_parabolic_sar(df)

# Verificar que el SAR calculó valores
assert df['sar'].notna().all(), \
    "FALLO: SAR tiene NaN"
assert df['sar_trend'].isin([-1, 0, 1]).all(), \
    "FALLO: trend fuera de rango"

# Verificar cambios de fase
changes_high = df['sar_ini_high'].sum()
changes_low  = df['sar_ini_low'].sum()

print(f"SAR calculado correctamente")
print(f"Cambios a alcista (ini_high): {changes_high}")
print(f"Cambios a bajista (ini_low):  {changes_low}")
print(f"Fase final: "
      f"{'LONG' if df.iloc[-1]['sar_trend'] > 0 else 'SHORT'}")

# Verificar que ini_high e ini_low
# no ocurren simultáneamente
simultaneous = (
    df['sar_ini_high'] & df['sar_ini_low']
).sum()
assert simultaneous == 0, \
    "FALLO: ini_high e ini_low simultáneos"

print("TEST PASSED — SAR implementado correctamente")
