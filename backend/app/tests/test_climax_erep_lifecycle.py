import os
import sys
import pytest
import pandas as pd
import numpy as np

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.strategy.virtual_sl_recovery import calculate_slv
from app.strategy.quantum_squeeze_hedge import (
    evaluate_fib_band_virtual_sl,
    scan_squeeze_opportunities,
)
from app.strategy.erep_recovery_engine import (
    evaluate_climax_ema_transition,
    evaluate_erep_entry_trigger,
)


def create_df_from_prices(prices, vol=100.0, step=0.2, spread=0.5):
    n = len(prices)
    opens = [p - step for p in prices]
    closes = list(prices)
    highs = [max(o, c) + spread for o, c in zip(opens, closes)]
    lows = [min(o, c) - spread for o, c in zip(opens, closes)]
    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [vol] * n
    })
    return df


# ============================================================================
# 1. MATHEMATICAL INVARIANT TESTS FOR calculate_slv
# ============================================================================

def test_calculate_slv_long_invariant():
    """
    Ensure SLV for LONG can NEVER be above entry price,
    even if the snapshot/band returns a value above entry.
    """
    entry_price = 2437.80
    corrupted_snap = {"lower_1": 2450.00, "atr": 5.0}
    res = calculate_slv(entry_price=entry_price, side="LONG", symbol="ETHUSDT", snap=corrupted_snap, market_type="crypto_futures")
    
    assert res is not None
    assert "slv_price" in res
    assert res["slv_price"] < entry_price, f"SLV {res['slv_price']} must be strictly below entry {entry_price} for LONG"
    assert res["source"] == "bounded_below_entry_long"


def test_calculate_slv_short_invariant():
    """
    Ensure SLV for SHORT can NEVER be below entry price,
    even if the snapshot/band returns a value below entry.
    """
    entry_price = 2437.80
    corrupted_snap = {"lower_1": 2400.00, "upper_1": 2410.00, "atr": 5.0}
    res = calculate_slv(entry_price=entry_price, side="SHORT", symbol="ETHUSDT", snap=corrupted_snap, market_type="crypto_futures")
    
    assert res is not None
    assert "slv_price" in res
    assert res["slv_price"] > entry_price, f"SLV {res['slv_price']} must be strictly above entry {entry_price} for SHORT"
    assert res["source"] == "bounded_above_entry_short"


# ============================================================================
# 2. VIRTUAL SL ISOLATION TESTS FOR CLIMAX POSITIONS
# ============================================================================

def test_evaluate_fib_band_virtual_sl_climax_long_isolated():
    """
    Climax / Lower6 positions must NOT be closed prematurely by fib_band_virtual_sl.
    It should return None (isolated from trend-continuation SL checks).
    """
    pos = {
        "id": "test_climax_long",
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry_price": 2437.80,
        "current_price": 2433.45,
        "rule_code": "Bb33_QSHR_CLIMAX_LOWER6_LONG",
        "erep_active": True,
        "structural_sl": 2400.00,
    }
    df_15m = create_df_from_prices([2440.0 - i * 0.5 for i in range(30)])

    result = evaluate_fib_band_virtual_sl(
        position=pos,
        df_15m=df_15m,
        current_price=2433.45,
        symbol="ETHUSDT"
    )
    assert result is None, f"Expected None (isolated) for Climax position, got {result}"


def test_evaluate_fib_band_virtual_sl_climax_short_isolated():
    """
    Climax / Upper6 SHORT positions must NOT be closed prematurely by fib_band_virtual_sl.
    It should return None (isolated).
    """
    pos = {
        "id": "test_climax_short",
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "entry_price": 60000.00,
        "current_price": 60200.00,
        "rule_code": "Bb33_QSHR_CLIMAX_UPPER6_SHORT",
        "erep_active": True,
        "structural_sl": 61500.00,
    }
    df_15m = create_df_from_prices([60000.0 + i * 10.0 for i in range(30)])

    result = evaluate_fib_band_virtual_sl(
        position=pos,
        df_15m=df_15m,
        current_price=60200.00,
        symbol="BTCUSDT"
    )
    assert result is None, f"Expected None (isolated) for Climax position, got {result}"


# ============================================================================
# 3. 3-STAGE CLIMAX EMA TRANSITION & SMART BREAKEVEN TESTS
# ============================================================================

def test_climax_transition_long_smart_breakeven_buffer():
    """
    Stage 1 with Smart BE:
    - If price gain is below +0.25% (e.g. 2438.50 vs 2437.80 is only +0.028%), do NOT move SL yet.
    - When price gain reaches >= +0.25% (e.g. 2445.00 is +0.295%), move SL to Breakeven.
    """
    pos = {
        "id": "pos_climax_1",
        "side": "LONG",
        "entry_price": 2437.80,
        "current_price": 2438.50,
        "sl_price": 2400.00,
        "rule_code": "Bb33_QSHR_CLIMAX_LOWER6_LONG",
        "be_activated": False,
        "partial_closed": False,
    }
    prices_5m = [2435.0] * 15 + [2436.0, 2436.5, 2437.0, 2437.5, 2438.5]
    df_5m = create_df_from_prices(prices_5m, step=0.2)
    df_5m.iloc[-1, df_5m.columns.get_loc('open')] = 2437.50
    df_5m.iloc[-1, df_5m.columns.get_loc('close')] = 2438.50

    prices_15m = [2455.0 - i * 0.8 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m)
    df_15m['basis'] = 2450.00

    # 1. Below 0.25% buffer -> Should NOT activate Breakeven
    action_early = evaluate_climax_ema_transition(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=2438.50,
        symbol="ETHUSDT",
        market_type="crypto_futures"
    )
    assert action_early is None, "Should not activate Breakeven before +0.25% gain is reached"

    # 2. At 2445.00 (+0.295% >= 0.25%) -> Should activate Breakeven
    df_5m.iloc[-1, df_5m.columns.get_loc('close')] = 2445.00
    action_buffered = evaluate_climax_ema_transition(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=2445.00,
        symbol="ETHUSDT",
        market_type="crypto_futures"
    )
    assert action_buffered is not None
    assert action_buffered["action"] == "adjust_sl_be"
    assert action_buffered["new_sl"] == 2437.80


def test_climax_transition_long_stage2_tp1_basis():
    """
    Stage 2: Price reaches or exceeds Basis (15m) -> Take partial profit 50%.
    """
    pos = {
        "id": "pos_climax_1",
        "side": "LONG",
        "entry_price": 2437.80,
        "current_price": 2450.00,
        "sl_price": 2437.80,
        "rule_code": "Bb33_QSHR_CLIMAX_LOWER6_LONG",
        "be_activated": True,
        "partial_closed": False,
    }
    prices_5m = [2440.0 + i * 0.5 for i in range(20)]
    df_5m = create_df_from_prices(prices_5m)

    prices_15m = [2445.0] * 30
    df_15m = create_df_from_prices(prices_15m)
    df_15m['basis'] = 2448.00  # Basis is 2448, current_price is 2450 >= Basis

    action = evaluate_climax_ema_transition(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=2450.00,
        symbol="ETHUSDT",
        market_type="crypto_futures"
    )
    assert action is not None
    assert action["action"] == "climax_tp_partial_basis"
    assert action["close_pct"] == 0.50


def test_climax_transition_long_stage3_macro_rotation():
    """
    Stage 3: Full 15m rotation (EMA3 > EMA9 > EMA20) -> Trend confirmation / runner.
    """
    pos = {
        "id": "pos_climax_1",
        "side": "LONG",
        "entry_price": 2437.80,
        "current_price": 2465.00,
        "sl_price": 2400.00,
        "rule_code": "Bb33_QSHR_CLIMAX_LOWER6_LONG",
        "be_activated": True,
        "partial_closed": True,
    }
    prices_5m = [2450.0 + i * 0.5 for i in range(20)]
    df_5m = create_df_from_prices(prices_5m)

    prices_15m = [2420.0 + i * 1.5 for i in range(40)]
    df_15m = create_df_from_prices(prices_15m)

    action = evaluate_climax_ema_transition(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=2465.00,
        symbol="ETHUSDT",
        market_type="crypto_futures"
    )
    assert action is not None
    assert action["action"] in ("confirm_trend", "climax_tp_full")
    if action["action"] == "confirm_trend":
        assert action["trend"] == "bullish"
        assert action["new_sl"] == 2437.80


def test_climax_transition_short_stages():
    """
    Verify symmetric stages for SHORT Climax (UPPER_6):
    Stage 1: 5m EMA3 < EMA9 with bearish bar & >= 5 pips profit in Forex -> SL to BE.
    Stage 2: Price drops below Basis (15m) -> Partial TP 50%.
    """
    pos = {
        "id": "pos_climax_short_1",
        "side": "SHORT",
        "entry_price": 1.1000,
        "current_price": 1.0990,
        "sl_price": 1.1050,
        "rule_code": "Bb33_QSHR_CLIMAX_UPPER6_SHORT",
        "be_activated": False,
        "partial_closed": False,
    }
    prices_5m = [1.1005] * 15 + [1.1000, 1.0998, 1.0995, 1.0992, 1.0990]
    df_5m = create_df_from_prices(prices_5m, step=-0.0002)
    df_5m.iloc[-1, df_5m.columns.get_loc('open')] = 1.0992
    df_5m.iloc[-1, df_5m.columns.get_loc('close')] = 1.0990

    prices_15m = [1.0920 + i * 0.0003 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m)
    df_15m['basis'] = 1.0950

    # 1.0990 vs 1.1000 is 10 pips gain (>= 5 pips buffer)
    action1 = evaluate_climax_ema_transition(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=1.0990,
        symbol="EURUSD",
        market_type="forex_futures"
    )
    assert action1 is not None
    assert action1["action"] == "adjust_sl_be"
    assert action1["new_sl"] == 1.1000

    # Stage 2: When price drops below Basis (15m)
    pos["be_activated"] = True
    action2 = evaluate_climax_ema_transition(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=1.0945,  # <= 1.0950 (Basis)
        symbol="EURUSD",
        market_type="forex_futures"
    )
    assert action2 is not None
    assert action2["action"] == "climax_tp_partial_basis"
    assert action2["close_pct"] == 0.50


# ============================================================================
# 4. PROACTIVE EREP ACCUMULATION / DCA TESTS (CRYPTO & FOREX)
# ============================================================================

def test_evaluate_erep_entry_trigger_crypto():
    """
    Test EREP P2 trigger on Crypto:
    LONG entry at 2437.80. If price drops >= 0.40% and reaches Lower 5,
    EREP P2 should trigger with 1.5x quantity to average down.
    """
    pos = {
        "id": "pos_crypto_erep",
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry_price": 2437.80,
        "size": 0.05,
        "erep_active": True,
        "erep_phase": 1,
        "erep_p1_price": 2437.80,
        "erep_q1": 0.05,
        "structural_sl": 2380.00,
    }
    current_price = 2420.00
    prices_5m = [2421.0 - i * 0.05 for i in range(20)]
    prices_5m[-1] = 2420.10
    df_5m = create_df_from_prices(prices_5m, step=0.1)
    
    prices_15m = [2430.0 - i * 0.3 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m, step=0.2)
    df_15m['lower_5'] = 2422.0

    trigger = evaluate_erep_entry_trigger(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=current_price,
        market_type="crypto_futures"
    )
    assert trigger is not None
    assert trigger["action"] == "execute_erep_p2"
    assert trigger["p2_size"] == pytest.approx(0.075, 0.001)  # 1.5x of 0.05
    assert trigger["p3_avg"] < 2437.80
    assert trigger["p3_avg"] > current_price


def test_evaluate_erep_entry_trigger_forex():
    """
    Test EREP P2 trigger on Forex:
    LONG entry at 1.0850. If price drops >= 25 pips (e.g. 1.0815 is 35 pips),
    EREP P2 should trigger.
    """
    pos = {
        "id": "pos_forex_erep",
        "symbol": "EURUSD",
        "side": "LONG",
        "entry_price": 1.0850,
        "size": 0.10,
        "erep_active": True,
        "erep_phase": 1,
        "erep_p1_price": 1.0850,
        "erep_q1": 0.10,
        "structural_sl": 1.0780,
    }
    current_price = 1.0815  # 35 pips drawdown (>= 25 pips)
    prices_5m = [1.0820 - i * 0.00002 for i in range(20)]
    prices_5m[-1] = 1.08160
    df_5m = create_df_from_prices(prices_5m, step=0.00005)

    prices_15m = [1.0840 - i * 0.0001 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m, step=0.0001)
    df_15m['lower_5'] = 1.0820

    trigger = evaluate_erep_entry_trigger(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=current_price,
        market_type="forex_futures"
    )
    assert trigger is not None
    assert trigger["action"] == "execute_erep_p2"
    assert trigger["p2_size"] >= 0.10
    assert trigger["p3_avg"] < 1.0850
    assert trigger["p3_avg"] > current_price


# ============================================================================
# 5. NUEVOS TESTS: CLÍMAX EN 5 MINUTOS CON FILTROS ANTI-PÉRDIDAS
# ============================================================================

def test_scan_climax_5m_lower6_long_with_filters():
    """
    Verifica que scan_squeeze_opportunities detecte Bb33_QSHR_CLIMAX_5M_LOWER6_LONG
    con size_factor=0.70 cuando se cumplen:
    - Toque de lower_6 en 5m
    - RSI 5m <= 32
    - Precio < Basis 15m
    - Absorción en mecha
    """
    # 5m bars: Touch of lower_6 with low RSI
    prices_5m = [2430.0 - i * 0.5 for i in range(25)]
    df_5m = create_df_from_prices(prices_5m, step=0.3)
    df_5m['lower_6'] = 2419.0
    df_5m['rsi'] = 28.0  # Oversold <= 32
    # Last bar touches lower_6 and leaves a lower wick
    df_5m.iloc[-1, df_5m.columns.get_loc('low')] = 2418.0
    df_5m.iloc[-1, df_5m.columns.get_loc('open')] = 2419.5
    df_5m.iloc[-1, df_5m.columns.get_loc('close')] = 2420.5

    # 15m bars: Basis is 2435.0 (above 2420.5), curva decreciente con expansión de bandas y RSI 15m sobrevendido
    prices_15m = [2500.0 - (i**1.2) * 0.6 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m)
    df_15m['basis_15m'] = 2435.0
    df_15m['lower_6'] = 2400.0  # 15m lower_6 is far below, so 15m trigger does NOT fire
    df_15m['rsi'] = 30.0  # Macro RSI oversold <= 36

    sig = scan_squeeze_opportunities('ETHUSDT', df_5m, df_15m, market_type='crypto_futures')
    assert sig is not None
    assert sig['rule_code'] == 'Bb33_QSHR_CLIMAX_5M_LOWER6_LONG'
    assert sig['side'] == 'long'
    assert sig['size_factor'] in (0.45, 0.70)
    assert sig['erep_eligible'] is True
    assert sig.get('sl_price') is not None and sig.get('sl_price') > 0
    assert sig.get('climax_slv') is not None


def test_scan_climax_5m_upper6_short_anti_macro_filter():
    """
    Verifica que el Filtro Anti-Tendencia Macro bloquee el SHORT en 5m cuando
    el marco de 15m está en rotación alcista confirmada (EMA3 > EMA9 > EMA20).
    """
    # 5m bars: Touch of upper_6 with high RSI
    prices_5m = [1.1000 + i * 0.0002 for i in range(25)]
    df_5m = create_df_from_prices(prices_5m, step=-0.0001, spread=0.0002)
    df_5m['upper_6'] = 1.1045
    df_5m['rsi'] = 75.0  # Overbought >= 68
    df_5m.iloc[-1, df_5m.columns.get_loc('high')] = 1.1050
    df_5m.iloc[-1, df_5m.columns.get_loc('open')] = 1.1048
    df_5m.iloc[-1, df_5m.columns.get_loc('close')] = 1.1042

    # 15m bars: Bullish rotation (EMA3 > EMA9 > EMA20)
    prices_15m = [1.0900 + i * 0.0006 for i in range(35)]
    df_15m = create_df_from_prices(prices_15m, step=0.0002, spread=0.0002)
    df_15m['basis_15m'] = 1.1000
    df_15m['upper_6'] = 1.1200  # 15m upper_6 not reached

    # Because 15m is in strong bull trend, 5m SHORT MUST BE BLOCKED!
    sig = scan_squeeze_opportunities('EURUSD', df_5m, df_15m, market_type='forex_futures')
    assert sig is None, "5m SHORT should be blocked when 15m is in strong bullish macro rotation"


# ============================================================================
# 6. TESTS DE FILTROS AVANZADOS: PENDIENTE EMA3, PENDIENTE BANDAS, CAPITULACIÓN
# ============================================================================

def test_indicators_v2_vectorized_fibonacci_zone():
    """
    Verifica que indicators_v2 calcule la zona fibonacci de forma verdaderamente
    vectorial e independiente por vela, y no copiando el valor de la última vela.
    """
    from app.analysis.indicators_v2 import calculate_all_indicators

    # Crear 60 velas con precio variable
    np.random.seed(42)
    closes = [2000.0 + np.sin(i / 3.0) * 100.0 for i in range(60)]
    df = pd.DataFrame({
        'open': closes,
        'high': [c + 5.0 for c in closes],
        'low': [c - 5.0 for c in closes],
        'close': closes,
        'volume': [100.0] * 60
    })

    df_res = calculate_all_indicators(df, cfg={'length': 10})
    zones = df_res['fibonacci_zone'].unique()
    # Debe contener múltiples zonas distintas, demostrando cálculo vectorial independiente
    assert len(zones) > 1, f"fibonacci_zone debe ser vectorial y tener múltiples valores, se obtuvo: {zones}"


def test_scan_climax_15m_blocked_by_ema3_freefall():
    """
    Verifica que una compra en LOWER_6 15m sea bloqueada si la EMA3 de 15m
    está en caída libre vertical (pendiente < -0.08 y sin giro 5m).
    """
    # 15m bars plunging hard: EMA3 falling sharply
    prices_15m = [2500.0 - i * 15.0 for i in range(25)]
    df_15m = create_df_from_prices(prices_15m, step=5.0)
    df_15m['lower_6'] = df_15m['close'] + 5.0  # Penetrated lower_6
    df_15m['basis_15m'] = 2500.0
    df_15m['atr'] = 10.0
    # No absorption, close <= open, ema3 plunging
    df_15m.iloc[-1, df_15m.columns.get_loc('open')] = prices_15m[-1] + 5.0
    df_15m.iloc[-1, df_15m.columns.get_loc('close')] = prices_15m[-1] - 5.0
    df_15m.iloc[-1, df_15m.columns.get_loc('low')] = prices_15m[-1] - 6.0

    # 5m bar also below ema3 5m
    prices_5m = [prices_15m[-1] - i * 2.0 for i in range(20)]
    df_5m = create_df_from_prices(prices_5m)

    sig = scan_squeeze_opportunities('ETHUSDT', df_5m, df_15m, market_type='crypto_futures')
    # Debe ser bloqueada porque la EMA3 cae en picada sin giro
    assert sig is None or sig.get('rule_code') != 'Bb33_QSHR_CLIMAX_LOWER6_LONG'


def test_scan_climax_15m_blocked_by_lower6_band_walking():
    """
    Verifica que la compra sea bloqueada si la banda lower_6 se está abriendo
    violentamente hacia abajo (l6_slope < -0.12).
    """
    prices_15m = [2450.0 - i * 4.0 for i in range(25)]
    df_15m = create_df_from_prices(prices_15m, step=1.0)
    df_15m['basis_15m'] = 2450.0
    df_15m['atr'] = 5.0
    # lower_6 collapsing rapidly: prev is 2360, curr is 2340 (slope = -20 / 5 = -4.0 < -0.12)
    df_15m['lower_6'] = 2360.0
    df_15m.iloc[-1, df_15m.columns.get_loc('lower_6')] = 2340.0
    df_15m.iloc[-1, df_15m.columns.get_loc('low')] = 2339.0

    prices_5m = [2350.0 - i * 0.5 for i in range(20)]
    df_5m = create_df_from_prices(prices_5m)

    sig = scan_squeeze_opportunities('ETHUSDT', df_5m, df_15m, market_type='crypto_futures')
    assert sig is None or sig.get('rule_code') != 'Bb33_QSHR_CLIMAX_LOWER6_LONG'


def test_scan_climax_blocked_by_insufficient_basis_distance_eurusd():
    """
    Verifica que el filtro de distancia mínima a Basis bloquee falsas señales
    cuando las bandas están comprimidas a menos de 15 pips en Forex (caso EURUSD).
    """
    # EURUSD in a tight 6-pip channel
    prices_15m = [1.1610 + i * 0.00005 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m, step=0.00002, spread=0.00005)
    df_15m['basis_15m'] = 1.1615
    df_15m['atr'] = 0.0004
    # lower_6 is at 1.1608 (only 7 pips from basis!)
    df_15m['lower_6'] = 1.1608
    df_15m.iloc[-1, df_15m.columns.get_loc('low')] = 1.1607
    df_15m.iloc[-1, df_15m.columns.get_loc('close')] = 1.1609

    prices_5m = [1.1610 for _ in range(20)]
    df_5m = create_df_from_prices(prices_5m, spread=0.00005)

    sig = scan_squeeze_opportunities('EURUSD', df_5m, df_15m, market_type='forex_futures')
    assert sig is None, "Debe ser bloqueado por bandas comprimidas (< 15 pips de distancia a Basis)"


def test_scan_climax_15m_returns_structural_sl():
    """
    Mandato de proteccion: Si el precio llego a LOWER_6 en 15m, entrar con Stop Loss estructural.
    Verifica que el signal retorne sl_price y structural_sl no nulos.
    """
    # 15m data touching lower_6 with absorption
    prices_15m = [2500.0 - (i**1.1) * 3.0 for i in range(25)]
    df_15m = create_df_from_prices(prices_15m, step=2.0)
    df_15m['basis_15m'] = 2500.0
    df_15m['atr'] = 10.0
    df_15m['lower_6'] = 2400.0
    df_15m['rsi'] = 30.0
    df_15m.iloc[-1, df_15m.columns.get_loc('low')] = 2395.0
    df_15m.iloc[-1, df_15m.columns.get_loc('open')] = 2405.0
    df_15m.iloc[-1, df_15m.columns.get_loc('close')] = 2410.0  # Green candle / absorption

    prices_5m = [2410.0 + i * 0.5 for i in range(20)]
    df_5m = create_df_from_prices(prices_5m)

    sig = scan_squeeze_opportunities('ETHUSDT', df_5m, df_15m, market_type='crypto_futures')
    assert sig is not None, "Debe generar señal Climax 15m"
    assert sig['rule_code'] == 'Bb33_QSHR_CLIMAX_LOWER6_LONG'
    assert sig['sl_price'] is not None and sig['sl_price'] > 0, "Climax 15m DEBE tener Stop Loss estructural"
    assert sig['structural_sl'] is not None


def test_scan_climax_5m_returns_structural_sl():
    """
    Mandato de proteccion: Operaciones Climax 5m tambien entran con Stop Loss estructural.
    """
    prices_5m = [2430.0 - i * 0.5 for i in range(25)]
    df_5m = create_df_from_prices(prices_5m, step=0.3)
    df_5m['lower_6'] = 2419.0
    df_5m['rsi'] = 28.0
    df_5m.iloc[-1, df_5m.columns.get_loc('low')] = 2418.0
    df_5m.iloc[-1, df_5m.columns.get_loc('open')] = 2419.5
    df_5m.iloc[-1, df_5m.columns.get_loc('close')] = 2420.5

    prices_15m = [2500.0 - (i**1.2) * 0.6 for i in range(30)]
    df_15m = create_df_from_prices(prices_15m)
    df_15m['basis_15m'] = 2435.0
    df_15m['lower_6'] = 2400.0
    df_15m['rsi'] = 30.0

    sig = scan_squeeze_opportunities('ETHUSDT', df_5m, df_15m, market_type='crypto_futures')
    assert sig is not None
    assert sig['rule_code'] == 'Bb33_QSHR_CLIMAX_5M_LOWER6_LONG'
    assert sig.get('sl_price') is not None and sig.get('sl_price') > 0, "Climax 5m DEBE tener Stop Loss estructural"
    assert sig.get('structural_sl') is not None


def test_evaluate_erep_dca_step_and_cluster_exit():
    """
    Verifica que evaluate_erep_dca_step realice compras escalonadas al cierre de 15m
    cuando el precio cae por debajo del precio promedio, hasta el límite de 3 compras,
    y que evaluate_erep_exit_trigger rescate la posición en breakeven.
    """
    from app.strategy.erep_recovery_engine import evaluate_erep_dca_step, evaluate_erep_exit_trigger

    pos = {
        'symbol': 'ETHUSDT',
        'side': 'LONG',
        'p1_price': 2400.0,
        'p1_qty': 1.0,
        'current_qty': 1.0,
        'avg_price': 2400.0,
        'erep_purchases_count': 0,
        'erep_phase': 1,
        'rule_code': 'Bb33_QSHR_CLIMAX_5M_LOWER6_LONG'
    }

    # Vela 1 de 15m cierra en 2380.0 (< avg_price 2400.0) -> Recompra Step #1
    c1 = {'close': 2380.0}
    step1 = evaluate_erep_dca_step(pos, c1, max_purchases=3)
    assert step1 is not None
    assert step1['step_number'] == 1
    assert step1['new_avg_price'] == 2390.0  # (2400*1 + 2380*1) / 2 = 2390.0
    assert step1['new_total_qty'] == 2.0

    # Aplicar Step 1
    pos['avg_price'] = step1['new_avg_price']
    pos['current_qty'] = step1['new_total_qty']
    pos['erep_purchases_count'] = 1
    pos['erep_phase'] = 2
    pos['erep_active'] = True

    # Vela 2 de 15m cierra en 2360.0 (< avg_price 2390.0) -> Recompra Step #2
    c2 = {'close': 2360.0}
    step2 = evaluate_erep_dca_step(pos, c2, max_purchases=3)
    assert step2 is not None
    assert step2['step_number'] == 2
    # Nuevo avg: (2390*2 + 2360*1) / 3 = 7140 / 3 = 2380.0
    assert step2['new_avg_price'] == 2380.0
    assert step2['new_total_qty'] == 3.0

    # Aplicar Step 2
    pos['avg_price'] = step2['new_avg_price']
    pos['current_qty'] = step2['new_total_qty']
    pos['erep_purchases_count'] = 2

    # Vela 3 de 15m cierra en 2350.0 (< avg_price 2380.0) -> Recompra Step #3 (Límite)
    c3 = {'close': 2350.0}
    step3 = evaluate_erep_dca_step(pos, c3, max_purchases=3)
    assert step3 is not None
    assert step3['step_number'] == 3

    # Aplicar Step 3
    pos['avg_price'] = step3['new_avg_price']
    pos['current_qty'] = step3['new_total_qty']
    pos['erep_purchases_count'] = 3

    # Vela 4 intenta recomprar, pero ya alcanzó el límite (max_purchases=3)
    c4 = {'close': 2330.0}
    step4 = evaluate_erep_dca_step(pos, c4, max_purchases=3)
    assert step4 is None, "No debe exceder el límite de compras EREP establecido"

    # Rebote del mercado hacia el precio promedio ponderado -> Rescate en Breakeven
    cluster_exit = evaluate_erep_exit_trigger(pos, current_price=pos['avg_price'])
    assert cluster_exit is not None
    assert cluster_exit['rule_code'] == 'Bb33_EREP_CLUSTER_EXIT'


