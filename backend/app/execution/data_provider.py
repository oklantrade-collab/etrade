"""
eTrade v3 — DataProvider Abstraction
Interface for all market data sources.
Trading logic NEVER calls Binance/OANDA directly — always through this contract.
"""
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class DataProvider(ABC):
    """
    Common interface for all market data providers.
    The trading logic never calls Binance or any other exchange directly.
    """

    @abstractmethod
    async def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        """Fetch OHLCV candle data."""
        pass

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get the current price for a symbol."""
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> dict:
        """Get current price and ticker data."""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> dict:
        """Place an order on the exchange."""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> dict:
        """Get the current position for a symbol."""
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel a specific order."""
        pass

    @abstractmethod
    async def get_account_balance(self, asset: str = "USDT") -> float:
        """Get available balance for an asset."""
        pass


import asyncio

class BinanceCryptoProvider(DataProvider):
    """
    Implementation for Crypto SPOT and Crypto FUTURES.
    Sprint 1 — only active provider.
    """

    _ban_until_ts = None

    @classmethod
    def is_banned(cls) -> bool:
        if cls._ban_until_ts is None:
            return False
        import time
        now_ms = int(time.time() * 1000)
        if now_ms < cls._ban_until_ts:
            return True
        cls._ban_until_ts = None
        return False

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        market: str = "futures",
        testnet: bool = True,
    ):
        self.market = market  # 'spot' | 'futures'
        self.testnet = testnet
        self.api_key = api_key
        self.api_secret = api_secret
        self._async_client = None
        self._init_lock = asyncio.Lock()

    async def close(self):
        """Cerrar sesiones asíncronas de Binance."""
        if self._async_client:
            await self._async_client.close_connection()
            self._async_client = None

    async def _get_async_client(self):
        async with self._init_lock:
            if self._async_client is None:
                from binance import AsyncClient as BinanceAsyncClient
                self._async_client = await BinanceAsyncClient.create(
                    self.api_key,
                    self.api_secret,
                    testnet=self.testnet,
                )
                if self.market == "futures":
                    try:
                        await self._async_client.futures_change_position_mode(dualSidePosition='true')
                        from app.core.logger import log_info
                        log_info('BINANCE', 'Hedge Mode (dualSidePosition) activado correctamente.')
                    except Exception as e:
                        err_str = str(e)
                        if "No need to change" not in err_str:
                            from app.core.logger import log_warning
                            log_warning('BINANCE', f'No se pudo activar Hedge Mode: {err_str} (Asegúrate de no tener posiciones abiertas).')
        return self._async_client

    async def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        """Fetch OHLCV data from Binance REST API (ASYNCHRONOUS) with retries."""
        if BinanceCryptoProvider.is_banned():
            raise Exception(f"Binance API request blocked: IP is banned until timestamp {BinanceCryptoProvider._ban_until_ts}")

        client = await self._get_async_client()
        symbol_clean = symbol.replace("/", "")

        interval_map = {
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w",
        }
        interval = interval_map.get(timeframe, timeframe)

        max_retries = 3
        klines = []
        for attempt in range(max_retries):
            try:
                import asyncio
                if self.market == "futures":
                    klines = await asyncio.wait_for(
                        client.futures_klines(symbol=symbol_clean, interval=interval, limit=limit),
                        timeout=15.0
                    )
                else:
                    klines = await asyncio.wait_for(
                        client.get_klines(symbol=symbol_clean, interval=interval, limit=limit),
                        timeout=15.0
                    )
                break # Success!
            except Exception as e:
                err_str = repr(e)
                if "IP banned" in err_str or "Way too many requests" in err_str or "418" in err_str:
                    import re
                    match = re.search(r"banned until (?:timestamp )?(\d+)", err_str)
                    if match:
                        BinanceCryptoProvider._ban_until_ts = int(match.group(1))

                import asyncio
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)

        df = pd.DataFrame(
            klines,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades_count",
                "taker_buy_volume",
                "taker_sell_volume",
                "ignore",
            ],
        )

        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

        return df

    async def get_current_price(self, symbol: str) -> float:
        if BinanceCryptoProvider.is_banned():
            raise Exception(f"Binance API request blocked: IP is banned until timestamp {BinanceCryptoProvider._ban_until_ts}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = await self._get_async_client()
                symbol_clean = symbol.replace("/", "")
                import asyncio
                if self.market == "futures":
                    ticker = await asyncio.wait_for(client.futures_symbol_ticker(symbol=symbol_clean), timeout=10.0)
                else:
                    ticker = await asyncio.wait_for(client.get_symbol_ticker(symbol=symbol_clean), timeout=10.0)
                return float(ticker["price"])
            except Exception as e:
                err_str = repr(e)
                if "IP banned" in err_str or "Way too many requests" in err_str or "418" in err_str:
                    import re
                    match = re.search(r"banned until (?:timestamp )?(\d+)", err_str)
                    if match:
                        BinanceCryptoProvider._ban_until_ts = int(match.group(1))

                import asyncio
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(1)
        return 0.0

    async def get_ticker(self, symbol: str) -> dict:
        """Fetch current price and ticker data."""
        if BinanceCryptoProvider.is_banned():
            raise Exception(f"Binance API request blocked: IP is banned until timestamp {BinanceCryptoProvider._ban_until_ts}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = await self._get_async_client()
                symbol_clean = symbol.replace("/", "")
                import asyncio
                if self.market == "futures":
                    ticker = await asyncio.wait_for(client.futures_symbol_ticker(symbol=symbol_clean), timeout=10.0)
                else:
                    ticker = await asyncio.wait_for(client.get_symbol_ticker(symbol=symbol_clean), timeout=10.0)

                return {
                    "symbol": symbol_clean,
                    "price": float(ticker["price"]),
                    "time": ticker.get("time") # Some endpoints don't return time
                }
            except Exception as e:
                err_str = repr(e)
                if "IP banned" in err_str or "Way too many requests" in err_str or "418" in err_str:
                    import re
                    match = re.search(r"banned until (?:timestamp )?(\d+)", err_str)
                    if match:
                        BinanceCryptoProvider._ban_until_ts = int(match.group(1))

                import asyncio
                if attempt == max_retries - 1:
                    raise Exception(f"get_ticker failed for {symbol}: {e}")
                await asyncio.sleep(1)
        return {}

    async def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
        **kwargs
    ) -> dict:
        client = await self._get_async_client()
        symbol_clean = symbol.replace("/", "")

        params = {
            "symbol": symbol_clean,
            "side": side.upper(),
            "type": order_type,
            "quantity": size,
        }
        if price and order_type == "LIMIT":
            params["price"] = str(price)
            params["timeInForce"] = "GTC"
            
        params.update(kwargs)

        if self.market == "futures":
            result = await client.futures_create_order(**params)
        else:
            result = await client.create_order(**params)
        return result

    async def get_position(self, symbol: str) -> dict:
        """Get position info (mainly for futures)."""
        client = await self._get_async_client()
        symbol_clean = symbol.replace("/", "")

        if self.market == "futures":
            positions = await client.futures_position_information(symbol=symbol_clean)
            for pos in positions:
                if float(pos.get("positionAmt", 0)) != 0:
                    return {
                        "symbol": symbol,
                        "side": "long" if float(pos["positionAmt"]) > 0 else "short",
                        "size": abs(float(pos["positionAmt"])),
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "unrealized_pnl": float(pos.get("unRealizedProfit", 0)),
                    }
        return {"symbol": symbol, "side": None, "size": 0, "entry_price": 0}

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        client = await self._get_async_client()
        symbol_clean = symbol.replace("/", "")
        if self.market == "futures":
            return await client.futures_cancel_order(symbol=symbol_clean, orderId=order_id)
        else:
            return await client.cancel_order(symbol=symbol_clean, orderId=order_id)

    async def get_account_balance(self, asset: str = "USDT") -> float:
        client = await self._get_async_client()
        if self.market == "futures":
            acc = await client.futures_account()
            for balance in acc.get("assets", []):
                if balance["asset"] == asset:
                    return float(balance["walletBalance"])
        else:
            account = await client.get_account()
            for balance in account["balances"]:
                if balance["asset"] == asset:
                    return float(balance["free"])
        return 0.0


class PaperTradingProvider(DataProvider):
    """
    Paper Trading provider — uses real prices but simulates fills.
    Wraps a real DataProvider for price/OHLCV data.
    """

    def __init__(self, real_provider: DataProvider):
        self.real = real_provider
        self.simulated_positions: dict = {}
        self.simulated_orders: list = []

    async def close(self):
        """Pass close to the real provider."""
        if hasattr(self.real, 'close'):
            await self.real.close()

    async def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        return await self.real.get_ohlcv(symbol, timeframe, limit)

    async def get_current_price(self, symbol: str) -> float:
        return await self.real.get_current_price(symbol)

    async def get_ticker(self, symbol: str) -> dict:
        return await self.real.get_ticker(symbol)

    async def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> dict:
        """Simulate a fill at the current close price."""
        current_price = await self.get_current_price(symbol)
        fill_price = price or current_price

        order = {
            "orderId": f"PAPER-{len(self.simulated_orders)+1}",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": size,
            "price": fill_price,
            "status": "FILLED",
            "mode": "paper",
        }
        self.simulated_orders.append(order)
        return order

    async def get_position(self, symbol: str) -> dict:
        return self.simulated_positions.get(
            symbol, {"symbol": symbol, "side": None, "size": 0, "entry_price": 0}
        )

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        return {"status": "cancelled", "orderId": order_id, "mode": "paper"}

    async def get_account_balance(self, asset: str = "USDT") -> float:
        return await self.real.get_account_balance(asset)
