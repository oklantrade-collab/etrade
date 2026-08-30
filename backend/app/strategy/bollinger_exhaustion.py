import pandas as pd
from ta.volatility import BollingerBands
import logging

MODULE = "bollinger_exhaustion"

def check_bollinger_exhaustion(df_15m: pd.DataFrame, side: str) -> bool:
    """
    Evaluates the Bollinger Exhaustion condition on a 15m timeframe.
    Requires at least 20 candles in the dataframe.
    df_15m must have 'open', 'high', 'low', 'close' columns, chronologically ordered (oldest first).
    Returns True if the climax condition is met to partially close a position.
    """
    if df_15m is None or len(df_15m) < 20:
        return False
        
    # Calcular Bandas de Bollinger (20, 2)
    bb = BollingerBands(close=df_15m["close"], window=20, window_dev=2)
    upper_band = bb.bollinger_hband().iloc[-1]
    lower_band = bb.bollinger_lband().iloc[-1]
    
    # Extraer las últimas 3 velas
    c0 = df_15m.iloc[-1]
    c1 = df_15m.iloc[-2]
    c2 = df_15m.iloc[-3]
    
    body0 = abs(c0['close'] - c0['open'])
    body1 = abs(c1['close'] - c1['open'])
    body2 = abs(c2['close'] - c2['open'])
    
    side = side.lower()
    
    if side == 'long':
        # 1. La vela actual debe ser verde
        if c0['close'] <= c0['open']:
            return False
            
        # 2. El tamaño del cuerpo actual debe ser estrictamente mayor a los dos anteriores
        if not (body0 > body1 and body0 > body2):
            return False
            
        # 3. El cierre debe romper la Banda Superior de Bollinger
        if c0['close'] <= upper_band:
            return False
            
        return True
        
    elif side == 'short':
        # 1. La vela actual debe ser roja
        if c0['close'] >= c0['open']:
            return False
            
        # 2. El tamaño del cuerpo actual debe ser estrictamente mayor a los dos anteriores
        if not (body0 > body1 and body0 > body2):
            return False
            
        # 3. El cierre debe romper la Banda Inferior de Bollinger
        if c0['close'] >= lower_band:
            return False
            
        return True
        
    return False

def _close_oldest_position(positions: list, sb) -> bool:
    """Closes the oldest position in the list."""
    if not positions:
        return False
        
    # Ordenar por created_at o opened_at ascendente (el más viejo primero)
    # Supabase retorna fechas ISO
    sorted_pos = sorted(positions, key=lambda x: x.get('opened_at') or x.get('created_at') or '')
    oldest = sorted_pos[0]
    pos_id = oldest.get('id')
    symbol = oldest.get('symbol') or oldest.get('ticker')
    market = oldest.get('market_type') or 'crypto'
    
    if 'forex' in market:
        from app.workers.forex_execution_service import close_forex_position
        # Ctrader usa ctrader_order_id, pero nuestra funcion close_forex_position toma el position dict o ID?
        # Revisemos como cierra forex
        pass # To implement below
        
    from app.core.position_monitor import close_position as close_crypto_pos
    # TODO: Refinar la importación y llamada real para cerrar según el mercado
    
    return True

async def execute_market_bollinger_exhaustion(market: str):
    """
    Evaluates the 15m Bollinger Exhaustion rule for all open positions of the specified market.
    market can be 'crypto', 'forex', or 'stocks'.
    """
    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    
    table_name = "positions"
    if market == 'forex':
        table_name = "forex_positions"
    elif market == 'stocks':
        table_name = "stocks_positions"
        
    # 1. Obtener todas las posiciones abiertas
    res = sb.table(table_name).select("*").eq("status", "open").execute()
    open_positions = res.data or []
    if not open_positions:
        return
        
    # Agrupar por símbolo y dirección (side)
    from collections import defaultdict
    grouped = defaultdict(list)
    for pos in open_positions:
        sym = pos.get('symbol') or pos.get('ticker')
        side = pos.get('side', '').lower()
        grouped[(sym, side)].append(pos)
        
    for (sym, side), pos_list in grouped.items():
        # 2. Descargar últimas 20 velas de 15m para el símbolo
        try:
            if market == 'stocks':
                import yfinance as yf
                t = yf.Ticker(sym)
                hist = t.history(period="5d", interval="15m")
                if hist is None or len(hist) < 20:
                    continue
                df_15m = pd.DataFrame({
                    'open': hist['Open'],
                    'high': hist['High'],
                    'low': hist['Low'],
                    'close': hist['Close'],
                    'volume': hist['Volume']
                }).dropna()
            else:
                # Forex y Crypto: MEMORY_STORE (RAM) en vez de Supabase
                from app.core.memory_store import get_memory_df
                db_symbol = sym.replace("/", "").replace("-", "")
                df_mem = get_memory_df(db_symbol, "15m")
                if df_mem is None or len(df_mem) < 20:
                    # Intentar con símbolo original
                    df_mem = get_memory_df(sym, "15m")
                    if df_mem is None or len(df_mem) < 20:
                        continue
                # Tomar las últimas 20 filas
                sub_df = df_mem.tail(20)
                df_15m = pd.DataFrame({
                    'open': [float(v) for v in sub_df['open'].values],
                    'high': [float(v) for v in sub_df['high'].values],
                    'low':  [float(v) for v in sub_df['low'].values],
                    'close':[float(v) for v in sub_df['close'].values],
                })
                
            # 3. Evaluar
            if check_bollinger_exhaustion(df_15m, side):
                # 4. Obtener la más antigua y calcular su PnL en tiempo real
                sorted_pos = sorted(pos_list, key=lambda x: x.get('opened_at') or x.get('created_at') or '')
                oldest_pos = sorted_pos[0]
                pos_id = oldest_pos.get('id')
                
                current_price = float(df_15m['close'].iloc[-1])
                entry_price = float(oldest_pos.get('entry_price') or oldest_pos.get('avg_entry_price') or 0)
                is_short = side in ('short', 'sell')
                
                # Calcular PnL estimado
                pnl_usd = 0.0
                if entry_price > 0 and current_price > 0:
                    if market == 'forex':
                        pip_sz = 0.01 if 'JPY' in sym.upper() else 0.0001
                        pips = (entry_price - current_price) / pip_sz if is_short else (current_price - entry_price) / pip_sz
                        lots = abs(float(oldest_pos.get('lots') or oldest_pos.get('size') or 0.01))
                        pnl_usd = pips * 10.0 * lots
                    else:
                        qty = abs(float(oldest_pos.get('size') or oldest_pos.get('shares') or oldest_pos.get('lots') or 1.0))
                        pnl_usd = (entry_price - current_price) * qty if is_short else (current_price - entry_price) * qty

                # [ADUANA SALIDA]: Proporcional a pips / lotaje en Forex y % en Crypto (Anti-Bloqueo de Ganancias)
                min_pnl_allowed = False
                if market == 'forex':
                    min_pnl_allowed = (pips >= 1.5) or (pnl_usd >= 0.15 * max(0.01, lots) / 0.01)
                elif market == 'stocks':
                    min_pnl_allowed = (pnl_usd >= 1.00)
                else: # crypto
                    pnl_pct = ((current_price - entry_price) / entry_price * 100) if not is_short else ((entry_price - current_price) / entry_price * 100)
                    min_pnl_allowed = (pnl_pct >= 0.15) or (pnl_usd > 0)

                if not min_pnl_allowed:
                    log_info(MODULE, f"🛡️ [ADUANA SALIDA / BOLLINGER EXHAUSTION SKIP] {sym} ({side.upper()}): Agotamiento 15m detectado pero PnL insuficiente (${pnl_usd:.2f}). No se ejecuta scale-out de pos {pos_id}.")
                    continue

                log_info(MODULE, f"🔥 BOLLINGER EXHAUSTION DETECTADO: {sym} ({side.upper()}) en 15m con PnL +${pnl_usd:.2f}. Iniciando Scale-Out (Cierre de la posición más antigua {pos_id}).")
                
                if market == 'stocks':
                    # stocks usa su propio mecanismo de cierre
                    from app.stocks.stocks_tp_manager import execute_tp_sell
                    order_payload = {
                        "ticker": sym,
                        "type": "market",
                        "side": "sell" if side == "long" else "buy",
                        "shares": oldest_pos.get("shares", 0),
                        "price": current_price,
                        "status": "pending",
                        "reason": "bollinger_exhaustion_15m"
                    }
                    o_res = sb.table("stocks_orders").insert(order_payload).execute()
                    if o_res.data:
                        log_info(MODULE, f"✅ Orden de cierre de agotamiento Bollinger enviada para {sym} (ID pos: {pos_id})")
                        
                elif market == 'forex':
                    from app.execution.order_manager import close_position as close_crypto_forex
                    close_crypto_forex(pos_id, reason="bollinger_exhaustion_15m")
                    log_info(MODULE, f"✅ Orden de cierre enviada para Forex {sym} (ID pos: {pos_id})")
                    
                elif market == 'crypto':
                    from app.execution.order_manager import close_position as close_crypto_forex
                    close_crypto_forex(pos_id, reason="bollinger_exhaustion_15m")
                    log_info(MODULE, f"✅ Orden de cierre enviada para Crypto {sym} (ID pos: {pos_id})")
                    
        except Exception as e:
            import traceback
            log_error(MODULE, f"Error evaluando exhaustion para {sym}: {e}\n{traceback.format_exc()}")

