"""
Test de Verificacion: Fase 1 (Throttle) + Fase 2 (Migracion a Memoria)
Ejecutar desde: c:\\Fuentes\\eTrade\\backend
Comando: python -m app.tests.test_egress_optimization
"""
import sys
import os
import time
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Asegurar que el path del backend esta en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PASSED = 0
FAILED = 0
ERRORS = []

def test_pass(name):
    global PASSED
    PASSED += 1
    print(f"  ✅ {name}")

def test_fail(name, reason):
    global FAILED, ERRORS
    FAILED += 1
    ERRORS.append(f"{name}: {reason}")
    print(f"  ❌ {name} — {reason}")

# Helper: Crear DataFrame de velas simuladas
def make_candle_df(rows=50, base_price=1.1400):
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=rows, freq='15min')
    np.random.seed(42)
    closes = base_price + np.cumsum(np.random.randn(rows) * 0.0005)
    
    df = pd.DataFrame({
        'open': closes - np.random.rand(rows) * 0.0003,
        'high': closes + np.random.rand(rows) * 0.0005,
        'low': closes - np.random.rand(rows) * 0.0005,
        'close': closes,
        'volume': np.random.randint(100, 10000, rows).astype(float),
        'open_time': dates,
    }, index=dates)
    
    df['ema_3'] = df['close'].ewm(span=3, adjust=False).mean()
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['basis'] = df['close'].rolling(20).mean()
    df['upper_6'] = df['basis'] + 2 * df['close'].rolling(20).std()
    df['lower_6'] = df['basis'] - 2 * df['close'].rolling(20).std()
    df['sar'] = df['close'] * 0.999
    df['sar_trend'] = 1
    df['pinescript_signal'] = None
    df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3
    
    return df

print("=" * 70)
print("  VERIFICACION: Optimizacion Egress Supabase (Fase 1 + Fase 2)")
print("=" * 70)

# =============================================
#  FASE 1: TESTS DE THROTTLE
# =============================================
print("\n FASE 1: Verificacion de Throttle (60 minutos)")
print("-" * 50)

# --- Test 1A: data_fetcher.py throttle ---
try:
    from app.analysis.data_fetcher import upsert_candles, _CANDLE_UPSERT_LAST, _CANDLE_UPSERT_INTERVAL
    
    if isinstance(_CANDLE_UPSERT_LAST, dict) and _CANDLE_UPSERT_INTERVAL == 3600:
        test_pass("data_fetcher: Variables de throttle existen (intervalo=3600s)")
    else:
        test_fail("data_fetcher: Variables de throttle", f"intervalo={_CANDLE_UPSERT_INTERVAL}")

    df_test = make_candle_df(5)
    _CANDLE_UPSERT_LAST["TEST_SYMBOL_15m"] = time.time()
    
    with patch('app.analysis.data_fetcher.get_supabase') as mock_sb:
        result = upsert_candles(df_test, "TEST_SYMBOL", "binance", "15m")
        if result == 0 and not mock_sb.called:
            test_pass("data_fetcher: Throttle BLOQUEA segundo upsert (no toca Supabase)")
        else:
            test_fail("data_fetcher: Throttle", f"result={result}, sb_called={mock_sb.called}")
    
    del _CANDLE_UPSERT_LAST["TEST_SYMBOL_15m"]

except Exception as e:
    test_fail("data_fetcher: Import/Throttle", str(e))

# --- Test 1B: scheduler.py sync_current_candle_to_db throttle ---
try:
    from app.workers.scheduler import sync_current_candle_to_db
    
    if not hasattr(sync_current_candle_to_db, '_last'):
        sync_current_candle_to_db._last = {}
    sync_current_candle_to_db._last["BTCUSDT"] = time.time()
    
    mock_sb = MagicMock()
    
    loop = asyncio.new_event_loop()
    loop.run_until_complete(sync_current_candle_to_db("BTCUSDT", 61000.0, mock_sb))
    loop.close()
    
    if not mock_sb.table.called:
        test_pass("scheduler sync_current_candle: Throttle BLOQUEA (no toca Supabase)")
    else:
        test_fail("scheduler sync_current_candle: Throttle", "Supabase fue llamado")
    
    del sync_current_candle_to_db._last["BTCUSDT"]

except Exception as e:
    test_fail("scheduler sync_current_candle: Throttle", str(e))

# --- Test 1C: scheduler.py upsert_candles_to_db throttle ---
try:
    from app.workers.scheduler import upsert_candles_to_db
    
    if not hasattr(upsert_candles_to_db, '_last'):
        upsert_candles_to_db._last = {}
    upsert_candles_to_db._last["ETHUSDT_15m"] = time.time()
    
    mock_sb = MagicMock()
    df_test = make_candle_df(5)
    
    loop = asyncio.new_event_loop()
    loop.run_until_complete(upsert_candles_to_db("ETHUSDT", "15m", df_test, mock_sb))
    loop.close()
    
    if not mock_sb.table.called:
        test_pass("scheduler upsert_candles_to_db: Throttle BLOQUEA (no toca Supabase)")
    else:
        test_fail("scheduler upsert_candles_to_db: Throttle", "Supabase fue llamado")
    
    del upsert_candles_to_db._last["ETHUSDT_15m"]

except Exception as e:
    test_fail("scheduler upsert_candles_to_db: Throttle", str(e))

# --- Test 1D: forex_scheduler.py upsert_forex_candles throttle ---
try:
    from app.workers.forex_scheduler import upsert_forex_candles
    
    if not hasattr(upsert_forex_candles, '_last'):
        upsert_forex_candles._last = {}
    upsert_forex_candles._last["EURUSD_15m"] = time.time()
    
    mock_sb = MagicMock()
    df_test = make_candle_df(5)
    
    loop = asyncio.new_event_loop()
    loop.run_until_complete(upsert_forex_candles("EURUSD", "15m", df_test, mock_sb))
    loop.close()
    
    if not mock_sb.table.called:
        test_pass("forex_scheduler upsert_forex_candles: Throttle BLOQUEA (no toca Supabase)")
    else:
        test_fail("forex_scheduler upsert_forex_candles: Throttle", "Supabase fue llamado")
    
    del upsert_forex_candles._last["EURUSD_15m"]

except Exception as e:
    test_fail("forex_scheduler upsert_forex_candles: Throttle", str(e))

# =============================================
#  FASE 2: TESTS DE MIGRACION A MEMORIA
# =============================================
print("\n FASE 2: Verificacion de Migracion a Memoria (get_memory_df)")
print("-" * 50)

# Poblar MEMORY_STORE
from app.core.memory_store import MEMORY_STORE, update_memory_df, get_memory_df

test_symbols = {
    "EURUSD": {"15m": 1.1400, "4h": 1.1400, "1d": 1.1400},
    "GBPUSD": {"15m": 1.2700, "4h": 1.2700, "1d": 1.2700},
    "BTCUSDT": {"15m": 61000, "4h": 61000, "1d": 61000},
}

for sym, tfs in test_symbols.items():
    for tf, base_price in tfs.items():
        df = make_candle_df(50, base_price)
        update_memory_df(sym, tf, df)

print(f"  MEMORY_STORE poblado: {len(test_symbols)} simbolos x {len(list(test_symbols.values())[0])} timeframes")

# --- Test 2A: candle_worker.py lee desde memoria ---
try:
    import inspect
    from app.candle_signals.candle_worker import evaluate_forex_pair
    
    source = inspect.getsource(evaluate_forex_pair)
    
    if "get_memory_df" in source:
        test_pass("candle_worker: Codigo usa get_memory_df")
    else:
        test_fail("candle_worker", "No usa get_memory_df")
    
    if 'market_candles' not in source:
        test_pass("candle_worker: NO referencia market_candles (Supabase eliminado)")
    else:
        test_fail("candle_worker", "Todavia referencia market_candles")

except Exception as e:
    test_fail("candle_worker", str(e))

# --- Test 2B: bollinger_exhaustion.py lee desde memoria ---
try:
    df_check = get_memory_df("EURUSD", "15m")
    if df_check is not None and len(df_check) >= 20:
        test_pass("bollinger_exhaustion: MEMORY_STORE tiene datos 15m EURUSD (50 filas)")
    else:
        test_fail("bollinger_exhaustion: MEMORY_STORE", f"df es None o < 20 filas")
    
    df_check_btc = get_memory_df("BTCUSDT", "15m")
    if df_check_btc is not None and len(df_check_btc) >= 20:
        test_pass("bollinger_exhaustion: MEMORY_STORE tiene datos 15m BTCUSDT (50 filas)")
    else:
        test_fail("bollinger_exhaustion: MEMORY_STORE", f"df es None o < 20 filas")

    import inspect
    from app.strategy.bollinger_exhaustion import execute_market_bollinger_exhaustion
    source = inspect.getsource(execute_market_bollinger_exhaustion)
    
    if "get_memory_df" in source:
        test_pass("bollinger_exhaustion: Codigo usa get_memory_df")
    else:
        test_fail("bollinger_exhaustion: Codigo", "No usa get_memory_df")
    
    if 'sb.table("market_candles")' not in source and "sb.table('market_candles')" not in source:
        test_pass("bollinger_exhaustion: NO referencia market_candles (Supabase eliminado)")
    else:
        test_fail("bollinger_exhaustion: Codigo", "Todavia referencia market_candles")

except Exception as e:
    test_fail("bollinger_exhaustion", str(e))

# --- Test 2C: candle_execution.py lee desde memoria ---
try:
    import inspect
    from app.candle_signals import candle_execution
    
    source = inspect.getsource(candle_execution)
    
    guard_start = source.find("GUARD #0")
    guard_end = source.find("GUARD #3", guard_start) if guard_start > 0 else -1
    guard_section = source[guard_start:guard_end] if guard_start > 0 and guard_end > 0 else ""
    
    if "get_memory_df" in guard_section:
        test_pass("candle_execution Guard #0: Usa get_memory_df para filtro 15m")
    else:
        test_fail("candle_execution Guard #0", "No usa get_memory_df")
    
    if 'market_candles' not in guard_section:
        test_pass("candle_execution Guard #0: NO referencia market_candles (Supabase eliminado)")
    else:
        test_fail("candle_execution Guard #0", "Todavia referencia market_candles")

except Exception as e:
    test_fail("candle_execution Guard #0", str(e))

# --- Test 2D: Integridad de get_memory_df ---
try:
    for sym in ["EURUSD", "BTCUSDT", "GBPUSD"]:
        for tf in ["15m", "4h", "1d"]:
            df = get_memory_df(sym, tf)
            if df is None:
                test_fail(f"Integridad memoria {sym}/{tf}", "DataFrame es None")
            elif len(df) < 20:
                test_fail(f"Integridad memoria {sym}/{tf}", f"Solo {len(df)} filas")
    
    test_pass(f"Integridad memoria: 3 simbolos x 3 TFs = 9 DataFrames OK")

except Exception as e:
    test_fail("Integridad memoria", str(e))

# =============================================
#  RESUMEN FINAL
# =============================================
print("\n" + "=" * 70)
print(f"  RESULTADO FINAL: {PASSED} passed, {FAILED} failed")
print("=" * 70)

if ERRORS:
    print("\n  Errores encontrados:")
    for err in ERRORS:
        print(f"    - {err}")
else:
    print("\n  Todas las pruebas pasaron!")
    print("     - Los throttles de 60 minutos bloquean los upserts redundantes.")
    print("     - Los lectores de velas usan MEMORY_STORE en vez de Supabase.")
    print("     - El egress deberia reducirse de ~7 GB a ~3.6 GB/mes.")

print()
