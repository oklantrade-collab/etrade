import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

MODULE = 'BREAKPOINT_DETECTOR'

@dataclass
class BreakpointEvent:
    detected: bool = False
    direction: str = ''        # 'bullish_cross' | 'bearish_cross'
    crossed_ema: str = ''      # 'ema9' | 'ema20' | 'both'
    prior_regime: str = ''     # 'short_aligned' | 'long_aligned'
    structure: str = ''        # 'HH_HL' | 'LH_LL' | 'none'
    detail: str = ''

class BreakpointDetector:
    """Detects price crossing EMA9/EMA20 in aligned EMA environments on 15m.
    
    When market is in SHORT alignment (ema_3 < ema_9 < ema_20) and price
    crosses above ema_9 or ema_20, that's a bullish breakpoint.
    
    When market is in LONG alignment (ema_3 > ema_9 > ema_20) and price
    crosses below ema_9 or ema_20, that's a bearish breakpoint.
    
    This event feeds two parallel decisions:
    - HALCÓN/CENTINELA: evaluates closing an existing position
    - REBOTE: evaluates opening a new position in the breakpoint direction
    """
    
    def detect(self, df_15m: pd.DataFrame) -> BreakpointEvent:
        if df_15m is None or df_15m.empty or len(df_15m) < 4:
            return BreakpointEvent(detail="Not enough data")
            
        df = df_15m.iloc[:-1] # Exclude forming candle
        if len(df) < 3:
            return BreakpointEvent(detail="Not enough closed candles")
            
        required_cols = ['close', 'high', 'low', 'ema_3', 'ema_9', 'ema_20']
        if not all(c in df.columns for c in required_cols):
            return BreakpointEvent(detail="Missing required columns")
            
        # Use last 2 closed candles
        prev_candle = df.iloc[-2]
        curr_candle = df.iloc[-1]
        
        # Check alignment on previous candle
        is_short_aligned = (prev_candle['ema_3'] < prev_candle['ema_9']) and (prev_candle['ema_9'] < prev_candle['ema_20'])
        is_long_aligned = (prev_candle['ema_3'] > prev_candle['ema_9']) and (prev_candle['ema_9'] > prev_candle['ema_20'])
        
        prior_regime = ''
        if is_short_aligned:
            prior_regime = 'short_aligned'
        elif is_long_aligned:
            prior_regime = 'long_aligned'
        else:
            return BreakpointEvent(detail="No clear EMA alignment")
            
        # Check crosses on current candle compared to previous
        crossed_ema9_up = prev_candle['close'] < prev_candle['ema_9'] and curr_candle['close'] > curr_candle['ema_9']
        crossed_ema20_up = prev_candle['close'] < prev_candle['ema_20'] and curr_candle['close'] > curr_candle['ema_20']
        
        crossed_ema9_down = prev_candle['close'] > prev_candle['ema_9'] and curr_candle['close'] < curr_candle['ema_9']
        crossed_ema20_down = prev_candle['close'] > prev_candle['ema_20'] and curr_candle['close'] < curr_candle['ema_20']
        
        detected = False
        direction = ''
        crossed_ema = ''
        
        if is_short_aligned and (crossed_ema9_up or crossed_ema20_up):
            detected = True
            direction = 'bullish_cross'
            if crossed_ema9_up and crossed_ema20_up:
                crossed_ema = 'both'
            elif crossed_ema20_up:
                crossed_ema = 'ema20'
            else:
                crossed_ema = 'ema9'
                
        elif is_long_aligned and (crossed_ema9_down or crossed_ema20_down):
            detected = True
            direction = 'bearish_cross'
            if crossed_ema9_down and crossed_ema20_down:
                crossed_ema = 'both'
            elif crossed_ema20_down:
                crossed_ema = 'ema20'
            else:
                crossed_ema = 'ema9'
                
        if not detected:
            return BreakpointEvent(detail="No breakpoint detected", prior_regime=prior_regime)
            
        # Structure analysis: check last 3 closed candles for HH/HL or LH/LL
        last_3 = df.iloc[-3:]
        highs = last_3['high'].values
        lows = last_3['low'].values
        
        hh_hl = (highs[2] > highs[1] and highs[1] > highs[0]) and (lows[2] > lows[1] and lows[1] > lows[0])
        lh_ll = (highs[2] < highs[1] and highs[1] < highs[0]) and (lows[2] < lows[1] and lows[1] < lows[0])
        
        structure = 'HH_HL' if hh_hl else 'LH_LL' if lh_ll else 'none'
        
        return BreakpointEvent(
            detected=True,
            direction=direction,
            crossed_ema=crossed_ema,
            prior_regime=prior_regime,
            structure=structure,
            detail=f"Detected {direction} across {crossed_ema} from {prior_regime} regime"
        )
