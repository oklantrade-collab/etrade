def calculate_pnl(market_type, side, entry_price, current_price, qty, symbol, supabase=None, config=None):
    """
    Calcula el PNL en USD y el PNL en % (ROI basado en margen)
    market_type: 'forex' o 'crypto'
    side: 'long' o 'short' (o 'buy'/'sell')
    qty: lotes para forex, o cantidad nominal para crypto
    symbol: ej. EURUSD, XAUUSD, BTCUSDT
    supabase: cliente para leer configuracion si config no es provisto
    config: diccionario con la configuracion de trading_config
    """
    if config is None and supabase is not None:
        try:
            cfg_res = supabase.table('trading_config').select('*').eq('id', 1).single().execute()
            config = cfg_res.data or {}
        except Exception:
            config = {}
    elif config is None:
        config = {}

    is_long = side.lower() in ['long', 'buy']
    pnl_usd = 0.0
    pnl_pct = 0.0
    margin = 0.0

    if market_type == 'forex' or 'forex' in str(market_type).lower() or market_type is None and ('USD' in symbol or 'EUR' in symbol or 'JPY' in symbol or 'XAU' in symbol):
        # Es Forex
        pip_size = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
        pip_val_std = 1.0 if 'XAU' in symbol else (6.5 if 'JPY' in symbol else 10.0)
        
        diff = (current_price - entry_price) if is_long else (entry_price - current_price)
        pips = diff / pip_size if pip_size > 0 else 0
        pnl_usd = pips * pip_val_std * qty
        
        # Calcular Margen Real
        # Usamos el mapa de apalancamiento si existe
        lev_map = config.get('leverage_map_forex') or {}
        
        # Buscar por prefijo o sufijo
        leverage = config.get('leverage_forex')
        if leverage is None: leverage = 500
        for key, val in lev_map.items():
            if key.upper() in symbol.upper():
                leverage = val if val is not None else 500
                break
                
        # Nocional para forex: qty (lotes) * contract_size (100k para forex, 100 para XAU)
        contract_size = 100 if 'XAU' in symbol else 100000
        notional = qty * contract_size * entry_price
        margin = notional / leverage if leverage and leverage > 0 else notional

    else:
        # Es Cripto / Stocks
        pnl_usd = (current_price - entry_price) * qty if is_long else (entry_price - current_price) * qty
        leverage = config.get('leverage_crypto')
        if leverage is None: leverage = 15
        notional = qty * entry_price
        margin = notional / leverage if leverage and leverage > 0 else notional

    if margin > 0:
        pnl_pct = (pnl_usd / margin) * 100
    else:
        # Fallback al % sin apalancamiento
        if entry_price > 0:
            raw_pct = ((current_price - entry_price) / entry_price * 100) if is_long else ((entry_price - current_price) / entry_price * 100)
            pnl_pct = raw_pct * (leverage if leverage else 1)

    return round(pnl_usd, 4), round(pnl_pct, 4)
