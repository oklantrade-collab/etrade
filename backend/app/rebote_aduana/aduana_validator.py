import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from app.rebote_aduana.config import ADUANA_PARAMS, MODULE
from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

@dataclass
class AduanaResult:
    approved: bool = True
    rule_triggered: str = ''    # '' if approved
    reason: str = ''
    step: int = 0               # Pipeline step (1-6)
    detail: dict = field(default_factory=dict)

class AduanaValidator:
    def __init__(self, params: dict = None, oraculo_manager=None):
        self.params = params or ADUANA_PARAMS
        self.oraculo = oraculo_manager

    def _normalize_side(self, side: str) -> str:
        s = side.lower()
        if s in ('buy', 'long'):
            return 'long'
        elif s in ('sell', 'short'):
            return 'short'
        return s

    def _get_fib_zone(self, df_15m: pd.DataFrame) -> int:
        if df_15m is None or df_15m.empty or len(df_15m) < 2:
            return 0
        last_closed = df_15m.iloc[-2] if len(df_15m) > 1 else df_15m.iloc[-1]
        try:
            val = last_closed.get('fibonacci_zone', 0)
            if val is None or pd.isna(val):
                return 0
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    def _get_halcon_macro_scores(self, symbol: str) -> dict:
        try:
            supabase = get_supabase()
            response = supabase.table('halcon_scores_log').select('*').eq('symbol', symbol).order('created_at', desc=True).limit(1).execute()
            if response.data and len(response.data) > 0:
                record = response.data[0]
                scores = record.get('scores_by_layer', {})
                return {
                    'score_1d': float(scores.get('1d', 0)),
                    'score_4h': float(scores.get('4h', 0))
                }
        except Exception as e:
            log_error(f"Error getting halcon macro scores: {e}", MODULE)
        return {'score_1d': 0.0, 'score_4h': 0.0}

    def _check_impulse_candle(self, df_15m: pd.DataFrame, side: str) -> tuple:
        if df_15m is None or df_15m.empty or len(df_15m) < 2:
            return False, ''
            
        last_closed = df_15m.iloc[-2] if len(df_15m) > 1 else df_15m.iloc[-1]
        try:
            high = float(last_closed.get('high', 0))
            low = float(last_closed.get('low', 0))
            close_p = float(last_closed.get('close', 0))
            open_p = float(last_closed.get('open', 0))
            atr = float(last_closed.get('atr', 0))
        except (ValueError, TypeError):
            return False, ''

        if atr == 0:
            return False, ''

        rng = high - low
        ratio = self.params.get('impulse_candle_atr_ratio', 1.8)
        is_impulse = rng > (ratio * atr)
        
        candle_dir = 'bullish' if close_p > open_p else 'bearish'
        
        return is_impulse, candle_dir

    def _check_range_regime(self, df_15m: pd.DataFrame) -> bool:
        if df_15m is None or df_15m.empty or len(df_15m) < 2:
            return False
            
        last_closed = df_15m.iloc[-2] if len(df_15m) > 1 else df_15m.iloc[-1]
        prev_closed = df_15m.iloc[-3] if len(df_15m) > 2 else last_closed
        
        try:
            adx = float(last_closed.get('adx', 0))
            bb_width = float(last_closed.get('bb_width', 100))
            ema20_curr = float(last_closed.get('ema_20', 0))
            ema20_prev = float(prev_closed.get('ema_20', 0))
        except (ValueError, TypeError):
            return False
            
        adx_thresh = self.params.get('adx_range_threshold', 20.0)
        bb_thresh = self.params.get('range_bb_bandwidth_threshold', 0.1)
        
        slope = abs(ema20_curr - ema20_prev) / ema20_prev if ema20_prev > 0 else 0
        
        return adx < adx_thresh and bb_width < bb_thresh and slope < 0.0005

    def validate(self, symbol: str, side: str, order_type: str,
                 market_data: dict, strategy: str = '',
                 halcon_scores: dict = None,
                 contra_trend_confirmed: bool = False) -> AduanaResult:
        
        norm_side = self._normalize_side(side)
        df_15m = market_data.get('df_15m')
        
        # Step 1: Check ORÁCULO trading_paused
        step = 1
        is_paused = False
        if self.oraculo and hasattr(self.oraculo, 'is_paused'):
            is_paused = self.oraculo.is_paused(symbol)
        else:
            try:
                supabase = get_supabase()
                resp = supabase.table('trading_state').select('trading_paused').eq('symbol', symbol).execute()
                if resp.data and len(resp.data) > 0:
                    is_paused = bool(resp.data[0].get('trading_paused', False))
            except Exception:
                pass
                
        if is_paused:
            return AduanaResult(approved=False, rule_triggered='ORACULO_PAUSE', reason='Trading is paused by Oraculo', step=step)

        # Step 2: Check extreme in SAME direction
        step = 2
        fib_zone = self._get_fib_zone(df_15m)
        if norm_side == 'long' and fib_zone >= 4:
            return AduanaResult(approved=False, rule_triggered='SAME_DIR_EXTREME', reason=f'Long at upper extreme (fib {fib_zone})', step=step)
        if norm_side == 'short' and fib_zone <= -4:
            return AduanaResult(approved=False, rule_triggered='SAME_DIR_EXTREME', reason=f'Short at lower extreme (fib {fib_zone})', step=step)

        # Step 3: Check contra macro HALCÓN bias without reinforced confirmation
        step = 3
        if not halcon_scores:
            halcon_scores = self._get_halcon_macro_scores(symbol)
            
        score_1d = float(halcon_scores.get('score_1d', 0))
        score_4h = float(halcon_scores.get('score_4h', 0))
        macro_avg = (score_1d + score_4h) / 2.0
        
        macro_thresh = self.params.get('macro_score_threshold', 40.0)
        
        if macro_avg < -macro_thresh and norm_side == 'long' and not contra_trend_confirmed:
            return AduanaResult(approved=False, rule_triggered='CONTRA_MACRO_NO_CONFIRM', reason=f'Long against strong macro bearish bias ({macro_avg})', step=step)
            
        if macro_avg > macro_thresh and norm_side == 'short' and not contra_trend_confirmed:
            return AduanaResult(approved=False, rule_triggered='CONTRA_MACRO_NO_CONFIRM', reason=f'Short against strong macro bullish bias ({macro_avg})', step=step)

        # Step 4: Check impulse candle
        step = 4
        is_impulse, candle_dir = self._check_impulse_candle(df_15m, norm_side)
        if is_impulse:
            if candle_dir == 'bearish' and norm_side == 'long':
                return AduanaResult(approved=False, rule_triggered='IMPULSE_CANDLE', reason='Strong bearish impulse candle against long entry', step=step)
            if candle_dir == 'bullish' and norm_side == 'short':
                return AduanaResult(approved=False, rule_triggered='IMPULSE_CANDLE', reason='Strong bullish impulse candle against short entry', step=step)

        # Step 4.5: Check CASCADA Hold Conflict (Spec 3.9 & 4.2.3)
        cascade_hold_active = market_data.get('cascade_hold_active', False)
        cascade_hold_side = market_data.get('cascade_hold_side', '')
        if cascade_hold_active and cascade_hold_side and cascade_hold_side != norm_side:
            # An order contradicting an active CASCADE_HOLD requires reinforced confirmation
            if not contra_trend_confirmed:
                return AduanaResult(
                    approved=False, 
                    rule_triggered='CONTRA_CASCADE_HOLD_NO_CONFIRM', 
                    reason=f"Order {norm_side} contradicts active CASCADE_HOLD in {cascade_hold_side} without reinforced confirmation", 
                    step=step
                )

        # Step 5: Range regime explicit approval
        step = 5
        is_range = self._check_range_regime(df_15m)
        if is_range:
            if norm_side == 'long' and fib_zone <= -3:
                return AduanaResult(approved=True, rule_triggered='RANGE_EXPLICIT_APPROVAL', reason='Long at lower extreme in range regime', step=step)
            if norm_side == 'short' and fib_zone >= 3:
                return AduanaResult(approved=True, rule_triggered='RANGE_EXPLICIT_APPROVAL', reason='Short at upper extreme in range regime', step=step)

        # Step 6: No rejection rule triggered -> APPROVE
        step = 6
        return AduanaResult(approved=True, rule_triggered='', reason='Passed all checks', step=step)
