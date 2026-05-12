"""
Forex Worker Standalone (Protobuf v3.1)

# FIXES:
# 1. Re-conexion automatica (Auto-reconnect) si cTrader desconecta.
# 2. Divisor Universal de 100,000 estable.
# 3. Limpieza de datos corruptos integrada.
# 4. Carga explicita del .env del backend (evita conflicto con .env padre).
"""

import os
import sys
import traceback
import json
import time
import threading

#     PASO 1: Resolver rutas y cargar .env manualmente    
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Carga manual del .env (robusta)
dotenv_path = os.path.join(root_dir, '.env')
discovered_keys = []
if os.path.exists(dotenv_path):
    # Intentamos leer el archivo completo primero para ver qu  hay
    try:
        with open(dotenv_path, 'rb') as f:
            raw = f.read()
            # Detectar si es UTF-16 (comun en Windows si se guardo con Notepad)
            content = ""
            if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
                content = raw.decode('utf-16')
            else:
                content = raw.decode('utf-8', errors='ignore')
            
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                os.environ[key] = value
                discovered_keys.append(key)
    except Exception as e:
        print(f"[ERROR] Fallo critico leyendo .env: {e}")

    s_url = os.getenv('SUPABASE_URL', '')
    print(f"[INFO] .env procesado. Total llaves: {len(discovered_keys)}")
    print(f"[INFO] Llaves encontradas: {', '.join(discovered_keys[:5])}...")
    print(f"[INFO] SUPABASE_URL detectada: {'S ' if s_url else 'NO'} ({len(s_url)} chars)")
    
    if not s_url:
        print(f"[CRITICAL]  SUPABASE_URL no encontrada en {dotenv_path}!")
        print(f"[DEBUG] Primeros 100 caracteres del archivo: {repr(content[:100])}")
else:
    print(f"[ERROR] No se encontro .env en {dotenv_path}")
    sys.exit(1)

#     PASO 2: Imports que dependen del .env    
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from app.core.safety_manager import register_heartbeat, check_circuit_breaker

from twisted.internet import reactor, threads, task
from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from supabase import create_client

#     PASO 3: Config    
CLIENT_ID     = os.getenv('CTRADER_CLIENT_ID')
CLIENT_SECRET = os.getenv('CTRADER_CLIENT_SECRET')
ACCOUNT_ID    = int(os.getenv('CTRADER_ACCOUNT_ID', 0))
ACCESS_TOKEN  = os.getenv('CTRADER_ACCESS_TOKEN')
CTRADER_ENV   = os.getenv('CTRADER_ENV', 'live')

SUPABASE_URL  = os.getenv('SUPABASE_URL')
SUPABASE_KEY  = os.getenv('SUPABASE_SERVICE_KEY')

# DEFAULT fallback symbols
DEFAULT_FOREX_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']

TF_MAP = {
    '15m': ProtoOATrendbarPeriod.M15,
    '1h':  ProtoOATrendbarPeriod.H1,
    '4h':  ProtoOATrendbarPeriod.H4,
    '1d':  ProtoOATrendbarPeriod.D1,
}

# Divisores de precio por simbolo
SYMBOL_DIVISORS = {
    'EURUSD': 100000,
    'GBPUSD': 100000,
    'USDJPY': 100000,
    'USDCHF': 100000,
    'AUDUSD': 100000,
    'NZDUSD': 100000,
    'USDCAD': 100000,
    'EURGBP': 100000,
    'EURJPY': 100000,
    'GBPJPY': 100000,
    'XAUUSD': 100000,
    'XAGUSD': 100000,
    'US30':   100,
    'US500':  100,
    'NAS100': 100,
}

def get_divisor(symbol):
    return SYMBOL_DIVISORS.get(symbol, 100000)


STATE = { 'symbol_ids': {}, 'prices': {}, 'candles': {}, 'cycle_count': 0 }
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def calculate_parabolic_sar(df, start=0.02, increment=0.02, maximum=0.20):
    """Calculo interno de SAR Parabolic para evitar dependencias de 'app'"""
    n = len(df)
    sar, trend, ep, af = np.zeros(n), np.zeros(n, dtype=int), np.zeros(n), np.zeros(n)
    sar[0], trend[0], ep[0], af[0] = df['c'].iloc[0], 0, df['c'].iloc[0], start
    for i in range(1, n):
        p_trend, p_sar, p_ep, p_af = trend[i-1], sar[i-1], ep[i-1], af[i-1]
        hi, lo, hp1, lp1 = df['h'].iloc[i], df['l'].iloc[i], df['h'].iloc[i-1], df['l'].iloc[i-1]
        hp2, lp2 = (df['h'].iloc[i-2] if i>=2 else hp1), (df['l'].iloc[i-2] if i>=2 else lp1)
        if p_trend == 0:
            if hi >= hp1 or lo >= lp1: trend[i], sar[i], ep[i] = 1, lp1, hp1
            else: trend[i], sar[i], ep[i] = -1, hp1, lp1
            af[i] = start
            continue
        nxt_sar, c_af, c_ep = p_sar, p_af, p_ep
        if p_trend > 0:
            if hp1 > c_ep: c_ep, c_af = hp1, min(maximum, c_af + increment)
            nxt_sar = min(min(lp1, lp2), p_sar + c_af * (c_ep - p_sar))
            if nxt_sar > lo: trend[i], sar[i], ep[i], af[i] = -1, c_ep, lo, start
            else: trend[i], sar[i], ep[i], af[i] = 1, nxt_sar, c_ep, c_af
        else:
            if lp1 < c_ep: c_ep, c_af = lp1, min(maximum, c_af + increment)
            nxt_sar = max(max(hp1, hp2), p_sar + c_af * (c_ep - p_sar))
            if nxt_sar < hi: trend[i], sar[i], ep[i], af[i] = 1, c_ep, hi, start
            else: trend[i], sar[i], ep[i], af[i] = -1, nxt_sar, c_ep, c_af
    df['sar'], df['sar_trend'] = sar, trend
    return df

class StandaloneForexWorker:
    def __init__(self):
        env = CTRADER_ENV
        self.host = EndPoints.PROTOBUF_LIVE_HOST if env == 'live' else EndPoints.PROTOBUF_DEMO_HOST
        self.port = EndPoints.PROTOBUF_PORT
        self.client = Client(host=self.host, port=self.port, protocol=TcpProtocol)
        self.client.setConnectedCallback(self.on_connected)
        self.client.setDisconnectedCallback(self.on_disconnected)
        self.client.setMessageReceivedCallback(self.on_message)
        self.execution = None  # Se inicializa despues de auth
        self.symbols = DEFAULT_FOREX_SYMBOLS

    def safe_send(self, req):
        from twisted.internet import reactor
        def _send():
            try:
                d = self.client.send(req)
                if hasattr(d, 'addErrback'):
                    d.addErrback(lambda f: None) # Silence timeout errors
            except Exception as e:
                self.log(f"Error sending request: {e}", "ERROR")
        
        reactor.callFromThread(_send)

    def log(self, msg, level='INFO'):
        from app.core.logger import log_info, log_error, log_warning
        
        ts = datetime.now().strftime('%H:%M:%S')
        
        # Clean message for console (ASCII only to avoid 'charmap' errors on Windows)
        # Use errors='replace' to turn non-ASCII into '?'
        console_msg = str(msg).encode('ascii', errors='replace').decode('ascii')
        
        # Clean message for DB (UTF-8 is fine for Supabase)
        db_msg = str(msg).encode('utf-8', errors='replace').decode('utf-8')
        
        # Console output
        print(f"[{ts}] [{level}] {console_msg}")
        sys.stdout.flush()
        
        # DB output
        try:
            if level == 'ERROR' or level == 'CRITICAL':
                log_error('forex_worker', db_msg)
            elif level == 'WARNING':
                log_warning('forex_worker', db_msg)
            else:
                log_info('forex_worker', db_msg)
        except Exception as e:
            # Fallback if DB logging fails
            print(f"[{ts}] [ERROR] Failed to log to DB: {e}")

    def start(self):
        self.log(f"Iniciando Worker v3.1 (Rutas Windows OK)...")
        self._load_dynamic_symbols()
        self.client.startService()
        # Iniciar ciclos base
        task.LoopingCall(self.send_heartbeat).start(25, now=False)
        task.LoopingCall(self.run_cycle).start(60, now=False)
        reactor.run()

    def on_connected(self, client):
        self.log("Conectado a cTrader. Autenticando...")
        self.send_app_auth()

    def on_disconnected(self, client, reason):
        self.log(f"Desconectado de cTrader ({reason}). Reintentando en 10s...", "WARNING")
        time.sleep(10)
        try: self.client.startService()
        except: pass

    def send_heartbeat(self):
        """Mantener viva la conexion (Requerido cada 25s)"""
        try:
            req = ProtoOAHeartbeatEvent()
            self.safe_send(req)
        except: pass

    def _load_dynamic_symbols(self):
        """Carga la lista de simbolos desde trading_config -> regime_params."""
        try:
            res = sb.table('trading_config').select('regime_params').eq('id', 1).execute()
            data = res.data[0] if res.data else {}
            if data.get('regime_params'):
                assets = data['regime_params'].get('forex_assets')
                if assets and isinstance(assets, list):
                    self.symbols = assets
                    self.log(f"Configuracion dinamica cargada: {', '.join(self.symbols)}")
                else:
                    self.log("No se encontro 'forex_assets' in regime_params. Usando valores por defecto.")
            else:
                self.log("No se pudo cargar trading_config. Usando valores por defecto.")
        except Exception as e:
            self.log(f"Error cargando s mbolos din micos: {e}. Usando valores por defecto.")

    def _init_execution_service(self):
        """Inicializa el Execution Service despues de cargar simbolos."""
        try:
            from app.workers.forex_execution_service import ForexExecutionService
            self.execution = ForexExecutionService(
                worker=self, 
                supabase_client=sb,
                state_ref=STATE,
                symbols_ref=self.symbols
            )
            self.log("[OK] Execution Service iniciado")

            # Ciclo de evaluacion de estrategias (cada 5 min, con offset de 30s)
            reactor.callLater(30, self._start_evaluation_loop)

            # Ciclo de gestion de posiciones (cada 15s) - OPTIMIZADO PARA MEMORIA
            self._mgmt_task = task.LoopingCall(self.execution.run_position_management)
            self._mgmt_task.start(15, now=False)

        except Exception as e:
            self.log(f"Error iniciando Execution Service: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")

    def _start_evaluation_loop(self):
        """Inicia el loop de evaluacion de estrategias."""
        self._eval_task = task.LoopingCall(self.execution.run_evaluation_cycle)
        self._eval_task.start(300, now=True)  # Cada 5 min, ejecutar inmediatamente

    def on_message(self, client, message):
        pt = message.payloadType
        if pt == ProtoOAApplicationAuthRes().payloadType: 
            self.log("Autenticacion de Aplicacion OK. Autenticando cuenta...")
            self.send_acc_auth()
        elif pt == ProtoOAAccountAuthRes().payloadType: 
            self.log("Autenticacion de Cuenta OK. Cargando simbolos...")
            self.load_symbols()
        elif pt == ProtoOAErrorRes().payloadType:
            err = Protobuf.extract(message)
            self.log(f"ERROR DE CTRADER: {err.errorCode} - {err.description}", "ERROR")
        elif pt == ProtoOASymbolsListRes().payloadType:
            res = Protobuf.extract(message)
            count = 0
            for sym in res.symbol:
                if sym.symbolName in self.symbols: 
                    STATE['symbol_ids'][sym.symbolName] = sym.symbolId
                    count += 1
            if count > 0:
                self.log(f"Simbolos vinculados: {count} ({', '.join(STATE['symbol_ids'].keys())})")
            self.subscribe_spots(); self.warmup_all()
            # Iniciar Execution Service despues de cargar simbolos
            reactor.callLater(5, self._init_execution_service)
        elif pt == ProtoOASpotEvent().payloadType:
            self.handle_spot(Protobuf.extract(message))
        elif pt == ProtoOAGetTrendbarsRes().payloadType:
            self.handle_bars(Protobuf.extract(message))
        elif pt == ProtoOAExecutionEvent().payloadType:
            self._handle_execution_event(Protobuf.extract(message))

    def _handle_execution_event(self, event):
        """Maneja respuestas de ejecucion de ordenes de cTrader."""
        try:
            if hasattr(event, 'order') and event.order:
                order = event.order
                self.log(
                    f"  Orden cTrader: id={order.orderId} "
                    f"status={event.executionType} "
                    f"symbol_id={order.tradeData.symbolId if hasattr(order, 'tradeData') else 'N/A'}"
                )
            
            if hasattr(event, 'position') and event.position:
                pos = event.position
                pid = pos.positionId
                p_status = pos.positionStatus
                self.log(f"  Posicion cTrader: id={pid} status={p_status}")

                # Vincular ID de cTrader con la DB si es una nueva posicion abierta
                if p_status == 1: # 1 = OPEN
                    # Buscar el simbolo por ID
                    name = next((n for n, sid in STATE['symbol_ids'].items() if sid == pos.tradeData.symbolId), None)
                    if name:
                        side = 'long' if pos.tradeData.tradeSide == 1 else 'short'
                        # Buscar la posicion mas reciente abierta en la DB que no tenga ID vinculado
                        try:
                            res = sb.table('forex_positions')\
                                .select('id')\
                                .eq('symbol', name)\
                                .eq('side', side)\
                                .eq('status', 'open')\
                                .is_('ctrader_pos_id', 'null')\
                                .order('opened_at', desc=True)\
                                .limit(1).execute()
                            
                            if res.data:
                                db_id = res.data[0]['id']
                                sb.table('forex_positions').update({'ctrader_pos_id': pid}).eq('id', db_id).execute()
                                self.log(f"[SYNC] Vinculado cTrader ID {pid} a posicion DB {db_id}")
                        except Exception as e:
                            self.log(f"Error vinculando ID: {e}", "ERROR")

        except Exception as e:
            self.log(f"Error procesando evento de ejecucion: {e}", "ERROR")

    def close_position(self, pos_id, volume_units):
        """Envía orden de cierre a cTrader."""
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAClosePositionReq
            req = ProtoOAClosePositionReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.positionId = int(pos_id)
            req.volume = int(volume_units)
            self.safe_send(req)
            self.log(f"[CTRIDER] Enviada solicitud de cierre para posicion {pos_id}")
            return True
        except Exception as e:
            self.log(f"Error enviando cierre a cTrader: {e}", "ERROR")
            return False

    def amend_position(self, pos_id, sl_price=None, tp_price=None, symbol=None):
        """Modifica SL/TP en cTrader."""
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAmendPositionSLTPReq
            req = ProtoOAAmendPositionSLTPReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.positionId = int(pos_id)
            
            divisor = get_divisor(symbol) if symbol else 100000
            
            if sl_price:
                req.stopLoss = int(round(sl_price * divisor))
            if tp_price:
                req.takeProfit = int(round(tp_price * divisor))
            
            self.safe_send(req)
            self.log(f"[CTRIDER] Enviada modificacion SL={sl_price}/TP={tp_price} para {pos_id}")
            return True
        except Exception as e:
            self.log(f"Error enviando modificacion a cTrader: {e}", "ERROR")
            return False

    def send_app_auth(self):
        req = ProtoOAApplicationAuthReq(); req.clientId = CLIENT_ID; req.clientSecret = CLIENT_SECRET; self.safe_send(req)
    def send_acc_auth(self):
        req = ProtoOAAccountAuthReq(); req.ctidTraderAccountId = ACCOUNT_ID; req.accessToken = ACCESS_TOKEN; self.safe_send(req)
    def load_symbols(self):
        req = ProtoOASymbolsListReq(); req.ctidTraderAccountId = ACCOUNT_ID; self.safe_send(req)

    def subscribe_spots(self):
        req = ProtoOASubscribeSpotsReq(); req.ctidTraderAccountId = ACCOUNT_ID
        for sid in STATE['symbol_ids'].values(): req.symbolId.append(sid)
        self.safe_send(req)

    def warmup_all(self):
        """Carga historica inicial no bloqueante para evitar congelar el reactor."""
        self.log("Preparando datos historicos (Lazy Warmup)...")
        # Marcamos que estamos en fase de arranque para NO guardar historial pesado en DB
        STATE['is_warming_up'] = True
        
        delay = 0.5
        for sym in self.symbols:
            self.log(f"-> Programando carga de {sym}...")
            # 15m
            reactor.callLater(delay, self.request_bars, sym, '15m', 300)
            delay += 2.0
            # 1h
            reactor.callLater(delay, self.request_bars, sym, '1h', 100)
            delay += 1.5
            # 4h
            reactor.callLater(delay, self.request_bars, sym, '4h', 100)
            delay += 1.5
            # 1d
            reactor.callLater(delay, self.request_bars, sym, '1d', 100)
            delay += 2.0
            
        # Desactivar warmup tras un tiempo prudencial (ej. 30 segundos)
        reactor.callLater(delay + 5.0, self._finish_warmup)

    def _finish_warmup(self):
        self.log("Warmup inicial completado en memoria. El guardado en DB se activara en el siguiente ciclo.")
        STATE['is_warming_up'] = False

    def request_bars(self, symbol, tf, limit=500):
        sid = STATE['symbol_ids'].get(symbol); p = TF_MAP.get(tf)
        if not sid or not p: return
        now_ms = int(time.time() * 1000)
        # Factor de minutos por TF
        tf_mins = {'15m': 15, '1h': 60, '4h': 240, '1d': 1440}
        m = tf_mins.get(tf, 15)
        from_ms = now_ms - (m * limit * 60 * 1000)
        req = ProtoOAGetTrendbarsReq(); req.ctidTraderAccountId = ACCOUNT_ID; req.symbolId = sid; req.period = p
        req.fromTimestamp = from_ms; req.toTimestamp = now_ms; req.count = limit; self.safe_send(req)

    def handle_spot(self, spot):
        name = next((n for n, sid in STATE['symbol_ids'].items() if sid == spot.symbolId), None)
        if not name: return
        div = get_divisor(name)
        bid_raw = spot.bid or 0
        ask_raw = spot.ask or 0

        # FIX: Preserve previous values for partial spot updates
        # cTrader sometimes sends only bid OR only ask, not both
        prev = STATE['prices'].get(name, {})
        bid = bid_raw / div if bid_raw else prev.get('bid', 0)
        ask = ask_raw / div if ask_raw else prev.get('ask', 0)

        if bid and ask:
            mid = (bid + ask) / 2
        elif bid:
            mid = bid
        elif ask:
            mid = ask
        else:
            mid = prev.get('mid', 0)

        if bid and ask:
            mid = (bid + ask) / 2
            if name == 'XAUUSD':
                self.log(f"DEBUG XAUUSD SPOT VERIFIED_V4: raw_bid={bid_raw}, raw_ask={ask_raw}, div={div}, bid={bid}, ask={ask}, mid={mid}")
            STATE['prices'][name] = {'bid': bid, 'ask': ask, 'mid': mid}

    def handle_bars(self, res):
        name = next((n for n, sid in STATE['symbol_ids'].items() if sid == res.symbolId), None)
        if not name: return
        p_rev = {v: k for k, v in TF_MAP.items()}; tf = p_rev.get(res.period, '15m')
        div = get_divisor(name)
        bars = []
        for b in res.trendbar:
            low = b.low / div
            if name == 'XAUUSD':
                self.log(f"DEBUG XAUUSD BAR: raw_low={b.low}, div={div}, low={low}")
            bars.append({'ts': b.utcTimestampInMinutes*60, 'o': low+b.deltaOpen/div, 'h': low+b.deltaHigh/div, 'l': low, 'c': low+b.deltaClose/div, 'v': b.volume or 0})
        if bars:
            self.log(f"Recibidas {len(bars)} velas de {name} ({tf})", "DEBUG")
            STATE['candles'][f"{name}_{tf}"] = bars
            threads.deferToThread(self.process_and_save, name, tf, bars)

    def safe_db_execute(self, query, retries=3):
        """Ejecuta una consulta a Supabase con reintentos para manejar inestabilidad de red."""
        for i in range(retries):
            try:
                return query.execute()
            except Exception as e:
                err_str = str(e)
                # Si es un error de Gateway o Schema Cache, esperamos m s tiempo
                wait_time = 5 * (i + 1)
                if "502" in err_str or "503" in err_str or "504" in err_str or "PGRST002" in err_str:
                    wait_time = 10 * (i + 1)
                
                self.log(f"Reintentando DB ({i+1}/{retries}) en {wait_time}s por error: {e}", "WARNING")
                if i < retries - 1:
                    time.sleep(wait_time)
                else:
                    raise e
        return None

    def process_and_save(self, sym, tf, bars):
        try:
            from app.analysis.indicators_v2 import calculate_all_indicators
            df_raw = pd.DataFrame(bars)
            # Renombrar para compatibilidad con indicators_v2
            df_raw = df_raw.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
            
            # Calcular todos los indicadores (MACD 4C, Pinescript, Bandas, SAR)
            df = calculate_all_indicators(df_raw, {})
            
            # NUEVO: Lazy Warmup. Si estamos arrancando, no guardamos el historial pesado en DB
            if STATE.get('is_warming_up', False) and len(df) > 10:
                # self.log(f"   [Lazy Skip DB] {sym} {tf} ({len(df)} velas)")
                return

            rows = []
            for i, row in df.tail(300).iterrows():
                rows.append({
                    'symbol': sym, 
                    'exchange': 'icmarkets', 
                    'timeframe': tf,
                    'open_time': datetime.fromtimestamp(row['ts'], timezone.utc).isoformat(),
                    'open':   float(row['open']), 
                    'high':   float(row['high']), 
                    'low':    float(row['low']), 
                    'close':  float(row['close']),
                    'volume': int(row['volume']), 
                    'basis':  float(row['basis']),
                    'sar':    float(row['sar']), 
                    'sar_trend': int(row['sar_trend']),
                    'upper_1': float(row.get('upper_1', 0)), 
                    'upper_2': float(row.get('upper_2', 0)),
                    'upper_3': float(row.get('upper_3', 0)),
                    'upper_4': float(row.get('upper_4', 0)),
                    'upper_5': float(row.get('upper_5', 0)),
                    'upper_6': float(row.get('upper_6', 0)),
                    'lower_1': float(row.get('lower_1', 0)), 
                    'lower_2': float(row.get('lower_2', 0)),
                    'lower_3': float(row.get('lower_3', 0)),
                    'lower_4': float(row.get('lower_4', 0)),
                    'lower_5': float(row.get('lower_5', 0)),
                    'lower_6': float(row.get('lower_6', 0)),
                    'pinescript_signal': str(row.get('pinescript_signal', '')) if row.get('pinescript_signal') in ('Buy', 'Sell') else None,
                    'is_closed': True
                })
            if rows: 
                self.safe_db_execute(sb.table('market_candles').upsert(rows, on_conflict='symbol,exchange,timeframe,open_time'))
        except Exception as e: 
            self.log(f"Error procesando {sym} ({tf}):\n{traceback.format_exc()}", "ERROR")

    def run_cycle(self):
        #    Heartbeat                              
        register_heartbeat('forex_worker')
        
        STATE['cycle_count'] = STATE.get('cycle_count', 0) + 1
        cycle = STATE['cycle_count']
        delay = 0
        for sym in self.symbols:
            # 15m cada minuto - Aumentamos a 100 para ATR estable
            reactor.callLater(delay, self.request_bars, sym, '15m', 100)
            
            # 1h cada 4 ciclos (~4 min)
            if cycle % 4 == 0:
                reactor.callLater(delay + 1.0, self.request_bars, sym, '1h', 50)
            
            # 4h cada 12 ciclos (~12 min)
            if cycle % 12 == 0:
                reactor.callLater(delay + 2.0, self.request_bars, sym, '4h', 50)
            
            # 1d cada 60 ciclos (~1 hora)
            if cycle % 60 == 0:
                reactor.callLater(delay + 3.0, self.request_bars, sym, '1d', 50)

            # Snapshot real-time
            reactor.callLater(delay + 4.0, self.save_snapshot, sym)
            delay += 5.0 
        
        self.log(f'Cycle {cycle} complete. TFs updated as scheduled.')

    def save_snapshot(self, symbol):
        try:
            key = f"{symbol}_15m"; data = STATE['candles'].get(key, [])
            if not data or len(data) < 20: 
                self.log(f"Snapshot abortado para {symbol}: Datos insuficientes ({len(data)} velas)", "WARNING")
                return
            df = pd.DataFrame(data)
            df['ema20'] = df['c'].ewm(span=20).mean()
            df['ema9']  = df['c'].ewm(span=9).mean()
            df['ema3']  = df['c'].ewm(span=3).mean()
            df['bb_up']  = df['ema20'] + (df['c'].rolling(20).std() * 2)
            df['bb_low'] = df['ema20'] - (df['c'].rolling(20).std() * 2)
            
            df['tr'] = np.maximum(df['h'] - df['l'], np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
            df['atr'] = df['tr'].rolling(window=14).mean()
            # Usar implementacion interna (ya no requiere renombrar columnas)
            calculate_parabolic_sar(df)
            
            # --- MACD 4C para Pinescript Signal ---
            df['macd_fast'] = df['c'].ewm(span=12, adjust=False).mean()
            df['macd_slow'] = df['c'].ewm(span=26, adjust=False).mean()
            df['macd'] = df['macd_fast'] - df['macd_slow']
            df['macd_prev'] = df['macd'].shift(1)
            
            # 1: Up Strong, 2: Up Weak, 3: Down Strong, 4: Down Weak
            df['macd_4c'] = np.select(
                [(df['macd'] > 0) & (df['macd'] > df['macd_prev']),
                 (df['macd'] > 0) & (df['macd'] <= df['macd_prev']),
                 (df['macd'] < 0) & (df['macd'] < df['macd_prev']),
                 (df['macd'] < 0) & (df['macd'] >= df['macd_prev'])],
                [1, 2, 3, 4], default=0
            )
            df['macd_buy'] = (df['macd_4c'] == 4) & (df['macd_4c'].shift(1) == 3)
            df['macd_sell'] = (df['macd_4c'] == 2) & (df['macd_4c'].shift(1) == 1)

            # --- ADX ---
            df['dm_plus'] = np.where((df['h'] - df['h'].shift(1)) > (df['l'].shift(1) - df['l']), np.maximum(df['h'] - df['h'].shift(1), 0), 0)
            df['dm_minus'] = np.where((df['l'].shift(1) - df['l']) > (df['h'] - df['h'].shift(1)), np.maximum(df['l'].shift(1) - df['l'], 0), 0)
            df['tr_14'] = df['tr'].rolling(window=14).mean()
            df['di_plus'] = 100 * (df['dm_plus'].rolling(window=14).mean() / df['tr_14'])
            df['di_minus'] = 100 * (df['dm_minus'].rolling(window=14).mean() / df['tr_14'])
            df['dx'] = 100 * abs(df['di_plus'] - df['di_minus']) / (df['di_plus'] + df['di_minus'] + 1e-10)
            df['adx'] = df['dx'].rolling(window=14).mean()
            
            last = df.iloc[-1]
            candle_price = float(last['c'])
            spot_price = STATE['prices'].get(symbol, {}).get('mid', 0)

            # FIX: Validate spot price against candle price
            # If spot is < 50% of candle price, it's corrupted (partial update bug)
            if spot_price > 0 and candle_price > 0:
                ratio = spot_price / candle_price
                if 0.5 < ratio < 2.0:
                    price = spot_price  # Spot looks valid
                else:
                    price = candle_price  # Fallback to candle
                    self.log(f"[WARN] Spot price {spot_price:.5f} vs candle {candle_price:.5f} for {symbol} - using candle", "WARNING")
            elif spot_price > 0:
                price = spot_price
            else:
                price = candle_price

            # --- SAFE DATA EXTRACTION ---
            def safe_f(val, default=0.0):
                try:
                    if val is None or (isinstance(val, float) and np.isnan(val)): return default
                    return float(val)
                except: return default

            ema20 = safe_f(last.get('ema20'))
            ema9  = safe_f(last.get('ema9'))
            ema3  = safe_f(last.get('ema3'))
            atr   = safe_f(last.get('atr'))
            adx   = safe_f(last.get('adx'), 25.0)

            # Bollinger Expansion detection
            prev = df.iloc[-2] if len(df) >= 2 else last
            bb_expanding = bool((last.get('bb_up', 0) > prev.get('bb_up', 0)) and (last.get('bb_low', 0) < prev.get('bb_low', 0)))
            
            multipliers = [1.0, 1.618, 2.618, 3.618, 4.236, 5.618]
            zone = 0
            if atr > 0:
                for i in range(6, 0, -1):
                    if price > ema20 + (atr * multipliers[i-1]): zone = i; break
                    if price < ema20 - (atr * multipliers[i-1]): zone = -i; break

            # --- CALCULO DE MTF SCORE ---
            mtf_score = 0.0
            tfs_checked = 0
            for tf_suffix in ['15m', '1h', '4h', '1d']:
                tf_key = f"{symbol}_{tf_suffix}"
                tf_data = STATE['candles'].get(tf_key, [])
                if len(tf_data) >= 10:
                    try:
                        tf_df = pd.DataFrame(tf_data)
                        tf_ema20 = tf_df['c'].ewm(span=20).mean().iloc[-1]
                        if price > tf_ema20: mtf_score += 0.25
                        else: mtf_score -= 0.25
                        tfs_checked += 1
                    except: pass
            
            # Calculate Fibonacci band levels
            fib_bands = {}
            if atr > 0:
                for i, m in enumerate(multipliers, 1):
                    fib_bands[f'upper_{i}'] = float(ema20 + (atr * m))
                    fib_bands[f'lower_{i}'] = float(ema20 - (atr * m))

            # Calculate SAR from 4h data if available
            sar_15m = safe_f(last.get('sar'))
            sar_4h = sar_15m  
            sar_trend_4h = 0
            key_4h = f"{symbol}_4h"
            data_4h = STATE['candles'].get(key_4h, [])
            if data_4h and len(data_4h) > 5:
                try:
                    df_4h = pd.DataFrame(data_4h)
                    df_4h['basis'] = df_4h['c'].ewm(span=20).mean()
                    df_4h['tr'] = np.maximum(df_4h['h'] - df_4h['l'], np.maximum(abs(df_4h['h'] - df_4h['c'].shift(1)), abs(df_4h['l'] - df_4h['c'].shift(1))))
                    df_4h['atr'] = df_4h['tr'].rolling(window=14).mean()
                    calculate_parabolic_sar(df_4h)
                    last_4h = df_4h.iloc[-1]
                    sar_4h = safe_f(last_4h.get('sar'))
                    sar_trend_4h = int(last_4h.get('sar_trend', 0))
                except: pass

            dist_basis = abs(price - ema20) / ema20 * 100 if ema20 > 0 else 0

            snap = {
                'symbol': symbol,
                'price': float(price),
                'basis': float(ema20),
                'atr': float(atr),  # Added atr for consistency with stocks_scheduler
                'fibonacci_zone': int(zone),
                'dist_basis_pct': round(dist_basis, 4),
                'mtf_score': float(mtf_score),
                'sar_4h': float(sar_4h),
                'sar_trend_4h': sar_trend_4h,
                'sar_15m': sar_15m,
                'sar_trend_15m': 1 if last.get('sar_trend', 0) > 0 else -1,
                'sar_phase': 'long' if sar_trend_4h > 0 else ('short' if sar_trend_4h < 0 else ('long' if price > sar_15m else 'short')),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'ema_3': ema3,
                'ema_9': ema9,
                'ema_20': ema20,
                'bb_expanding': bb_expanding,
                'adx': adx,
                'pinescript_signal': 'Buy' if last.get('macd_buy') else ('Sell' if last.get('macd_sell') else None)
            }

            # Add Fibonacci bands
            snap.update(fib_bands)

            query = sb.table('market_snapshot').upsert(snap, on_conflict='symbol')
            
            def safe_upsert(q, s):
                try:
                    return q.execute()
                except Exception as e:
                    err_str = str(e).lower()
                    if "column" in err_str and ("atr" in err_str or "bb_expanding" in err_str or "ema_" in err_str):
                        # Limpieza agresiva de columnas conflictivas
                        for col in ['atr', 'bb_expanding', 'ema_3', 'ema_9', 'ema_20']:
                            if col in s: del s[col]
                        return sb.table('market_snapshot').upsert(s, on_conflict='symbol').execute()

                    raise e

            threads.deferToThread(safe_upsert, query, snap).addErrback(
                lambda f: self.log(f"Error async db snapshot: {f.getErrorMessage()}", "ERROR")
            )
        except Exception as e: 
            self.log(f"Error snap {symbol}:\n{traceback.format_exc()}", "ERROR")

if __name__ == '__main__':
    worker = StandaloneForexWorker(); worker.start()
