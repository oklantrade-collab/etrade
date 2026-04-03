import math
import logging

def round_step_size(quantity: float, step_size: float) -> float:
    if step_size <= 0: return quantity
    precision = int(round(-math.log(step_size, 10), 0))
    return round(quantity - (quantity % step_size), precision)

def round_price(price: float, tick_size: float) -> float:
    if tick_size <= 0: return price
    precision = int(round(-math.log(tick_size, 10), 0))
    return round(price - (price % tick_size), precision)

def build_oco_params(
    signal: dict,
    balance_usdt: float,
    symbol_info: dict,
    risk_config: dict
) -> dict | None:
    # PASO 1 — Extraer parámetros del riesgo:
    entry_price  = signal['entry_price']
    atr_4h       = signal.get('atr_4h_used') or signal.get('atr_4h')
    signal_type  = signal['signal_type']    # 'BUY' o 'SELL'
    sl_mult      = float(risk_config.get('sl_multiplier', 2.0))
    rr_ratio     = float(risk_config.get('rr_ratio', 2.5))
    risk_pct     = float(risk_config.get('max_risk_per_trade_pct', 1.0)) / 100
    slippage     = float(risk_config.get('slippage_estimate_pct', 0.05)) / 100
    
    # PASO 2 — Verificar que tenemos ATR válido
    if atr_4h is None or atr_4h <= 0:
        logging.error('ATR_4h no disponible, no se puede calcular SL/TP')
        return None
        
    # PASO 3 — Calcular distancias de SL y TP
    sl_distance = atr_4h * sl_mult
    tp_distance = sl_distance * rr_ratio
    
    if signal_type == 'BUY':
        sl_raw = entry_price - sl_distance
        tp_raw = entry_price + tp_distance
    elif signal_type == 'SELL':
        sl_raw = entry_price + sl_distance
        tp_raw = entry_price - tp_distance
    else:
        return None
        
    # PASO 4 — Redondear precios al tick_size de Binance:
    tick_size = symbol_info.get('tick_size', 0.01)
    sl_price  = round_price(sl_raw, tick_size)
    tp_price  = round_price(tp_raw, tick_size)
    
    # Para OCO, Binance requiere un stopLimitPrice ligeramente 
    # peor que el stopPrice para garantizar la ejecución
    if signal_type == 'BUY':
        sl_limit_price = round_price(sl_price * 0.998, tick_size)
    else:
        sl_limit_price = round_price(sl_price * 1.002, tick_size)
        
    # PASO 5 — Position Sizing (máx 1% de riesgo):
    sl_distance_with_slippage = sl_distance + (entry_price * slippage)
    if sl_distance_with_slippage <= 0:
        return None
    max_loss_usdt = balance_usdt * risk_pct
    raw_quantity  = max_loss_usdt / sl_distance_with_slippage
    
    # PASO 6 — Redondear cantidad al step_size de Binance:
    step_size = symbol_info.get('step_size', 0.001)
    quantity  = round_step_size(raw_quantity, step_size)
    
    # PASO 7 — Validar cantidad mínima:
    min_qty      = symbol_info.get('min_qty', 0.0)
    min_notional = symbol_info.get('min_notional', 10.0)
    order_value  = quantity * entry_price
    
    if quantity < min_qty:
        logging.warning(f'Quantity {quantity} < min_qty {min_qty}')
        return None
        
    if order_value < min_notional:
        logging.warning(f'Order value ${order_value:.2f} < min ${min_notional}')
        return None
        
    # PASO 8 — Verificar que el balance alcanza:
    if order_value > balance_usdt * 0.95:  # 5% de margen de seguridad
        logging.warning(f'Balance insuficiente: necesita ${order_value:.2f}')
        return None
        
    return {
        'symbol': signal['symbol'].replace('/', ''),  # 'BTC/USDT' → 'BTCUSDT'
        'side': signal_type,                          # 'BUY' o 'SELL'
        'quantity': quantity,
        'entry_price': entry_price,
        'stop_loss': sl_price,
        'stop_limit': sl_limit_price,
        'take_profit': tp_price,
        'order_value_usdt': order_value,
        'max_loss_usdt': round(max_loss_usdt, 2),
        'risk_reward_ratio': rr_ratio,
        'sl_distance': sl_distance,
        'tp_distance': tp_distance
    }
