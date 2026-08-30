import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import pytest
except ImportError:
    pass

import pandas as pd
import numpy as np

from app.strategy.candle_momentum_guard import (
    should_allow_exit,
    get_ema20_slope_pct,
    get_ema3_slope_pct,
    get_ema_values,
    calculate_bollinger_bands,
)


def create_trend_dataframe(start_price: float, step: float, num_bars: int = 30) -> pd.DataFrame:
    """Crea un DataFrame simulando una tendencia constante."""
    prices = [start_price + (i * step) for i in range(num_bars)]
    return pd.DataFrame({
        'open': prices,
        'high': [p + 0.5 for p in prices],
        'low': [p - 0.5 for p in prices],
        'close': prices,
        'volume': [1000] * num_bars
    })


def test_long_strong_trend_blocks_exits():
    """
    Caso 1 (Como SOLUSDT hoy):
    Tendencia fuerte alcista en 15M (EMA3 > EMA9 > EMA20, EMA20 slope > +0.02%).
    5M también alcista (EMA3 > EMA9 > EMA20).
    PnL > 0.
    -> Debe BLOQUEAR salidas como hold_agresivo, early_profit_protect_ema_5m, ts_close.
    """
    df_15m = create_trend_dataframe(start_price=100.0, step=0.3, num_bars=35)
    df_5m = create_trend_dataframe(start_price=108.0, step=0.2, num_bars=35)
    current_price = float(df_15m['close'].iloc[-1])  # ~110.2

    position = {
        'id': 'test-pos-sol-long',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 103.94,
    }

    # 1.1 Max Holding
    allow_hold, msg_hold = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='hold_agresivo',
        market_type='crypto_futures'
    )
    assert allow_hold is False
    assert "MOMENTUM_GUARD BLOQUEA" in msg_hold

    # 1.2 Early Profit Protect 5M
    allow_epp, msg_epp = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='early_profit_protect_ema_5m',
        market_type='crypto_futures'
    )
    assert allow_epp is False

    # 1.5 Trailing Stop Prematuro
    allow_ts, _ = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='ts_close',
        market_type='crypto_futures'
    )
    assert allow_ts is False


def test_long_subcondition_111_5m_breakdown_allows_exit():
    """
    Sub-condición 1.1.1:
    15M sigue alcista macro, pero en 5M se confirma debilitamiento rápido (EMA3 < EMA9 < EMA20).
    -> Debe PERMITIR la salida.
    """
    df_15m = create_trend_dataframe(start_price=100.0, step=0.3, num_bars=35)
    # 5M con giro bajista reciente
    df_5m = create_trend_dataframe(start_price=115.0, step=-0.4, num_bars=35)
    current_price = float(df_15m['close'].iloc[-1])

    position = {
        'id': 'test-pos-sol-long',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 103.94,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='early_profit_protect_ema_5m',
        market_type='crypto_futures'
    )
    assert allow is True
    assert "Long 1.1.1" in msg


def test_long_subcondition_112_bollinger_exhaustion_allows_exit():
    """
    Sub-condición 1.1.2:
    15M: Close > Upper Bollinger y EMA3 gira a la baja (pendiente negativa).
    -> Debe PERMITIR la salida por agotamiento en techo.
    """
    # Crear serie con subida y retroceso en la última vela
    closes = [100.0 + i * 0.5 for i in range(30)]
    closes[-1] = 114.0  # Mechazo por encima de BB pero con caída
    closes[-2] = 116.0  # EMA3 girando hacia abajo

    df_15m = pd.DataFrame({'close': closes, 'open': closes, 'high': closes, 'low': closes, 'volume': [1000]*30})
    df_5m = create_trend_dataframe(start_price=110.0, step=0.1, num_bars=30)
    current_price = 117.0  # por encima de upper BB

    position = {
        'id': 'test-pos-long-bb',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 100.0,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='range_bollinger_touch_exit',
        market_type='crypto_futures'
    )
    assert allow is True
    assert "Long 1.1.2" in msg


def test_long_subcondition_113_compression_allows_exit():
    """
    Sub-condición 1.1.3:
    15M: Distancia entre EMA3 y EMA9 <= 0.05% (compresión inminente).
    -> Debe PERMITIR salida.
    """
    # 20 velas de tendencia seguidas de 15 velas planas para que EMA3 y EMA9 converjan a < 0.05%
    closes = [100.0 + (i * 0.2) for i in range(20)] + [104.0] * 15
    df_15m = pd.DataFrame({'close': closes, 'open': closes, 'high': closes, 'low': closes, 'volume': [1000]*len(closes)})
    df_5m = create_trend_dataframe(start_price=104.0, step=0.01, num_bars=30)
    current_price = 104.0

    position = {
        'id': 'test-pos-long-comp',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 100.0,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='hold_moderado',
        market_type='crypto_futures'
    )
    assert allow is True


def test_short_strong_downtrend_blocks_exits():
    """
    Caso 1 SHORT:
    15M fuertemente bajista (EMA3 < EMA9 < EMA20, EMA20 slope < -0.02%).
    5M también bajista. PnL > 0.
    -> Debe BLOQUEAR salidas de toma de ganancias prematura.
    """
    df_15m = create_trend_dataframe(start_price=100.0, step=-0.3, num_bars=35)
    df_5m = create_trend_dataframe(start_price=92.0, step=-0.2, num_bars=35)
    current_price = float(df_15m['close'].iloc[-1])  # ~89.8

    position = {
        'id': 'test-pos-eth-short',
        'symbol': 'ETHUSDT',
        'side': 'short',
        'entry_price': 98.0,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='hold_agresivo',
        market_type='crypto_futures'
    )
    assert allow is False
    assert "MOMENTUM_GUARD BLOQUEA" in msg


def test_anti_round_trip_protection():
    """
    Mejora 2: Protección Anti-Round Trip.
    Ganancia alta (+6.0% >= +4.0%), precio perfora por debajo de EMA9 15M.
    -> Debe PERMITIR salida inmediata para asegurar la mega-ganancia.
    """
    df_15m = create_trend_dataframe(start_price=100.0, step=0.3, num_bars=35)
    df_5m = create_trend_dataframe(start_price=108.0, step=0.2, num_bars=35)
    
    # Supongamos entrada a 100 y precio actual 106 (+6%), pero cayó por debajo de EMA9
    _, ema9_val, _ = get_ema_values(df_15m)
    current_price = ema9_val - 0.5  # Perfora EMA9

    position = {
        'id': 'test-pos-huge-profit',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 100.0,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        exit_rule_id='ts_close',
        market_type='crypto_futures'
    )
    assert allow is True
    assert "Anti-Round Trip" in msg


def test_anti_round_trip_tier2_sol_ada():
    """
    Propuesta 1: Anti-Round Trip para Altcoins (SOL/ADA) con umbral adaptativo (+1.8%).
    """
    df_15m = create_trend_dataframe(start_price=100.0, step=0.1, num_bars=35)
    _, ema9_val, _ = get_ema_values(df_15m)
    current_price = ema9_val - 0.2  # Perfora EMA9

    # Ganancia de +2.2% (mayor a +1.8% de Alts pero menor al +3.0% de BTC)
    position = {
        'id': 'test-pos-sol-tier2',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 100.0,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        exit_rule_id='hold_agresivo',
        market_type='crypto_futures'
    )
    assert allow is True
    assert "Anti-Round Trip" in msg


def test_rsi_divergence_detection():
    """
    Propuesta 5: Detección de Divergencia Regular Bajista en 15M (Precio sube, RSI baja).
    """
    from app.strategy.candle_momentum_guard import detect_rsi_divergence
    
    # Serie simulando subida inicial fuerte y subida posterior con menos fuerza
    p1 = [100.0 + i*1.0 for i in range(15)]       # Fuerte subida (RSI alto)
    p2 = [115.0 - i*0.2 for i in range(5)]        # Retroceso leve
    p3 = [114.0 + i*0.25 for i in range(10)]      # Nuevo máximo en precio con menor pendiente (RSI bajo)
    
    closes = p1 + p2 + p3
    df_15m = pd.DataFrame({'close': closes, 'volume': [1000]*len(closes)})
    
    has_div, msg = detect_rsi_divergence(df_15m, is_long=True, lookback=15)
    assert has_div is True
    assert "Divergencia Bajista" in msg


def test_macro_trend_gate_1h():
    """
    Propuesta 4: Filtro de Régimen Macro de 1 Hora (Macro Trend Gate).
    """
    from app.strategy.macro_filter import check_1h_macro_trend_gate

    # 1H con tendencia bajista clara
    df_1h_down = create_trend_dataframe(start_price=100.0, step=-0.5, num_bars=30)
    
    # Intentar entrar LONG en contra de la tendencia 1H
    allow_long, msg_long = check_1h_macro_trend_gate(df_1h_down, side='long', current_price=85.0)
    assert allow_long is False
    assert "MACRO_GATE_BLOCKED" in msg_long

    # Intentar entrar SHORT a favor de la tendencia 1H
    allow_short, msg_short = check_1h_macro_trend_gate(df_1h_down, side='short', current_price=85.0)
    assert allow_short is True


def test_weekend_close_forex_always_allowed():
    """
    Mejora 4: Weekend Close en Forex (2.5) tiene prioridad absoluta de seguridad.
    """
    df_15m = create_trend_dataframe(start_price=1.0800, step=0.0005, num_bars=35)
    df_5m = create_trend_dataframe(start_price=1.0900, step=0.0002, num_bars=35)

    position = {
        'id': 'test-pos-eurusd',
        'symbol': 'EURUSD',
        'side': 'long',
        'entry_price': 1.0820,
    }

    allow, msg = should_allow_exit(
        position=position,
        current_price=1.0950,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='weekend_close',
        market_type='forex_futures'
    )
    assert allow is True
    assert "Weekend Close" in msg


def test_rebote_traversal_guard():
    """
    Validar que las estrategias de REBOTE (AaReb_Traversal) bloquean salidas prematuras
    mientras el precio cruza el canal hacia la Banda Superior opuesta.
    """
    df_15m = create_trend_dataframe(start_price=90.0, step=0.4, num_bars=35)
    df_5m = create_trend_dataframe(start_price=95.0, step=-0.1, num_bars=35)
    current_price = 98.0  # Todavía no llega a Upper BB (104.0)

    position = {
        'id': 'test-pos-rebote',
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 92.0,
        'rule_code': 'AaReb_Traversal'
    }

    # Ruido en 5M normalmente permitiría salida en tendencia, pero para REBOTE debe bloquearse hasta tocar banda superior
    allow, msg = should_allow_exit(
        position=position,
        current_price=current_price,
        df_15m=df_15m,
        df_5m=df_5m,
        exit_rule_id='early_profit_protect_ema_5m',
        market_type='crypto_futures'
    )
    assert allow is False
    assert "LONG_REBOTE" in msg or "Rebote Traversal" in msg


if __name__ == "__main__":
    print("Ejecutando tests completos de Candle Momentum Guard v5.2 + Rebote...")
    test_long_strong_trend_blocks_exits()
    print("[PASS] test_long_strong_trend_blocks_exits")
    test_long_subcondition_111_5m_breakdown_allows_exit()
    print("[PASS] test_long_subcondition_111_5m_breakdown_allows_exit")
    test_long_subcondition_112_bollinger_exhaustion_allows_exit()
    print("[PASS] test_long_subcondition_112_bollinger_exhaustion_allows_exit")
    test_long_subcondition_113_compression_allows_exit()
    print("[PASS] test_long_subcondition_113_compression_allows_exit")
    test_short_strong_downtrend_blocks_exits()
    print("[PASS] test_short_strong_downtrend_blocks_exits")
    test_anti_round_trip_protection()
    print("[PASS] test_anti_round_trip_protection")
    test_rsi_divergence_detection()
    print("[PASS] test_rsi_divergence_detection")
    test_macro_trend_gate_1h()
    print("[PASS] test_macro_trend_gate_1h")
    test_weekend_close_forex_always_allowed()
    print("[PASS] test_weekend_close_forex_always_allowed")
    test_rebote_traversal_guard()
    print("[PASS] test_rebote_traversal_guard")
    print("\n>>> TODOS LOS TESTS DE GUARD Y REBOTE PASARON EXITOSAMENTE! <<<")
