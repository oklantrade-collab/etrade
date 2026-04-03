"""
eTrader v2 — Historical Data Loader (Sprint 6)
Loads historical OHLCV data from Binance into market_candles
for backtesting purposes. Run this script ONCE.

Usage:
    python backend/scripts/load_historical_data.py
"""
import sys
import os
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from binance.client import Client
from app.core.config import settings
from app.core.supabase_client import get_supabase

# ── Configuration ──
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT',
    'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT',
    'DOTUSDT', 'MATICUSDT', 'LINKUSDT', 'LTCUSDT',
    'TRXUSDT', 'NEARUSDT', 'UNIUSDT', 'APTUSDT',
    'ARBUSDT', 'OPUSDT', 'SUIUSDT', 'PEPEUSDT',
]

# Binance does NOT support 45m interval — using 1h instead
TIMEFRAME_CONFIG = {
    '15m': 90,    # últimos 90 días
    '30m': 90,    # últimos 90 días
    '1h':  90,    # últimos 90 días (reemplaza 45m)
    '4h':  365,   # 1 año completo
    '1d':  730,   # 2 años
    '1w':  1460,  # 4 años
}

# Map our timeframe keys to Binance interval constants
BINANCE_INTERVAL_MAP = {
    '15m': Client.KLINE_INTERVAL_15MINUTE,
    '30m': Client.KLINE_INTERVAL_30MINUTE,
    '1h':  Client.KLINE_INTERVAL_1HOUR,
    '4h':  Client.KLINE_INTERVAL_4HOUR,
    '1d':  Client.KLINE_INTERVAL_1DAY,
    '1w':  Client.KLINE_INTERVAL_1WEEK,
}

BATCH_SIZE = 500


def to_internal_symbol(binance_symbol: str) -> str:
    """Convert BTCUSDT -> BTC/USDT."""
    for quote in ['USDT', 'BUSD', 'USDC']:
        if binance_symbol.endswith(quote):
            base = binance_symbol[:-len(quote)]
            return f"{base}/{quote}"
    return binance_symbol


def load_historical(
    client: Client,
    supabase,
    symbol_binance: str,
    timeframe: str,
    days_back: int,
):
    """
    Load historical klines from Binance and upsert into market_candles.
    Uses get_historical_klines which handles pagination automatically.
    """
    interval = BINANCE_INTERVAL_MAP.get(timeframe, timeframe)
    start_str = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%d %b %Y')
    internal_symbol = to_internal_symbol(symbol_binance)

    print(f'  ⏳ {symbol_binance} {timeframe}: fetching from {start_str}...')

    klines = client.get_historical_klines(
        symbol_binance, interval, start_str
    )

    if not klines:
        print(f'  ⚠️  {symbol_binance} {timeframe}: No data returned')
        return

    records = []
    now = datetime.now(timezone.utc)

    for k in klines:
        open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)

        # Skip candles that haven't closed yet
        if open_time >= now:
            continue

        records.append({
            'symbol':            internal_symbol,
            'exchange':          'binance',
            'timeframe':         timeframe,
            'open_time':         open_time.isoformat(),
            'open':              float(k[1]),
            'high':              float(k[2]),
            'low':               float(k[3]),
            'close':             float(k[4]),
            'volume':            float(k[5]),
            'quote_volume':      float(k[7]),
            'trades_count':      int(k[8]),
            'taker_buy_volume':  float(k[9]),
            'taker_sell_volume': float(k[5]) - float(k[9]),
        })

    if not records:
        print(f'  ⚠️  {symbol_binance} {timeframe}: 0 valid candles after filtering')
        return

    # Upsert in batches
    total = len(records)
    for i in range(0, total, BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        for attempt in range(3):
            try:
                supabase.table('market_candles').upsert(
                    batch,
                    on_conflict='symbol,exchange,timeframe,open_time'
                ).execute()
                print(f'    Insertados {min(i + BATCH_SIZE, total)}/{total} registros')
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    print(f'    ⚠️ Retry {attempt + 1}/3: {e}. Esperando {wait}s...')
                    time.sleep(wait)
                else:
                    print(f'    ❌ Falló después de 3 intentos: {e}')

    print(f'  ✅ {symbol_binance} {timeframe}: {total} velas cargadas')


def main():
    print('=' * 60)
    print('  eTrader v2 — Carga de Datos Históricos')
    print('=' * 60)

    # Initialize Binance client (uses production API for historical data)
    api_key = os.getenv('BINANCE_API_KEY') or settings.binance_api_key
    api_secret = os.getenv('BINANCE_SECRET') or settings.binance_secret

    # For historical data we use the PRODUCTION API (not testnet)
    # Testnet has very limited historical data
    client = Client(api_key, api_secret, testnet=False)
    
    try:
        client.ping()
        print('✅ Conexión a Binance OK\n')
    except Exception as e:
        print(f'❌ Error conectando a Binance: {e}')
        sys.exit(1)

    supabase = get_supabase()

    total_symbols = len(SYMBOLS)
    total_timeframes = len(TIMEFRAME_CONFIG)

    for idx, symbol in enumerate(SYMBOLS, 1):
        print(f'\n📊 [{idx}/{total_symbols}] Cargando {symbol}...')
        for tf, days in TIMEFRAME_CONFIG.items():
            try:
                load_historical(client, supabase, symbol, tf, days)
                time.sleep(0.5)  # Respect Binance rate limits
            except Exception as e:
                print(f'  ❌ Error {symbol} {tf}: {e}')
                time.sleep(1)

    print('\n' + '=' * 60)
    print('✅ Carga histórica completada')
    print('Ya puedes ejecutar backtests desde la UI.')
    print('=' * 60)

    # Verification query
    try:
        result = supabase.table('market_candles') \
            .select('timeframe', count='exact') \
            .eq('timeframe', '4h') \
            .execute()
        print(f'\n📊 Verificación: market_candles con timeframe=4h: {result.count} registros')
    except Exception as e:
        print(f'⚠️  No se pudo verificar conteo: {e}')


if __name__ == '__main__':
    main()
