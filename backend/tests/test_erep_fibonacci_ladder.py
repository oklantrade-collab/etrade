"""
Suite de Pruebas Unitarias: Motor EREP por Grados Fibonacci y Blindaje Estructural
eTrade v5.0 / v6.0
"""

import pytest
import pandas as pd
import numpy as np

from app.strategy.erep_manager import (
    get_fibonacci_erep_target,
    detect_p2_entry_signal,
    evaluate_erep_phase,
    EREP_CONFIG
)
from app.strategy.quantum_squeeze_hedge import scan_squeeze_opportunities


def test_fibonacci_ladder_long_targets():
    """Verifica la cascada de niveles Fibonacci para compras (LONG): LOWER_3 -> 4 -> 5 -> 6."""
    snap = {
        'basis': 100.0,
        'lower_1': 98.0,
        'lower_2': 96.0,
        'lower_3': 94.0,
        'lower_4': 92.0,
        'lower_5': 90.0,
        'lower_6': 88.0,
    }

    # Caso 1: Compra en LOWER_3 (94.0) -> P2 debe ser LOWER_4 (92.0)
    target_l3 = get_fibonacci_erep_target(entry_price=94.0, current_price=93.0, side='long', snap=snap)
    assert target_l3['target_band'] == 'lower_4'
    assert target_l3['target_price'] == 92.0
    assert target_l3['reached'] is False

    # Al caer a 91.50, alcanzó LOWER_4
    target_l3_reached = get_fibonacci_erep_target(entry_price=94.0, current_price=91.5, side='long', snap=snap)
    assert target_l3_reached['reached'] is True

    # Caso 2: Compra en LOWER_4 (92.0) -> P2 debe ser LOWER_5 (90.0)
    target_l4 = get_fibonacci_erep_target(entry_price=92.0, current_price=91.0, side='long', snap=snap)
    assert target_l4['target_band'] == 'lower_5'
    assert target_l4['target_price'] == 90.0

    # Caso 3: Compra en LOWER_5 (90.0) -> P2 debe ser LOWER_6 (88.0)
    target_l5 = get_fibonacci_erep_target(entry_price=90.0, current_price=89.0, side='long', snap=snap)
    assert target_l5['target_band'] == 'lower_6'
    assert target_l5['target_price'] == 88.0

    # Caso 4: Compra en LOWER_6 (88.0) -> Entrada Clímax sin banda inferior
    target_l6 = get_fibonacci_erep_target(entry_price=87.5, current_price=87.0, side='long', snap=snap)
    assert target_l6['is_climax_entry'] is True
    assert target_l6['target_band'] is None


def test_fibonacci_ladder_short_targets():
    """Verifica la cascada de niveles Fibonacci para ventas (SHORT): UPPER_3 -> 4 -> 5 -> 6."""
    snap = {
        'basis': 100.0,
        'upper_1': 102.0,
        'upper_2': 104.0,
        'upper_3': 106.0,
        'upper_4': 108.0,
        'upper_5': 110.0,
        'upper_6': 112.0,
    }

    # Caso 1: Venta en UPPER_3 (106.0) -> P2 debe ser UPPER_4 (108.0)
    target_u3 = get_fibonacci_erep_target(entry_price=106.0, current_price=107.0, side='short', snap=snap)
    assert target_u3['target_band'] == 'upper_4'
    assert target_u3['target_price'] == 108.0
    assert target_u3['reached'] is False

    # Al subir a 108.5, alcanzó UPPER_4
    target_u3_reached = get_fibonacci_erep_target(entry_price=106.0, current_price=108.5, side='short', snap=snap)
    assert target_u3_reached['reached'] is True

    # Caso 2: Venta en UPPER_4 (108.0) -> P2 debe ser UPPER_5 (110.0)
    target_u4 = get_fibonacci_erep_target(entry_price=108.0, current_price=109.0, side='short', snap=snap)
    assert target_u4['target_band'] == 'upper_5'
    assert target_u4['target_price'] == 110.0

    # Caso 3: Venta en UPPER_5 (110.0) -> P2 debe ser UPPER_6 (112.0)
    target_u5 = get_fibonacci_erep_target(entry_price=110.0, current_price=111.0, side='short', snap=snap)
    assert target_u5['target_band'] == 'upper_6'
    assert target_u5['target_price'] == 112.0

    # Caso 4: Venta en UPPER_6 (112.0) -> Entrada Clímax sin banda superior
    target_u6 = get_fibonacci_erep_target(entry_price=112.5, current_price=113.0, side='short', snap=snap)
    assert target_u6['is_climax_entry'] is True
    assert target_u6['target_band'] is None


def test_detect_p2_signal_by_fibonacci_ladder():
    """Valida que detect_p2_entry_signal detecte el toque de la banda de menor grado."""
    snap = {
        'price': 91.8,
        'lower_3': 94.0,
        'lower_4': 92.0,
        'lower_5': 90.0,
        'lower_6': 88.0,
    }
    # Entrada en 94.0 (LOWER_3), precio actual 91.8 (por debajo de LOWER_4 92.0)
    sig = detect_p2_entry_signal(
        df_15m=None,
        snap=snap,
        side='long',
        symbol='BTCUSDT',
        market_type='crypto_futures',
        entry_price=94.0
    )
    assert sig['has_signal'] is True
    assert any('fib_ladder_lower_4' in s['type'] for s in sig['signals'])


def test_catastrophic_breakdown_cut_in_erep():
    """Valida que una ruptura violenta bajo LOWER_6 - 1.2 ATR cierre incondicionalmente para evitar liquidación."""
    pos = {
        'id': 'pos-test-1',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'erep_phase': 2,
        'erep_p1_price': 100.0,
        'size': 1.0,
    }
    snap = {
        'lower_6': 88.0,
        'atr': 2.0, # Umbral límite: 88.0 - (1.2 * 2.0) = 85.60
    }
    # Precio actual en 84.0 (por debajo de 85.60 -> CRASH ESTRUCTURAL)
    res = evaluate_erep_phase(
        position=pos,
        current_price=84.0,
        snap=snap,
        df_15m=None,
        market_type='crypto_futures'
    )
    assert res['action'] == 'close_all'
    assert res['close_type'] == 'erep_structural_breakdown'
    assert 'QUIEBRE ESTRUCTURAL CATASTRÓFICO' in res['reason']


def test_recovery_success_phase3_breakeven_plus_fee():
    """Valida que tras P2, alcanzar el precio promedio + 0.35% cierre la canasta con ganancia neta."""
    pos = {
        'id': 'pos-test-2',
        'symbol': 'BTCUSDT',
        'side': 'long',
        'erep_phase': 3,
        'erep_p1_price': 100.0,
        'erep_p2_price': 90.0,
        'erep_p3_avg': 95.0, # Promedio de la canasta
        'size': 2.0,
    }
    snap = {
        'lower_6': 80.0,
        'atr': 2.0,
    }
    # Precio actual sube a 95.40 (+0.42% sobre 95.0, superior al 0.35% de comisiones cubiertas)
    df_15m = pd.DataFrame({'close': [94.0, 95.40]})
    res = evaluate_erep_phase(
        position=pos,
        current_price=95.40,
        snap=snap,
        df_15m=df_15m,
        market_type='crypto_futures'
    )
    assert res['action'] == 'close_all'
    assert 'recovery_success' in res['close_type']
