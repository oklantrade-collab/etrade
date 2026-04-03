"""
eTrader — cTrader Provider (IC Markets)
========================================
Proveedor para IC Markets via cTrader Open API.
Soporta Forex, CFDs y otros instrumentos.

Documentación: https://connect.spotware.com/docs/

CREDENCIALES NECESARIAS (variables de entorno):
    CTRADER_CLIENT_ID      - de IC Markets portal
    CTRADER_CLIENT_SECRET  - de IC Markets portal
    CTRADER_ACCESS_TOKEN   - OAuth 2.0
    CTRADER_ACCOUNT_ID     - número de cuenta
    CTRADER_ENV            - 'demo' o 'live'
"""
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional

from .base_provider import BaseMarketProvider
from app.core.logger import log_info, log_error, log_warning


class CTraderProvider(BaseMarketProvider):
    """
    Proveedor para IC Markets via cTrader Open API.
    Soporta Forex, CFDs y otros instrumentos.
    """

    # ── Endpoints ──────────────────────────────────
    DEMO_HOST = 'demo.ctraderapi.com'
    LIVE_HOST = 'live.ctraderapi.com'
    AUTH_URL  = 'https://connect.spotware.com/apps/token'
    API_BASE  = 'https://api.spotware.com/connect'

    # ── Mapeo de timeframes eTrader → cTrader ──────
    TF_MAP = {
        '1m':  'M1',
        '5m':  'M5',
        '15m': 'M15',
        '30m': 'M30',
        '1h':  'H1',
        '4h':  'H4',
        '1d':  'D1',
        '1w':  'W1',
    }

    # ── Pips por símbolo Forex / CFD ───────────────
    PIP_SIZES = {
        'EURUSD':  0.0001,
        'GBPUSD':  0.0001,
        'USDJPY':  0.01,
        'USDCHF':  0.0001,
        'AUDUSD':  0.0001,
        'NZDUSD':  0.0001,
        'USDCAD':  0.0001,
        'EURGBP':  0.0001,
        'EURJPY':  0.01,
        'GBPJPY':  0.01,
        'XAUUSD':  0.01,     # Oro
        'XAGUSD':  0.001,    # Plata
        'US30':    1.0,      # Dow Jones
        'US500':   0.1,      # S&P 500
        'NAS100':  0.1,      # Nasdaq
    }

    # ── Minutes per cTrader timeframe ──────────────
    TF_MINUTES = {
        'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
        'H1': 60, 'H4': 240, 'D1': 1440, 'W1': 10080,
    }

    MODULE = 'CTRADER'

    def __init__(
        self,
        client_id:     str,
        client_secret: str,
        account_id:    str,
        access_token:  str,
        environment:   str = 'demo',   # 'demo' o 'live'
    ):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.account_id    = account_id
        self.access_token  = access_token
        self.env           = environment
        self.host          = (
            self.LIVE_HOST if environment == 'live'
            else self.DEMO_HOST
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self._connected = False

    # ── Properties ─────────────────────────────────

    @property
    def market_type(self) -> str:
        return 'forex_futures'

    @property
    def pip_size(self) -> dict:
        return self.PIP_SIZES

    # ── Connection ─────────────────────────────────

    async def connect(self) -> bool:
        """Establecer sesión HTTP con cTrader API."""
        try:
            self.session = aiohttp.ClientSession(
                headers={
                    'Authorization': f'Bearer {self.access_token}',
                    'Content-Type':  'application/json',
                }
            )
            # Verificar conexión con ping al balance
            balance = await self.get_account_balance()
            if balance:
                self._connected = True
                log_info(
                    self.MODULE,
                    f'Conectado a IC Markets ({self.env}) — '
                    f'Balance: {balance.get("balance")}'
                )
                return True
            return False
        except Exception as e:
            log_error(self.MODULE, f'Error de conexión: {e}')
            return False

    async def disconnect(self) -> None:
        """Cerrar sesión HTTP."""
        if self.session:
            await self.session.close()
            self.session = None
        self._connected = False
        log_info(self.MODULE, 'Desconectado de IC Markets')

    # ── Market Data ────────────────────────────────

    async def get_ohlcv(
        self,
        symbol:    str,
        timeframe: str,
        limit:     int = 300,
    ) -> pd.DataFrame:
        """
        Obtener velas históricas desde cTrader.
        Retorna DataFrame indexado por timestamp UTC con
        columnas: open, high, low, close, volume.
        """
        tf_ct = self.TF_MAP.get(timeframe, 'M15')

        # Calcular fecha de inicio basada en el timeframe
        minutes = self.TF_MINUTES.get(tf_ct, 15)
        start_dt = (
            datetime.now(timezone.utc)
            - timedelta(minutes=minutes * limit)
        )

        url = (
            f'{self.API_BASE}/tradingaccounts/'
            f'{self.account_id}/symbols/'
            f'{symbol}/trendbars'
        )
        params = {
            'period': tf_ct,
            'from':   int(start_dt.timestamp() * 1000),
            'to':     int(datetime.now(timezone.utc).timestamp() * 1000),
            'count':  limit,
        }

        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()

            if 'data' not in data:
                log_warning(
                    self.MODULE,
                    f'get_ohlcv {symbol}/{timeframe}: '
                    f'Sin datos — respuesta: {str(data)[:200]}'
                )
                return pd.DataFrame()

            bars = data['data']
            df = pd.DataFrame(bars)

            # Normalizar columnas al formato eTrader
            df = df.rename(columns={
                'utcTimestampInMinutes': 'timestamp',
                'open':   'open',
                'high':   'high',
                'low':    'low',
                'close':  'close',
                'volume': 'volume',
            })

            df['timestamp'] = pd.to_datetime(
                df['timestamp'] * 60, unit='s', utc=True
            )
            df = df.set_index('timestamp')

            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            return df.sort_index()

        except Exception as e:
            log_error(
                self.MODULE,
                f'Error get_ohlcv {symbol}/{timeframe}: {e}'
            )
            return pd.DataFrame()

    async def get_current_price(self, symbol: str) -> float:
        """Obtener precio actual (mid price = promedio bid/ask)."""
        url = (
            f'{self.API_BASE}/tradingaccounts/'
            f'{self.account_id}/symbols/'
            f'{symbol}/ticks'
        )
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
            bid = float(data.get('bid', 0))
            ask = float(data.get('ask', 0))
            return (bid + ask) / 2  # mid price
        except Exception as e:
            log_error(self.MODULE, f'Error precio {symbol}: {e}')
            return 0.0

    # ── Order Execution ────────────────────────────

    async def place_order(
        self,
        symbol:     str,
        side:       str,        # 'buy' o 'sell'
        order_type: str,        # 'market' o 'limit'
        quantity:   float,      # lotes (0.01 = micro lote)
        price:      Optional[float] = None,
        sl_price:   Optional[float] = None,
        tp_price:   Optional[float] = None,
    ) -> dict:
        """
        Colocar orden en IC Markets via cTrader.
        quantity = lotes (0.01 = micro lote)
        cTrader usa unidades: 1 lote = 100,000 unidades
        """
        url = (
            f'{self.API_BASE}/tradingaccounts/'
            f'{self.account_id}/orders'
        )

        # Convertir lotes a unidades cTrader
        volume_units = int(quantity * 100_000)

        order_data = {
            'symbolName': symbol,
            'orderType':  'MARKET' if order_type == 'market' else 'LIMIT',
            'tradeSide':  'BUY' if side == 'buy' else 'SELL',
            'volume':     volume_units,
        }

        if price and order_type == 'limit':
            order_data['limitPrice'] = price

        if sl_price:
            order_data['stopLoss'] = sl_price

        if tp_price:
            order_data['takeProfit'] = tp_price

        try:
            async with self.session.post(url, json=order_data) as resp:
                data = await resp.json()

            log_info(
                self.MODULE,
                f'Orden ejecutada: {side.upper()} '
                f'{quantity} lotes {symbol} '
                f'→ ID: {data.get("orderId")}'
            )
            return {
                'order_id':  str(data.get('orderId')),
                'symbol':    symbol,
                'side':      side,
                'quantity':  quantity,
                'price':     data.get('executionPrice'),
                'status':    'filled',
                'raw':       data,
            }

        except Exception as e:
            log_error(self.MODULE, f'Error place_order: {e}')
            return {'error': str(e)}

    async def close_order(
        self,
        order_id: str,
        symbol:   str,
        quantity: float,
    ) -> dict:
        """Cerrar posición abierta."""
        url = (
            f'{self.API_BASE}/tradingaccounts/'
            f'{self.account_id}/positions/'
            f'{order_id}/close'
        )
        try:
            async with self.session.post(url) as resp:
                data = await resp.json()
            log_info(
                self.MODULE,
                f'Posición cerrada: {order_id} ({symbol})'
            )
            return {
                'closed':   True,
                'order_id': order_id,
                'raw':      data,
            }
        except Exception as e:
            log_error(self.MODULE, f'Error close_order: {e}')
            return {'error': str(e)}

    # ── Account Info ───────────────────────────────

    async def get_account_balance(self) -> dict:
        """
        Obtener balance de la cuenta.
        cTrader retorna valores en centavos → dividir por 100.
        """
        url = (
            f'{self.API_BASE}/tradingaccounts/'
            f'{self.account_id}'
        )
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
            return {
                'balance':     float(data.get('balance', 0)) / 100,
                'equity':      float(data.get('equity', 0)) / 100,
                'margin_free': float(data.get('freeMargin', 0)) / 100,
                'currency':    data.get('currency', 'USD'),
            }
        except Exception as e:
            log_error(self.MODULE, f'Error balance: {e}')
            return {}

    async def get_open_positions(self) -> list:
        """Obtener posiciones abiertas."""
        url = (
            f'{self.API_BASE}/tradingaccounts/'
            f'{self.account_id}/positions'
        )
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
            return data.get('position', [])
        except Exception as e:
            log_error(self.MODULE, f'Error positions: {e}')
            return []
