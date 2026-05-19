"""
Forex Execution Service v1.2 - Multiple Positions Support
Supports up to 4 concurrent positions per symbol.
"""

import os
import time
import traceback
from datetime import datetime, timezone, timedelta

from ctrader_open_api import Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *

from app.strategy.proactive_exit import evaluate_proactive_exit
from app.strategy.capital_protection import (
    ProtectionState,
    evaluate_all_protections,
    PROTECTION_CONFIG
)
from app.strategy.forex_adaptive_exit import evaluate_forex_tp, evaluate_forex_sl
from app.core.safety_manager import register_sl_event, reset_sl_counter

#    Configuracion                                 
def get_forex_config():
    """Obtiene la configuracion de riesgo de Forex desde Supabase"""
    try:
        from app.core.supabase_client import get_risk_config
        config = get_risk_config()
        return {
            'capital_usd': float(config.get('forex_capital', 5000.0)),
            'risk_per_trade_pct': float(config.get('forex_risk_per_trade_pct', 1.0)),
            'max_total_risk_pct': float(config.get('forex_max_total_risk_pct', 30.0)),
            'leverage': int(config.get('forex_leverage', 500))
        }
    except:
        return {'capital_usd': 5000.0, 'risk_per_trade_pct': 1.0, 'max_total_risk_pct': 30.0, 'leverage': 500}

PIP_CONFIG = {
    'EURUSD': {'pip': 0.0001, 'pip_val_std': 10.0},
    'GBPUSD': {'pip': 0.0001, 'pip_val_std': 10.0},
    'USDJPY': {'pip': 0.01,   'pip_val_std': 6.5},
    'XAUUSD': {'pip': 0.01,   'pip_val_std': 1.0, 'contract': 100}, 
}

def normalize_forex_price(symbol, price):
    # El usuario confirma que el precio de 4600+ es correcto, no dividir.
    return price

#    HARD CAP: Perdida maxima absoluta por trade   
# Si se excede CUALQUIERA de estos limites, se cierra inmediatamente
# sin esperar confirmaciones tecnicas.
HARD_CAP_LOSS_PIPS = {
    'EURUSD': 40,
    'GBPUSD': 60,   # Aumentado de 40 a 60 pips por la volatilidad natural de la Libra (Cable)
    'USDJPY': 100, # Aumentado de 40 a 100 pips para dar espacio a la alta volatilidad del Yen
    'XAUUSD': 1200, # Aumentado de 80 a 1200 pips ($12.00 USD) para dar margen a la volatilidad del Oro
}
HARD_CAP_LOSS_USD = 25.0  # Pérdida máxima de emergencia en USD por trade
MAX_SL_PIPS = {
    'EURUSD': 30,
    'GBPUSD': 50,   # Aumentado de 30 a 50 pips para evitar salidas prematuras en la Libra
    'USDJPY': 80,  # Aumentado de 30 a 80 pips para evitar cierres prematuros en el Yen
    'XAUUSD': 1000, # Aumentado de 60 a 1000 pips ($10.00 USD) para evitar cierres prematuros en Oro
}

class ForexExecutionService:
    def __init__(self, worker, supabase_client, state_ref, symbols_ref):
        self.worker   = worker
        self.sb       = supabase_client
        self.state    = state_ref
        self.symbols  = symbols_ref
        self.log      = worker.log
        self.protection_states = {} # Cache de estados de proteccion
        # Usar variable de entorno directamente para el modo
        self.mode     = os.getenv('CTRADER_ENV', 'paper')
        self._open_positions_list = []
        self._load_open_positions()

    def _safe_float(self, val, default=0.0):
        try:
            if val is None: return default
            return float(val)
        except: return default

    def _load_open_positions(self, retries=3):
        for i in range(retries):
            try:
                res = self.sb.table('forex_positions').select('*').eq('status', 'open').execute()
                self._open_positions_list = res.data or []
                self.log(f'Posiciones abiertas cargadas: {len(self._open_positions_list)}')
                return
            except Exception as e:
                self.log(f'[WARNING] Reintentando DB ({i+1}/{retries}) en 5s por error: {e}', 'WARNING')
                if i < retries - 1:
                    import time
                    time.sleep(5)
                else:
                    self.log(f'[ERROR] Error critico cargando posiciones tras {retries} intentos: {e}', 'ERROR')
                    self._open_positions_list = []

    def run_evaluation_cycle(self):
        try:
            # 1. Recargar posiciones frescas desde DB para evitar discrepancias
            self._load_open_positions()
            
            # Verificación de Día y Hora para Protecciones en Forex (Viernes 3 PM GMT-5 es 20:00 UTC)
            now = datetime.now(timezone.utc)
            weekday = now.weekday()  # 4 = Viernes, 6 = Domingo
            hour = now.hour

            # A. Bloqueo de Nuevas Entradas el Viernes a partir de las 3:00 PM local (20:00 UTC)
            if weekday == 4 and hour >= 20:
                self.log("⚠️ [PROTECCIÓN VIERNES] Bloqueo de nuevas señales activo después de las 3:00 PM local.")
                return

            # B. Filtro de Estabilización de Reapertura Dominical (22:00 a 23:59 UTC)
            if weekday == 6 and hour >= 22:
                self.log("⏳ [ESTABILIZACIÓN DOMINGO] Esperando normalización de spreads dominicales. Nuevas señales omitidas.")
                return

            open_count = len(self._open_positions_list)

            # 2. Cargar config de riesgo dinamica
            from app.core.supabase_client import get_risk_config
            risk_config = get_risk_config()
            limit_per_symbol = int(risk_config.get('max_positions_per_symbol', 4))
            limit_global = int(risk_config.get('max_total_positions', 16))
            max_retries = 3

            if open_count >= limit_global:
                self.log(f'Limite global de posiciones alcanzado ({open_count}/{limit_global})')
                return

            pos_count = {}
            for p in self._open_positions_list:
                s = p['symbol']
                pos_count[s] = pos_count.get(s, 0) + 1

            symbols = list(self.state['symbol_ids'].keys()) or self.symbols
            
            # 3. Obtener snapshots con reintentos por desconexion
            snaps_data = []
            for attempt in range(max_retries):
                try:
                    snaps_res = self.sb.table('market_snapshot').select('*').in_('symbol', symbols).execute()
                    snaps_data = snaps_res.data or []
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.log(f'Reintentando Market Snapshot ({attempt+1}/{max_retries}): {e}', 'WARNING')
                        time.sleep(2)
                    else:
                        raise e
            
            summary = ", ".join([f"{s}: {pos_count.get(s,0)}" for s in symbols])
            self.log(f'Evaluando {len(snaps_data)} simbolos. Total: {open_count} | {summary} (Limite/Simbolo: {limit_per_symbol})')

            for snap in snaps_data:
                symbol = snap['symbol']
                count = pos_count.get(symbol, 0)
                if count >= limit_per_symbol:
                    if count > limit_per_symbol:
                        self.log(f"[EXCESO] Detectado en {symbol}: {count} > {limit_per_symbol}", "WARNING")
                    continue 
                
                self._evaluate_symbol(snap)

        except Exception as e:
            self.log(f'Error en ciclo evaluacion: {e}', 'ERROR')

    def _evaluate_symbol(self, snap: dict):
        try:
            context = self._build_context(snap)
            for direction in ['long', 'short']:
                signal = self._check_rules(context, direction)
                if signal and signal['triggered']:
                    self.log(f'[SIGNAL] {direction.upper()} {snap["symbol"]}: {signal["rule_code"]}')
                    self._execute_signal(snap['symbol'], direction, signal, snap)
                    break
        except Exception as e:
            self.log(f'{snap["symbol"]} evaluacion error: {e}', 'ERROR')

    def _build_context(self, snap: dict) -> dict:
        price = self._safe_float(snap.get('price'))
        adx = self._safe_float(snap.get('adx'), 25.0)
        if adx < 20: velocity = 'debil'
        elif adx < 35: velocity = 'moderado'
        elif adx < 50: velocity = 'agresivo'
        else: velocity = 'explosivo'

        mtf_score = self._safe_float(snap.get('mtf_score'))

        return {
            'symbol': snap.get('symbol'),
            'price': price,
            'basis': self._safe_float(snap.get('basis'), price),
            'dist_basis_pct': self._safe_float(snap.get('dist_basis_pct')),
            'adx': adx,
            'adx_velocity': velocity,
            'mtf_score': mtf_score,
            'sar_trend_4h': int(snap.get('sar_trend_4h') or 0),
            'sar_trend_15m': int(snap.get('sar_trend_15m') or 0),
            'sar_phase': str(snap.get('sar_phase') or 'neutral'),
            'fibonacci_zone': int(snap.get('fibonacci_zone') or 0),
            'pinescript_signal': str(snap.get('pinescript_signal') or ''),
            'allow_long_4h': bool(snap.get('allow_long_4h') if snap.get('allow_long_4h') is not None else True),
            'allow_short_4h': bool(snap.get('allow_short_4h') if snap.get('allow_short_4h') is not None else True),
            'upper_1': self._safe_float(snap.get('upper_1')),
            'lower_1': self._safe_float(snap.get('lower_1')),
            'upper_6': self._safe_float(snap.get('upper_6')),
            'lower_6': self._safe_float(snap.get('lower_6')),
            'ema_3': self._safe_float(snap.get('ema_3')),
            'ema_9': self._safe_float(snap.get('ema_9')),
            'ema_20': self._safe_float(snap.get('ema_20')),
            'bb_expanding': bool(snap.get('bb_expanding', False)),
        }

    def _check_rules(self, context: dict, direction: str) -> dict:
        results = []
        sar_4h = context['sar_trend_4h']
        sar_15m = context['sar_trend_15m']
        mtf = context['mtf_score']
        pine = context['pinescript_signal']
        struct_ok = context['allow_long_4h'] if direction == 'long' else context['allow_short_4h']
        fib_zone = context['fibonacci_zone']

        if direction == 'long':
            sar_4h_ok, sar_15m_ok = sar_4h > 0, sar_15m > 0
            mtf_ok, pine_ok = mtf >= 0.25, pine == 'Buy'
            pine_not_opposite = pine != 'Sell'
            mtf_directional = mtf > 0  # Al menos momentum positivo
        else:
            sar_4h_ok, sar_15m_ok = sar_4h < 0, sar_15m < 0
            mtf_ok, pine_ok = mtf <= -0.25, pine == 'Sell'
            pine_not_opposite = pine != 'Buy'
            mtf_directional = mtf < 0  # Al menos momentum negativo

        # Aa31/Bb31: SAR alignment + Momentum + No opposite Pine (STRICT - Require MTF alignment)
        # REFINAMIENTO V2: Añadimos filtro de ADX y confirmación de EMAs rápidas para evitar fakeouts en XAUUSD.
        rule_alignment_triggered = False
        adx   = context.get('adx', 0)
        ema3  = context.get('ema_3', 0)
        ema9  = context.get('ema_9', 0)
        
        symbol = context.get('symbol', '')
        ema20 = context.get('ema_20', 0)
        
        # Símbolos que requieren alineación estricta y cascada de EMAs
        strict_symbols = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']
        
        price = context.get('price', 0)
        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)

        # Ventanas de pullback dinámicas en pips por volatilidad (Evita falsas señales y cuchillos caídos)
        PULLBACK_WINDOW_PIPS = {
            'EURUSD': 5,
            'GBPUSD': 5,
            'USDJPY': 15,
            'XAUUSD': 50,
        }
        pb_pips = PULLBACK_WINDOW_PIPS.get(symbol, 5)

        if direction == 'long':
            # Long: SAR 15m alcista Y (SAR 4h alcista O MTF >= 0.5) Y MTF >= 0.4 Y no opuesto Pine Y no en techo Y ADX > 25 Y pullback confirmado
            if symbol in strict_symbols:
                # REFINAMIENTO V4: Entrada en pullback ordenado (precio entre EMA20 y EMA9 + pb_pips) + gatillo de ruptura de EMA3 + confirmación de giro (EMA3 > EMA9)
                # NOTA CRÍTICA: Se exige (ema3 > ema9) para evitar el bucle de cierre inmediato del stop de protección contrario
                pullback_confirmed = (ema9 > ema20) and (ema20 <= price <= ema9 + (pb_pips * pip_size)) and (price > ema3) and (ema3 > ema9) if (ema3 and ema9 and ema20) else True
                rule_alignment_triggered = (
                    sar_15m_ok and sar_4h_ok and 
                    mtf >= 0.4 and pine_not_opposite and 
                    struct_ok and fib_zone <= 3 and 
                    adx > 25 and pullback_confirmed
                )
            else:
                rule_alignment_triggered = (
                    sar_15m_ok and (sar_4h_ok or mtf >= 0.5) and 
                    mtf >= 0.4 and pine_not_opposite and 
                    struct_ok and fib_zone <= 3 and 
                    adx > 25 and (ema3 > ema9 if ema3 and ema9 else True)
                )
        else:
            # Short: SAR 15m bajista Y (SAR 4h bajista O MTF <= -0.5) Y MTF <= -0.4 Y no opuesto Pine Y no en piso Y ADX > 25 Y pullback confirmado
            if symbol in strict_symbols:
                # REFINAMIENTO V4: Entrada en pullback ordenado (precio entre EMA9 - pb_pips y EMA20) + gatillo de ruptura de EMA3 + confirmación de giro (EMA3 < EMA9)
                # NOTA CRÍTICA: Se exige (ema3 < ema9) para evitar el bucle de cierre inmediato del stop de protección contrario
                pullback_confirmed = (ema9 < ema20) and (ema9 - (pb_pips * pip_size) <= price <= ema20) and (price < ema3) and (ema3 < ema9) if (ema3 and ema9 and ema20) else True
                rule_alignment_triggered = (
                    sar_15m_ok and sar_4h_ok and 
                    mtf <= -0.4 and pine_not_opposite and 
                    struct_ok and fib_zone >= -3 and 
                    adx > 25 and pullback_confirmed
                )
            else:
                rule_alignment_triggered = (
                    sar_15m_ok and (sar_4h_ok or mtf <= -0.5) and 
                    mtf <= -0.4 and pine_not_opposite and 
                    struct_ok and fib_zone >= -3 and 
                    adx > 25 and (ema3 < ema9 if ema3 and ema9 else True)
                )

        results.append({
            'rule_code': 'Aa31a' if direction == 'long' else 'Bb31a', 
            'triggered': rule_alignment_triggered, 
            'score': 0.7
        })

        # NUEVA REGLA: HOT_MOMENTUM (Especifica y Quirurgica)
        ema3, ema9, ema20 = context.get('ema_3'), context.get('ema_9'), context.get('ema_20')
        bb_exp = context.get('bb_expanding', False)
        
        hot_triggered = False
        if ema3 and ema9 and ema20:
            if direction == 'long':
                # LONG: EMA3 > EMA9 > EMA20 + (Bollinger abri ndose O MTF fuerte) + MTF Aligned
                hot_triggered = (ema3 > ema9 > ema20) and (bb_exp or mtf >= 0.5) and (-6 <= fib_zone <= 3) and sar_15m_ok and mtf > 0
            else:
                # SHORT: EMA3 < EMA9 < EMA20 + (Bollinger abri ndose O MTF fuerte) + MTF Aligned
                hot_triggered = (ema3 < ema9 < ema20) and (bb_exp or mtf <= -0.5) and (-6 <= fib_zone <= 3) and sar_15m_ok and mtf < 0

        results.append({
            'rule_code': 'Aa_HOT' if direction == 'long' else 'Bb_HOT',
            'triggered': hot_triggered,
            'score': 0.95 # Alta prioridad
        })

        # NUEVA ESTRATEGIA: Aa61 (Squeeze Breakout / Bollinger Explosion)
        explosion_triggered = False
        if ema3 and ema9 and ema20:
            if direction == 'long':
                # LONG Aa61: Expansión de Bollinger + cruce de EMAs alcista + precio sobre Basis + ADX > 20
                explosion_triggered = (
                    ema3 > ema9 > ema20 and
                    price > ema20 and
                    bb_exp and
                    adx > 20 and
                    sar_15m_ok and
                    pine_not_opposite and
                    fib_zone <= 3
                )
            else:
                # SHORT Aa61_short: Expansión de Bollinger + cruce de EMAs bajista + precio bajo Basis + ADX > 20
                explosion_triggered = (
                    ema3 < ema9 < ema20 and
                    price < ema20 and
                    bb_exp and
                    adx > 20 and
                    sar_15m_ok and
                    pine_not_opposite and
                    fib_zone >= -3
                )

        results.append({
            'rule_code': 'Aa61' if direction == 'long' else 'Aa61_short',
            'triggered': explosion_triggered,
            'score': 0.98 # Prioridad ultra alta
        })

        # Dd Reversal: Solo si alinea con tendencia 4h (sar_4h_ok)
        fib_reversal = (direction == 'long' and fib_zone <= -2) or (direction == 'short' and fib_zone >= 2)
        
        # Propuesta 2: Filtro de fuerza de contratendencia (Evitar cuchillos caídos)
        # Si la tendencia contraria es ultra-fuerte (ADX > 35) y alineada en contra, se bloquea la entrada Swing.
        adx_val = context.get('adx', 0)
        strong_contratrend = (
            (direction == 'long' and adx_val > 35 and mtf <= -0.5) or
            (direction == 'short' and adx_val > 35 and mtf >= 0.5)
        )
        
        # NUEVA LÓGICA SWING AVANZADA (SIPV + Giro de Bandas de Bollinger + RSI)
        from app.core.memory_store import MEMORY_STORE
        df_15m = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
        
        swing_triggered = False
        
        if df_15m is not None and len(df_15m) >= 6:
            last_row = df_15m.iloc[-1].to_dict()
            
            if direction == 'long':
                # Swing Long (Dd21_15m): 
                # 1. Pendiente de lower_6 plana o girando alcista
                lower6_flat = False
                lower6_slope = 0.0
                if 'lower_6' in df_15m.columns:
                    lower6_now = float(df_15m['lower_6'].iloc[-1])
                    lower6_prev = float(df_15m['lower_6'].iloc[-5])
                    if lower6_prev > 0:
                        lower6_slope = (lower6_now - lower6_prev) / lower6_prev * 100
                        lower6_flat = lower6_slope >= -0.15
                
                # 2. Señal SIPV de reversión alcista
                sipv_signal = (
                    bool(last_row.get('is_dragonfly', False)) or
                    bool(last_row.get('is_bullish_engulfing', False)) or
                    bool(last_row.get('low_higher_than_prev', False)) or
                    bool(last_row.get('is_doji', False))
                )
                
                # 3. RSI en sobreventa (<= 35)
                rsi_val = float(last_row.get('rsi_14', 30.0))
                rsi_ok = rsi_val <= 35
                
                # 4. Precio interactuando con banda lower_5 o inferior
                lower5 = float(last_row.get('lower_5', 0))
                near_support = price <= lower5 if lower5 > 0 else True
                
                swing_triggered = (
                    lower6_flat and sipv_signal and rsi_ok and near_support and
                    sar_15m_ok and sar_4h_ok and struct_ok and not strong_contratrend
                )
            else:
                # Swing Short (Dd11_15m):
                # 1. Pendiente de upper_6 plana o girando bajista
                upper6_flat = False
                upper6_slope = 0.0
                if 'upper_6' in df_15m.columns:
                    upper6_now = float(df_15m['upper_6'].iloc[-1])
                    upper6_prev = float(df_15m['upper_6'].iloc[-5])
                    if upper6_prev > 0:
                        upper6_slope = (upper6_now - upper6_prev) / upper6_prev * 100
                        upper6_flat = upper6_slope <= 0.15
                
                # 2. Señal SIPV de reversión bajista
                sipv_signal = (
                    bool(last_row.get('is_gravestone', False)) or
                    bool(last_row.get('is_bearish_engulfing', False)) or
                    bool(last_row.get('high_lower_than_prev', False)) or
                    bool(last_row.get('is_doji', False))
                )
                
                # 3. RSI en sobrecompra (>= 65)
                rsi_val = float(last_row.get('rsi_14', 70.0))
                rsi_ok = rsi_val >= 65
                
                # 4. Precio interactuando con banda upper_5 o superior
                upper5 = float(last_row.get('upper_5', 0))
                near_resistance = price >= upper5 if upper5 > 0 else True
                
                swing_triggered = (
                    upper6_flat and sipv_signal and rsi_ok and near_resistance and
                    sar_15m_ok and sar_4h_ok and struct_ok and not strong_contratrend
                )
        else:
            # Fallback en caso de no tener histórico en memoria (mantiene la lógica básica)
            swing_triggered = fib_reversal and sar_15m_ok and sar_4h_ok and struct_ok and not strong_contratrend

        results.append({
            'rule_code': 'Dd21_15m' if direction == 'long' else 'Dd11_15m', 
            'triggered': swing_triggered, 
            'score': 0.9
        })

        triggered = [r for r in results if r.get('triggered')]
        return max(triggered, key=lambda x: x['score']) if triggered else None

    def _execute_signal(self, symbol, direction, signal, snap):
        # CHECK 0: Bloqueos de Seguridad por Subprocesos
        from app.core.safety_manager import is_forex_safety_blocked, check_db_safety_block
        if is_forex_safety_blocked() or check_db_safety_block('forex_futures'):
            self.log(f"⚠️ ORDEN ABORTADA para {symbol} ({direction.upper()}): El sistema de validación de seguridad (15-min Safety Checklist) tiene un bloqueo activo para FOREX.", "CRITICAL")
            return

        # 1. Reglas Multi-layer (Misma estrategia)
        same_strat = [p for p in self._open_positions_list if p['symbol'] == symbol and p['rule_code'] == signal['rule_code']]
        
        if same_strat:
            # Regla 1: 1 compra por vela (usamos 15 min como est ndar solicitado)
            last_pos = sorted(same_strat, key=lambda x: x['opened_at'], reverse=True)[0]
            opened_at_str = str(last_pos['opened_at'])
            if 'Z' in opened_at_str: opened_at_str = opened_at_str.replace('Z', '+00:00')
            opened_at = datetime.fromisoformat(opened_at_str)
            now = datetime.now(timezone.utc)
            
            if (now - opened_at).total_seconds() < 900: # 15 minutos
                 self.log(f'Omitiendo {symbol} {signal["rule_code"]}: Ya hay una abierta en los ultimos 15 min.')
                 return
            
            # Regla 2: Mejora de precio (DCA)
            price = self._safe_float(snap.get('price'))
            last_entry = self._safe_float(last_pos.get('entry_price'))
            if direction == 'long' and price >= last_entry:
                 self.log(f'[WAIT] Omitiendo {symbol} {direction.upper()}: Precio {price} >= {last_entry} (No mejora costo)')
                 return
            if direction == 'short' and price <= last_entry:
                 self.log(f'[WAIT] Omitiendo {symbol} {direction.upper()}: Precio {price} <= {last_entry} (No mejora costo)')
                 return
            
            self.log(f'Agregando CAPA {len(same_strat)+1} para {symbol} ({signal["rule_code"]})')

        # 2. Spam Protection: Verificar historial reciente (Cerradas)
        try:
            # Consultar  ltimas posiciones cerradas del mismo s mbolo y estrategia en los  ltimos 15 min
            since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
            hist = self.sb.table('forex_positions')\
                .select('opened_at')\
                .eq('symbol', symbol)\
                .eq('rule_code', signal['rule_code'])\
                .gte('opened_at', since)\
                .order('opened_at', desc=True)\
                .limit(1).execute()
            
            if hist.data:
                last_hist = hist.data[0]
                hist_at_str = str(last_hist['opened_at']).replace('Z', '+00:00')
                hist_at = datetime.fromisoformat(hist_at_str)
                if (datetime.now(timezone.utc) - hist_at).total_seconds() < 900:
                    self.log(f'Omitiendo {symbol} {signal["rule_code"]}: Spam protection (Cerrada recientemente, cool-down 15min active).')
                    return
        except Exception as e:
            self.log(f"Error checking position history: {e}", "WARNING")

        # 3. Guardian final: Limite TOTAL por simbolo (Para todas las estrategias)
        total_symbol = len([p for p in self._open_positions_list if p['symbol'] == symbol])
        from app.core.supabase_client import get_risk_config
        max_per_symbol = int(get_risk_config().get('max_positions_per_symbol', 4))
        if total_symbol >= max_per_symbol:
            self.log(f'LIMITE TOTAL ALCANZADO para {symbol}: {total_symbol}/{max_per_symbol} posiciones.', 'WARNING')
            return

        # 4. Calcular parámetros e idoneidad de la nueva orden ANTES de revertir
        price = self._safe_float(snap.get('price'))
        sl, tp, sl_pips = self._calculate_sl_tp(symbol, direction, price, snap, signal["rule_code"])
        lots = self._calculate_lot_size(symbol, sl_pips)

        f_config = get_forex_config()
        riesgo_limite = f_config['capital_usd'] * f_config['risk_per_trade_pct'] / 100
        pip_val = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
        riesgo_real = lots * sl_pips * pip_val

        # Verificar Riesgo Total Acumulado (Máximo 30%)
        total_risk_usd = 0
        for p in self._open_positions_list:
            try:
                p_lots = abs(self._safe_float(p.get('lots')))
                p_entry = self._safe_float(p.get('entry_price'))
                p_sl = self._safe_float(p.get('sl_price'), p_entry)
                p_pip_size = PIP_CONFIG.get(p['symbol'], {}).get('pip', 0.0001)
                p_pip_val = PIP_CONFIG.get(p['symbol'], {}).get('pip_val_std', 10.0)
                total_risk_usd += p_lots * abs(p_entry - p_sl) / p_pip_size * p_pip_val
            except: continue

        max_accumulated = f_config['capital_usd'] * f_config['max_total_risk_pct'] / 100
        
        if (total_risk_usd + riesgo_real) > max_accumulated:
            self.log(f'RIESGO TOTAL EXCEDIDO (${total_risk_usd:.2f} + ${riesgo_real:.2f} > ${max_accumulated:.2f}). Nueva señal abortada sin revertir.', 'WARNING')
            return

        if riesgo_real > (riesgo_limite * 1.5): # Margen de holgura por el mínimo de 0.01 lotes
            self.log(
                f'ABORTANDO {symbol}: Riesgo proyectado ${riesgo_real:.2f} '
                f'excede el límite de ${riesgo_limite:.2f} '
                f'(SL Pips: {sl_pips:.1f}, Lots: {lots}). Sin revertir.',
                'WARNING'
            )
            return

        # 5. Reversion forzada condicional con exclusión estricta de Swing (Hedge OFF) - MANDATORIO
        opposite = 'short' if direction == 'long' else 'long'
        opp_positions = [p for p in self._open_positions_list if p['symbol'] == symbol and p['side'].lower() == opposite]
        
        opp_to_close = []
        for p in opp_positions:
            p_rule = (p.get('rule_code') or '').lower()
            if 'dd11' in p_rule or 'dd21' in p_rule:
                self.log(f"[SWING SAFE] Omitiendo cierre por reversión para la posición Swing {p['id']} ({p_rule})")
                continue
            opp_to_close.append(p)

        if opp_to_close:
            self.log(f'[REVERSION] Cerrando {len(opp_to_close)} posiciones {opposite.upper()} por entrada {direction.upper()} viable')
            for p in opp_to_close:
                entry = self._safe_float(p.get('entry_price'))
                lots_abs = abs(self._safe_float(p.get('lots'), 0.01))
                pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
                
                side = p.get('side', 'long').lower()
                pips = (price - entry)/pip_size if side == 'long' else (entry - price)/pip_size
                self._close_position(p, price, f'reversal_{direction}', pips)
            # Recargar posiciones tras cerrar opuestas
            self._load_open_positions()

        # 6. Ejecutar nueva señal
        self.log(f'[ORDEN] {direction.upper()} {symbol} ({signal["rule_code"]}): lots={lots} risk=${riesgo_real:.2f}')
        if self.mode == 'live': self._execute_live_order(symbol, direction, lots, price, sl, tp, signal['rule_code'])
        else: self._execute_paper_order(symbol, direction, lots, price, sl, tp, signal['rule_code'])

    def _calculate_lot_size(self, symbol, sl_pips):
        """
        Calcula el lotaje basado en RIESGO REAL EN USD.
        Riesgo USD = Capital * %Riesgo
        Lotes = Riesgo USD / (SL Pips * Valor del Pip por Lote Estándar)
        """
        try:
            f_config = get_forex_config()
            # Calcular riesgo base, pero limitarlo a un maximo de $15 USD por trade 
            # para asegurar que NUNCA toque el Hard Cap de $25 por error.
            riesgo_usd = min(f_config['capital_usd'] * f_config['risk_per_trade_pct'] / 100, 15.0)
            
            # Valor estándar de 1 pip por 1 lote (100,000 unidades)
            pip_val_std = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
            
            # Piso seguro para el SL para no generar lotajes gigantes
            safe_sl_pips = max(sl_pips, 10.0) 
            
            lots = riesgo_usd / (safe_sl_pips * pip_val_std)
                
            self.log(f"[LOTS] Capital: ${f_config['capital_usd']} | Riesgo Cap: ${riesgo_usd} | SL Pips: {safe_sl_pips:.1f} | Lots: {lots:.2f}")
            return min(max(round(lots, 2), 0.01), 1.0)
        except Exception as e:
            self.log(f"Error calculando lotes: {e}", "ERROR")
            return 0.01


    def _calculate_sl_tp(self, symbol, direction, entry, snap, rule_code):
        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
        max_sl_pips = MAX_SL_PIPS.get(symbol, 30)
        u1 = self._safe_float(snap.get('upper_1'))
        l1 = self._safe_float(snap.get('lower_1'))
        atr = abs(u1 - l1) / 3.236 if (u1 > 0 and l1 > 0) else (20 * pip_size)
        
        # Usamos niveles de Fibonacci para consistencia con Crypto
        ema20 = self._safe_float(snap.get('ema_20'))
        
        # Configurar offset de SL dinámico por símbolo para dar suficiente espacio
        SL_OFFSET_PIPS = {
            'EURUSD': 10,
            'GBPUSD': 15,  # Aumentado de 10 a 15 pips por la volatilidad de la Libra
            'USDJPY': 30,  # Aumentado de 10 a 30 pips ($0.30 JPY) para evitar que quede demasiado pegado a la EMA20 en el Yen
            'XAUUSD': 300, # 300 pips ($3.00 USD) para evitar que quede demasiado pegado a la EMA20
        }
        offset_pips = SL_OFFSET_PIPS.get(symbol, 10)
        
        if direction == 'long':
            # SL dinámico: offset_pips por debajo de la EMA20 (si está disponible)
            if ema20 > 0:
                sl = ema20 - (offset_pips * pip_size)
            else:
                sl = self._safe_float(snap.get('lower_6'), (entry - 50 * pip_size)) - (0.5 * atr)
            
            if sl >= entry: sl = entry - (offset_pips * pip_size)  # fallback
            
            # TP: Upper 3 (Partial Target)
            tp = self._safe_float(snap.get('upper_3'), entry + (3 * atr))
            if tp <= entry: tp = entry + (2 * atr)  # Forzar TP rentable
        else:
            # SL dinámico: offset_pips por encima de la EMA20 (si está disponible)
            if ema20 > 0:
                sl = ema20 + (offset_pips * pip_size)
            else:
                sl = self._safe_float(snap.get('upper_6'), (entry + 50 * pip_size)) + (0.5 * atr)
            
            if sl <= entry: sl = entry + (offset_pips * pip_size)  # fallback
            
            # TP: Lower 3 (Partial Target)
            tp = self._safe_float(snap.get('lower_3'), entry - (3 * atr))
            if tp >= entry: tp = entry - (2 * atr)  # Forzar TP rentable
        
        #    CAP: Limitar SL a maximo permitido   
        sl_pips_raw = abs(entry - sl) / pip_size
        if sl_pips_raw > max_sl_pips:
            self.log(f"   [SL CAP] {symbol}: SL de {sl_pips_raw:.0f} pips excede maximo de {max_sl_pips}. Reduciendo.")
            if direction == 'long':
                sl = entry - (max_sl_pips * pip_size)
            else:
                sl = entry + (max_sl_pips * pip_size)
        
        return round(sl, 6), round(tp, 6), abs(entry-sl)/pip_size

    def _execute_live_order(self, symbol, direction, lots, entry, sl, tp, rule_code):
        try:
            from app.workers.forex_worker_standalone import ACCOUNT_ID, get_divisor
            sid = self.state['symbol_ids'].get(symbol)
            if not sid: return
            
            divisor = get_divisor(symbol)
            
            req = ProtoOANewOrderReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.symbolId, req.orderType, req.tradeSide = sid, 1, (1 if direction=='long' else 2)
            req.volume = int(lots * 100000)
            
            if sl > 0: req.stopLoss = int(round(sl * divisor))
            if tp > 0: req.takeProfit = int(round(tp * divisor))
            
            self.worker.client.send(req)
            self._save_position(symbol, direction, lots, entry, sl, tp, rule_code, mode='live')
        except Exception as e: self.log(f'Error live: {e}')

    def _execute_paper_order(self, symbol, direction, lots, entry, sl, tp, rule_code):
        self._save_position(symbol, direction, lots, entry, sl, tp, rule_code, mode='paper')
        self._send_telegram(f'[PAPER] {direction.upper()} {symbol} (Rule: {rule_code})')

    def _save_position(self, symbol, direction, lots, entry, sl, tp, rule_code, mode='paper'):
        try:
            # Aplicar signo algebraico (Negativo para SHORT/SELL)
            final_lots = -abs(float(lots)) if str(direction).lower() == 'short' or str(direction).lower() == 'sell' else abs(float(lots))
            
            #    SLVM: Calcular Stop Loss Virtual   
            slv_price = None
            try:
                from app.strategy.virtual_sl_recovery import calculate_slv
                snap_res = self.sb.table('market_snapshot').select('*').eq('symbol', symbol).limit(1).execute()
                snap_slv = snap_res.data[0] if snap_res.data else {}
                slv_data = calculate_slv(
                    entry_price=float(entry), side=direction, symbol=symbol,
                    snap=snap_slv, market_type='forex_futures',
                )
                slv_price = slv_data['slv_price']
                self.log(f'SLVM [{symbol}]: SLV={slv_price:.6f} ({slv_data["distance_pips"]:.1f} pips, {slv_data["source"]})')
            except Exception as slv_e:
                self.log(f'SLVM calc error for {symbol}: {slv_e}')

            pos = {
                'symbol': symbol, 
                'side': direction, 
                'lots': final_lots, 
                'entry_price': float(entry), 
                'sl_price': float(sl), 
                'tp_price': float(tp), 
                'status': 'open', 
                'mode': mode, 
                'rule_code': rule_code, 
                'opened_at': datetime.now(timezone.utc).isoformat(),
                #    SLVM Fields   
                'slv_price': slv_price,
                'recovery_mode': False,
                'recovery_cycles': 0,
            }
            res = self.sb.table('forex_positions').insert(pos).execute()
            if res.data: 
                self.log(f'Guardada posicion {symbol} {direction.upper()} Lots: {final_lots}')
                self._open_positions_list.append(res.data[0])
        except Exception as e: self.log(f'Error guardando: {e}')

    def run_position_management(self):
        """Gestiona SL, TP, HardCap y Protecciones. Optimizada para MEMORIA."""
        # A. Viernes Fin de Semana Auto-Close:
        # A partir del Viernes a las 20:55 UTC (15:55 local GMT-5 / 3:55 PM local), liquidamos posiciones abiertas
        # para protegernos del riesgo de Gap del fin de semana.
        now = datetime.now(timezone.utc)
        if now.weekday() == 4 and now.hour == 20 and now.minute >= 55:
            self.log(f"🚨 [WEEKEND CLOSE] Liquidando posiciones por cierre de sesión del Viernes (20:55 UTC).")
            for p in list(self._open_positions_list):
                try:
                    symbol = p['symbol']
                    price_data = self.state['prices'].get(symbol)
                    price = self._safe_float(price_data.get('mid')) if price_data else 0
                    if price <= 0:
                        price = self._safe_float(p.get('current_price'))
                    if price <= 0:
                        continue
                    entry = self._safe_float(p.get('entry_price'))
                    pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
                    side = p.get('side', 'long').lower()
                    pips = (price - entry)/pip_size if side == 'long' else (entry - price)/pip_size
                    self._close_position(p, price, 'weekend_close', pips)
                except Exception as e:
                    self.log(f"Error cerrando posición en fin de semana: {e}", "ERROR")
            return

        if not self._open_positions_list: return
        
        snaps = {}
        # Solo consultamos snapshots (indicadores) cada 60s para ahorrar trafico
        # Pero el chequeo de precios (SL/TP) se hace cada 15s en memoria.
        should_fetch_snaps = (int(time.time()) % 60 < 15) 
        
        if should_fetch_snaps:
            try:
                symbols = list(set(p['symbol'] for p in self._open_positions_list))
                res = self.sb.table('market_snapshot').select('*').in_('symbol', symbols).execute()
                for s in (res.data or []): snaps[s['symbol']] = s
            except Exception as e: 
                self.log(f"Error gestion snaps (DB-Skip): {e}")

        for pos in list(self._open_positions_list):
            try: 
                symbol = pos['symbol']
                snap = snaps.get(symbol)
                
                #    OBTENER PRECIO DE MEMORIA (REAL-TIME)   
                price_data = self.state['prices'].get(symbol)
                price = self._safe_float(price_data.get('mid')) if price_data else 0
                
                # Fallback solo si memoria falla
                if price <= 0 and snap:
                    price = self._safe_float(snap.get('price'))
                
                if price <= 0: continue # No hay precio, no podemos evaluar

                #    1. HARD CAP & SL/TP (MEMORIA PURA - PRIORIDAD ALTA)   
                # Estos se ejecutan SIEMPRE cada 15s sin depender de la DB
                if self._manage_position_fast(pos, price, snap):
                    continue # Posicion cerrada

                #    SLVM: Modo Recuperacion   
                try:
                    from app.strategy.virtual_sl_recovery import (
                        check_slv_trigger, evaluate_recovery_mode,
                        activate_recovery_mode_sync, update_recovery_cycle_sync,
                        finalize_recovery_exit_sync, update_slv_from_bands_sync,
                    )

                    if pos.get('recovery_mode') and price > 0:
                        mr_result = evaluate_recovery_mode(
                            position=pos, current_price=price,
                            snap=snap or {}, symbol=symbol,
                            market_type='forex_futures',
                        )
                        update_recovery_cycle_sync(pos, mr_result, self.sb, 'forex_positions')
                        self.log(f'SLVM MR [{symbol}] ciclo {mr_result["recovery_cycles"]}: {mr_result["reason"]}')

                        if mr_result['should_close']:
                            finalize_recovery_exit_sync(pos, mr_result, price, symbol, self.sb, 'forex_positions')
                            pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
                            pips_pnl = mr_result['pnl_pips']
                            self._close_position(pos, price, f'recovery_{mr_result["exit_type"]}', pips_pnl, mr_result=mr_result)
                            continue
                        else:
                            # En MR: trailing sigue activo
                            if snap:
                                self._run_protection_forex(pos, snap)
                            continue

                    if pos.get('slv_price') and price > 0 and check_slv_trigger(pos, price):
                        activate_recovery_mode_sync(pos, price, symbol, 'forex_futures', self.sb, 'forex_positions')
                        continue

                    if pos.get('slv_price') and snap:
                        update_slv_from_bands_sync(pos, snap, symbol, 'forex_futures', self.sb, 'forex_positions')

                except Exception as slvm_e:
                    self.log(f'SLVM error for {symbol}: {slvm_e}')

                #    Primero: Verificar cierre proactivo   
                if snap and self._check_proactive_exit_forex(pos, snap):
                    continue # Posici n cerrada

                #    3. Sistema de Protecci n de Capital (Trailling, BE, etc.)   
                # Requiere snap (indicadores), solo corre si tenemos snap fresco
                if snap:
                    self._run_protection_forex(pos, snap)

                    # Cruce contrario de EMAs (Propuesta D - Corte rápido de pérdidas para estrategias de Momentum)
                    ema3_val = self._safe_float(snap.get('ema_3'))
                    ema9_val = self._safe_float(snap.get('ema_9'))
                    rule = pos.get('rule_code', '')
                    is_momentum_rule = '31a' in rule or 'HOT' in rule or '61' in rule
                    
                    if is_momentum_rule and ema3_val > 0 and ema9_val > 0:
                        side = pos['side'].lower()
                        entry = self._safe_float(pos.get('entry_price'))
                        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
                        pips_pnl = (price - entry) / pip_size if side in ['long', 'buy'] else (entry - price) / pip_size
                        
                        # --- CIERRE PROACTIVO PERSONALIZADO Bb61 (Aa61 / Aa61_short) ---
                        if '61' in rule:
                            triggered_exit_61 = False
                            exit_reason = ""
                            
                            # 1. Chequeo en 5 minutos para corte ultra rápido: si EMA3 < EMA9 (para LONG)
                            from app.core.memory_store import MEMORY_STORE
                            df_5m = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
                            
                            if df_5m is not None and len(df_5m) >= 2:
                                last_5m = df_5m.iloc[-1]
                                ema3_5m = self._safe_float(last_5m.get('ema1'))
                                ema9_5m = self._safe_float(last_5m.get('ema2'))
                                
                                if side in ['long', 'buy'] and ema3_5m > 0 and ema9_5m > 0 and ema3_5m < ema9_5m:
                                    triggered_exit_61 = True
                                    exit_reason = f"Bb61 (5m contrary cross: EMA3 {ema3_5m:.5f} < EMA9 {ema9_5m:.5f})"
                                elif side in ['short', 'sell'] and ema3_5m > 0 and ema9_5m > 0 and ema3_5m > ema9_5m:
                                    triggered_exit_61 = True
                                    exit_reason = f"Bb61 (5m contrary cross: EMA3 {ema3_5m:.5f} > EMA9 {ema9_5m:.5f})"
                            
                            # 2. Chequeo en 15m: si tiende a cruzar (proximidad estrecha)
                            if not triggered_exit_61:
                                proximity = abs(ema3_val - ema9_val) / ema9_val * 100
                                if side in ['long', 'buy']:
                                    if ema3_val < ema9_val:
                                        triggered_exit_61 = True
                                        exit_reason = f"Bb61 (15m cross: EMA3 {ema3_val:.5f} < EMA9 {ema9_val:.5f})"
                                    elif proximity < 0.02:  # Menos de 0.02% de distancia: tiende a cruzar
                                        triggered_exit_61 = True
                                        exit_reason = f"Bb61 (15m proximity: EMA3 se acerca a EMA9, dist={proximity:.3f}%)"
                                elif side in ['short', 'sell']:
                                    if ema3_val > ema9_val:
                                        triggered_exit_61 = True
                                        exit_reason = f"Bb61 (15m cross: EMA3 {ema3_val:.5f} > EMA9 {ema9_val:.5f})"
                                    elif proximity < 0.02:
                                        triggered_exit_61 = True
                                        exit_reason = f"Bb61 (15m proximity: EMA3 se acerca a EMA9, dist={proximity:.3f}%)"
                            
                            if triggered_exit_61:
                                self.log(f"[EARLY EXIT Bb61] {symbol} {side.upper()}: {exit_reason}. Cerrando.")
                                self._close_position(pos, price, 'Bb61', pips_pnl)
                                self._send_telegram(f"🔔 [EARLY EXIT Bb61] {symbol} {side.upper()} cerrado proactivamente por: {exit_reason} (PnL: {pips_pnl:.1f} pips)")
                                continue
                        
                        # --- CORTES CONTRARIOS ESTANDAR ---
                        elif side in ['long', 'buy'] and ema3_val < ema9_val:
                            self.log(f"[EARLY EXIT] {symbol} LONG ({rule}): EMA3 ({ema3_val:.5f}) < EMA9 ({ema9_val:.5f}) - Cruce contrario. Cerrando.")
                            self._close_position(pos, price, 'ema_contrary_cross', pips_pnl)
                            continue
                        elif side in ['short', 'sell'] and ema3_val > ema9_val:
                            self.log(f"[EARLY EXIT] {symbol} SHORT ({rule}): EMA3 ({ema3_val:.5f}) > EMA9 ({ema9_val:.5f}) - Cruce contrario. Cerrando.")
                            self._close_position(pos, price, 'ema_contrary_cross', pips_pnl)
                            continue

                    # 1. TP Adaptativo
                    tp_res = evaluate_forex_tp(symbol, [pos], price, snap)
                    if tp_res['should_close']:
                        self.log(f"[ADAPTIVE TP] {symbol}: {tp_res['close_reason']} (PnL: {tp_res['pnl_pips']:.1f} pips)")
                        self._close_position(pos, price, tp_res['close_reason'], tp_res['pnl_pips'])
                        reset_sl_counter(symbol, pos['side'])
                        continue

                    # 2. SL Adaptativo / SLV
                    sl_res = evaluate_forex_sl(symbol, [pos], price, snap)
                    if sl_res['should_close']:
                        self.log(f"[ADAPTIVE SL] {symbol}: {sl_res.get('exit_type', 'sl_v5')} (PnL: {sl_res['pnl_pips']:.1f} pips)")
                        self._close_position(pos, price, sl_res.get('exit_type', 'sl_v5'), sl_res['pnl_pips'])
                        register_sl_event(symbol, pos['side'])
                        continue
                    elif sl_res.get('slv_triggered'):
                         if not pos.get('recovery_mode'):
                             from app.strategy.virtual_sl_recovery import activate_recovery_mode_sync
                             activate_recovery_mode_sync(pos, price, symbol, 'forex_futures', self.sb, 'forex_positions')

            except Exception as e: self.log(f'Error gestion: {e}')

    def _manage_position_fast(self, pos, price, snap=None):
        """
        Chequeo rapido en memoria de SL, TP y Hard Cap.
        Retorna True si la posicion fue cerrada.
        """
        symbol = pos['symbol']
        side   = pos['side'].lower()
        entry  = self._safe_float(pos.get('entry_price'))
        sl     = self._safe_float(pos.get('sl_price'))
        tp     = self._safe_float(pos.get('tp_price'))
        
        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
        pip_val  = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
        lots_abs = abs(self._safe_float(pos.get('lots'), 0.01))
        
        pips_pnl = (price - entry) / pip_size if side in ['long', 'buy'] else (entry - price) / pip_size
        pnl_usd  = pips_pnl * pip_val * lots_abs

        #   1. HARD CAP: Perdida maxima absoluta ($15 USD)
        max_loss_pips = HARD_CAP_LOSS_PIPS.get(symbol, 25)
        if pips_pnl < -max_loss_pips or pnl_usd < -HARD_CAP_LOSS_USD:
            self.log(f"[HARD CAP] {symbol}: PnL ${pnl_usd:.2f} ({pips_pnl:.1f} pips). CIERRE INMEDIATO.")
            self._close_position(pos, price, 'hard_cap_loss', pips_pnl)
            return True

        #   2. SL / TP Estandar
        hit_sl = (sl > 0 and ((side in ['long', 'buy'] and price <= sl) or (side in ['short', 'sell'] and price >= sl)))
        hit_tp = (tp > 0 and ((side in ['long', 'buy'] and price >= tp) or (side in ['short', 'sell'] and price <= tp)))
        
        if hit_sl or hit_tp:
            reason = 'sl' if hit_sl else 'tp'
            self._close_position(pos, price, reason, pips_pnl)
            return True

        #   3. TP Band (Si tenemos snap)
        if snap:
            u6 = self._safe_float(snap.get('upper_6'))
            l6 = self._safe_float(snap.get('lower_6'))
            if (side in ['long', 'buy'] and u6 > 0 and price >= u6) or (side in ['short', 'sell'] and l6 > 0 and price <= l6):
                self._close_position(pos, price, 'tp_band', pips_pnl)
                return True
        
        return False

    def _check_proactive_exit_forex(self, pos: dict, snap: dict) -> bool:
        """
        Evalua Aa51/Bb51 para posiciones Forex.
        Retorna True si se cerro la posicion.
        """
        symbol = pos['symbol']
        price_data = self.state['prices'].get(symbol)
        if not price_data:
            return False
        price = self._safe_float(price_data.get('mid'))
        if price <= 0:
            return False

        # Obtener velas 4H del STATE
        key_4h = f'{symbol}_4h'
        bars_4h = self.state['candles'].get(key_4h, [])

        if len(bars_4h) < 3:
            return False

        # Convertir a DataFrame
        import pandas as pd
        df_4h = pd.DataFrame(bars_4h)
        # Renombrar columnas abreviadas (o,h,l,c) a formato est ndar
        df_4h = df_4h.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'ts': 'open_time'})
        df_4h['open_time'] = pd.to_datetime(df_4h['open_time'], unit='s')
        df_4h = df_4h.set_index('open_time')
        
        # Limpiar datos nulos que causan float() error
        df_4h = df_4h.dropna(subset=['open', 'high', 'low', 'close'])
        for col in ['open','high','low','close']:
            if col in df_4h.columns:
                df_4h[col] = pd.to_numeric(df_4h[col], errors='coerce').fillna(0)

        # Adaptar position al formato estandar (en Forex usamos 'lots' -> 'size')
        position_std = {
            'symbol':           symbol,
            'side':             pos['side'],
            'avg_entry_price':  self._safe_float(pos.get('entry_price')),
            'size':             self._safe_float(pos.get('lots')),
            'id':               pos['id']
        }

        result = evaluate_proactive_exit(
            position      = position_std,
            current_price = price,
            snap          = snap,
            df_4h         = df_4h,
            market_type   = 'forex_futures',
        )

        if not result['should_close']:
            if result.get('rule_code') is None and 'Reversi n' in result.get('reason', ''):
                self.log(f"   [PROACTIVE EVAL] {symbol}: {result['reason']}", "DEBUG")
            return False

        pnl = result['pnl']
        self.log(
            f'[PROACTIVE EXIT] FOREX {symbol}: '
            f'{result["rule_code"]} '
            f'+{pnl["pnl_pct"]:.3f}% '
            f'({pnl["pnl_pips"]:.1f} pips) - {result["reason"]}'
        )

        # Cerrar posicion
        self._close_position(pos, price, result['rule_code'], pnl['pnl_pips'])
        self._send_telegram(
            f"CIERRE PROACTIVO FOREX [{symbol}]\n"
            f"Regla: {result['rule_code']}\n"
            f"Pips: +{pnl['pnl_pips']:.1f}\n"
            f"Razon: {result['reason']}"
        )

        return True

    def _run_protection_forex(self, pos: dict, snap: dict):
        """Aplica Trailing Stop, Break-Even, etc."""
        symbol = pos['symbol']
        price = self._safe_float(snap.get('price'))
        if price <= 0: return

        # Obtener o crear estado
        pos_id = pos['id']
        if pos_id not in self.protection_states:
            self.protection_states[pos_id] = ProtectionState(
                position_id=pos_id,
                symbol=symbol,
                side=pos['side'].lower(),
                entry_price=self._safe_float(pos['entry_price']),
                current_sl=self._safe_float(pos.get('sl_price')),
                original_sl=self._safe_float(pos.get('sl_price')),
                market_type='forex_futures'
            )

        state = self.protection_states[pos_id]
        # Actualizar precio actual en el estado
        state.entry_price = self._safe_float(pos['entry_price'])
        
        # Track highest and lowest price continuously for accurate dynamic trailing stop
        if state.side in ('long', 'buy'):
            state.highest_price = max(state.highest_price, price) if state.highest_price > 0 else max(state.entry_price, price)
        else:
            state.lowest_price = min(state.lowest_price, price) if state.lowest_price > 0 else min(state.entry_price, price)
            
        # Extraer dataframes si están disponibles
        import pandas as pd
        
        def _get_df(tf):
            bars = self.state['candles'].get(f'{symbol}_{tf}', [])
            if not bars: return None
            df = pd.DataFrame(bars)
            df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'ts': 'open_time'})
            df['open_time'] = pd.to_datetime(df['open_time'], unit='s')
            df = df.set_index('open_time')
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            for col in ['open','high','low','close']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            return df
            
        df_15m = _get_df('15m')
        df_5m = _get_df('5m')

        result = evaluate_all_protections(state, price, snap, df_15m=df_15m, df_5m=df_5m)
        
        if result.get('has_action') and 'primary' in result:
            primary = result['primary']
            action = primary.get('action')
            
            if action in ('activate_be', 'update_sl'):
                new_sl = primary.get('be_price') if action == 'activate_be' else primary.get('new_sl')
                self.log(f"[PROTECTION] {symbol}: Moviendo SL a {new_sl} ({primary.get('reason')})")
                
                # Sincronizar con cTrader si es cuenta real
                if pos.get('mode') == 'live' and pos.get('ctrader_pos_id'):
                    self.worker.amend_position(pos['ctrader_pos_id'], sl_price=new_sl, symbol=symbol)

                # Actualizar en DB
                self.sb.table('forex_positions').update({'sl_price': new_sl}).eq('id', pos_id).execute()
                # Actualizar en memoria
                pos['sl_price'] = new_sl
                # Actualizar estado interno de protecci n
                state.current_sl = new_sl
                if action == 'activate_be': state.be_activated = True
                if action == 'update_sl': state.trailing_level = primary.get('new_level', state.trailing_level)
                
            elif action == 'partial_close':
                self.log(f"   [PROTECTION] {symbol}: Cierre parcial sugerido (No implementado en esta version)")
            elif action == 'close_market':
                self.log(f"   [PROTECTION] {symbol}: Cierre por senal inversa confirmada")
                self._close_position(pos, price, 'inverse_signal', 0)

    def _manage_position(self, pos, snap=None):
        symbol = pos['symbol']
        # Fallback de precio: Prioridad a tiempo real, luego snapshot
        price_data = self.state['prices'].get(symbol)
        price = 0
        if price_data:
            price = normalize_forex_price(symbol, self._safe_float(price_data.get('mid')))
        
        if price <= 0 and snap:
            price = normalize_forex_price(symbol, self._safe_float(snap.get('price')))

        if price <= 0: return

        side  = pos['side'].lower()
        entry = self._safe_float(pos.get('entry_price'))
        sl    = self._safe_float(pos.get('sl_price'))
        tp    = self._safe_float(pos.get('tp_price'))
        
        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
        pip_val  = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
        lots_abs = abs(self._safe_float(pos.get('lots'), 0.01))
        pips_pnl = (price - entry) / pip_size if side in ['long', 'buy'] else (entry - price) / pip_size
        pnl_usd  = pips_pnl * pip_val * lots_abs

        #                                                   
        #   HARD CAP: Perdida maxima absoluta (PRIORIDAD 0)
        # Se ejecuta ANTES de cualquier otra logica.
        #                                                   
        max_loss_pips = HARD_CAP_LOSS_PIPS.get(symbol, 25)
        if pips_pnl < -max_loss_pips or pnl_usd < -HARD_CAP_LOSS_USD:
            self.log(
                f"[HARD CAP] {symbol}: Perdida excede limite! "
                f"Pips: {pips_pnl:.1f} (max: -{max_loss_pips}) | "
                f"USD: ${pnl_usd:.2f} (max: -${HARD_CAP_LOSS_USD:.2f}) - CIERRE FORZADO"
            )
            self._close_position(pos, price, 'hard_cap_loss', pips_pnl)
            self._send_telegram(
                f"HARD CAP LOSS [{symbol}]\n"
                f"Pips: {pips_pnl:.1f} | USD: ${pnl_usd:.2f}\n"
                f"Limite: -{max_loss_pips} pips / -${HARD_CAP_LOSS_USD}"
            )
            return

        #    TP Band Exit   
        if snap:
            u6 = self._safe_float(snap.get('upper_6'))
            l6 = self._safe_float(snap.get('lower_6'))
            if (side in ['long', 'buy'] and u6 > 0 and price >= u6) or (side in ['short', 'sell'] and l6 > 0 and price <= l6):
                self._close_position(pos, price, 'tp_band', pips_pnl)
                return

        #    Verificaci n estricta de SL/TP   
        hit_sl = (sl > 0 and ((side in ['long', 'buy'] and price <= sl) or (side in ['short', 'sell'] and price >= sl)))
        hit_tp = (tp > 0 and ((side in ['long', 'buy'] and price >= tp) or (side in ['short', 'sell'] and price <= tp)))

        if hit_sl or hit_tp:
            reason = 'sl' if hit_sl else 'tp'
            self.log(f"[EXECUTION] Disparando cierre {reason.upper()} para {symbol} at {price} (SL: {sl}, TP: {tp})")
            self._close_position(pos, price, reason, pips_pnl)

    def _close_position(self, pos, close_price, reason, pips_pnl, mr_result=None):
        try:
            symbol = pos['symbol']
            
            # Cerrar en cTrader si es cuenta real
            if pos.get('mode') == 'live' and pos.get('ctrader_pos_id'):
                lots_abs = abs(self._safe_float(pos.get('lots')))
                self.worker.close_position(pos['ctrader_pos_id'], lots_abs * 100000)

            # Usar valor absoluto de lots para el calculo de PnL ya que pips_pnl ya considera la direccion
            pip_val = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
            pnl_usd = pips_pnl * pip_val * abs(self._safe_float(pos.get('lots')))
            
            update_data = {
                'status': 'closed', 
                'current_price': close_price, 
                'close_reason': reason, 
                'pnl_usd': round(pnl_usd, 2), 
                'pnl_pips': round(pips_pnl, 1), 
                'closed_at': datetime.now(timezone.utc).isoformat()
            }
            
            #    SLVM V2 Audit Logging   
            if mr_result:
                update_data.update({
                    'slv_hard_stop_trigger': mr_result.get('exit_type'),
                    'slv_hard_stop_pips': mr_result.get('hs_pips'),
                    'slv_v1_open': mr_result.get('v1_open'),
                    'v2_close_prev': mr_result.get('v2_close_prev'),
                    'slv_timeframe_trigger': '5m_service'
                })

            self.sb.table('forex_positions').update(update_data).eq('id', pos['id']).execute()
            
            # Registrar profit
            try:
                from app.core.capital_manager import register_realized_pnl
                register_realized_pnl('forex', round(pnl_usd, 2))
            except Exception as cap_e:
                self.log(f'Error actualizando capital acumulado forex: {cap_e}', 'ERROR')
            
            self._open_positions_list = [p for p in self._open_positions_list if p['id'] != pos['id']]
            self.log(f'Cerrada {symbol}: {reason} | PnL: {pips_pnl:.1f} pips | USD: {pnl_usd:.2f}')
        except Exception as e: self.log(f'Error cierre: {e}')

    def _send_telegram(self, message):
        try:
            import requests
            token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
            if token and chat_id: requests.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': message}, timeout=5)
        except: pass
