"""
IC Markets / cTrader Provider — Protobuf TCP

Usa la librería oficial ctrader-open-api
que maneja el protocolo Protobuf internamente.

Equivalente a BinanceCryptoProvider pero
para Forex via cTrader Open API.

Credenciales necesarias (.env):
  CTRADER_CLIENT_ID
  CTRADER_CLIENT_SECRET
  CTRADER_ACCOUNT_ID
  CTRADER_ACCESS_TOKEN
  CTRADER_ENV (demo o live)
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable
import os

from ctrader_open_api import (
    Client,
    Protobuf,
    TcpProtocol,
    Auth,
    EndPoints,
)
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (
    ProtoMessage,
)
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOASpotEvent,
    ProtoOANewOrderReq,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOATraderReq,
    ProtoOATraderRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOAClosePositionReq,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOATrendbarPeriod,
    ProtoOAOrderType,
    ProtoOATradeSide,
)

from .base_provider import BaseMarketProvider
from app.core.logger import log_info, log_error


import threading
from twisted.internet import reactor

class CTraderProtobufProvider(BaseMarketProvider):
    """
    Proveedor IC Markets via cTrader Open API
    usando protocolo Protobuf sobre TCP.

    Arquitectura:
      - Conexión TCP persistente con el servidor
      - Autenticación con Application + Account
      - Subscripción a spots (precios en tiempo real)
      - Descarga de trendbars (velas históricas)
      - Envío de órdenes via Protobuf

    Equivalente a Binance WebSocket para Crypto.
    """

    # Timeframe map: eTrader → cTrader Protobuf
    TF_MAP = {
        '1m':  ProtoOATrendbarPeriod.M1,
        '5m':  ProtoOATrendbarPeriod.M5,
        '15m': ProtoOATrendbarPeriod.M15,
        '30m': ProtoOATrendbarPeriod.M30,
        '1h':  ProtoOATrendbarPeriod.H1,
        '4h':  ProtoOATrendbarPeriod.H4,
        '1d':  ProtoOATrendbarPeriod.D1,
        '1w':  ProtoOATrendbarPeriod.W1,
    }

    # Pip sizes por símbolo
    PIP_SIZES = {
        'EURUSD': 0.0001,
        'GBPUSD': 0.0001,
        'USDJPY': 0.01,
        'USDCHF': 0.0001,
        'AUDUSD': 0.0001,
        'NZDUSD': 0.0001,
        'USDCAD': 0.0001,
        'EURGBP': 0.0001,
        'EURJPY': 0.01,
        'GBPJPY': 0.01,
        'XAUUSD': 0.01,
        'XAGUSD': 0.001,
    }

    # Divisores de precio por símbolo
    # cTrader envía precios multiplicados por 10^5
    PRICE_DIVISOR = {
        'EURUSD': 100000,
        'GBPUSD': 100000,
        'USDJPY': 1000,
        'USDCHF': 100000,
        'AUDUSD': 100000,
        'NZDUSD': 100000,
        'USDCAD': 100000,
        'EURGBP': 100000,
        'EURJPY': 1000,
        'GBPJPY': 1000,
        'XAUUSD': 100,
        'XAGUSD': 1000,
    }

    def __init__(
        self,
        client_id:     str,
        client_secret: str,
        account_id:    int,
        access_token:  str,
        environment:   str = 'demo'
    ):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.account_id    = int(account_id)
        self.access_token  = access_token
        self.env           = environment

        # Endpoint según ambiente
        self.host = (
            EndPoints.PROTOBUF_LIVE_HOST
            if environment == 'live'
            else EndPoints.PROTOBUF_DEMO_HOST
        )
        self.port = EndPoints.PROTOBUF_PORT

        # Estado de la conexión
        self._client:       Optional[Client] = None
        self._connected     = False
        self._authenticated = False

        # Precios en tiempo real (cache)
        self._live_prices:  dict = {}

        # Mapa de símbolos → symbol_id de cTrader
        self._symbol_ids:   dict = {}

        # Callbacks de precio
        self._price_callbacks: list[Callable] = []

    @property
    def market_type(self) -> str:
        return 'forex_futures'

    @property
    def pip_size(self) -> dict:
        return self.PIP_SIZES

    # ──────────────────────────────────────────
    # CONEXIÓN Y AUTENTICACIÓN
    # ──────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Establece conexión TCP con cTrader
        y realiza la autenticación en dos pasos:
          1. Application Auth (Client ID + Secret)
          2. Account Auth (Access Token)
        """
        try:
            loop = asyncio.get_event_loop()

            # Crear cliente TCP
            self._client = Client(
                host     = self.host,
                port     = self.port,
                protocol = TcpProtocol,
            )

            # Configurar callbacks
            self._client.setConnectedCallback(
                self._on_connected
            )
            self._client.setDisconnectedCallback(
                self._on_disconnected
            )
            self._client.setMessageReceivedCallback(
                self._on_message
            )

            # Iniciar reactor en thread si no está corriendo
            if not reactor.running:
                def run_reactor():
                    try:
                        reactor.run(installSignalHandlers=False)
                    except Exception as e:
                        print("Reactor exception:", e)
                threading.Thread(target=run_reactor, daemon=True).start()
                import time
                time.sleep(0.5)

            # Conectar desde el thread del reactor
            reactor.callFromThread(self._client.startService)

            # Esperar conexión (max 10 seg)
            for _ in range(100):
                if self._connected:
                    break
                await asyncio.sleep(0.1)

            if not self._connected:
                log_error('CTRADER',
                    'Timeout esperando conexión TCP'
                )
                return False

            # Paso 1: App Auth
            await self._app_auth()
            await asyncio.sleep(1)

            # Paso 2: Account Auth
            await self._account_auth()
            
            # Esperar autenticación (max 15 seg)
            for _ in range(150):
                if self._authenticated:
                    break
                await asyncio.sleep(0.1)

            if self._authenticated:
                log_info('CTRADER',
                    f'✅ Conectado a IC Markets '
                    f'({self.env}) vía Protobuf TCP'
                )
                # Cargar mapa de símbolos
                await self._load_symbols()
                return True

            return False

        except Exception as e:
            log_error('CTRADER',
                f'Error de conexión: {e}'
            )
            return False

    async def _app_auth(self):
        """Autenticación de la aplicación."""
        request = ProtoOAApplicationAuthReq()
        request.clientId     = self.client_id
        request.clientSecret = self.client_secret

        await self._send_request(request)
        log_info('CTRADER', 'App Auth enviado...')

    async def _account_auth(self):
        """Autenticación de la cuenta de trading."""
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = self.account_id
        request.accessToken = self.access_token

        await self._send_request(request)
        log_info('CTRADER', 'Account Auth enviado...')

    async def _send_request(self, request):
        """Envía un mensaje Protobuf al servidor en el thread del reactor."""
        event = asyncio.Event()

        def send_and_set():
            try:
                self._client.send(request)
            except Exception as e:
                log_error('CTRADER', f'Error sending: {e}')
            loop.call_soon_threadsafe(event.set)

        loop = asyncio.get_event_loop()
        reactor.callFromThread(send_and_set)
        await event.wait()

    # ──────────────────────────────────────────
    # CALLBACKS DE EVENTOS
    # ──────────────────────────────────────────

    def _on_connected(self, client):
        log_info('CTRADER', 'TCP conectado')
        self._connected = True

    def _on_disconnected(self, client, reason):
        log_error('CTRADER',
            f'Desconectado: {reason}'
        )
        self._connected     = False
        self._authenticated = False

    def _on_message(self, client, message):
        """
        Procesa todos los mensajes entrantes
        del servidor cTrader.
        """
        msg_type = message.payloadType
        log_info('CTRADER', f'Mensaje recibido: {msg_type}')

        # App Auth Response
        if msg_type == \
           ProtoOAApplicationAuthRes().payloadType:
            log_info('CTRADER', '✅ App Auth OK')

        # Account Auth Response
        elif msg_type == \
             ProtoOAAccountAuthRes().payloadType:
            log_info('CTRADER', '✅ Account Auth OK')
            self._authenticated = True

        # Error
        elif msg_type == 50: # ProtoOAErrorRes
            error = Protobuf.extract(message)
            log_error('CTRADER', f'❌ Error del servidor: {error}')


        # Spot Price Update (precio en tiempo real)
        elif msg_type == \
             ProtoOASpotEvent().payloadType:
            spot = Protobuf.extract(message)
            self._handle_spot(spot)

        # Trendbars Response (velas históricas)
        elif msg_type == \
             ProtoOAGetTrendbarsRes().payloadType:
            bars = Protobuf.extract(message)
            self._handle_trendbars(bars)

        # Symbols List Response
        elif msg_type == \
             ProtoOASymbolsListRes().payloadType:
            symbols = Protobuf.extract(message)
            self._handle_symbols(symbols)

    def _handle_spot(self, spot):
        """
        Procesa un tick de precio en tiempo real.
        Equivalente al WebSocket de Binance.
        """
        # Encontrar símbolo por ID
        symbol_name = None
        for name, sid in self._symbol_ids.items():
            if sid == spot.symbolId:
                symbol_name = name
                break

        if not symbol_name:
            return

        divisor = self.PRICE_DIVISOR.get(
            symbol_name, 100000
        )

        bid = spot.bid / divisor if spot.bid else 0
        ask = spot.ask / divisor if spot.ask else 0
        mid = (bid + ask) / 2 if bid and ask else 0

        self._live_prices[symbol_name] = {
            'bid':       bid,
            'ask':       ask,
            'mid':       mid,
            'timestamp': datetime.now(timezone.utc),
        }

        # Ejecutar callbacks de precio
        for callback in self._price_callbacks:
            try:
                callback(symbol_name, mid, bid, ask)
            except Exception as e:
                log_error('CTRADER',
                    f'Callback error: {e}'
                )

    def _handle_trendbars(self, response):
        """Almacena las velas descargadas."""
        self._last_trendbars = response

    def _handle_symbols(self, response):
        """Construye el mapa de símbolos."""
        for sym in response.symbol:
            self._symbol_ids[sym.symbolName] = \
                sym.symbolId
        log_info('CTRADER',
            f'Mapa de símbolos: '
            f'{len(self._symbol_ids)} símbolos'
        )

    async def _load_symbols(self):
        """Carga el catálogo de símbolos."""
        request = ProtoOASymbolsListReq()
        request.ctidTraderAccountId = self.account_id
        await self._send_request(request)
        await asyncio.sleep(2)

    # ──────────────────────────────────────────
    # API PÚBLICA (equivalente a Binance)
    # ──────────────────────────────────────────

    async def subscribe_prices(
        self,
        symbols: list[str],
        callback: Callable = None
    ) -> bool:
        """
        Subscribe a precios en tiempo real.
        Equivalente al WebSocket de Binance.

        El callback recibe:
          (symbol, mid_price, bid, ask)
        """
        if callback:
            self._price_callbacks.append(callback)

        symbol_ids = []
        for sym in symbols:
            sid = self._symbol_ids.get(sym)
            if sid:
                symbol_ids.append(sid)
            else:
                log_error('CTRADER',
                    f'Símbolo {sym} no encontrado'
                )

        if not symbol_ids:
            return False

        request = ProtoOASubscribeSpotsReq()
        request.ctidTraderAccountId = \
            self.account_id
        request.symbolId.extend(symbol_ids)

        await self._send_request(request)
        log_info('CTRADER',
            f'Subscrito a precios: {symbols}'
        )
        return True

    async def get_current_price(
        self,
        symbol: str
    ) -> float:
        """
        Obtiene el precio actual del cache.
        Si no está en cache, espera hasta 5 seg.
        """
        for _ in range(50):
            if symbol in self._live_prices:
                return self._live_prices[
                    symbol
                ]['mid']
            await asyncio.sleep(0.1)

        log_error('CTRADER',
            f'Sin precio para {symbol}'
        )
        return 0.0

    async def get_ohlcv(
        self,
        symbol:    str,
        timeframe: str,
        limit:     int = 300
    ) -> pd.DataFrame:
        """
        Descarga velas históricas via Protobuf.
        Equivalente a client.get_klines() de Binance.
        """
        if not self._authenticated:
            log_error('CTRADER', 'No autenticado')
            return pd.DataFrame()

        symbol_id = self._symbol_ids.get(symbol)
        if not symbol_id:
            log_error('CTRADER',
                f'Símbolo {symbol} no en catálogo'
            )
            return pd.DataFrame()

        tf_proto = self.TF_MAP.get(timeframe)
        if not tf_proto:
            return pd.DataFrame()

        # Calcular rango de tiempo
        tf_minutes = {
            '1m':1,'5m':5,'15m':15,'30m':30,
            '1h':60,'4h':240,'1d':1440,'1w':10080
        }
        minutes = tf_minutes.get(timeframe, 15)
        now_ms  = int(
            datetime.now(timezone.utc).timestamp()
            * 1000
        )
        from_ms = now_ms - (
            minutes * limit * 60 * 1000
        )

        # Limpiar respuesta anterior
        self._last_trendbars = None

        request = ProtoOAGetTrendbarsReq()
        request.ctidTraderAccountId = \
            self.account_id
        request.symbolId  = symbol_id
        request.period    = tf_proto
        request.fromTimestamp = from_ms
        request.toTimestamp   = now_ms
        request.count     = limit

        await self._send_request(request)

        # Esperar respuesta (max 10 seg)
        for _ in range(100):
            if self._last_trendbars is not None:
                break
            await asyncio.sleep(0.1)

        if self._last_trendbars is None:
            log_error('CTRADER',
                f'Timeout descargando velas '
                f'{symbol}/{timeframe}'
            )
            return pd.DataFrame()

        return self._trendbars_to_df(
            self._last_trendbars,
            symbol,
            timeframe
        )

    def _trendbars_to_df(
        self,
        response,
        symbol:    str,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Convierte la respuesta Protobuf de trendbars
        a un DataFrame de pandas con el formato
        estándar de eTrader.
        """
        divisor = self.PRICE_DIVISOR.get(
            symbol, 100000
        )
        bars = response.trendbar
        if not bars:
            return pd.DataFrame()

        data = []
        for bar in bars:
            # cTrader: low + delta para cada precio
            low   = bar.low / divisor
            open_ = low + bar.deltaOpen / divisor
            high  = low + bar.deltaHigh / divisor
            close = low + bar.deltaClose / divisor
            vol   = bar.volume

            ts = pd.Timestamp(
                bar.utcTimestampInMinutes * 60,
                unit='s', tz='UTC'
            )

            data.append({
                'open_time': ts,
                'open':      round(open_,  6),
                'high':      round(high,   6),
                'low':       round(low,    6),
                'close':     round(close,  6),
                'volume':    vol,
            })

        df = pd.DataFrame(data)
        if df.empty:
            return df

        df = df.set_index('open_time')
        df = df.sort_index()

        # Eliminar velas duplicadas
        df = df[~df.index.duplicated(keep='last')]

        log_info('CTRADER',
            f'{symbol}/{timeframe}: '
            f'{len(df)} velas descargadas'
        )
        return df

    async def place_order(
        self,
        symbol:     str,
        side:       str,    # 'buy' o 'sell'
        order_type: str,    # 'market' o 'limit'
        quantity:   float,  # lotes
        price:      float = None,
        sl_price:   float = None,
        tp_price:   float = None,
    ) -> dict:
        """
        Coloca una orden via Protobuf.
        quantity en lotes (1 lote = 100,000 unidades)
        Equivalente a client.create_order() de Binance.
        """
        if not self._authenticated:
            return {'error': 'No autenticado'}

        symbol_id = self._symbol_ids.get(symbol)
        if not symbol_id:
            return {
                'error': f'Símbolo {symbol} '
                         f'no encontrado'
            }

        # Convertir lotes a unidades cTrader
        # 1 lote = 100,000 unidades
        volume = int(quantity * 100000)

        request = ProtoOANewOrderReq()
        request.ctidTraderAccountId = \
            self.account_id
        request.symbolId    = symbol_id
        request.orderType   = (
            ProtoOAOrderType.MARKET
            if order_type == 'market'
            else ProtoOAOrderType.LIMIT
        )
        request.tradeSide   = (
            ProtoOATradeSide.BUY
            if side == 'buy'
            else ProtoOATradeSide.SELL
        )
        request.volume      = volume

        if order_type == 'limit' and price:
            divisor = self.PRICE_DIVISOR.get(
                symbol, 100000
            )
            request.limitPrice = int(
                price * divisor
            )

        if sl_price:
            divisor = self.PRICE_DIVISOR.get(
                symbol, 100000
            )
            request.stopLoss = int(
                sl_price * divisor
            )

        if tp_price:
            divisor = self.PRICE_DIVISOR.get(
                symbol, 100000
            )
            request.takeProfit = int(
                tp_price * divisor
            )

        await self._send_request(request)

        log_info('CTRADER',
            f'Orden enviada: {side.upper()} '
            f'{quantity} lotes {symbol} '
            f'@ {price or "MARKET"}'
        )

        return {
            'order_id':  'pending',
            'symbol':    symbol,
            'side':      side,
            'quantity':  quantity,
            'price':     price,
            'status':    'submitted',
        }

    async def close_order(
        self,
        order_id: str,
        symbol:   str,
        quantity: float
    ) -> dict:
        """Cerrar una posición abierta."""
        position_id = int(order_id)
        volume = int(quantity * 100000)
        request = ProtoOAClosePositionReq()
        request.ctidTraderAccountId = \
            self.account_id
        request.positionId = position_id
        request.volume     = volume

        await self._send_request(request)
        return {
            'closed': True,
            'position_id': position_id
        }

    async def get_account_balance(self) -> dict:
        """Obtiene el balance de la cuenta."""
        request = ProtoOATraderReq()
        request.ctidTraderAccountId = \
            self.account_id

        self._last_trader = None
        await self._send_request(request)

        for _ in range(50):
            if hasattr(self, '_last_trader') \
               and self._last_trader:
                break
            await asyncio.sleep(0.1)

        if hasattr(self, '_last_trader') \
           and self._last_trader:
            trader = self._last_trader
            return {
                'balance':     trader.balance / 100,
                'equity':      trader.equity / 100,
                'margin_free': trader.freeMargin / 100,
                'currency':    trader.depositCurrency,
            }
        return {}

    async def get_open_positions(self) -> list:
        """Obtiene las posiciones abiertas."""
        request = ProtoOAReconcileReq()
        request.ctidTraderAccountId = \
            self.account_id

        self._last_reconcile = None
        await self._send_request(request)

        for _ in range(50):
            if hasattr(self, '_last_reconcile') \
               and self._last_reconcile:
                break
            await asyncio.sleep(0.1)

        if hasattr(self, '_last_reconcile') \
           and self._last_reconcile:
            return list(
                self._last_reconcile.position
            )
        return []

    async def disconnect(self):
        """Cierra la conexión TCP."""
        if self._client:
            self._client.stopService()
        self._connected     = False
        self._authenticated = False
        log_info('CTRADER', 'Desconectado')
