"""
eTrader v2 — Binance Connector
Low-level Binance API wrapper for exchange info, balance, and order queries.
"""
from datetime import datetime, timedelta, timezone

from binance.client import Client as BinanceClient
from app.core.config import settings
from app.core.logger import log_info, log_error
import os
from binance.exceptions import BinanceAPIException

MODULE = "binance_connector"

_client: BinanceClient | None = None

# ── Symbol info cache with TTL ──
_symbol_info_cache: dict[str, tuple[dict, datetime]] = {}
_SYMBOL_INFO_TTL = timedelta(hours=1)

def get_client() -> BinanceClient:
    api_key    = os.getenv('BINANCE_API_KEY') or settings.binance_api_key
    api_secret = os.getenv('BINANCE_SECRET') or settings.binance_secret
    testnet_val = os.getenv('BINANCE_TESTNET')
    if testnet_val is not None:
        testnet = testnet_val.lower() == 'true'
    else:
        testnet = settings.binance_testnet
    
    global _client
    if _client is None:
        log_info(MODULE, f"Connecting to Binance (Testnet={testnet}) with Key: {api_key[:5]}...")
        _client = BinanceClient(api_key, api_secret, testnet=testnet)
        try:
            _client.ping()
        except BinanceAPIException as e:
            raise ConnectionError(f'Binance connection failed: {e}')
    return _client

def get_account_balance(client: BinanceClient, asset: str = 'USDT') -> float:
    """Retorna el balance disponible del asset especificado."""
    try:
        account = client.get_account()
        for balance in account['balances']:
            if balance['asset'] == asset:
                return float(balance['free'])
    except Exception as e:
        log_error(MODULE, f"Failed to get {asset} balance: {e}")
    return 0.0

def get_usdt_balance() -> float:
    return get_account_balance(get_client(), 'USDT')

def get_symbol_info(client: BinanceClient, symbol: str) -> dict:
    """
    Retorna información del símbolo: step_size, min_notional, etc.
    symbol en formato Binance: 'BTCUSDT' (sin slash)
    """
    info = client.get_symbol_info(symbol)
    result = {
        'symbol': symbol,
        'step_size': None,
        'min_qty': None,
        'min_notional': None,
        'price_precision': None,
        'qty_precision': None,
        'tick_size': None
    }
    
    if not info:
        return result

    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            result['step_size'] = float(f['stepSize'])
            result['min_qty']   = float(f['minQty'])
        if f['filterType'] == 'NOTIONAL' or f['filterType'] == 'MIN_NOTIONAL':
            result['min_notional'] = float(f.get('minNotional', f.get('notional', 10.0)))
        if f['filterType'] == 'PRICE_FILTER':
            result['tick_size'] = float(f['tickSize'])
    
    return result


def get_symbol_info_cached(client: BinanceClient, symbol: str) -> dict:
    """
    Cached version of get_symbol_info with 1-hour TTL.
    Symbol info (step_size, min_notional, tick_size) rarely changes,
    so caching reduces Binance API calls from ~20/cycle to ~0/cycle
    after the first cycle.
    """
    now = datetime.now(timezone.utc)

    if symbol in _symbol_info_cache:
        data, expires_at = _symbol_info_cache[symbol]
        if now < expires_at:
            return data

    info = get_symbol_info(client, symbol)
    _symbol_info_cache[symbol] = (info, now + _SYMBOL_INFO_TTL)
    return info


def get_step_size(symbol: str) -> float:
    info = get_symbol_info_cached(get_client(), symbol)
    return info.get('step_size') or 0.001

def get_tick_size(symbol: str) -> float:
    info = get_symbol_info_cached(get_client(), symbol)
    return info.get('tick_size') or 0.01

def get_current_price(symbol: str) -> float:
    try:
        client = get_client()
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])
    except Exception as e:
        log_error(MODULE, f"Failed to get price for {symbol}: {e}")
        return 0.0

def round_step_size(quantity: float, step_size: float) -> float:
    import math
    if step_size <= 0: return quantity
    precision = int(round(-math.log(step_size, 10), 0))
    return round(quantity - (quantity % step_size), precision)

def round_price(price: float, tick_size: float) -> float:
    import math
    if tick_size <= 0: return price
    precision = int(round(-math.log(tick_size, 10), 0))
    return round(price - (price % tick_size), precision)
