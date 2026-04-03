import pandas as pd
import numpy as np
from app.analysis.parabolic_sar import calculate_parabolic_sar

def calculate_emas(df: pd.DataFrame,
                   v1=3, v2=9, v3=20, v4=50, v5=200) -> pd.DataFrame:
    df = df.copy()
    for i, span in enumerate([v1, v2, v3, v4, v5], start=1):
        # Asegurar que close no sea None
        df[f'ema{i}'] = df['close'].ffill().ewm(span=span, adjust=False).mean()
    return df


def classify_ema20_phase(df: pd.DataFrame,
                          flat_pct:       float = 20.0,
                          peak_pct:       float = 80.0,
                          lookback_window: int  = 100,
                          atr_lookback:   int   = 10) -> pd.DataFrame:
    """
    PERCENTILES ADAPTATIVOS — sin umbrales fijos.
    Funciona para BTC/15m, SOL/4h o cualquier par/TF
    sin intervención manual.
    """
    df = df.copy()

    # ATR normaliza el ángulo (igual a f_angle del PineScript original)
    df['atr'] = (
        df[['high', 'close']].max(axis=1) -
        df[['low',  'close']].min(axis=1)
    ).rolling(atr_lookback).mean()

    df['ema20_angle'] = np.degrees(
        np.arctan(
            (df['ema3'] - df['ema3'].shift(2)) /
            (df['atr'] * 2 + 1e-10)
        )
    )

    # Percentil rolling — auto-adaptativo al activo/TF
    df['ema20_pct'] = (
        df['ema20_angle'].rolling(lookback_window).rank(pct=True) * 100
    )

    flat_std = df['ema20_angle'].rolling(lookback_window).std()
    is_flat  = df['ema20_angle'].abs() < (flat_std * 0.3)

    peak_5   = df['ema20_angle'].rolling(5).max()
    falling  = (df['ema20_angle'] > 0) & (df['ema20_angle'] < peak_5) & (df['ema20_pct'] >= peak_pct * 0.6)

    # For short side (rising from trough)
    trough_5 = df['ema20_angle'].rolling(5).min()
    rising_short = (df['ema20_angle'] < 0) & (df['ema20_angle'] > trough_5) & (df['ema20_pct'] <= (100 - peak_pct) * 1.4)

    phases = [
        'flat',
        'nivel_1_long',  'nivel_2_long',  'nivel_3_long',
        'nivel_1_short', 'nivel_2_short', 'nivel_3_short',
    ]
    conditions = [
        is_flat,
        (~is_flat) & (df['ema20_angle'] > 0) & df['ema20_pct'].between(flat_pct, 50),
        (~is_flat) & (df['ema20_angle'] > 0) & df['ema20_pct'].between(50, peak_pct),
        (~is_flat) & (df['ema20_angle'] > 0) & falling,
        (~is_flat) & (df['ema20_angle'] < 0) & df['ema20_pct'].between(100-50, 100-flat_pct),
        (~is_flat) & (df['ema20_angle'] < 0) & df['ema20_pct'].between(100-peak_pct, 100-50),
        (~is_flat) & (df['ema20_angle'] < 0) & rising_short,
    ]
    df['ema20_phase']       = np.select(conditions, phases, default='flat')
    df['was_flat_recently'] = df['ema20_phase'].shift(1).isin(['flat']) | \
                              df['ema20_phase'].shift(2).isin(['flat']) | \
                              df['ema20_phase'].shift(3).isin(['flat'])
    return df

def calculate_macd_4c(df: pd.DataFrame,
                       fast: int = 12, slow: int = 26) -> pd.DataFrame:
    df = df.copy()
    df['macd'] = (
        df['close'].ewm(span=fast, adjust=False).mean() -
        df['close'].ewm(span=slow, adjust=False).mean()
    )
    prev = df['macd'].shift(1)
    df['macd_4c'] = np.select(
        [(df['macd'] > 0) & (df['macd'] > prev),
         (df['macd'] > 0) & (df['macd'] <= prev),
         (df['macd'] < 0) & (df['macd'] < prev),
         (df['macd'] < 0) & (df['macd'] >= prev)],
        [1, 2, 3, 4], default=0
    )
    c = df['macd_4c']
    df['macd_buy']  = (c == 4) & (c.shift(1) == 3) & (c.shift(2) == 3)
    df['macd_sell'] = (c == 2) & (c.shift(1) == 1) & (c.shift(2) == 1)
    return df

def calculate_ema_angles(df: pd.DataFrame, lookback: int = 2) -> pd.DataFrame:
    df = df.copy()
    atr = df.get('atr')
    if atr is None:
        atr = (df[['high', 'close']].max(axis=1) - df[['low', 'close']].min(axis=1)).rolling(10).mean()
        df['atr'] = atr
    
    for ema_col, angle_col in [('ema2', 'ema9_angle'), ('ema3', 'ema20_angle'), ('ema4', 'ema50_angle')]:
        if ema_col in df.columns:
            df[angle_col] = np.degrees(np.arctan((df[ema_col] - df[ema_col].shift(lookback)) / (df['atr'] * lookback + 1e-10)))
    return df

def detect_ema_crosses(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if 'ema4' in df.columns and 'basis' in df.columns:
        df['ema4_cross_above_basis'] = (df['ema4'] > df['basis']) & (df['ema4'].shift(1) <= df['basis'].shift(1))
        df['ema4_cross_below_basis'] = (df['ema4'] < df['basis']) & (df['ema4'].shift(1) >= df['basis'].shift(1))
    return df

def calculate_all_indicators(df: pd.DataFrame, cfg: dict = None) -> pd.DataFrame:
    """Master function to calculate everything in memory pipeline."""
    from app.analysis.fibonacci_bb import fibonacci_bollinger
    from app.analysis.adx_di import calculate_adx
    from app.analysis.volume_candles import detect_volume_signals, detect_reversal_candles
    
    cfg = cfg or {}
    df = fibonacci_bollinger(df, length=cfg.get('length', 200), mult=cfg.get('mult', 3.0))
    df = calculate_emas(df)
    df = calculate_macd_4c(df)
    df = calculate_adx(df)
    df = detect_volume_signals(df, vol_ema_period=cfg.get('vol_ema_period', 20))
    df = detect_reversal_candles(df)
    # Usar defaults si cfg tiene el campo pero es None en DB (null)
    f_pct = cfg.get('flat_pct')
    if f_pct is None: f_pct = 20.0
    
    p_pct = cfg.get('peak_pct')
    if p_pct is None: p_pct = 80.0

    df = classify_ema20_phase(df, 
        flat_pct=float(f_pct), 
        peak_pct=float(p_pct)
    )
    df = calculate_ema_angles(df)
    df = detect_ema_crosses(df)
    df = calculate_parabolic_sar(df)
    
    # Fill any NaNs that might cause issues in calculation
    df = df.ffill().fillna(0)
    
    # --- CALCULO DE ZONA FIBONACCI (PUENTE SNAPSHOT) ---
    # fibonacci_bollinger solo calcula bandas, aqui extraemos la zona
    from app.analysis.fibonacci_bb import extract_fib_levels
    fib_levels = extract_fib_levels(df)
    df['fibonacci_zone'] = fib_levels['zone']
    
    # --- INYECCIÓN DE SEÑAL PINESCRIPT (CORRECCIÓN 2) ---
    # Proxy del PineScript -- basado en MACD 4C hasta integracion real.
    # pinescript_signal='Buy' ocurre exactamente cuando macd_buy=True (alias 1:1).
    # signal_age cuenta las barras desde la ultima señal activa.
    df['pinescript_signal'] = np.where(df['macd_buy'], 'Buy', 
                                np.where(df['macd_sell'], 'Sell', None))
    
    # Calcular la edad de la señal (cuántas barras han pasado desde el último 'Buy' o 'Sell')
    def calc_signal_data(series):
        ages = []
        last_signals = []
        
        cur_age = 999
        cur_signal = None
        
        for val in series:
            if val is not None:
                cur_age = 0
                cur_signal = val
            else:
                cur_age += 1
            
            ages.append(cur_age)
            last_signals.append(cur_signal)
            
        return ages, last_signals

    ages, last_sigs = calc_signal_data(df['pinescript_signal'])
    df['signal_age'] = ages
    df['last_pinescript_signal'] = last_sigs
    
    return df
