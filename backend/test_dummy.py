from app.analysis.swing_detector import calculate_fall_maturity, SWING_CONFIG
import pandas as pd
import numpy as np

# ADA simulado
n = 50
prices = np.linspace(0.270, 0.251, n)
df = pd.DataFrame({
    'open':    prices * 1.001,
    'high':    prices * 1.002,
    'low':     prices * 0.998,
    'close':   prices,
    'volume':  np.random.uniform(1000, 5000, n),
    'basis':   np.full(n, 0.260),
    'lower_1': np.full(n, 0.258),
    'lower_2': np.full(n, 0.256),
    'lower_3': np.full(n, 0.254),
    'lower_4': np.full(n, 0.252),
    'lower_5': np.full(n, 0.250),
    'lower_6': np.full(n, 0.248),
})

for tf in ['15m', '4h']:
    cfg  = SWING_CONFIG[tf]
    result = calculate_fall_maturity(
        df             = df,
        direction      = 'long',
        min_bands      = cfg['min_bands'],
        min_basis_dist = cfg['min_basis_dist'],
        lookback       = cfg['lookback']
    )
    print(f'ADA {tf}:')
    print(f'  is_mature:     {result["is_mature"]}')
    print(f'  bands:         {result.get("bands_perforated")}')
    print(f'  basis_dist:    {result.get("basis_dist_pct")}%')
    print(f'  momentum_decr: {result.get("momentum_decreasing")}')
    print(f'  reason:        {result["reason"]}')
    print()
