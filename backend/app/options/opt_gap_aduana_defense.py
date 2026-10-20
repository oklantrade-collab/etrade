"""
eTrade v6.0 — ADUANA DEFENSIVE SHIELD (OPTIONS GAP RUNNER)
==========================================================
Módulo de protección, salidas y trailing ratchets para posiciones
de opciones (CALLs y PUTs) abiertas bajo la estrategia ADUANA_GAP_RUNNER.

Reglas Implementadas:
1. Hard Stop Loss en Prima (-35%): Fusible de seguridad absoluto ante colapso de IV o reversión.
2. Stall Guard por Theta Decay (20 min sin avance y prima <= -15%): Evita desangrado temporal.
3. Trailing Ratchet Tier 2 (PnL Prima >= +25%): Piso mínimo garantizado de +15% neto.
4. Trailing Ratchet Tier 3 (PnL Prima >= +50%): Blindaje del 70% de la ganancia máxima pico.
5. SL Dinámico Técnico por Subyacente: EMA9 de 15m con actualización monotónica.
6. Trailing Stop 1H Midpoint: Al 50% de la vela de 1H cerrada fuera de las Bandas de Bollinger.
7. Take Profit Parcial (50% contratos): En Upper 6 (CALL) o Lower 6 (PUT) con excepción Rocket Hold.
8. Take Profit Clímax Total (100% contratos): RSI 1H >= 85 (CALL) o RSI 1H <= 15 (PUT).
"""

from __future__ import annotations

import math
from typing import Dict, Any, Optional, Tuple
import pandas as pd

from app.core.logger import log_info, log_warning
from app.options.aduana_gap_runner_options import (
    evaluate_options_gap_aduana_exit,
    compute_rsi,
    compute_bollinger_bands,
    _safe_col
)

MODULE = "OPT_GAP_DEFENSE"


def evaluate_opt_gap_defense(
    position: Dict[str, Any],
    current_underlying_price: float,
    current_option_premium: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    position_age_minutes: float = 0.0,
    sipv_signal: Optional[str] = None
) -> Dict[str, Any]:
    """
    Función de entrada para la evaluación defensiva de una posición de Gap Runner en Opciones.
    Retorna un diccionario estructurado con la recomendación de salida o actualización de Stop Loss.
    """
    return evaluate_options_gap_aduana_exit(
        position=position,
        current_underlying_price=current_underlying_price,
        current_option_premium=current_option_premium,
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        position_age_minutes=position_age_minutes,
        sipv_signal=sipv_signal
    )
