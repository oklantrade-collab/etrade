import logging

def can_open_short(market_type: str) -> bool:
    """
    Determina si el mercado permite abrir posiciones SHORT.
    FUTURES:  SHORT real → True
    SPOT:     Solo LONG  → False
    """
    return market_type in (
        'crypto_futures',
        'forex_futures',
        'futures' # Versión corta en DB
    )

def get_bearish_action(
    market_type:    str,
    has_long_open:  bool
) -> str:
    """
    Determina qué hacer con una señal bajista según el tipo de mercado.
    Returns:
      'open_short'   → abrir SHORT (futuros)
      'close_long'   → cerrar LONG existente (spot)
      'no_action'    → no hacer nada (spot sin posición)
    """
    if can_open_short(market_type):
        return 'open_short'
    elif has_long_open:
        # En spot, señal bajista = cerrar LONG
        return 'close_long'
    else:
        # En spot sin posición → no entrar
        return 'no_action'

def calculate_sl_tp(
    side:         str,
    entry_price:  float,
    atr:          float,
    atr_mult:     float,
    levels:       dict   # Fibonacci levels (upper_x, lower_x, basis)
) -> dict:
    """
    Calcula SL y TP de forma simétrica según la dirección.
    """
    basis = float(levels.get('basis', entry_price))
    
    if side == 'long' or side == 'Buy':
        sl_price   = entry_price - (atr * atr_mult)
        tp_partial = float(levels.get('upper_5', basis * 1.05))
        tp_full    = float(levels.get('upper_6', basis * 1.08))
    else:  # short / Sell
        sl_price   = entry_price + (atr * atr_mult)
        tp_partial = float(levels.get('lower_5', basis * 0.95))
        tp_full    = float(levels.get('lower_6', basis * 0.92))

    return {
        'sl_price':         round(sl_price, 8),
        'tp_partial_price': round(tp_partial, 8),
        'tp_full_price':    round(tp_full, 8)
    }


def calculate_position_size(
    symbol: str,
    entry_price: float,
    sl_price: float,
    market_type: str,    # 'crypto_futures'|'crypto_spot'
    trade_number: int,    # 1, 2 o 3 (T1, T2, T3)
    regime: str,
    supabase
) -> dict:
    """
    Calcula el tamaño de posición correcto basado en el capital configurado, 
    NO en el balance real de Binance (evita errores en Testnet).
    """
    try:
        # Leer configuración desde Supabase
        cfg = supabase.table('trading_config').select('*').eq('id', 1).single().execute()
        c = cfg.data
        if not c:
            raise ValueError("No se pudo cargar la configuración de trading_config (id=1)")

        if market_type == 'crypto_futures':
            capital_base = float(c.get('capital_crypto_futures', 500))
            leverage = int(c.get('leverage_crypto', 5))
        elif market_type == 'crypto_spot':
            capital_base = float(c.get('capital_crypto_spot', 0))
            leverage = 1
        else:
            capital_base = float(c.get('capital_total', 500))
            leverage = 1

        # Capital operativo (90% del capital base para margen/seguridad)
        buffer = 0.90
        capital_op = capital_base * buffer

        # Distribución del capital operativo por niveles (T1, T2, T3)
        distributions = {
            1: [1.00],
            2: [0.40, 0.60],
            3: [0.20, 0.30, 0.50],
            4: [0.15, 0.20, 0.30, 0.35],
            5: [0.10, 0.15, 0.20, 0.25, 0.30],
        }
        max_by_regime = {
            'alto_riesgo': 1,
            'riesgo_medio': 3,
            'bajo_riesgo': 5
        }
        
        regime_key = regime if regime in max_by_regime else 'riesgo_medio'
        max_trades = max_by_regime.get(regime_key, 3)
        dist = distributions[max_trades]

        # Monto nominal en USD para este trade específico
        trade_idx = min(trade_number - 1, len(dist) - 1)
        usd_amount = capital_op * dist[trade_idx]

        # PARA FUTUROS: Dimensionar por RIESGO (1% del capital base)
        # riesgo_usd = capital_base * 1%
        risk_pct = 0.01  # 1% de riesgo máximo sobre capital base
        risk_usd = capital_base * risk_pct
        
        # sl_distance como porcentaje (distancia fraccional)
        sl_distance = abs(entry_price - sl_price) / entry_price if entry_price > 0 else 0

        if sl_distance > 0:
            # Nocional necesario para que el SL equivalga a risk_usd
            nocional_por_riesgo = risk_usd / sl_distance
            # No permitir que el nocional exceda: capital asignado × leverage
            max_nocional = usd_amount * leverage
            nocional = min(nocional_por_riesgo, max_nocional)
        else:
            # Si no hay SL (spot sin SL), usamos el capital máximo asignado
            nocional = usd_amount

        # Cantidad en unidades del activo
        quantity = nocional / entry_price if entry_price > 0 else 0

        return {
            'capital_base': capital_base,
            'capital_op':   round(capital_op, 2),
            'usd_amount':   round(usd_amount, 2),
            'nocional':     round(nocional, 2),
            'quantity':     round(quantity, 8),
            'leverage':     leverage,
            'risk_usd':     round(risk_usd, 2),
            'risk_pct':     risk_pct * 100,
            'market_type':  market_type,
            'regime_max_trades': max_trades
        }
    except Exception as e:
        logging.error(f"Error en calculate_position_size: {e}")
        return None
