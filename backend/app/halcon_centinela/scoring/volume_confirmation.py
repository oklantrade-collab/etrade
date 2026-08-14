import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def check_volume_confirmation(df: pd.DataFrame, cross_bar_idx: int, params: dict,
                               market_type: str = 'forex') -> dict:
    """Volume confirmation for EMA crosses:
    - Volume of cross candle > volume_confirmation_multiplier (1.3x) * avg volume of last 10 candles
    - Forex: use tick volume or high-low range expansion as proxy
    - Crypto: use actual volume
    If not confirmed: score reduction factor = 0.5 (50% reduction, not full block)
    Returns: {'confirmed': bool, 'volume_ratio': float, 'score_multiplier': float, 'detail': str}
    """
    default_res = {'confirmed': False, 'volume_ratio': 1.0, 'score_multiplier': 0.5, 'detail': 'Missing data'}
    
    if df is None or df.empty:
        return default_res
        
    if cross_bar_idx < 0 or cross_bar_idx >= len(df):
        return default_res
        
    cross_row = df.iloc[cross_bar_idx]
    
    start_idx = max(0, cross_bar_idx - 10)
    if cross_bar_idx == start_idx:
        return default_res
        
    past_10 = df.iloc[start_idx:cross_bar_idx]
    
    mult = params.get('volume_confirmation_multiplier', 1.3)
    
    cross_vol = 0
    avg_vol = 1e-10
    
    if market_type == 'forex':
        if 'volume' in df.columns:
            cross_vol = cross_row.get('volume', 0)
            avg_vol = past_10['volume'].mean()
        else:
            # Proxy: High-Low range
            cross_vol = cross_row.get('high', 0) - cross_row.get('low', 0)
            avg_vol = (past_10['high'] - past_10['low']).mean()
    else:
        # Crypto
        if 'volume' in df.columns:
            cross_vol = cross_row.get('volume', 0)
            avg_vol = past_10['volume'].mean()
            
    if pd.isna(avg_vol) or avg_vol == 0:
        avg_vol = 1e-10
        
    ratio = cross_vol / avg_vol
    confirmed = bool(ratio > mult)
    
    score_mult = 1.0 if confirmed else 0.5
    
    return {
        'confirmed': confirmed,
        'volume_ratio': float(ratio),
        'score_multiplier': float(score_mult),
        'detail': f'Confirmed: {confirmed} with ratio {ratio:.2f}'
    }
