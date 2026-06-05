import asyncio
import os
import sys
import pandas as pd
from datetime import datetime, timezone

# Ensure backend root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.execution.provider_factory import create_provider
from app.core.logger import log_info

async def run_apex_ema_simulation():
    print("=" * 70)
    print("📈 SIMULACIÓN APEX_EMA (ÚLTIMAS 8 HORAS) - CRYPTO Y FOREX 📈")
    print("=" * 70)
    
    # 1. Configuración de Proveedores
    provider_crypto = create_provider('crypto_futures')
    provider_forex = create_provider('forex_futures')
    
    # Conectamos Forex
    print("Conectando con cTrader para Forex...")
    forex_connected = False
    try:
        forex_connected = await provider_forex.connect()
    except Exception as e:
        print(f"cTrader conexión error: {e}")
        
    print(f"cTrader conexión: {'ÉXITO' if forex_connected else 'FALLIDO'}")
    
    symbols_to_simulate = [
        {'symbol': 'BTCUSDT', 'market': 'crypto', 'provider': provider_crypto},
        {'symbol': 'ETHUSDT', 'market': 'crypto', 'provider': provider_crypto},
    ]
    
    if forex_connected:
        symbols_to_simulate.append({'symbol': 'EURUSD', 'market': 'forex', 'provider': provider_forex})
        symbols_to_simulate.append({'symbol': 'GBPUSD', 'market': 'forex', 'provider': provider_forex})
        
    for s_info in symbols_to_simulate:
        symbol = s_info['symbol']
        market = s_info['market']
        provider = s_info['provider']
        
        print("\n" + "=" * 60)
        print(f"🔍 SIMULANDO PAR: {symbol} ({market.upper()})")
        print("=" * 60)
        
        # Descargamos 250 velas de 15m para tener suficiente lookback para EMA200
        print("Descargando velas históricas de 15m...")
        df_raw = await provider.get_ohlcv(symbol, '15m', limit=250)
        
        if df_raw is None or df_raw.empty:
            print(f"❌ Error: No se pudieron obtener velas para {symbol}")
            continue
            
        print(f"Velas obtenidas: {len(df_raw)}")
        
        # 2. Calcular EMAs
        df = df_raw.copy()
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # Las últimas 8 horas equivalen a 32 velas de 15 minutos (8 * 4)
        sim_length = min(32, len(df) - 100)
        start_idx = len(df) - sim_length
        
        print(f"Simulando {sim_length} velas (últimas 8 horas)...")
        
        active_position = None  # None o dict {'entry': float, 'sl': float, 'side': str, 'orders': list}
        pending_limits = []    # list of dict {'price': float, 'name': str, 'size_pct': int, 'side': str}
        
        placed_orders_count = 0
        executed_orders_count = 0
        cancelled_orders_count = 0
        trailing_stop_updates = 0
        er_transitions = 0
        
        for idx in range(start_idx, len(df)):
            window = df.iloc[:idx+1]
            last = window.iloc[-1]
            
            # Indicadores actuales
            ema3 = float(last['ema3'])
            ema9 = float(last['ema9'])
            ema20 = float(last['ema20'])
            ema50 = float(last['ema50'])
            ema200 = float(last['ema200'])
            ema200_3 = float(window.iloc[-4]['ema200'])
            
            close_price = float(last['close'])
            open_price = float(last['open'])
            high_price = float(last['high'])
            low_price = float(last['low'])
            
            # Extraer fecha/hora del índice o de la columna
            time_val = last.name if hasattr(last, 'name') and last.name is not None else 'unknown'
            if hasattr(time_val, 'strftime'):
                time_str = time_val.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = str(time_val)
            
            # --- A. EVALUAR ÓRDENES PENDIENTES ---
            if pending_limits:
                # Cancelación preventoria
                cancel_long = (ema3 < ema9)
                cancel_short = (ema3 > ema9)
                
                direction = pending_limits[0]['side']
                if (direction == 'LONG' and cancel_long) or (direction == 'SHORT' and cancel_short):
                    print(f" [{time_str}] 🧹 CANCEL PENDING: Canceladas las limit orders pendientes de {direction} por reversión rápida (EMA3/EMA9).")
                    pending_limits = []
                    cancelled_orders_count += 1
                else:
                    # Verificar ejecución
                    still_pending = []
                    for po in pending_limits:
                        limit_px = po['price']
                        hit = False
                        if po['side'] == 'LONG':
                            hit = (low_price <= limit_px)
                        else:
                            hit = (high_price >= limit_px)
                            
                        if hit:
                            print(f" [{time_str}] 🚀 EXEC LIMIT: Ejecutada {po['name']} de {po['side']} a ${limit_px:.4f} (lotes/size: {po['size_pct']}%).")
                            executed_orders_count += 1
                            
                            # Crear o añadir capa a la posición activa
                            if active_position is None:
                                active_position = {
                                    'entry': limit_px,
                                    'side': po['side'],
                                    'sl': 0.0,
                                    'layers': [limit_px],
                                    'status': 'open'
                                }
                            else:
                                active_position['layers'].append(limit_px)
                                active_position['entry'] = sum(active_position['layers']) / len(active_position['layers'])
                        else:
                            still_pending.append(po)
                    pending_limits = still_pending
            
            # --- B. GESTIONAR POSICIÓN ACTIVA (TRAILING Y EREP) ---
            if active_position and active_position['status'] == 'open':
                side = active_position['side']
                
                # Traspaso proactivo a EREP por reversión de tendencia
                reversal = (side == 'LONG' and ema3 < ema9) or (side == 'SHORT' and ema3 > ema9)
                if reversal:
                    print(f" [{time_str}] ⚠️ EREP HANDOVER: Cruce adverso detectado. Traspasando posición {side} (Entry Avg: ${active_position['entry']:.4f}) al motor de recuperación EREP Fase 2.")
                    active_position['status'] = 'erep_fase2'
                    er_transitions += 1
                    continue
                    
                # Trailing Stop adaptativo en velas a favor de tendencia
                if side == 'LONG':
                    if close_price > open_price and close_price > ema3:
                        if active_position['sl'] == 0 or close_price > active_position['sl']:
                            active_position['sl'] = close_price
                            print(f" [{time_str}] 🛡️ TRAILING SL: Moviendo SL LONG a ${close_price:.4f} (Cierre vela verde > EMA3).")
                            trailing_stop_updates += 1
                else:
                    if close_price < open_price and close_price < ema3:
                        if active_position['sl'] == 0 or close_price < active_position['sl']:
                            active_position['sl'] = close_price
                            print(f" [{time_str}] 🛡️ TRAILING SL: Moviendo SL SHORT a ${close_price:.4f} (Cierre vela roja < EMA3).")
                            trailing_stop_updates += 1
                            
            # --- C. GATILLAR NUEVAS ÓRDENES LÍMITE ---
            if active_position is None and not pending_limits:
                trigger_long = (ema3 > ema9) and (ema9 > ema20) and (ema50 > ema200) and (ema200 > ema200_3)
                trigger_short = (ema3 < ema9) and (ema9 < ema20) and (ema50 < ema200) and (ema200 < ema200_3)
                
                if trigger_long or trigger_short:
                    direction = 'LONG' if trigger_long else 'SHORT'
                    rule = 'AaApexEma' if trigger_long else 'BbApexEma'
                    dist_pct = abs(ema9 - ema20) / ema20
                    
                    print(f" [{time_str}] 🎯 TRIGGER {direction} ({rule}): EMA Ribbon faneada. Pendiente EMA200 positiva.")
                    print(f"   Valores: EMA3={ema3:.4f}, EMA9={ema9:.4f}, EMA20={ema20:.4f}, EMA200={ema200:.4f}, EMA200_3={ema200_3:.4f}")
                    
                    if dist_pct >= 0.004:
                        print(f"   Distancia EMA9-EMA20 es {dist_pct*100:.2f}% (>= 0.4%). Colocando 2 órdenes limitadas (Sizing 40/60).")
                        pending_limits = [
                            {'price': ema9, 'name': 'Order 1 (EMA9)', 'size_pct': 40, 'side': direction},
                            {'price': ema20, 'name': 'Order 2 (EMA20)', 'size_pct': 60, 'side': direction}
                        ]
                    else:
                        print(f"   Distancia EMA9-EMA20 es {dist_pct*100:.2f}% (< 0.4%). Colocando 1 sola orden consolidada en EMA9 (Sizing 100%).")
                        pending_limits = [
                            {'price': ema9, 'name': 'Order 1 Consolidada (EMA9)', 'size_pct': 100, 'side': direction}
                        ]
                    placed_orders_count += len(pending_limits)
        
        # Resumen del par
        print(f"\n📊 RESUMEN SIMULACIÓN {symbol}:")
        print(f"  - Órdenes Límite colocadas: {placed_orders_count}")
        print(f"  - Órdenes Límite ejecutadas: {executed_orders_count}")
        print(f"  - Órdenes canceladas por reversión: {cancelled_orders_count}")
        print(f"  - Actualizaciones de Trailing Stop: {trailing_stop_updates}")
        print(f"  - Traspasos proactivos al motor EREP: {er_transitions}")
        
    if forex_connected:
        try:
            await provider_forex.disconnect()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(run_apex_ema_simulation())
