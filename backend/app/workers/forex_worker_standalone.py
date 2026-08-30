from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASymbolByIdRes, ProtoOAOrderErrorEvent
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
import asyncio

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
from dataclasses import field
from app.strategy.proactive_exit import evaluate_proactive_exit
from app.strategy.dynamic_sl_manager import evaluate_sl_action
from app.strategy.capital_protection import ProtectionState, evaluate_volatile_trailing_v2, evaluate_trailing_stop

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
    '5m':  ProtoOATrendbarPeriod.M5,
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

def convert_ctrader_volume_to_lots(symbol: str, volume: int) -> float:
    """Convierte el volumen de cTrader OpenAPI a lotes estándar de eTrade."""
    s = (symbol or '').upper()
    if s == 'XAUUSD':
        return round(float(volume) / 10000.0, 4)
    elif s in ('US30', 'US500', 'NAS100', 'XAGUSD'):
        return round(float(volume) / 100.0, 4)
    else:
        return round(float(volume) / 10000000.0, 4)

def format_ctrader_price(symbol: str, price: float) -> float:
    """Formatea la precisión del precio para cTrader según el símbolo para evitar TRADING_BAD_STOPS."""
    if not price:
        return 0.0
    s = (symbol or '').upper()
    if 'JPY' in s:
        return float(round(price, 3))
    elif s in ('XAUUSD', 'US30', 'US500', 'NAS100'):
        return float(round(price, 2))
    else:
        return float(round(price, 5))




STATE = { 'symbol_ids': {}, 'prices': {}, 'candles': {}, 'cycle_count': 0, 'highest_prices_cache': {}, 'lowest_prices_cache': {} }
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
        self._notified_broker_closed = set()

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
        from app.core.safety_manager import set_current_worker
        set_current_worker('forex_worker', instance=self)
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
            from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent
            req = ProtoHeartbeatEvent()
            self.safe_send(req)
        except Exception as e:
            self.log(f"Error enviando heartbeat: {e}", "ERROR")

    def _load_dynamic_symbols(self):
        """Carga la lista de simbolos y actualiza BOT_STATE.config_cache con trading_config y risk_config."""
        try:
            from app.core.memory_store import BOT_STATE
            res = sb.table('trading_config').select('*').eq('id', 1).execute()
            data = res.data[0] if res.data else {}
            if data:
                BOT_STATE.config_cache.update(data)
                
            rc_res = sb.table('risk_config').select('*').limit(1).execute()
            if rc_res.data:
                BOT_STATE.config_cache.update(rc_res.data[0])
                
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
            self.log(f"Error cargando símbolos dinámicos: {e}. Usando valores por defecto.")

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

            # Ciclo de actualizacion de configuracion desde DB (cada 5 min)
            self._config_task = task.LoopingCall(self._load_dynamic_symbols)
            self._config_task.start(300, now=False)

            # Ciclo de reconciliacion en tiempo real con cTrader (cada 30s)
            self._reconcile_task = task.LoopingCall(self.request_reconciliation)
            self._reconcile_task.start(30, now=True)

            # Ciclo de lectura de comandos IPC (cada 3s)
            self._ipc_task = task.LoopingCall(self._process_manual_commands)
            self._ipc_task.start(3, now=False)

        except Exception as e:
            self.log(f"Error iniciando Execution Service: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")

    def _start_evaluation_loop(self):
        """Inicia el loop de evaluacion de estrategias."""
        self._eval_task = task.LoopingCall(self.execution.run_evaluation_cycle)
        self._eval_task.start(300, now=True)  # Cada 5 min, ejecutar inmediatamente

    def _process_manual_commands(self):
        """Lee el archivo de comandos IPC y ejecuta ordenes manuales."""
        import os
        import json
        cmd_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scratch", "forex_commands.json")
        if not os.path.exists(cmd_file):
            return
            
        try:
            with open(cmd_file, "r") as f:
                cmds = json.load(f)
            
            if not cmds:
                return
                
            # Clear file
            with open(cmd_file, "w") as f:
                json.dump([], f)
                
            for cmd in cmds:
                action = cmd.get("action")
                symbol = cmd.get("symbol")
                if action == "open":
                    self.log(f"⚡ [MANUAL OPEN] {symbol} {cmd.get('direction').upper()} lots: {cmd.get('lots')}")
                    self.execution._execute_live_order(
                        symbol=symbol,
                        direction=cmd.get("direction"),
                        lots=cmd.get("lots"),
                        entry=0, # Market order o base para Limit si se deja as 
                        sl=cmd.get("sl", 0),
                        tp=cmd.get("tp", 0),
                        rule_code="MANUAL",
                        order_type=cmd.get("order_type", "market"),
                        limit_price=cmd.get("limit_price", 0)
                    )
                elif action == "close":
                    pos_id = cmd.get("pos_id")
                    self.log(f"⚡ [MANUAL CLOSE] Cerrando posicion {symbol} (id: {pos_id})")
                    # Try to find position in memory
                    pos_in_mem = next((p for p in self.execution._open_positions_list if str(p.get("id")) == str(pos_id)), None)
                    if pos_in_mem:
                        # Grab real time price
                        price_data = STATE['prices'].get(symbol)
                        price = float(price_data.get('mid')) if price_data else float(pos_in_mem.get('current_price', 0))
                        
                        pip_size = 0.0001
                        if "JPY" in symbol: pip_size = 0.01
                        elif "XAU" in symbol: pip_size = 0.01
                        
                        entry = float(pos_in_mem.get('entry_price', 0))
                        is_long = pos_in_mem.get('side', '').lower() in ('long', 'buy')
                        pips = (price - entry) / pip_size if is_long else (entry - price) / pip_size
                        
                        self.execution._close_position(pos_in_mem, price, "MANUAL_CLOSE", pips)
                    else:
                        self.log(f"⚠️ [MANUAL CLOSE] Posicion {pos_id} no encontrada en memoria.")
                elif action == "modify":
                    pos_id = cmd.get("pos_id")
                    new_tp = cmd.get("tp")
                    new_sl = cmd.get("sl")
                    pos_in_mem = next((p for p in self.execution._open_positions_list if str(p.get("id")) == str(pos_id)), None)
                    if pos_in_mem:
                        if new_tp is not None:
                            pos_in_mem["tp_price"] = new_tp
                        if new_sl is not None:
                            pos_in_mem["sl_price"] = new_sl
                        self.log(f"⚡ [MANUAL MODIFY] TP/SL actualizados en memoria para la posicion {pos_id}")
                    else:
                        self.log(f"⚠️ [MANUAL MODIFY] Posicion {pos_id} no encontrada en memoria.")

        except Exception as e:
            self.log(f"Error procesando comandos manuales: {e}", "ERROR")


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
            try:
                # Limpiar cualquier posición fantasma reciente sin ID cTrader
                sb.table('forex_positions').update({
                    'status': 'closed',
                    'close_reason': f"ctrader_error_{err.errorCode}"
                }).eq('status', 'open').is_('ctrader_pos_id', 'null').execute()
            except Exception as clean_err:
                self.log(f"Error limpiando posicion fantasma: {clean_err}", "ERROR")
        elif pt == ProtoOAOrderErrorEvent().payloadType:
            err = Protobuf.extract(message)
            self.log(f"RECHAZO DE CTRADER (OrderError): {err.errorCode} - {getattr(err, 'description', '')}", "ERROR")
            try:
                sb.table('forex_positions').update({
                    'status': 'closed',
                    'close_reason': f"ctrader_error_{err.errorCode}"
                }).eq('status', 'open').is_('ctrader_pos_id', 'null').execute()
            except Exception as clean_err:
                self.log(f"Error limpiando posicion fantasma: {clean_err}", "ERROR")
        elif pt == ProtoOASymbolsListRes().payloadType:
            res = Protobuf.extract(message)
            STATE['pending_symbol_ids'] = []
            STATE['symbol_candidates'] = {}
            STATE['id_to_name'] = {}
            for sym in res.symbol:
                base_name = sym.symbolName.split('.')[0].upper().strip()
                if base_name in self.symbols:
                    STATE['pending_symbol_ids'].append(sym.symbolId)
                    STATE['id_to_name'][sym.symbolId] = sym.symbolName
                    if base_name not in STATE['symbol_candidates']:
                        STATE['symbol_candidates'][base_name] = []
                    STATE['symbol_candidates'][base_name].append({'id': sym.symbolId, 'name': sym.symbolName})
            
            if STATE['pending_symbol_ids']:
                from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASymbolByIdReq
                req = ProtoOASymbolByIdReq()
                req.ctidTraderAccountId = ACCOUNT_ID
                req.symbolId.extend(STATE['pending_symbol_ids'])
                self.safe_send(req)
                self.log(f"Consultando detalles de {len(STATE['pending_symbol_ids'])} posibles IDs para validacion estricta...")
            else:
                self.log("No se encontraron simbolos candidatos.")
                
        elif pt == ProtoOASymbolByIdRes().payloadType:
            res = Protobuf.extract(message)
            count = 0
            for sym in res.symbol:
                if getattr(sym, 'tradingMode', -1) == 0:  # 0 = ENABLED
                    sym_name = STATE.get('id_to_name', {}).get(sym.symbolId, "")
                    if not sym_name:
                        continue
                    base_name = sym_name.split('.')[0].upper().strip()
                    if base_name in self.symbols:
                        if base_name in STATE['symbol_ids']:
                            if '.' in sym_name:
                                STATE['symbol_ids'][base_name] = sym.symbolId
                                STATE.setdefault('symbol_names', {})[base_name] = sym_name
                        else:
                            STATE['symbol_ids'][base_name] = sym.symbolId
                            STATE.setdefault('symbol_names', {})[base_name] = sym_name
                            
            for bname, sid in STATE.get('symbol_ids', {}).items():
                sname = STATE.get('symbol_names', {}).get(bname, bname)
                self.log(f"Vinculado definitivamente: {bname} -> {sname} (ID: {sid}) | TradingMode: ENABLED")
                count += 1
                
            if count > 0:
                self.subscribe_spots(); self.warmup_all()
                reactor.callLater(5, self._init_execution_service)
        elif pt == ProtoOASpotEvent().payloadType:
            self.handle_spot(Protobuf.extract(message))
        elif pt == ProtoOAGetTrendbarsRes().payloadType:
            self.handle_bars(Protobuf.extract(message))
        elif pt == ProtoOAExecutionEvent().payloadType:
            self._handle_execution_event(Protobuf.extract(message))
        elif pt == ProtoOAReconcileRes().payloadType:
            self._handle_reconcile_res(Protobuf.extract(message))

    def request_reconciliation(self):
        """Solicita reconciliación oficial a cTrader para verificar posiciones vivas en IC Markets."""
        try:
            self.log(f"🔄 [RECONCILE LOOP] Enviando ProtoOAReconcileReq para cuenta {ACCOUNT_ID}...")
            req = ProtoOAReconcileReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            self.safe_send(req)
        except Exception as e:
            self.log(f"Error en request_reconciliation: {e}")

    def _handle_reconcile_res(self, res):
        """Maneja la respuesta de reconciliación oficial de cTrader para sincronización 100% real de posiciones y montos."""
        try:
            pos_list = list(getattr(res, 'position', []))
            self.log(f"📥 [RECONCILE RES] Recibida respuesta de cTrader. Posiciones en broker: {len(pos_list)}")
            active_ctrader_ids = set()
            if hasattr(res, 'position'):
                for pos in res.position:
                    pid = pos.positionId
                    p_status = pos.positionStatus
                    
                    if p_status == 1: # 1 = OPEN en IC Markets
                        active_ctrader_ids.add(pid)
                        symbol_name = next((n for n, sid in STATE.get('symbol_ids', {}).items() if sid == pos.tradeData.symbolId), None)
                        if not symbol_name:
                            raw_name = STATE.get('id_to_name', {}).get(pos.tradeData.symbolId, '')
                            if raw_name:
                                symbol_name = raw_name.split('.')[0].upper().strip()
                                
                        if not symbol_name:
                            self.log(f"⚠️ [RECONCILE WARN] No se pudo mapear símbolo para symbolId {pos.tradeData.symbolId} (Pos ID: {pid})")
                            continue
                            
                        # 🛡️ Si el símbolo NO está en la lista permitida de Forex, auto-liquidar de inmediato
                        if symbol_name not in self.symbols:
                            self.log(f"🚨 [AUTO-LIQUIDATE UNAUTHORIZED SYMBOL] {symbol_name} no está en lista de permitidos ({self.symbols}). Liquidando posición cTrader ID {pid} a mercado...")
                            self.close_position(pid, symbol=symbol_name, reason='unauthorized_symbol_safety_close')
                            continue

                        side = 'long' if pos.tradeData.tradeSide == 1 else 'short'
                        
                        # Extraer monto en lotes y precio de entrada oficial del broker
                        volume = getattr(pos.tradeData, 'volume', 0)
                        lots = convert_ctrader_volume_to_lots(symbol_name, volume)
                        entry_price = getattr(pos, 'price', 0.0) or STATE.get('prices', {}).get(symbol_name, {}).get('bid', 0.0)
                        sl_price = getattr(pos, 'stopLoss', None)
                        tp_price = getattr(pos, 'takeProfit', None)
                        
                        try:
                            # 1. Buscar si la posición ya existe por ctrader_pos_id
                            db_res = sb.table('forex_positions').select('*').eq('ctrader_pos_id', pid).execute()
                            if db_res.data:
                                db_pos = db_res.data[0]
                                update_fields = {}
                                if db_pos.get('status') != 'open':
                                    update_fields['status'] = 'open'
                                    update_fields['close_reason'] = None
                                if abs(float(db_pos.get('lots') or 0) - lots) > 0.0001:
                                    update_fields['lots'] = lots
                                if entry_price > 0 and abs(float(db_pos.get('entry_price') or 0) - entry_price) > 0.0001:
                                    update_fields['entry_price'] = entry_price
                                if sl_price and abs(float(db_pos.get('sl_price') or 0) - sl_price) > 0.0001:
                                    update_fields['sl_price'] = sl_price
                                if tp_price and abs(float(db_pos.get('tp_price') or 0) - tp_price) > 0.0001:
                                    update_fields['tp_price'] = tp_price
                                    
                                if update_fields:
                                    sb.table('forex_positions').update(update_fields).eq('id', db_pos['id']).execute()
                                    self.log(f"🔄 [RECONCILE UPDATE] Posición IC Markets ID {pid} actualizada en DB: {update_fields}")
                            else:
                                # 2. Buscar si hay una posición abierta sin vincular (ctrader_pos_id NULL)
                                unlinked = sb.table('forex_positions').select('id')\
                                    .eq('symbol', symbol_name)\
                                    .eq('side', side)\
                                    .eq('status', 'open')\
                                    .is_('ctrader_pos_id', 'null')\
                                    .order('opened_at', desc=True)\
                                    .limit(1).execute()
                                    
                                if unlinked.data:
                                    db_id = unlinked.data[0]['id']
                                    sb.table('forex_positions').update({
                                        'ctrader_pos_id': pid,
                                        'status': 'open',
                                        'lots': lots,
                                        'entry_price': entry_price
                                    }).eq('id', db_id).execute()
                                    self.log(f"🔄 [RECONCILE SUCCESS] Vinculada posición IC Markets ID {pid} (Lotes: {lots}) a DB {db_id}")
                                else:
                                    # 3. Buscar si fue cerrada erróneamente en DB local
                                    wrongly_closed = sb.table('forex_positions').select('id')\
                                        .eq('symbol', symbol_name)\
                                        .eq('side', side)\
                                        .eq('status', 'closed')\
                                        .order('opened_at', desc=True)\
                                        .limit(1).execute()
                                        
                                    if wrongly_closed.data:
                                        wc_id = wrongly_closed.data[0]['id']
                                        sb.table('forex_positions').update({
                                            'status': 'open',
                                            'ctrader_pos_id': pid,
                                            'lots': lots,
                                            'entry_price': entry_price,
                                            'close_reason': None
                                        }).eq('id', wc_id).execute()
                                        self.log(f"🛡️ [RECONCILE RE-OPEN] Posición IC Markets ID {pid} re-abierta en DB (Lotes: {lots}).")
                                    else:
                                        # 4. POSICIÓN NUEVA / EXTERNA (creada desde la app móvil o fuera de eTrade) -> IMPORTAR
                                        now_iso = datetime.now(timezone.utc).isoformat()
                                        new_pos_data = {
                                            'symbol': symbol_name,
                                            'side': side,
                                            'lots': lots,
                                            'entry_price': entry_price,
                                            'sl_price': sl_price or 0.0,
                                            'tp_price': tp_price or 0.0,
                                            'status': 'open',
                                            'mode': 'live',
                                            'ctrader_pos_id': pid,
                                            'rule_code': 'EXTERNAL_ICMARKETS',
                                            'opened_at': now_iso,
                                        }
                                        sb.table('forex_positions').insert(new_pos_data).execute()
                                        self.log(f"📥 [RECONCILE IMPORT] Posición externa IC Markets importada exitosamente: {side.upper()} {symbol_name} {lots} lotes @ {entry_price} (ID cTrader: {pid})")
                                        
                                        # Notificar por Telegram
                                        try:
                                            from app.workers.alerts_service import send_telegram_message
                                            msg = (
                                                f"🔄 *[POSICIÓN IMPORTADA DE BROKER]*\n"
                                                f"Se detectó e importó una posición de IC Markets:\n"
                                                f"• *Símbolo*: {symbol_name}\n"
                                                f"• *Lado*: {side.upper()}\n"
                                                f"• *Monto/Lotes*: {lots}\n"
                                                f"• *Precio Entrada*: {entry_price:.5f}\n"
                                                f"• *cTrader ID*: `{pid}`"
                                            )
                                            reactor.callInThread(lambda: asyncio.run(send_telegram_message(msg)))
                                        except Exception as tele_e:
                                            self.log(f"Error enviando notificación Telegram de importación: {tele_e}")

                        except Exception as db_e:
                            self.log(f"Error procesando reconcile DB para pos {pid}: {db_e}")

            # 5. DETECTAR Y CERRAR POSICIONES EN DB QUE YA NO EXISTEN EN EL BROKER
            try:
                db_open_res = sb.table('forex_positions').select('id, ctrader_pos_id, symbol, side, lots')\
                    .eq('status', 'open')\
                    .not_.is_('ctrader_pos_id', 'null')\
                    .execute()
                
                if db_open_res.data:
                    for db_p in db_open_res.data:
                        c_id = str(db_p.get('ctrader_pos_id') or '')
                        if c_id and (int(c_id) if c_id.isdigit() else c_id) not in active_ctrader_ids and c_id not in active_ctrader_ids:
                            # 1. Sincronizar el cierre en DB
                            synced = self._sync_broker_closed_position(db_p['id'], close_price=None, close_reason='closed_at_broker')
                            self.log(f"🛡️ [RECONCILE CLOSE] Posición DB {db_p['id']} (cTrader {c_id}) ya no está activa en IC Markets. Marcada como CLOSED (synced={synced}).")

                            # 2. Notificar por Telegram una sola vez
                            if c_id not in self._notified_broker_closed:
                                self._notified_broker_closed.add(c_id)
                                try:
                                    from app.workers.alerts_service import send_telegram_message
                                    msg = (
                                        f"🛡️ *[POSICIÓN CERRADA EN BROKER]*\n"
                                        f"La posición fue cerrada en IC Markets y sincronizada en eTrade:\n"
                                        f"• *Símbolo*: {db_p.get('symbol')}\n"
                                        f"• *Lado*: {(db_p.get('side') or '').upper()}\n"
                                        f"• *Lotes*: {db_p.get('lots')}\n"
                                        f"• *cTrader ID*: `{c_id}`"
                                    )
                                    reactor.callInThread(lambda: asyncio.run(send_telegram_message(msg)))
                                except Exception as tele_e:
                                    pass
            except Exception as close_sync_e:
                self.log(f"Error sincronizando cierres desde cTrader: {close_sync_e}")

            # 6. RECONCILIACIÓN DE ÓRDENES PENDIENTES (ANTI-FANTASMAS)
            try:
                if hasattr(res, 'order') and res.order:
                    for ord_item in res.order:
                        ord_id = getattr(ord_item, 'orderId', None)
                        if not ord_id:
                            continue
                        ord_sym_id = getattr(getattr(ord_item, 'tradeData', None), 'symbolId', None)
                        ord_sym_name = next((n for n, sid in STATE.get('symbol_ids', {}).items() if sid == ord_sym_id), None)
                        
                        should_cancel = False
                        cancel_reason = ""
                        
                        if ord_sym_name and ord_sym_name not in self.symbols:
                            should_cancel = True
                            cancel_reason = f"Símbolo no autorizado ({ord_sym_name})"
                        else:
                            try:
                                db_ord = sb.table('forex_positions').select('id, status')\
                                    .eq('ctrader_order_id', ord_id)\
                                    .in_('status', ['pending', 'pending_limit'])\
                                    .execute()
                                if not db_ord.data:
                                    should_cancel = True
                                    cancel_reason = "Orden huérfana no reconocida en eTrade"
                            except Exception:
                                pass
                                
                        if should_cancel:
                            self.log(f"🧹 [ANTI-GHOST] Cancelando orden fantasma en cTrader OrderID {ord_id} ({ord_sym_name or 'N/A'}). Razón: {cancel_reason}")
                            self.cancel_order(ord_id)
            except Exception as ord_reconcile_e:
                self.log(f"Error reconciliando órdenes pendientes cTrader: {ord_reconcile_e}", "WARNING")

        except Exception as e:
            self.log(f"Error procesando ProtoOAReconcileRes: {e}")

    def _sync_broker_closed_position(self, pos_id, close_price=None, close_reason='ctrader_broker_closed'):
        """Actualiza el cierre de una posición en DB calculando PnL exacto si cerró en cTrader."""
        try:
            from app.strategy.capital_protection import PIP_SIZES
            res = sb.table('forex_positions').select('*').eq('id', pos_id).execute()
            if not res.data:
                return False
            pos = res.data[0]
            symbol = pos.get('symbol') or ''
            side = (pos.get('side') or 'long').lower()
            entry_price = float(pos.get('entry_price') or 0)
            lots_qty = abs(float(pos.get('lots') or 0))
            
            if not close_price or close_price <= 0:
                close_price = float(STATE.get('prices', {}).get(symbol, {}).get('bid') or entry_price)
                
            upd_fields = {
                'status': 'closed',
                'closed_at': datetime.now(timezone.utc).isoformat(),
                'close_reason': close_reason
            }
            
            if entry_price > 0 and close_price > 0:
                pip_size_val = PIP_SIZES.get(symbol, 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001)
                pip_val_usd = 1.0 if 'XAU' in symbol else (6.5 if 'JPY' in symbol else 10.0)
                is_short_pos = side in ('short', 'sell')
                pips_pnl_calc = (entry_price - close_price) / pip_size_val if is_short_pos else (close_price - entry_price) / pip_size_val
                pnl_usd_calc = pips_pnl_calc * pip_val_usd * lots_qty
                
                upd_fields['current_price'] = close_price
                upd_fields['pnl_pips'] = round(pips_pnl_calc, 1)
                upd_fields['pnl_usd'] = round(pnl_usd_calc, 2)
                
                try:
                    from app.core.capital_manager import register_realized_pnl
                    register_realized_pnl('forex', round(pnl_usd_calc, 2))
                except Exception:
                    pass
                    
            self.safe_db_execute(sb.table('forex_positions').update(upd_fields).eq('id', pos_id))
            self.log(f"[SYNC] Cierre sincronizado en DB (ID: {pos_id}, Razón: {close_reason}, Exit: {close_price}, PnL: {upd_fields.get('pnl_usd')})")
            return True
        except Exception as e:
            self.log(f"Error sincronizando cierre en DB para {pos_id}: {e}", "ERROR")
            return False

    def _handle_execution_event(self, event):
        """Maneja respuestas de ejecucion de ordenes de cTrader."""
        try:
            if hasattr(event, 'order') and event.order:
                order = event.order
                oid = order.orderId
                self.log(
                    f"  Orden cTrader: id={oid} "
                    f"status={event.executionType} "
                    f"symbol_id={order.tradeData.symbolId if hasattr(order, 'tradeData') else 'N/A'}"
                )
            
                # Manejar rechazo de orden por parte del broker (cTrader)
                exec_type_str = str(getattr(event, 'executionType', '')).upper()
                if 'REJECT' in exec_type_str or str(getattr(event, 'executionType', '')) == '5':
                    self.log(f"⚠️ [BROKER REJECT] Orden rechazada por cTrader: {exec_type_str}. Marcando como cancelled_rejected en DB.")
                    try:
                        sym_id = getattr(order, 'tradeData', None)
                        sym_id_val = getattr(sym_id, 'symbolId', None) if sym_id else None
                        name = next((n for n, sid in STATE['symbol_ids'].items() if sid == sym_id_val), None)
                        if name:
                            sb.table('forex_positions').update({
                                'status': 'cancelled_rejected',
                                'close_reason': 'ctrader_rejected_by_broker'
                            }).eq('symbol', name).in_('status', ['open', 'pending']).is_('ctrader_pos_id', 'null').execute()
                    except Exception as rej_err:
                        self.log(f"Error limpiando posición rechazada por broker: {rej_err}", "WARNING")
                elif getattr(event, 'executionType', None) == 1: # ORDER_ACCEPTED
                    # Vincular ctrader_order_id a la orden pendiente en DB
                    try:
                        sym_id = getattr(order, 'tradeData', None)
                        sym_id_val = getattr(sym_id, 'symbolId', None) if sym_id else None
                        name = next((n for n, sid in STATE['symbol_ids'].items() if sid == sym_id_val), None)
                        if name:
                            sb.table('forex_positions').update({'ctrader_order_id': oid})\
                                .eq('symbol', name)\
                                .in_('status', ['pending', 'pending_limit'])\
                                .is_('ctrader_order_id', 'null')\
                                .order('opened_at', desc=True)\
                                .limit(1).execute()
                    except Exception as ord_link_e:
                        self.log(f"Error vinculando ctrader_order_id {oid}: {ord_link_e}", "DEBUG")

            if hasattr(event, 'position') and event.position:
                pos = event.position
                pid = pos.positionId
                p_status = pos.positionStatus
                self.log(f"  Posicion cTrader: id={pid} status={p_status}")

                # Solo vincular y abrir la posicion en DB si la orden se llenó (ejecutada)
                # executionType: 2 = ORDER_FILLED, 3 = ORDER_REPLACED, etc. 
                # (Evitamos 1 = ORDER_ACCEPTED para que las LIMIT pendientes no cambien a OPEN)
                exec_type = getattr(event, 'executionType', None)
                if p_status == 1 and exec_type == 2: # 1 = OPEN, 2 = ORDER_FILLED
                    # Buscar el simbolo por ID
                    name = next((n for n, sid in STATE['symbol_ids'].items() if sid == pos.tradeData.symbolId), None)
                    if name:
                        # 🛡️ Si el símbolo NO está en la lista permitida de Forex, auto-liquidar de inmediato
                        if name not in self.symbols:
                            self.log(f"🚨 [AUTO-LIQUIDATE UNAUTHORIZED SYMBOL] {name} no permitido ({self.symbols}). Liquidando posición cTrader ID {pid} a mercado...")
                            self.close_position(pid, symbol=name, reason='unauthorized_symbol_safety_close')
                            return

                        # 🛡️ Anti-Duplicados: Verificar si este ctrader_pos_id ya existe en DB
                        try:
                            existing_pos = sb.table('forex_positions').select('id, status').eq('ctrader_pos_id', pid).execute()
                            if existing_pos.data:
                                self.log(f"[SYNC] cTrader ID {pid} ya registrado en DB (ID: {existing_pos.data[0]['id']}). Omitiendo duplicado.")
                                return
                        except Exception:
                            pass

                        side = 'long' if pos.tradeData.tradeSide == 1 else 'short'
                        # Buscar la posicion mas reciente abierta o pendiente en DB sin ID vinculado
                        try:
                            res = sb.table('forex_positions')\
                                .select('id, sl_price, tp_price, entry_price')\
                                .eq('symbol', name)\
                                .eq('side', side)\
                                .in_('status', ['open', 'pending', 'pending_limit'])\
                                .is_('ctrader_pos_id', 'null')\
                                .order('opened_at', desc=True)\
                                .limit(1).execute()
                            
                            if res.data:
                                db_pos = res.data[0]
                                db_id = db_pos['id']
                                fill_price = float(pos.price) if hasattr(pos, 'price') and pos.price else float(db_pos.get('entry_price') or 0)
                                sb.table('forex_positions').update({
                                    'ctrader_pos_id': pid,
                                    'status': 'open',
                                    'entry_price': fill_price if fill_price > 0 else db_pos.get('entry_price'),
                                    'close_reason': None
                                }).eq('id', db_id).execute()
                                self.log(f"[SYNC] Vinculado cTrader ID {pid} a posicion DB {db_id} (Gestión 100% Virtual SL/TP por eTrade)")
                            else:
                                # Si no existía registro previo, insertar una nueva posición limpia sin pisar el historial cerrado
                                entry_px = float(pos.price) if hasattr(pos, 'price') and pos.price else float(STATE.get('prices', {}).get(name, {}).get('bid') or 0)
                                lot_size = float(pos.tradeData.volume) / 10000000.0 if hasattr(pos, 'tradeData') and hasattr(pos.tradeData, 'volume') else 0.01
                                pip_sz = 0.01 if name in ('USDJPY', 'XAUUSD') else 0.0001
                                # SL Virtual Fibonacci: NO enviar SL real al broker.
                                # eTrade controla 100% las salidas. Solo un SL catástrofe ultra-lejano como red de seguridad.
                                catastrophe_pips = 500 if name in ('XAUUSD',) else 200
                                default_sl = round(entry_px - (catastrophe_pips * pip_sz) if side == 'long' else entry_px + (catastrophe_pips * pip_sz), 5)
                                new_rec = {
                                    'symbol': name,
                                    'side': side,
                                    'lots': round(lot_size, 2) if lot_size > 0 else 0.01,
                                    'entry_price': entry_px,
                                    'sl_price': default_sl if entry_px > 0 else 0.0,
                                    'tp_price': 0.0,
                                    'rule_code': 'cTrader_Direct',
                                    'ctrader_pos_id': pid,
                                    'status': 'open',
                                    'market_type': 'forex_futures',
                                    'mode': 'live',
                                    'opened_at': datetime.now(timezone.utc).isoformat()
                                }
                                sb.table('forex_positions').insert(new_rec).execute()
                                self.log(f"[SYNC] Creado nuevo registro en DB para cTrader ID {pid} ({name} {side.upper()}, SL: {default_sl})")
                        except Exception as e:
                            self.log(f"Error vinculando ID: {e}", "ERROR")

                elif p_status == 2: # 2 = CLOSED
                    try:
                        db_res = sb.table('forex_positions').select('id').eq('ctrader_pos_id', pid).eq('status', 'open').execute()
                        close_px = None
                        if hasattr(event, 'deal') and event.deal and hasattr(event.deal, 'executionPrice') and event.deal.executionPrice:
                            close_px = float(event.deal.executionPrice)
                        elif hasattr(pos, 'price') and pos.price:
                            close_px = float(pos.price)
                            
                        if db_res.data:
                            for db_p in db_res.data:
                                self._sync_broker_closed_position(db_p['id'], close_price=close_px, close_reason='ctrader_broker_closed')
                        self.log(f"[SYNC] Sincronizado cierre oficial en cTrader ID {pid}")
                    except Exception as e:
                        self.log(f"Error sincronizando cierre cTrader: {e}", "ERROR")

        except Exception as e:
            self.log(f"Error procesando evento de ejecucion: {e}", "ERROR")

    def cancel_order(self, order_id):
        """Envía ProtoOACancelOrderReq a cTrader OpenAPI para cancelar una orden pendiente."""
        try:
            if not order_id:
                return False
            req = ProtoOACancelOrderReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.orderId = int(order_id)
            if hasattr(self, 'safe_send'):
                self.safe_send(req)
            else:
                self.client.send(req)
            self.log(f"🧹 [CTRADER CANCEL] Enviada orden de cancelación a cTrader para OrderID {order_id}")
            return True
        except Exception as e:
            self.log(f"Error enviando cancel_order a cTrader para {order_id}: {e}", "ERROR")
            return False

    def close_position(self, pos_id, volume_units=None, symbol=None, reason='manual', is_qshr=False, **kwargs):
        """Envía orden de cierre a cTrader OpenAPI."""
        try:
            pos = None
            if hasattr(self, 'execution') and hasattr(self.execution, '_open_positions_list'):
                pos = next((p for p in self.execution._open_positions_list if str(p.get('ctrader_pos_id')) == str(pos_id) or str(p.get('id')) == str(pos_id)), None)
            if not pos:
                try:
                    res = sb.table('forex_positions').select('*').eq('ctrader_pos_id', int(pos_id)).limit(1).execute()
                    if res.data:
                        pos = res.data[0]
                except Exception:
                    pass

            sym = (symbol or (pos.get('symbol') if pos else 'GBPUSD')).upper()
            
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAClosePositionReq
            req = ProtoOAClosePositionReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.positionId = int(pos_id)
            
            if volume_units is None:
                lots_abs = abs(float(pos.get('lots', 0.01))) if pos else 0.01
                if sym == 'XAUUSD':
                    volume_units = int(round(lots_abs * 10_000))
                elif sym in ('US30', 'US500', 'NAS100', 'XAGUSD'):
                    volume_units = int(round(lots_abs * 100))
                else:
                    volume_units = int(round(lots_abs * 10_000_000))
                    
            req.volume = int(volume_units)
            self.safe_send(req)
            self.log(f"[CTRADER] Enviada solicitud de cierre para posicion {pos_id} (vol: {req.volume}, symbol: {sym}, reason: {reason})")
            return True
        except Exception as e:
            self.log(f"Error enviando cierre a cTrader para pos {pos_id}: {e}", "ERROR")
            return False

    def trigger_forex_reentry_standalone(self, symbol, side, lots, df_15m):
        try:
            if df_15m is None or len(df_15m) < 20:
                return
                
            df = df_15m.copy()
            df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            
            last_row = df.iloc[-1]
            ema9 = float(last_row['ema9'])
            ema20 = float(last_row['ema20'])
            
            mode_val = os.getenv('FOREX_MODE', 'paper')
            
            orders = [
                {'limit_price': ema9, 'pct': 40, 'name': 'Order 1 (EMA9)'},
                {'limit_price': ema20, 'pct': 60, 'name': 'Order 2 (EMA20)'}
            ]
            
            from datetime import datetime, timezone, timedelta
            for op in orders:
                limit_px = round(op['limit_price'], 5)
                qty_val = round(lots * (op['pct'] / 100.0), 2)
                
                if qty_val <= 0:
                    continue
                    
                new_order = {
                    'symbol': symbol,
                    'direction': side.lower(),
                    'order_type': 'limit',
                    'trade_type': 'swing_ema',
                    'rule_code': 'AaApexEma' if side.lower() in ('long', 'buy') else 'BbApexEma',
                    'limit_price': limit_px,
                    'sl_price': 0,
                    'tp1_price': 0,
                    'tp2_price': 0,
                    'band_name': op['name'],
                    'status': 'pending',
                    'mode': mode_val,
                    'expires_at': (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
                    'sizing_pct': op['pct'] / 100.0,
                    'timeframe': '15m',
                    'movement_type': 'trend_ema',
                    'signal_quality': 'high',
                    'fib_zone_entry': 0
                }
                
                sb.table('pending_orders').insert(new_order).execute()
                self.log(f"🎯 [FOREX TS STANDALONE RE-ENTRY LIMIT] {symbol} {side.upper()}: {op['name']} colocada a {limit_px} | Lots: {qty_val}")
                
                # Telegram notification
                try:
                    from app.workers.alerts_service import send_telegram_message
                    from twisted.internet import reactor
                    reactor.callInThread(lambda: asyncio.run(send_telegram_message(
                        f"🎯 RE-ENTRADA TRAILING STOP STANDALONE FOREX [{symbol}]\n"
                        f"Dirección: {side.upper()}\n"
                        f"Nivel: {op['name']}\n"
                        f"Precio LIMIT: {limit_px:.5f}\n"
                        f"Lots: {qty_val}\n"
                        f"Modo: {mode_val.upper()}"
                    )))
                except Exception as tg_e:
                    self.log(f"Telegram alert error: {tg_e}")
        except Exception as e:
            self.log(f"Error placing forex reentry: {e}", "ERROR")

    def amend_position(self, pos_id, sl_price=None, tp_price=None, symbol=None):
        """Modifica SL/TP en cTrader."""
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAmendPositionSLTPReq
            req = ProtoOAAmendPositionSLTPReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.positionId = int(pos_id)
            
            divisor = get_divisor(symbol) if symbol else 100000
            
            if sl_price:
                req.stopLoss = format_ctrader_price(symbol, sl_price)
            if tp_price:
                req.takeProfit = format_ctrader_price(symbol, tp_price)
            
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
            # 5m (NUEVO para Trailing SHORT)
            reactor.callLater(delay, self.request_bars, sym, '5m', 200)
            delay += 1.5
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

        # Actualizar watchdog
        STATE.setdefault('last_data_ts', {})[name] = time.time()
        
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
        
        # Robustly extract period value (handles raw int, enum wrapper, or string)
        period_val = res.period
        if hasattr(period_val, 'value'):
            period_val = period_val.value
        try:
            period_int = int(period_val)
        except (ValueError, TypeError):
            period_int = period_val
            
        p_rev = {}
        for k, v in TF_MAP.items():
            val = v
            if hasattr(val, 'value'):
                val = val.value
            try:
                p_rev[int(val)] = k
            except (ValueError, TypeError):
                p_rev[val] = k
                
        tf = p_rev.get(period_int, '15m')
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
            STATE.setdefault('last_data_ts', {})[name] = time.time()
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
            # pero SÍ sincronizamos MEMORY_STORE para que las señales funcionen desde el inicio
            if STATE.get('is_warming_up', False) and len(df) > 10:
                self._sync_memory_store(sym, tf, df)
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
                # THROTTLE: Solo upsertear a Supabase cada 60 min para reducir egress
                import time as _time
                if not hasattr(self, '_upsert_last'):
                    self._upsert_last = {}
                _key = f"{sym}_{tf}"
                _now = _time.time()
                if _key not in self._upsert_last or (_now - self._upsert_last[_key]) >= 3600:
                    self._upsert_last[_key] = _now
                    self.safe_db_execute(sb.table('market_candles').upsert(rows, on_conflict='symbol,exchange,timeframe,open_time'))
            
            # CRITICAL FIX: Sincronizar MEMORY_STORE para que forex_execution_service pueda leer datos
            self._sync_memory_store(sym, tf, df)
        except Exception as e: 
            self.log(f"Error procesando {sym} ({tf}):\n{traceback.format_exc()}", "ERROR")

    def _sync_memory_store(self, symbol, tf, df):
        """
        Sincroniza el DataFrame procesado con MEMORY_STORE para que
        forex_execution_service.py pueda acceder a los indicadores necesarios
        (SIPV patterns, EMAs, ADX, DI+/DI-, ema20_angle/phase).
        
        SIN ESTE MÉTODO, MEMORY_STORE está vacío para forex y NUNCA se generan señales.
        """
        try:
            from app.core.memory_store import update_memory_df
            
            if df is None or df.empty or len(df) < 20:
                return
            
            df_mem = df.copy()
            
            # --- EMAs compatibles con el formato esperado (ema1=3, ema2=9, ema3=20, ema4=50, ema5=200) ---
            if 'close' in df_mem.columns:
                close_col = df_mem['close']
            elif 'c' in df_mem.columns:
                close_col = df_mem['c']
            else:
                return
            
            df_mem['ema1'] = close_col.ewm(span=3, adjust=False).mean()   # EMA 3
            df_mem['ema2'] = close_col.ewm(span=9, adjust=False).mean()   # EMA 9
            df_mem['ema3'] = close_col.ewm(span=20, adjust=False).mean()  # EMA 20
            df_mem['ema4'] = close_col.ewm(span=50, adjust=False).mean()  # EMA 50
            df_mem['ema5'] = close_col.ewm(span=200, adjust=False).mean() # EMA 200
            
            # --- ADX, DI+, DI- ---
            high_col = df_mem.get('high', df_mem.get('h'))
            low_col = df_mem.get('low', df_mem.get('l'))
            if high_col is not None and low_col is not None:
                tr = np.maximum(high_col - low_col, 
                       np.maximum(abs(high_col - close_col.shift(1)), 
                                  abs(low_col - close_col.shift(1))))
                df_mem['atr'] = tr.rolling(window=14).mean()
                
                dm_plus = np.where(
                    (high_col - high_col.shift(1)) > (low_col.shift(1) - low_col),
                    np.maximum(high_col - high_col.shift(1), 0), 0)
                dm_minus = np.where(
                    (low_col.shift(1) - low_col) > (high_col - high_col.shift(1)),
                    np.maximum(low_col.shift(1) - low_col, 0), 0)
                
                tr_14 = tr.rolling(window=14).mean()
                df_mem['plus_di'] = 100 * (pd.Series(dm_plus, index=df_mem.index).rolling(14).mean() / (tr_14 + 1e-10))
                df_mem['minus_di'] = 100 * (pd.Series(dm_minus, index=df_mem.index).rolling(14).mean() / (tr_14 + 1e-10))
                dx = 100 * abs(df_mem['plus_di'] - df_mem['minus_di']) / (df_mem['plus_di'] + df_mem['minus_di'] + 1e-10)
                df_mem['adx'] = dx.rolling(window=14).mean()
            
            # --- EMA20 Angle y Phase ---
            ema20 = df_mem['ema3']  # ema3 = EMA 20
            if len(ema20) >= 3:
                df_mem['ema20_angle'] = ema20.diff()
                df_mem['ema20_phase'] = np.where(
                    df_mem['ema20_angle'] > 0, 'rising',
                    np.where(df_mem['ema20_angle'] < 0, 'falling', 'flat'))
            
            # --- SIPV Candlestick Patterns ---
            o = df_mem.get('open', df_mem.get('o'))
            h = high_col
            l = low_col
            c = close_col
            
            if o is not None and h is not None and l is not None:
                body = abs(c - o)
                full_range = h - l + 1e-10
                
                # Dragonfly Doji (bullish): Larga sombra inferior, sin sombra superior
                lower_shadow = np.minimum(o, c) - l
                upper_shadow = h - np.maximum(o, c)
                df_mem['is_dragonfly'] = (lower_shadow > body * 2) & (upper_shadow < body * 0.5) & (body < full_range * 0.3)
                
                # Gravestone Doji (bearish): Larga sombra superior, sin sombra inferior
                df_mem['is_gravestone'] = (upper_shadow > body * 2) & (lower_shadow < body * 0.5) & (body < full_range * 0.3)
                
                # Doji: Body muy pequeño
                df_mem['is_doji'] = body < full_range * 0.1
                
                # Bullish Engulfing
                prev_o = o.shift(1)
                prev_c = c.shift(1)
                df_mem['is_bullish_engulfing'] = (prev_c < prev_o) & (c > o) & (c > prev_o) & (o < prev_c)
                
                # Bearish Engulfing
                df_mem['is_bearish_engulfing'] = (prev_c > prev_o) & (c < o) & (c < prev_o) & (o > prev_c)
                
                # Low higher than previous low
                df_mem['low_higher_than_prev'] = l > l.shift(1)
                
                # High lower than previous high
                df_mem['high_lower_than_prev'] = h < h.shift(1)
            
            # Guardar en MEMORY_STORE
            update_memory_df(symbol, tf, df_mem)
            
        except Exception as e:
            self.log(f"Error sincronizando MEMORY_STORE para {symbol}/{tf}: {e}", "WARNING")

    def run_cycle(self):
        #    Heartbeat                              
        register_heartbeat('forex_worker')
        
        STATE['cycle_count'] = STATE.get('cycle_count', 0) + 1
        cycle = STATE['cycle_count']
        delay = 0
        for sym in self.symbols:
            # Watchdog Activo: Verificar si hay datos recientes (últimos 5 min)
            last_ts = STATE.get('last_data_ts', {}).get(sym, 0)
            if last_ts > 0 and (time.time() - last_ts) > 300:
                self.log(f"WATCHDOG ALERT: Sin datos para {sym} en >5min. Re-evaluando símbolos...", "ERROR")
                # Enviar de nuevo la petición de símbolos para auto-recuperar si el ID cambió
                self.load_symbols()
                # Reiniciar ts para no inundar los logs
                STATE['last_data_ts'][sym] = time.time()
                
            # 5m (NUEVO para Trailing SHORT)
            reactor.callLater(delay, self.request_bars, sym, '5m', 100)
            
            # 15m cada minuto
            reactor.callLater(delay + 1.0, self.request_bars, sym, '15m', 100)
            
            # 1h cada 4 ciclos (~4 min)
            if cycle % 4 == 0:
                reactor.callLater(delay + 2.0, self.request_bars, sym, '1h', 50)
            
            # 4h cada 12 ciclos (~12 min)
            if cycle % 12 == 0:
                reactor.callLater(delay + 3.0, self.request_bars, sym, '4h', 50)
            
            # 1d cada 60 ciclos (~1 hora)
            if cycle % 60 == 0:
                reactor.callLater(delay + 4.0, self.request_bars, sym, '1d', 50)

            # Snapshot real-time
            reactor.callLater(delay + 5.0, self.save_snapshot, sym)
            
            # Gestión de posiciones 5m (Trailing SHORT)
            # Solo ejecutamos si tenemos las velas cargadas (con un pequeño delay tras request_bars)
            reactor.callLater(delay + 7.0, self._manage_position_5m, sym)
            
            delay += 8.0 
        
        self.log(f'Cycle {cycle} complete. TFs updated and 5m management scheduled.')

    def _get_candles_df(self, symbol, tf):
        """Convierte la lista de velas en un DataFrame compatible."""
        key = f"{symbol}_{tf}"
        data = STATE['candles'].get(key, [])
        if not data: return None
        df = pd.DataFrame(data)
        # Renombrar para compatibilidad con el engine
        df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
        return df

    def _route_qshr_to_aduana(self, symbol, signal, df_5m, df_15m, positions=None):
        """Enruta señal QSHR v5 a ADUANAS respetando Cant. Monedas Activas y Cant. Operación x Par."""
        try:
            from app.rebote_aduana.aduana_validator import AduanaValidator
            from app.core.memory_store import BOT_STATE
            
            regime_params = BOT_STATE.config_cache.get('regime_params') or {}
            max_active = int(regime_params.get('max_active_symbols_forex', 1))
            max_per_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 3))
            
            # Consultar símbolos y posiciones activos en tiempo real (open, pending, pending_limit)
            res = self.safe_db_execute(sb.table('forex_positions').select('symbol').in_('status', ['open', 'pending', 'pending_limit']))
            open_symbols = list(set([r['symbol'] for r in (res.data or []) if r.get('symbol')]))
            
            sym_pos_res = self.safe_db_execute(sb.table('forex_positions').select('id').eq('symbol', symbol).in_('status', ['open', 'pending', 'pending_limit']))
            current_sym_positions = len(sym_pos_res.data or [])
            
            # Pre-filtro estricto antes de ADUANA
            if symbol not in open_symbols and len(open_symbols) >= max_active:
                self.log(f"🛑 [QSHR ACTIVE SYMBOL LIMIT] {symbol}: Máximo de {max_active} monedas activas alcanzado ({len(open_symbols)}/{max_active}: {open_symbols})")
                return False
                
            if current_sym_positions >= max_per_symbol:
                self.log(f"🛑 [QSHR MAX POSITIONS PER SYMBOL] {symbol}: Máximo de {max_per_symbol} posiciones alcanzado ({current_sym_positions}/{max_per_symbol})")
                return False
            
            aduana = AduanaValidator()
            side = signal.get('side', 'long')
            market_data = {
                'df_15m': df_15m,
                'df_5m': df_5m,
                'squeeze_velocity': float(signal.get('velocity', 0.0)),
                'open_symbols': open_symbols,
                'max_active_symbols': max_active,
                'current_symbol_positions': current_sym_positions,
                'max_positions_per_symbol': max_per_symbol
            }
            
            rule_code = signal.get('rule_code', 'Bb33_QSHR')
            result = aduana.validate(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                market_data=market_data,
                strategy=rule_code
            )
            
            if not result.approved:
                self.log(f"🛑 [ADUANA QSHR REJECT] {symbol} {side.upper()}: {result.rule_triggered} — {result.reason}")
                return False
                
            self.log(f"✅ [ADUANA QSHR APPROVED] {symbol} {side.upper()}: {signal.get('reason')}")
            self._execute_qshr_order(symbol, side, signal, df_5m)
            return True
        except Exception as e:
            self.log(f"Error enrutando QSHR a Aduana: {e}", "ERROR")
            return False

    def _execute_qshr_order(self, symbol, side, signal, df_5m):
        """Ejecuta orden MARKET para QSHR v5 con lotaje fijo según Settings."""
        try:
            from app.core.memory_store import BOT_STATE
            regime_params = BOT_STATE.config_cache.get('regime_params') or {}
            custom_lots = regime_params.get('custom_lots_forex') or {}
            sym_upper = symbol.upper()
            
            if signal.get('lots') and float(signal['lots']) > 0:
                lots = round(float(signal['lots']), 2)
            elif signal.get('custom_lots') and float(signal['custom_lots']) > 0:
                lots = round(float(signal['custom_lots']), 2)
            elif sym_upper in custom_lots and float(custom_lots[sym_upper]) > 0:
                lots = round(float(custom_lots[sym_upper]), 2)
            elif 'XAU' in sym_upper or 'GOLD' in sym_upper:
                lots = 0.10
            else:
                lots = 0.05
                
            price_data = STATE['prices'].get(symbol, {})
            current_price = price_data.get('mid', 0)
            if current_price <= 0:
                last_c = df_5m['close'].iloc[-1] if df_5m is not None and not df_5m.empty else 0
                current_price = float(last_c)
                
            if current_price <= 0:
                self.log(f"No se pudo determinar precio para orden QSHR en {symbol}", "WARNING")
                return

            rule_code = signal.get('rule_code', 'Bb33_QSHR_DIRECT')
            sl_price = float(signal.get('sl_price') or 0)
            mode_val = os.getenv('FOREX_MODE', 'paper')
            
            if mode_val == 'live' and hasattr(self, 'execution') and self.execution:
                self.execution._execute_live_order(
                    symbol=symbol,
                    direction=side,
                    lots=lots,
                    entry=current_price,
                    sl=sl_price,
                    tp=0.0,
                    rule_code=rule_code,
                    order_type='market'
                )
            elif hasattr(self, 'execution') and self.execution:
                self.execution._execute_paper_order(
                    symbol=symbol,
                    direction=side,
                    lots=lots,
                    entry=current_price,
                    sl=sl_price,
                    tp=0.0,
                    rule_code=rule_code
                )
            else:
                new_pos = {
                    'symbol': symbol,
                    'side': side.lower(),
                    'lots': lots,
                    'entry_price': current_price,
                    'sl_price': sl_price,
                    'tp_price': 0,
                    'status': 'open',
                    'rule_code': rule_code,
                    'mode': mode_val,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                self.safe_db_execute(sb.table('forex_positions').insert(new_pos))

            self.log(f"⚡ [QSHR MARKET ORDER EXECUTED] {symbol} {side.upper()} | Lots: {lots} | Price: {current_price} | Rule: {rule_code}")
            
            try:
                from app.workers.alerts_service import send_telegram_message
                reactor.callInThread(lambda: asyncio.run(send_telegram_message(
                    f"⚡ QUANTUM SQUEEZE BREAKOUT [{symbol}]\n"
                    f"Dirección: {side.upper()}\n"
                    f"Velocidad 5m: {signal.get('velocity', 'N/A')}\n"
                    f"BB Expansion: {signal.get('bandwidth_ratio', 'N/A')}x\n"
                    f"Precio: {current_price:.5f}\n"
                    f"Lots: {lots} (Lotes Fijos)\n"
                    f"Aprobado por ADUANAS ✅"
                )))
            except Exception as tg_e:
                self.log(f"Error enviando alerta Telegram QSHR: {tg_e}", "WARNING")

            try:
                from app.halcon_centinela.logger import log_halcon_score
                log_halcon_score(
                    position_id='QSHR_SCANNER',
                    symbol=symbol,
                    scores_by_layer={'5m_squeeze': float(signal.get('velocity', 2.5))},
                    score_final=float(signal.get('velocity', 2.5)) * 10,
                    semaforo='VERDE' if side == 'long' else 'ROJO',
                    decision='QSHR_BREAKOUT',
                    executed=True,
                    detail=f"Squeeze Breakout {side.upper()} ejecutado a MARKET"
                )
            except Exception as hl_e:
                self.log(f"Error registrando score HALCÓN QSHR: {hl_e}", "DEBUG")

        except Exception as e:
            self.log(f"Error ejecutando orden QSHR {symbol}: {e}", "ERROR")

    def _manage_position_5m(self, symbol: str):
        """
        Gestión de posiciones en ciclo rápido (5m).
        Implementa scanner multi-par QSHR v5 y trailing dinámico reactivo para SHORT/SELL.
        """
        try:
            # 1. Obtener posiciones abiertas del símbolo
            res = self.safe_db_execute(sb.table('forex_positions').select('*').eq('symbol', symbol).eq('status', 'open'))
            positions = res.data or []

            # 2. Obtener dataframes (15m, 5m y 4h)
            df_15m = self._get_candles_df(symbol, '15m')
            df_5m  = self._get_candles_df(symbol, '5m')
            df_4h  = self._get_candles_df(symbol, '4h')

            # ─── TTL 90M: Cancelación automática de órdenes limit huérfanas ───
            try:
                pending_res = self.safe_db_execute(sb.table('forex_positions').select('*').eq('symbol', symbol).in_('status', ['pending_limit', 'pending']))
                for p_order in (pending_res.data or []):
                    opened_str = p_order.get('opened_at') or p_order.get('created_at')
                    if opened_str:
                        opened_dt = datetime.fromisoformat(opened_str.replace('Z', '+00:00'))
                        elapsed_min = (datetime.now(timezone.utc) - opened_dt).total_seconds() / 60.0
                        if elapsed_min >= 90.0:
                            # 🛡️ Cancelar orden real en cTrader si tiene ctrader_order_id
                            ord_id_to_cancel = p_order.get('ctrader_order_id')
                            if ord_id_to_cancel:
                                self.cancel_order(ord_id_to_cancel)
                            self.safe_db_execute(sb.table('forex_positions').update({'status': 'cancelled_ttl'}).eq('id', p_order['id']))
                            self.log(f"🧹 [TTL 90M EXPIRED] {symbol}: Orden límite {p_order['id'][:8]} cancelada en broker y DB por exceder 90 min ({elapsed_min:.0f}m)")
            except Exception as ttl_e:
                self.log(f"Error en TTL 90M cleanup {symbol}: {ttl_e}", "DEBUG")

            # ─── NUEVO: QSHR v5 Scanner Multi-Par Autónomo (antes de if not positions) ───
            try:
                from app.strategy.quantum_squeeze_hedge import scan_squeeze_opportunities
                squeeze_signal = scan_squeeze_opportunities(symbol, df_5m, df_15m, market_type='forex_futures')
                if squeeze_signal and not positions:
                    self._route_qshr_to_aduana(symbol, squeeze_signal, df_5m, df_15m, positions)
            except Exception as sq_err:
                self.log(f"Error en QSHR Scanner {symbol}: {sq_err}", "WARNING")

            if not positions: return
            
            # 3. Obtener snapshot para indicadores
            snap_res = self.safe_db_execute(sb.table('market_snapshot').select('*').eq('symbol', symbol).limit(1))
            snap = snap_res.data[0] if snap_res.data else {}

            price_data = STATE['prices'].get(symbol, {})
            current_price = price_data.get('mid', 0)
            if current_price <= 0 and snap:
                current_price = snap.get('price', 0)

            if current_price <= 0: return

            # 0. Viernes Fin de Semana Auto-Close (Viernes 20:50 UTC / 15:50 GMT-5):
            now = datetime.now(timezone.utc)
            is_weekend_close_window = (now.weekday() == 4 and now.hour == 20 and now.minute >= 50) or (now.weekday() == 5)
            if is_weekend_close_window:
                for pos in list(positions):
                    try:
                        entry = float(pos.get('entry_price') or 0)
                        if entry <= 0: continue
                        side = pos.get('side', 'long').lower()
                        pct = ((current_price - entry) / entry * 100) if side == 'long' else ((entry - current_price) / entry * 100)
                        if pct < -1.0:
                            self.log(f"⏸️ [WEEKEND CLOSE SKIP] {symbol} {side.upper()} se mantiene activa. Pérdida {pct:.2f}% supera el 1%.")
                            continue
                        self.log(f"🚨 [WEEKEND CLOSE] Liquidando {symbol} por cierre de sesión de Fin de Semana (PnL: {pct:.2f}%).")
                        c_id = pos.get('ctrader_pos_id')
                        if c_id:
                            self.close_position(c_id, symbol=symbol)
                        from app.core.position_monitor import _execute_paper_close
                        reactor.callInThread(lambda: asyncio.run(_execute_paper_close(pos, current_price, 'weekend_close', sb)))
                    except Exception as e:
                        self.log(f"Error cerrando en fin de semana: {e}", "ERROR")
                return

            # ─── Evaluacion QUANTUM SQUEEZE CLUSTER EXIT (15m SIPV Take Profit) ───
            try:
                from app.strategy.quantum_squeeze_hedge import evaluate_cluster_exit
                cluster_res = evaluate_cluster_exit(symbol, positions, df_5m, df_15m, current_price)
                if cluster_res and cluster_res.get('action') == 'cluster_take_profit':
                    cl_side = cluster_res.get('side', '').lower()
                    target_cl_pos = [p for p in positions if p.get('side', '').lower() in (cl_side, 'buy' if cl_side == 'long' else 'sell')]
                    self.log(f"🎯 [QSHR CLUSTER TAKE PROFIT] {symbol} {cl_side.upper()}: {cluster_res['reason']} ({len(target_cl_pos)} posiciones)")
                    for p in target_cl_pos:
                        c_id = p.get('ctrader_pos_id')
                        if c_id:
                            self.close_position(c_id, symbol=symbol)
                        from app.core.position_monitor import _execute_paper_close
                        reactor.callInThread(lambda pos_to_close=p: asyncio.run(_execute_paper_close(pos_to_close, current_price, 'qshr_cluster_tp_15m', sb)))
                    return
            except Exception as cl_err:
                self.log(f"Error evaluando cluster exit {symbol}: {cl_err}", "DEBUG")

            for pos in positions:
                try:
                    side = pos['side'].lower()
                    is_short = side in ('short', 'sell')
                    
                    # ─── EVALUACIÓN PROFIT TARGET: PnL >= $1.00 USD ───
                    entry_px = float(pos.get('entry_price') or 0)
                    lots_qty = abs(float(pos.get('lots') or 0.01))
                    pip_val_usd = 10.0
                    from app.strategy.capital_protection import PIP_SIZES
                    pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                    pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short else (current_price - entry_px) / pip_size_val
                    pnl_usd_calc = pips_pnl_calc * pip_val_usd * lots_qty

                    if pnl_usd_calc >= 1.00:
                        self.log(f"🎯 [TAKE PROFIT $1.00 REACHED] {symbol} {side.upper()} @ {current_price:.5f} | PnL: +${pnl_usd_calc:.2f} (+{pips_pnl_calc:.1f} pips) >= $1.00 USD. Cerrando posición para asegurar ganancias.", "WARNING")
                        c_id = pos.get('ctrader_pos_id')
                        if c_id:
                            self.close_position(c_id, symbol=symbol)
                        upd_fields = {
                            'status': 'closed',
                            'current_price': current_price,
                            'pnl_pips': round(pips_pnl_calc, 1),
                            'pnl_usd': round(pnl_usd_calc, 2),
                            'closed_at': datetime.now(timezone.utc).isoformat(),
                            'close_reason': 'take_profit_target_1usd'
                        }
                        try:
                            self.safe_db_execute(sb.table('forex_positions').update(upd_fields).eq('id', pos['id']))
                            from app.core.capital_manager import register_realized_pnl
                            register_realized_pnl('forex', round(pnl_usd_calc, 2))
                        except Exception as upd_err:
                            self.log(f"Error actualizando DB en TP $1.00 Close: {upd_err}", "ERROR")
                        continue
                    
                    # ─── Evaluacion EREP v2.0 (Rescate por Escalamiento Asimétrico) ───
                    try:
                        from app.strategy.erep_recovery_engine import evaluate_erep_entry_trigger, evaluate_erep_exit_trigger
                        
                        # 1. Chequear salida Breakeven si P2 ya se encuentra activo
                        erep_exit = evaluate_erep_exit_trigger(pos, current_price, symbol)
                        if erep_exit and erep_exit.get('action') == 'close_erep_cluster':
                            erep_side = erep_exit.get('side', side).lower()
                            target_erep_pos = [p for p in positions if p.get('side', '').lower() in (erep_side, 'buy' if erep_side == 'long' else 'sell')]
                            self.log(f"🎯 [EREP v2.0 CLUSTER EXIT] {symbol} {erep_side.upper()}: {erep_exit['reason']} ({len(target_erep_pos)} posiciones)")
                            for p in target_erep_pos:
                                c_id = p.get('ctrader_pos_id')
                                if c_id:
                                    self.close_position(c_id, symbol=symbol)
                                from app.core.position_monitor import _execute_paper_close
                                reactor.callInThread(lambda p_close=p: asyncio.run(_execute_paper_close(p_close, current_price, 'erep_breakeven_p3', sb)))
                            return

                        # 2. Chequear entrada P2 de Rescate si la posición está en drawdown
                        erep_entry = evaluate_erep_entry_trigger(pos, df_5m, df_15m, current_price, snap)
                        if erep_entry and erep_entry.get('action') == 'execute_erep_p2':
                            p2_side = erep_entry['side']
                            self.log(f"🚑 [EREP v2.0 P2 RESCATE TRIGGER] {symbol} {p2_side.upper()}: {erep_entry['reason']}")
                            approved = self._route_qshr_to_aduana(
                                symbol,
                                {
                                    'side': p2_side,
                                    'rule_code': 'Bb33_EREP_RECOVERY_P2',
                                    'reason': erep_entry['reason'],
                                    'velocity': 1.0,
                                    'custom_lots': erep_entry['p2_size']
                                },
                                df_5m, df_15m, positions
                            )
                            if approved:
                                self.safe_db_execute(sb.table('forex_positions').update({
                                    'erep_active': True,
                                    'erep_p2_price': current_price,
                                    'erep_p2_size': erep_entry['p2_size'],
                                    'erep_p3_avg': erep_entry['p3_avg'],
                                    'erep_q2': erep_entry['p2_size'],
                                    'erep_activated_at': datetime.now(timezone.utc).isoformat()
                                }).eq('id', pos['id']))
                                pos['erep_active'] = True
                                pos['erep_p2_price'] = current_price
                                pos['erep_p3_avg'] = erep_entry['p3_avg']
                    except Exception as erep_err:
                        self.log(f"Error evaluando EREP v2.0 {symbol}: {erep_err}", "DEBUG")
                    
                    # ─── PASO PRIORITARIO: STOP LOSS VIRTUAL FIBONACCI (eTrade 100% Control) ───
                    try:
                        from app.strategy.quantum_squeeze_hedge import evaluate_fib_band_virtual_sl
                        fib_sl_res = evaluate_fib_band_virtual_sl(pos, df_15m, current_price, symbol)
                        if fib_sl_res and fib_sl_res.get('action') == 'close_virtual_fib_sl':
                            self.log(f"🛡️ [VIRTUAL FIB SL TRIGGERED] {symbol} {side.upper()}: {fib_sl_res.get('reason')}", "WARNING")
                            c_id = pos.get('ctrader_pos_id')
                            if c_id:
                                self.close_position(c_id, symbol=symbol, reason='qshr_fib_band_virtual_sl', is_qshr=True)
                            upd_fields = {
                                'status': 'closed',
                                'current_price': current_price,
                                'closed_at': datetime.now(timezone.utc).isoformat(),
                                'close_reason': 'qshr_fib_band_virtual_sl'
                            }
                            try:
                                self.safe_db_execute(sb.table('forex_positions').update(upd_fields).eq('id', pos['id']))
                            except Exception as upd_err:
                                self.log(f"Error actualizando DB en Virtual Fib SL: {upd_err}", "ERROR")
                            continue
                    except Exception as fib_sl_err:
                        self.log(f"Error evaluando SL Virtual Fibonacci {symbol}: {fib_sl_err}", "DEBUG")
                    
                    # ─── Evaluacion QUANTUM SQUEEZE HEDGE & REVERSAL & BOOSTER (Bb33_QSHR v5) ───
                    try:
                        from app.strategy.quantum_squeeze_hedge import evaluate_qshr_hedge_signal
                        qshr_res = evaluate_qshr_hedge_signal(
                            symbol=symbol,
                            df_5m=df_5m,
                            df_15m=df_15m,
                            active_position=pos,
                            market_type='forex_futures'
                        )
                        
                        if qshr_res:
                            q_action = qshr_res['action']
                            q_reason = qshr_res['reason']
                            
                            if q_action in ('open_booster_long', 'open_booster_short'):
                                # Límite estricto de máximo 2 posiciones totales por símbolo (1 primaria + 1 booster)
                                if len(positions) >= 2:
                                    self.log(f"⛔ [BOOSTER MAX POS LIMIT] {symbol}: Ya existen {len(positions)} posiciones abiertas (Máx: 2). Booster omitido.", "INFO")
                                    continue
                                booster_side = 'long' if 'long' in q_action else 'short'
                                self.log(f"🚀 [QSHR TREND BOOSTER {booster_side.upper()}] {symbol}: {q_reason}")
                                self._route_qshr_to_aduana(
                                    symbol,
                                    {
                                        'side': booster_side,
                                        'rule_code': qshr_res.get('rule_code', 'Bb33_QSHR_BOOSTER'),
                                        'reason': q_reason,
                                        'velocity': qshr_res.get('velocity', 2.5),
                                        'sl_price': qshr_res.get('sl_price', 0),
                                        'unrealized_pnl_pips': qshr_res.get('unrealized_pnl_pips', 5.0)
                                    },
                                    df_5m, df_15m, positions
                                )
                                # Sincronizar Cluster Stop Loss para todas las posiciones del par
                                cluster_sl = qshr_res.get('sl_price')
                                if cluster_sl:
                                    for p in [x for x in positions if x.get('side', '').lower() in (booster_side, 'buy' if booster_side == 'long' else 'sell')]:
                                        try:
                                            self.safe_db_execute(sb.table('forex_positions').update({'sl_price': cluster_sl}).eq('id', p['id']))
                                            self.log(f"🛡️ [CLUSTER SL SYNC] {symbol} Pos {p['id'][:8]}: SL ajustado a {cluster_sl}")
                                        except Exception as sl_e:
                                            self.log(f"Error actualizando Cluster SL {p['id']}: {sl_e}", "DEBUG")
                            elif q_action == 'open_hedge_short':
                                self.log(f"🛡️ [QSHR HEDGE SHORT] {symbol}: {q_reason}")
                                self._route_qshr_to_aduana(symbol, {'side': 'short', 'rule_code': 'Bb33_QSHR_HEDGE', 'reason': q_reason, 'velocity': 2.5}, df_5m, df_15m, positions)
                            elif q_action == 'open_hedge_long':
                                self.log(f"🛡️ [QSHR HEDGE LONG] {symbol}: {q_reason}")
                                self._route_qshr_to_aduana(symbol, {'side': 'long', 'rule_code': 'Bb33_QSHR_HEDGE', 'reason': q_reason, 'velocity': 2.5}, df_5m, df_15m, positions)
                            elif q_action in ('close_and_flip_long', 'close_and_flip_short'):
                                # 1. Cerrar inmediatamente la posición anterior en pérdida
                                entry_px = float(pos.get('entry_price') or 0)
                                lots_qty = abs(float(pos.get('lots') or 0))
                                from app.strategy.capital_protection import PIP_SIZES
                                pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                                is_short_pos = side.lower() in ('short', 'sell')
                                pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short_pos else (current_price - entry_px) / pip_size_val
                                pnl_usd_calc = pips_pnl_calc * 10.0 * lots_qty
                                pnl_label = f"+${pnl_usd_calc:.2f}, +{pips_pnl_calc:.1f} pips" if pips_pnl_calc >= 0 else f"-${abs(pnl_usd_calc):.2f}, {pips_pnl_calc:.1f} pips"

                                self.log(f"🔄 [QSHR CUT & FLIP TRIGGER] {symbol}: Cerrando {side.upper()} ({pnl_label}) y girando a {qshr_res['flip_side'].upper()} ({qshr_res.get('flip_lots', 0.02)}L)")
                                c_id = pos.get('ctrader_pos_id')
                                if c_id:
                                    self.close_position(c_id, symbol=symbol)
                                from app.core.position_monitor import _execute_paper_close
                                reactor.callInThread(lambda: asyncio.run(_execute_paper_close(pos, current_price, 'qshr_cut_and_flip', sb)))

                                # 2. Abrir inmediatamente la posición contraria con volumen asimétrico
                                flip_signal = {
                                    'side': qshr_res['flip_side'],
                                    'rule_code': qshr_res.get('flip_rule', 'Bb33_QSHR_FLIP'),
                                    'lots': qshr_res.get('flip_lots', 0.02),
                                    'custom_lots': qshr_res.get('flip_lots', 0.02),
                                    'sl_price': qshr_res.get('sl_price', 0),
                                    'velocity': qshr_res.get('velocity', 2.5),
                                    'reason': qshr_res['reason']
                                }
                                self._route_qshr_to_aduana(symbol, flip_signal, df_5m, df_15m, positions)

                            elif q_action in ('close_original_long', 'close_original_short', 'close_market_active_sipv', 'close_bollinger_exhaustion', 'close_cascada_fib_stagnation', 'partial_close_market_active_sipv', 'close_virtual_fib_sl'):
                                entry_px = float(pos.get('entry_price') or 0)
                                lots_qty = abs(float(pos.get('lots') or 0))
                                from app.strategy.capital_protection import PIP_SIZES
                                pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                                is_short_pos = side.lower() in ('short', 'sell')
                                pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short_pos else (current_price - entry_px) / pip_size_val
                                pnl_usd_calc = pips_pnl_calc * 10.0 * lots_qty

                                # Salidas de EMERGENCIA / INVALIDACIÓN QSHR (close_original_long / close_original_short) cierran SIEMPRE, incluso en pérdida
                                is_emergency_cut = q_action in ('close_original_long', 'close_original_short')
                                min_pnl_ok = is_emergency_cut or (pips_pnl_calc >= 1.5) or (pnl_usd_calc >= 0.15 * max(0.01, lots_qty) / 0.01)

                                if not min_pnl_ok:
                                    self.log(f"🛡️ [ADUANA SALIDA / QSHR SKIP] {symbol} {side.upper()}: Salida QSHR ({q_action}) ignorada por PnL insuficiente (${pnl_usd_calc:.2f}, {pips_pnl_calc:.1f} pips). Se mantiene posición activa.", "INFO")
                                else:
                                    pnl_label = f"+${pnl_usd_calc:.2f}, +{pips_pnl_calc:.1f} pips" if pips_pnl_calc >= 0 else f"-${abs(pnl_usd_calc):.2f}, {pips_pnl_calc:.1f} pips"
                                    self.log(f"🛡️ [QSHR EXIT / {'EMERGENCY CUT' if is_emergency_cut else 'RIDE & CLOSE'}] {symbol}: {q_reason} (PnL: {pnl_label})")
                                    c_id = pos.get('ctrader_pos_id')
                                    if c_id:
                                        self.close_position(c_id, symbol=symbol)
                                    from app.core.position_monitor import _execute_paper_close
                                    exit_reason = (
                                        'qshr_early_invalidation' if 'Early Invalidation' in q_reason
                                        else ('bollinger_exhaustion' if 'bollinger' in q_action 
                                        else ('cascada_fib_stagnation' if 'cascada' in q_action 
                                        else ('qshr_sipv_climax' if 'sipv' in q_action else 'qshr_4factor_exit')))
                                    )
                                    reactor.callInThread(lambda: asyncio.run(_execute_paper_close(pos, current_price, exit_reason, sb)))
                            elif q_action == 'adjust_trailing_sl':
                                new_sl = qshr_res.get('sl_price')
                                if new_sl:
                                    try:
                                        self.safe_db_execute(sb.table('forex_positions').update({'sl_price': new_sl}).eq('id', pos['id']))
                                        self.log(f"🛡️ [CASCADA FIB SL SYNC] {symbol} Pos {pos['id'][:8]}: SL ajustado a {new_sl}")
                                    except Exception as sl_e:
                                        self.log(f"Error actualizando Fib SL {pos['id']}: {sl_e}", "DEBUG")
                            elif q_action in ('reversal_at_level5', 'reversal_at_level6'):
                                self.log(f"🎯 [QSHR 15M REVERSAL] {symbol}: {q_reason}")
                                c_id = pos.get('ctrader_pos_id')
                                if c_id:
                                    self.close_position(c_id, symbol=symbol)
                                from app.core.position_monitor import _execute_paper_close
                                reactor.callInThread(lambda: asyncio.run(_execute_paper_close(pos, current_price, 'qshr_reversal_15m', sb)))
                                rev_side = qshr_res.get('reversal_side', 'long')
                                self._route_qshr_to_aduana(symbol, {'side': rev_side, 'rule_code': qshr_res.get('rule_code', 'Bb33_QSHR_REVERSAL'), 'reason': q_reason, 'velocity': 2.5}, df_5m, df_15m, positions)
                    except Exception as q_err:
                        self.log(f"Error evaluando QSHR para {symbol}: {q_err}", "WARNING")
                    
                    # El trailing dinámico reactivo es mandatorio para SHORT en 5m
                    # Para LONG mantenemos 15m (según requerimiento)
                    
                    # Crear objeto de estado temporal para evaluación, recuperando marcas históricas de memoria
                    h_p = STATE['highest_prices_cache'].get(pos['id']) or float(pos.get('highest_price') or pos.get('entry_price') or 0)
                    l_p = STATE['lowest_prices_cache'].get(pos['id']) or float(pos.get('lowest_price') or pos.get('entry_price') or 0)
                    highest_band = pos.get('highest_band_reached') or ''
                    bb_touched_val = 'bb_touched' in str(highest_band)
                    rule_val = pos.get('rule_code') or ''
                    
                    state = ProtectionState(
                        position_id = str(pos['id']),
                        symbol      = symbol,
                        side        = side,
                        entry_price = float(pos.get('entry_price') or 0),
                        current_sl  = float(pos.get('sl_price') or 0),
                        original_sl = float(pos.get('original_sl') or pos.get('sl_price') or 0),
                        market_type = 'forex_futures',
                        highest_price = h_p,
                        lowest_price  = l_p,
                        rule_code   = rule_val,
                        bb_touched   = bb_touched_val,
                        opened_at   = str(pos.get('opened_at') or '')
                    )

                    # Precio base para el trailing (mejor precio alcanzado)
                    if is_short:
                        best_p = state.lowest_price if state.lowest_price > 0 else state.entry_price
                    else:
                        best_p = state.highest_price if state.highest_price > 0 else state.entry_price

                    # Evaluar Trailing Stop (ApexConfluence)
                    res_trail = evaluate_trailing_stop(state, current_price, df_15m=df_15m, df_5m=df_5m, snap=snap)
                    
                    if res_trail['action'] == 'none' and not res_trail.get('update_bb_touched'):
                        # Fallback to Volatile Trailing v2
                        res_trail = evaluate_volatile_trailing_v2(
                            symbol        = symbol,
                            side          = side,
                            entry_price   = state.entry_price,
                            current_price = current_price,
                            best_price    = best_p,
                            current_sl    = state.current_sl,
                            df_15m        = df_15m,
                            df_5m         = df_5m,
                            atr_snap      = float(snap.get('atr') or 0)
                        )
                        
                    # Handle bb_touched update
                    if res_trail.get('update_bb_touched') or res_trail['action'] == 'update_bb_touched':
                        try:
                            curr_band = pos.get('highest_band_reached') or ''
                            new_band = f"{curr_band};bb_touched" if curr_band else "bb_touched"
                            self.safe_db_execute(sb.table('forex_positions').update({
                                'highest_band_reached': new_band
                            }).eq('id', pos['id']))
                            pos['highest_band_reached'] = new_band
                            state.bb_touched = True
                            self.log(f"[PROTECTION] {symbol}: bb_touched detectado. Actualizado DB.")
                        except Exception as e:
                            self.log(f"Error actualizando bb_touched para {symbol}: {e}", "WARNING")

                    if res_trail.get('action') == 'update_sl':
                        new_sl = res_trail.get('sl_price') or res_trail.get('new_sl') or pos.get('sl_price')
                        new_tp = res_trail.get('new_tp')
                        self.log(f"[TRAILING-5M] {symbol} {side.upper()} -> Nuevo SL: {new_sl:.5f} ({res_trail['reason']})")
                        if new_tp:
                            self.log(f"[TRAILING-5M] {symbol} {side.upper()} -> Nuevo TP: {new_tp:.5f}")
                        
                        # Actualizar en Supabase (Gestión Virtual eTrade)
                        upd_data = {'sl_price': new_sl}
                        if new_tp:
                            upd_data['tp_price'] = new_tp
                            pos['tp_price'] = new_tp
                        if is_short:
                            STATE['lowest_prices_cache'][pos['id']] = min(state.lowest_price if state.lowest_price > 0 else current_price, current_price)
                        else:
                            STATE['highest_prices_cache'][pos['id']] = max(state.highest_price, current_price)
                            
                        self.safe_db_execute(sb.table('forex_positions').update(upd_data).eq('id', pos['id']))
                        
                        # Gestión 100% Virtual por eTrade: NO enviamos SL/TP físico al broker cTrader
                        # para evitar cazas de stop por ensanchamiento de spread / aperturas de fin de semana.
                        # c_id = pos.get('ctrader_pos_id')
                        # if c_id:
                        #     self.amend_position(c_id, sl_price=new_sl, tp_price=new_tp, symbol=symbol)
                        
                    elif res_trail['action'] == 'close_market':
                        # Spec Section 3.6: CASCADA SLV/SLVM Delegation
                        is_rebote_cascade = (str(pos.get('origen', '')).upper() == 'REBOTE' or str(pos.get('rule_code', '')).startswith(('AaReb', 'BbReb', 'REBOTE')))
                        trail_reason = str(res_trail.get('reason', ''))
                        
                        if is_rebote_cascade and ('ema' in trail_reason.lower() or 'pnl_floor' in trail_reason.lower() or 'pnl <= $1' in trail_reason.lower()):
                            self.log(f"🌊 [CASCADA DELEGATION] {symbol} {side.upper()} — Trailing trigger '{trail_reason}' delegado a evaluación de CASCADA")
                            continue

                        # 🛡️ ADUANA SALIDA: Solo permitir cierre de Trailing si está en ganancia
                        entry_px = float(pos.get('entry_price') or 0)
                        lots_qty = abs(float(pos.get('lots') or 0))
                        from app.strategy.capital_protection import PIP_SIZES
                        pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                        is_short_pos = side.lower() in ('short', 'sell')
                        pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short_pos else (current_price - entry_px) / pip_size_val
                        pnl_usd_calc = pips_pnl_calc * 10.0 * lots_qty

                        if pnl_usd_calc < 0.0:
                            self.log(f"🛡️ [TRAILING-5M SKIP LOSS] {symbol} {side.upper()}: Trailing Stop omitido porque PnL es negativo (${pnl_usd_calc:.2f}, {pips_pnl_calc:.1f} p). Cierre en pérdida SOLO permitido por QSHR.", "INFO")
                            continue

                        self.log(f"[TRAILING-5M CLOSE] {symbol} {side.upper()} @ {current_price} | Razón: {res_trail['reason']}", "WARNING")
                        # 1. Cerrar en cTrader
                        c_id = pos.get('ctrader_pos_id')
                        if c_id:
                            self.close_position(c_id, symbol=symbol, reason=res_trail['reason'])
                        # 2. Cerrar en DB con datos reales financieros
                        try:
                            entry_px = float(pos.get('entry_price') or 0)
                            lots_qty = abs(float(pos.get('lots') or 0))
                            pip_val_usd = 10.0  # Lote estándar pips value
                            from app.strategy.capital_protection import PIP_SIZES
                            pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                            is_short_pos = side.lower() in ('short', 'sell')
                            pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short_pos else (current_price - entry_px) / pip_size_val
                            pnl_usd_calc = pips_pnl_calc * pip_val_usd * lots_qty
                            
                            upd_fields = {
                                'status': 'closed', 
                                'current_price': current_price,
                                'pnl_pips': round(pips_pnl_calc, 1),
                                'pnl_usd': round(pnl_usd_calc, 2),
                                'closed_at': datetime.now(timezone.utc).isoformat(), 
                                'close_reason': res_trail['reason']
                            }
                            
                            # Registrar en capital manager
                            try:
                                from app.core.capital_manager import register_realized_pnl
                                register_realized_pnl('forex', round(pnl_usd_calc, 2))
                            except Exception:
                                pass
                        except Exception as calc_err:
                            self.log(f"Error calculando PnL de cierre: {calc_err}", "ERROR")
                            upd_fields = {
                                'status': 'closed', 
                                'current_price': current_price,
                                'closed_at': datetime.now(timezone.utc).isoformat(), 
                                'close_reason': res_trail['reason']
                            }
                            
                        self.safe_db_execute(sb.table('forex_positions').update(upd_fields).eq('id', pos['id']))
                        
                        # 3. Si no tocó BB, re-entrar con órdenes límite!
                        if not res_trail.get('bb_touched', False):
                            qty = abs(float(pos.get('lots') or 0))
                            self.trigger_forex_reentry_standalone(symbol, side, qty, df_15m)
                        continue
                    
                    # ── NUEVO: CIERRE PROACTIVO MARKET POR GIRO DE TENDENCIA (15m EMA3 vs EMA9) ──
                    # [ADUANA SALIDA]: Solo cierra si el beneficio neto garantizado es PnL >= $1.00 USD
                    if df_15m is not None and len(df_15m) >= 2:
                        last_15m = df_15m.iloc[-1]
                        c_series_15m = df_15m['close']
                        ema3_15m = float(last_15m.get('ema1') or last_15m.get('ema_3') or c_series_15m.ewm(span=3, adjust=False).mean().iloc[-1])
                        ema9_15m = float(last_15m.get('ema2') or last_15m.get('ema_9') or c_series_15m.ewm(span=9, adjust=False).mean().iloc[-1])
                        
                        is_long_pos = side.lower() in ('long', 'buy')
                        should_trend_close = (is_long_pos and ema3_15m < ema9_15m) or ((not is_long_pos) and ema3_15m > ema9_15m)
                        
                        if should_trend_close:
                            entry_px = float(pos.get('entry_price') or 0)
                            lots_qty = abs(float(pos.get('lots') or 0))
                            pip_val_usd = 10.0
                            from app.strategy.capital_protection import PIP_SIZES
                            pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                            is_short_pos = side.lower() in ('short', 'sell')
                            pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short_pos else (current_price - entry_px) / pip_size_val
                            pnl_usd_calc = pips_pnl_calc * pip_val_usd * lots_qty
                            
                            reason_str = 'trend_reversal_ema3_below_ema9' if is_long_pos else 'trend_reversal_ema3_above_ema9'
                            
                            if pnl_usd_calc < 1.00:
                                self.log(f"🛡️ [ADUANA SALIDA / TREND REVERSAL SKIP] {symbol} {side.upper()}: Giro 15m detectado ({reason_str}) pero PnL insuficiente (${pnl_usd_calc:.2f} < $1.00 USD, {pips_pnl_calc:.1f} pips). Se mantiene posición activa.", "INFO")
                            else:
                                self.log(f"🚨 [PROACTIVE MARKET CLOSE] {symbol} {side.upper()} @ {current_price:.5f} | Razón: 15m Giro de Tendencia ({reason_str}) con PnL +${pnl_usd_calc:.2f} | ema3={ema3_15m:.5f}, ema9={ema9_15m:.5f}", "WARNING")
                                c_id = pos.get('ctrader_pos_id')
                                if c_id:
                                    self.close_position(c_id, symbol=symbol)
                                
                                upd_fields = {
                                    'status': 'closed', 
                                    'current_price': current_price,
                                    'pnl_pips': round(pips_pnl_calc, 1),
                                    'pnl_usd': round(pnl_usd_calc, 2),
                                    'closed_at': datetime.now(timezone.utc).isoformat(), 
                                    'close_reason': reason_str
                                }
                                try:
                                    sb.table('forex_positions').update(upd_fields).eq('id', pos['id']).execute()
                                    from app.core.capital_manager import register_realized_pnl
                                    register_realized_pnl('forex', round(pnl_usd_calc, 2))
                                except Exception as upd_err:
                                    self.log(f"Error actualizando DB en Proactive Close: {upd_err}", "ERROR")
                                continue

                    # --- NUEVO: CIERRE PROACTIVO (AaEXT/AaEXH) ---
                    proactive_res = evaluate_proactive_exit(
                        position      = pos,
                        current_price = current_price,
                        snap          = snap,
                        df_4h         = df_4h,
                        market_type   = 'forex_futures'
                    )
                    
                    if proactive_res['should_close']:
                        entry_px = float(pos.get('entry_price') or 0)
                        lots_qty = abs(float(pos.get('lots') or 0))
                        from app.strategy.capital_protection import PIP_SIZES
                        pip_size_val = PIP_SIZES.get(symbol, 0.0001)
                        is_short_pos = side.lower() in ('short', 'sell')
                        pips_pnl_calc = (entry_px - current_price) / pip_size_val if is_short_pos else (current_price - entry_px) / pip_size_val
                        pnl_usd_calc = pips_pnl_calc * 10.0 * lots_qty

                        if pnl_usd_calc < 0.0:
                            self.log(f"🛡️ [PROACTIVE-EXIT SKIP LOSS] {symbol} {side.upper()}: Proactive Exit omitido porque PnL es negativo (${pnl_usd_calc:.2f}, {pips_pnl_calc:.1f} p). Cierre en pérdida SOLO permitido por QSHR.", "INFO")
                            continue

                        # ── VALIDACIÓN MTF TREND GUARD (Anti-Micro-Scalp 15m -> 5m) ──
                        try:
                            from app.strategy.profit_capture import evaluate_mtf_trend_guard
                            pnl_pct_calc = (pips_pnl_calc * pip_size_val / entry_px * 100.0) if entry_px > 0 else 0.0
                            mtf_guard = evaluate_mtf_trend_guard(
                                side=side, df_15m=df_15m, df_5m=df_5m,
                                current_price=current_price, symbol=symbol,
                                market_type='forex_futures',
                                pnl_pips=pips_pnl_calc, pnl_pct=pnl_pct_calc
                            )
                            if mtf_guard.get('should_block'):
                                self.log(f"🛡️ [MTF TREND GUARD] {symbol} {side.upper()}: Proactive Exit omitido. {mtf_guard.get('reason')}", "INFO")
                                continue
                        except Exception as mtf_e:
                            self.log(f"Error evaluando MTF Trend Guard {symbol}: {mtf_e}", "DEBUG")

                        self.log(f"[PROACTIVE-EXIT] {symbol} {side.upper()} @ {current_price} | Regla: {proactive_res['rule_code']} | Razón: {proactive_res['reason']}", "WARNING")
                        # Cerrar en cTrader
                        c_id = pos.get('ctrader_pos_id')
                        if c_id:
                            self.close_position(c_id, symbol=symbol, reason=proactive_res['reason'])
                            
                        try:
                            upd_fields = {
                                'status': 'closed', 
                                'current_price': current_price,
                                'pnl_pips': round(pips_pnl_calc, 1),
                                'pnl_usd': round(pnl_usd_calc, 2),
                                'closed_at': datetime.now(timezone.utc).isoformat(), 
                                'close_reason': proactive_res.get('reason') or proactive_res.get('rule_code')
                            }
                            
                            try:
                                from app.core.capital_manager import register_realized_pnl
                                register_realized_pnl('forex', round(pnl_usd_calc, 2))
                            except Exception:
                                pass
                        except Exception as calc_err:
                            self.log(f"Error calculando PnL de cierre proactivo: {calc_err}", "ERROR")
                            upd_fields = {
                                'status': 'closed', 
                                'current_price': current_price,
                                'closed_at': datetime.now(timezone.utc).isoformat(), 
                                'close_reason': proactive_res.get('reason') or proactive_res.get('rule_code')
                            }
                            
                        self.safe_db_execute(sb.table('forex_positions').update(upd_fields).eq('id', pos['id']))
                        continue

                    else:
                        # Si no hay update de SL, al menos actualizamos en memoria local el mejor precio si mejoró
                        if is_short:
                            low = min(state.lowest_price if state.lowest_price > 0 else current_price, current_price)
                            if low < (state.lowest_price if state.lowest_price > 0 else 999999):
                                STATE['lowest_prices_cache'][pos['id']] = low
                        else:
                            high = max(state.highest_price, current_price)
                            if high > state.highest_price:
                                STATE['highest_prices_cache'][pos['id']] = high
                except Exception as pos_err:
                    import traceback
                    self.log(f"Error managing position ID {pos.get('id')} ({symbol}): {pos_err}\n{traceback.format_exc()}", "ERROR")
                    continue

        except Exception as e:
            self.log(f"Error en _manage_position_5m para {symbol}: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")

    def save_snapshot(self, symbol):
        try:
            key = f"{symbol}_15m"; data = STATE['candles'].get(key, [])
            if not data or len(data) < 20: 
                self.log(f"Snapshot abortado para {symbol}: Datos insuficientes ({len(data)} velas)", "WARNING")
                return
            df = pd.DataFrame(data)
            # V7: adjust=False para fórmula EMA estándar financiera (compatible con TradingView/cTrader)
            df['ema20'] = df['c'].ewm(span=20, adjust=False).mean()
            df['ema9']  = df['c'].ewm(span=9, adjust=False).mean()
            df['ema3']  = df['c'].ewm(span=3, adjust=False).mean()
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
            
            # EMA Exhaustion detection
            ema_dist = abs(ema3 - ema9) / (ema9 + 1e-10) * 100
            ema_dist_avg = df['ema3'].sub(df['ema9']).abs().div(df['ema9'].add(1e-10)).mul(100).rolling(10).mean().iloc[-1]
            ema_exhaustion = bool(ema_dist < (ema_dist_avg * 0.3))

            multipliers = [1.0, 1.618, 2.618, 3.618, 4.236, 5.618]
            zone = 0
            if atr > 0:
                for i in range(6, 0, -1):
                    if price > ema20 + (atr * multipliers[i-1]): zone = i; break
                    if price < ema20 - (atr * multipliers[i-1]): zone = -i; break

            # Eliminado upsert duplicado síncrono propenso a errores.
            # Los datos se de-duplican y se guardan de forma segura en la sección inferior.

            # --- CALCULO DE MTF SCORE ---
            mtf_score = 0.0
            tfs_checked = 0
            for tf_suffix in ['15m', '1h', '4h', '1d']:
                tf_key = f"{symbol}_{tf_suffix}"
                tf_data = STATE['candles'].get(tf_key, [])
                if len(tf_data) >= 10:
                    try:
                        tf_df = pd.DataFrame(tf_data)
                        tf_ema20 = tf_df['c'].ewm(span=20, adjust=False).mean().iloc[-1]
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
                    df_4h['basis'] = df_4h['c'].ewm(span=20, adjust=False).mean()
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
                    if "column" in err_str and ("ema_" in err_str or "ema_exhaustion" in err_str):
                        # Limpieza de columnas conflictivas que no existen en DB
                        for col in ['ema_3', 'ema_9', 'ema_20', 'ema_exhaustion', 'ema20_phase']:
                            if col in s: del s[col]
                        return sb.table('market_snapshot').upsert(s, on_conflict='symbol').execute()

                    raise e

            # Update RADAR shared signal bus
            try:
                from app.core.memory_store import update_memory_df
                df['close'] = df['c']
                df['high'] = df['h']
                df['low'] = df['l']
                df['open'] = df['o']
                df['ema_3'] = df['ema3']
                df['ema_9'] = df['ema9']
                df['ema_20'] = df['ema20']
                df['fibonacci_zone'] = int(zone)
                update_memory_df(symbol, '15m', df)

                from app.radar.radar_service import RadarService
                RadarService.get_instance().update(symbol, '15m')
            except Exception as radar_err:
                self.log(f"⚠️ [RADAR] Error updating signals for {symbol}: {radar_err}", "WARNING")

            threads.deferToThread(safe_upsert, query, snap).addErrback(
                lambda f: self.log(f"Error async db snapshot: {f.getErrorMessage()}", "ERROR")
            )
        except Exception as e: 
            self.log(f"Error snap {symbol}:\n{traceback.format_exc()}", "ERROR")

if __name__ == '__main__':
    worker = StandaloneForexWorker(); worker.start()
