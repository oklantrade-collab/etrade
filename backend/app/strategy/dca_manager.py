import os
from datetime import datetime, timezone
from app.core.logger import log_info, log_warning, log_error

def evaluate_proactive_dca(position: dict, current_price: float, snap: dict, symbol: str, market_type: str) -> dict:
    """
    Evalúa si se debe hacer un DCA (Dollar Cost Averaging) proactivo antes de que toque el Stop Loss.
    Condiciones para LONG:
    - current_price <= lower_6
    - O rsi_15m <= 15
    - O Señal SIPV 15m == "Reversión Alcista"

    Condiciones para SHORT:
    - current_price >= upper_6
    - O rsi_15m >= 75
    - O Señal SIPV 15m == "Reversión Bajista"
    """
    # 1. Validaciones iniciales
    if position.get('dca_executed', False):
        return {'should_dca': False}
    
    side = position.get('side', 'long').lower()
    is_long = side in ('long', 'buy')
    
    # Obtener valores del snapshot
    lower_6 = float(snap.get('lower_6', 0))
    upper_6 = float(snap.get('upper_6', 0))
    rsi = float(snap.get('rsi', 50))
    signal_sipv = str(snap.get('signal', ''))
    
    trigger_reason = None
    
    if is_long:
        if lower_6 > 0 and current_price <= lower_6:
            trigger_reason = f"Precio <= Lower_6 ({current_price} <= {lower_6})"
        elif rsi <= 15:
            trigger_reason = f"RSI_15m extremo bajista ({rsi} <= 15)"
        elif "Reversión Alcista" in signal_sipv:
            trigger_reason = f"Señal SIPV 15m: Reversión Alcista"
    else:
        if upper_6 > 0 and current_price >= upper_6:
            trigger_reason = f"Precio >= Upper_6 ({current_price} >= {upper_6})"
        elif rsi >= 75:
            trigger_reason = f"RSI_15m extremo alcista ({rsi} >= 75)"
        elif "Reversión Bajista" in signal_sipv:
            trigger_reason = f"Señal SIPV 15m: Reversión Bajista"
            
    if trigger_reason:
        size = float(position.get('size', 0.01))
        return {
            'should_dca': True,
            'reason': f"DCA Proactivo Activado: {trigger_reason}",
            'dca_size': size # 100% of current position size
        }
        
    return {'should_dca': False}
