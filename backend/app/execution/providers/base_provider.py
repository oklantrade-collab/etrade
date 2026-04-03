"""
eTrader — Base Market Provider Interface
=========================================
Interface base para todos los proveedores de mercado.
Cualquier proveedor nuevo (Binance, cTrader, OANDA, etc.)
debe implementar estos métodos.

Diseñado para ser compatible con el Strategy Engine v1.0
y las reglas Aa/Bb/Cc/Dd existentes.
"""
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class BaseMarketProvider(ABC):
    """
    Interface base para todos los proveedores de mercado.
    Cualquier proveedor nuevo debe implementar estos métodos.
    """

    @abstractmethod
    async def connect(self) -> bool:
        """Establecer conexión con el proveedor."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Cerrar conexión."""
        pass

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol:    str,
        timeframe: str,
        limit:     int = 300
    ) -> pd.DataFrame:
        """
        Obtener velas históricas OHLCV.
        Retorna DataFrame con columnas:
            open, high, low, close, volume
        Index: datetime UTC
        """
        pass

    @abstractmethod
    async def get_current_price(
        self,
        symbol: str
    ) -> float:
        """Obtener precio actual bid/ask."""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol:     str,
        side:       str,       # 'buy' o 'sell'
        order_type: str,       # 'market' o 'limit'
        quantity:   float,
        price:      Optional[float] = None,
        sl_price:   Optional[float] = None,
        tp_price:   Optional[float] = None
    ) -> dict:
        """
        Colocar una orden.
        Retorna dict con order_id y detalles.
        """
        pass

    @abstractmethod
    async def close_order(
        self,
        order_id: str,
        symbol:   str,
        quantity: float
    ) -> dict:
        """Cerrar una posición abierta."""
        pass

    @abstractmethod
    async def get_account_balance(self) -> dict:
        """
        Obtener balance de la cuenta.
        Retorna: {balance, equity, margin_free}
        """
        pass

    @abstractmethod
    async def get_open_positions(self) -> list:
        """Obtener posiciones abiertas."""
        pass

    @property
    @abstractmethod
    def market_type(self) -> str:
        """
        Tipo de mercado:
        'crypto_futures' | 'crypto_spot' | 'forex_futures' | 'forex_spot'
        """
        pass

    @property
    @abstractmethod
    def pip_size(self) -> dict:
        """
        Tamaño del pip por símbolo.
        ej: {'EURUSD': 0.0001, 'USDJPY': 0.01}
        """
        pass
