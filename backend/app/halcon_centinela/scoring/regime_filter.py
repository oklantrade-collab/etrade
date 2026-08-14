MODULE = "HALCON_CENTINELA"

def classify_regime(adx: float, plus_di: float, minus_di: float) -> dict:
    """Classify ADX regime:
    - adx < 15: 'choppy' (range, prioritize squeeze, reduce EMA cross weight 50%)
    - 15 <= adx <= 30: 'moderate' (normal, require volume confirmation)
    - adx > 30: 'strong_trend' (increase macro weight 20%, require more extreme micro score)
    Also determines direction: plus_di > minus_di = bullish, else bearish
    Returns: {'regime': str, 'adx': float, 'direction': str,
              'ema_cross_weight_mult': float, 'macro_weight_boost': float,
              'micro_close_threshold_override': float|None}
    """
    if adx < 15:
        regime = 'choppy'
        ema_cross_weight_mult = 0.5
        macro_weight_boost = 1.0
        micro_override = None
    elif 15 <= adx <= 30:
        regime = 'moderate'
        ema_cross_weight_mult = 1.0
        macro_weight_boost = 1.0
        micro_override = None
    else:
        regime = 'strong_trend'
        ema_cross_weight_mult = 1.0
        macro_weight_boost = 1.2
        micro_override = -60.0

    direction = 'bullish' if plus_di > minus_di else 'bearish'
    
    return {
        'regime': regime,
        'adx': float(adx),
        'direction': direction,
        'ema_cross_weight_mult': ema_cross_weight_mult,
        'macro_weight_boost': macro_weight_boost,
        'micro_close_threshold_override': micro_override
    }

def apply_regime_adjustments(scores: dict, regime: dict, weights: dict, params: dict) -> dict:
    """Apply regime modifiers to the weighted scores and thresholds.
    - choppy: multiply 15m score by ema_cross_weight_mult (0.5)
    - strong_trend: boost 1d and 4h weights by 20%, override close threshold to -60
    Returns: {'adjusted_weights': dict, 'adjusted_scores': dict, 'close_threshold_override': float|None}
    """
    adj_weights = weights.copy()
    adj_scores = scores.copy()
    
    if regime.get('regime') == 'choppy':
        if '15m' in adj_scores:
            adj_scores['15m'] = max(-100, min(100, int(adj_scores['15m'] * regime.get('ema_cross_weight_mult', 0.5))))
            
    elif regime.get('regime') == 'strong_trend':
        if '1d' in adj_weights:
            adj_weights['1d'] *= regime.get('macro_weight_boost', 1.2)
        if '4h' in adj_weights:
            adj_weights['4h'] *= regime.get('macro_weight_boost', 1.2)
            
    return {
        'adjusted_weights': adj_weights,
        'adjusted_scores': adj_scores,
        'close_threshold_override': regime.get('micro_close_threshold_override')
    }
