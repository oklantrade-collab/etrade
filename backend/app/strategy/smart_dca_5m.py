from app.core.logger import log_info, log_warning, log_error

def evaluate_smart_dca(snap_15m: dict, snap_5m: dict, is_long: bool) -> dict:
    """
    Evalúa si se debe realizar una compra secundaria (DCA) basándose en una estrategia de francotirador
    de 5 minutos, escudada por la tendencia macro en 15 minutos.
    
    Estrategias:
    1. Pullback Confirmado (Trend Dip)
    2. Bollinger Exhaustion Reversion
    3. Capitulación Elástica Extrema
    """
    
    # Extraer valores 15m (Macro)
    ema3_15m = float(snap_15m.get('ema_3', snap_15m.get('ema3', 0)))
    ema9_15m = float(snap_15m.get('ema_9', snap_15m.get('ema9', 0)))
    ema50_15m = float(snap_15m.get('ema_50', snap_15m.get('ema50', 0)))
    ema200_15m = float(snap_15m.get('ema_200', snap_15m.get('ema200', 0)))
    
    # Extraer valores 5m (Micro/Sniper)
    ema3_5m = float(snap_5m.get('ema_3', snap_5m.get('ema3', 0)))
    ema9_5m = float(snap_5m.get('ema_9', snap_5m.get('ema9', 0)))
    ema20_5m = float(snap_5m.get('ema_20', snap_5m.get('ema20', 0)))
    ema50_5m = float(snap_5m.get('ema_50', snap_5m.get('ema50', 0)))
    
    close_5m = float(snap_5m.get('close', 0))
    open_5m = float(snap_5m.get('open', 0))
    low_5m = float(snap_5m.get('low', 0))
    high_5m = float(snap_5m.get('high', 0))
    
    lower_band_5m = float(snap_5m.get('lower_band', snap_5m.get('lower', 0)))
    upper_band_5m = float(snap_5m.get('upper_band', snap_5m.get('upper', 0)))
    rsi_5m = float(snap_5m.get('rsi_14', snap_5m.get('rsi', 50)))
    
    reason = None
    rule_code = None

    if is_long:
        # Filtros Macro 15m para LONG
        macro_trend_intact = (ema3_15m > ema9_15m) and ema9_15m > 0
        macro_structure_bullish = (ema50_15m > ema200_15m) and ema200_15m > 0
        
        # Estrategia 1: Pullback Confirmado (Trend Dip)
        if macro_trend_intact:
            if (ema3_5m > ema9_5m > ema20_5m) and (close_5m < ema20_5m) and (close_5m > open_5m):
                reason = "Trend Dip: Retroceso a EMA20 en 5m con vela confirmada (verde) y macro intacto."
                rule_code = "SMART_DCA_1_LONG"
                
        # Estrategia 2: Bollinger Exhaustion Reversion
        if not reason and macro_structure_bullish:
            if (low_5m < lower_band_5m) and (close_5m > lower_band_5m) and (rsi_5m < 30):
                reason = f"Bollinger Exhaustion: Rechazo en banda inferior 5m, RSI={rsi_5m:.1f} y macro alcista."
                rule_code = "SMART_DCA_2_LONG"
                
        # Estrategia 3: Capitulación Elástica Extrema
        if not reason and macro_structure_bullish and ema50_5m > 0:
            dev_pct = ((ema50_5m - close_5m) / ema50_5m) * 100
            if dev_pct > 0.20 and rsi_5m < 20:
                reason = f"Capitulación Extrema: Alejamiento {dev_pct:.2f}% bajo EMA50 5m, RSI={rsi_5m:.1f} y macro alcista."
                rule_code = "SMART_DCA_3_LONG"

    else:
        # Filtros Macro 15m para SHORT
        macro_trend_intact = (ema3_15m < ema9_15m) and ema3_15m > 0
        macro_structure_bearish = (ema50_15m < ema200_15m) and ema50_15m > 0
        
        # Estrategia 1: Pullback Confirmado (Trend Dip)
        if macro_trend_intact:
            if (ema3_5m < ema9_5m < ema20_5m) and (close_5m > ema20_5m) and (close_5m < open_5m):
                reason = "Trend Dip: Retroceso a EMA20 en 5m con vela confirmada (roja) y macro intacto bajista."
                rule_code = "SMART_DCA_1_SHORT"
                
        # Estrategia 2: Bollinger Exhaustion Reversion
        if not reason and macro_structure_bearish:
            if (high_5m > upper_band_5m) and (close_5m < upper_band_5m) and (rsi_5m > 70):
                reason = f"Bollinger Exhaustion: Rechazo en banda superior 5m, RSI={rsi_5m:.1f} y macro bajista."
                rule_code = "SMART_DCA_2_SHORT"
                
        # Estrategia 3: Capitulación Elástica Extrema
        if not reason and macro_structure_bearish and ema50_5m > 0:
            dev_pct = ((close_5m - ema50_5m) / ema50_5m) * 100
            if dev_pct > 0.20 and rsi_5m > 80:
                reason = f"Capitulación Extrema: Alejamiento {dev_pct:.2f}% sobre EMA50 5m, RSI={rsi_5m:.1f} y macro bajista."
                rule_code = "SMART_DCA_3_SHORT"
                
    if reason:
        return {
            'should_dca': True,
            'reason': reason,
            'rule_code': rule_code
        }
        
    return {'should_dca': False}
