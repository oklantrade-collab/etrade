"""
eTrader — Forex Configuration
===============================
Configuración específica para operaciones en Forex
via IC Markets / cTrader.

Compatible con el Strategy Engine v1.0 y las reglas
Aa/Bb/Cc/Dd existentes.
"""
import os


# ── Forex Symbols ──────────────────────────────────
# Pares principales a operar
FOREX_SYMBOLS = [
    s.strip()
    for s in os.getenv('FOREX_SYMBOLS', 'EURUSD,GBPUSD,USDJPY,XAUUSD').split(',')
    if s.strip()
]

# ── Symbol Map: Forex format ───────────────────────
# cTrader usa formato sin slash (EURUSD),
# consistente con el formato interno de eTrader.
FOREX_SYMBOL_MAP = {
    'EURUSD':  'EUR/USD',
    'GBPUSD':  'GBP/USD',
    'USDJPY':  'USD/JPY',
    'USDCHF':  'USD/CHF',
    'AUDUSD':  'AUD/USD',
    'NZDUSD':  'NZD/USD',
    'USDCAD':  'USD/CAD',
    'EURGBP':  'EUR/GBP',
    'EURJPY':  'EUR/JPY',
    'GBPJPY':  'GBP/JPY',
    'XAUUSD':  'XAU/USD',
    'XAGUSD':  'XAG/USD',
    'US30':    'US30',
    'US500':   'US500',
    'NAS100':  'NAS100',
}

# ── Timeframes for Forex ───────────────────────────
# Los mismos timeframes que usa el motor de estrategias
# pero con mayor límite de velas para Forex (mercado 24/5)
FOREX_TIMEFRAMES = {
    '5m':  {'limit': 200, 'weight': 0.10},
    '15m': {'limit': 200, 'weight': 0.35},
    '30m': {'limit': 200, 'weight': 0.20},
    '1h':  {'limit': 200, 'weight': 0.15},
    '4h':  {'limit': 200, 'weight': 0.15},
    '1d':  {'limit': 60,  'weight': 0.05},
}

# ── Pip Sizes ──────────────────────────────────────
# Tamaño del pip para cálculo de SL/TP
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
    'XAUUSD':  0.01,
    'XAGUSD':  0.001,
    'US30':    1.0,
    'US500':   0.1,
    'NAS100':  0.1,
}

# ── Lot Sizes ──────────────────────────────────────
# Tamaño mínimo e incremental de lotes
LOT_CONFIG = {
    'min_lot':       0.01,    # Micro lote
    'lot_step':      0.01,    # Incremento mínimo
    'standard_lot':  1.0,     # 100,000 unidades
    'mini_lot':      0.1,     # 10,000 unidades
    'micro_lot':     0.01,    # 1,000 unidades
}

# ── Trading Sessions (UTC) ────────────────────────
# Horarios de las sesiones principales del mercado Forex
FOREX_SESSIONS = {
    'sydney':  {'open': '21:00', 'close': '06:00'},
    'tokyo':   {'open': '00:00', 'close': '09:00'},
    'london':  {'open': '07:00', 'close': '16:00'},
    'newyork': {'open': '12:00', 'close': '21:00'},
}

# ── Spread Limits (pips) ──────────────────────────
# Spread máximo aceptable para ejecutar órdenes
MAX_SPREAD_PIPS = {
    'EURUSD':  2.0,
    'GBPUSD':  2.5,
    'USDJPY':  2.0,
    'USDCHF':  2.5,
    'AUDUSD':  2.0,
    'NZDUSD':  3.0,
    'USDCAD':  2.5,
    'EURGBP':  2.5,
    'EURJPY':  3.0,
    'GBPJPY':  4.0,
    'XAUUSD':  5.0,
    'XAGUSD':  5.0,
    'US30':    3.0,
    'US500':   1.5,
    'NAS100':  2.0,
}

# ── Risk Management ───────────────────────────────
FOREX_RISK_CONFIG = {
    'max_risk_per_trade':    0.01,     # 1% del equity
    'max_open_positions':    5,        # Máximo de posiciones simultáneas
    'max_positions_per_pair': 1,       # Una posición por par
    'max_daily_loss':        0.03,     # 3% circuit breaker
    'default_leverage':      100,      # Apalancamiento por defecto
    'sl_pips_default':       30,       # SL por defecto en pips
    'tp_rr_ratio':           2.5,     # Risk:Reward ratio
}

# ── cTrader Environment ────────────────────────────
CTRADER_CONFIG = {
    'environment':    os.getenv('CTRADER_ENV', 'demo'),
    'client_id':      os.getenv('CTRADER_CLIENT_ID', ''),
    'client_secret':  os.getenv('CTRADER_CLIENT_SECRET', ''),
    'account_id':     os.getenv('CTRADER_ACCOUNT_ID', ''),
    'access_token':   os.getenv('CTRADER_ACCESS_TOKEN', ''),
}
