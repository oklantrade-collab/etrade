"""
eTrade v3 — Rule Engine
Evaluates trading rules (Aa11-Aa24, Bb11-Bb23) against current market conditions.
Rules are loaded from Supabase and can be edited by the user.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase

MODULE = "rule_engine"

# Maximum signal age in bars before it expires
MAX_SIGNAL_AGE_BARS = 3


def is_signal_valid(signal_bar_index: int, current_bar_index: int) -> bool:
    """Check if a PineScript signal is still valid (within MAX_SIGNAL_AGE_BARS)."""
    return (current_bar_index - signal_bar_index) <= MAX_SIGNAL_AGE_BARS


# ─── Default Rules (seeded to Supabase on first run) ───

DEFAULT_RULES = [
    # ═══ LONG RULES — RAMA A1 (EMA50 < EMA200, macro bajista) ═══
    {
        "id": 1003,
        "rule_code": "Aa11",
        "name": "EMA20+ADX bajo+DI cruce",
        "description": "EMA20 angle >= 0, ADX < 20, nivel_1_long, DI cross bullish. Baja confianza.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 3,
        "confidence": "medium_low",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema20_angle", "operator": ">=", "value": 0},
            {"indicator": "adx", "operator": "<", "value": 20},
            {"indicator": "ema20_phase", "operator": "==", "value": "nivel_1_long"},
            {"indicator": "di_cross_bullish", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Solo en régimen riesgo_medio o bajo_riesgo. Sizing: solo T1. (v2 forced)",
    },
    {
        "id": 1002,
        "rule_code": "Aa12",
        "name": "Rebote lower_5/6",
        "description": "Rebote desde zona de sobreventa extrema con confirmación de vela.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 2,
        "confidence": "medium",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "price_touched_lower_5_6", "operator": "==", "value": True},
            {"indicator": "reversal_confirmation_long", "operator": "==", "value": True},
            {"indicator": "bb_lower_slope_positive", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Rebote desde zona de sobreventa extrema. Funciona contra-tendencia. (v2 forced)",
    },
    {
        "id": 1001,
        "rule_code": "Aa13",
        "name": "EMA50 cruza basis (macro bajista)",
        "description": "EMA50 supera la VWMA (basis) en mercado macro bajista. Señal de cambio de tendencia local.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema4_cross_above_basis", "operator": "==", "value": True},
            {"indicator": "ema9_above_ema20", "operator": "==", "value": True},
            {"indicator": "ema3_above_ema9_5m", "operator": "==", "value": True},
            {"indicator": "ema9_above_ema20_5m", "operator": "==", "value": True},
            {"indicator": "bb_upper_5m_opens", "operator": "==", "value": True},
            {"indicator": "bb_lower_5m_opens", "operator": "==", "value": True},
            {"indicator": "bb_lower_slope_positive", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Al momento del cruce comprar al primer señal de Buy. (v2 forced)",
    },
    # ═══ LONG RULES — RAMA A2 (EMA50 > EMA200, macro alcista) ═══
    {
        "id": 1007,
        "rule_code": "Aa21",
        "name": "DIP Sniper EMA20 (15m)",
        "description": "Compra el retroceso exacto (LOW < EMA20 en 15m) mientras la tendencia corta sigue viva (EMA9 > EMA20).",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["bajo_riesgo", "riesgo_medio", "alto_riesgo"],
        "priority": 4,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema9_above_ema20_15m", "operator": "==", "value": True},
            {"indicator": "low_below_ema20_15m", "operator": "==", "value": True},
            {"indicator": "ema20_angle", "operator": ">=", "value": 0},
        ],
        "logic": "AND",
        "notes": "Estrategia Mean-Reversion de alta precisión. (v2 forced)",
    },
    {
        "id": 1005,
        "rule_code": "Aa22",
        "name": "EMA50 asc + sobre basis",
        "description": "EMA50 ascendente (ángulo positivo) y EMA50 sobre la VWMA.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 2,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema50_angle", "operator": ">=", "value": 0},
            {"indicator": "ema4_above_basis", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Tendencia macro y local alineadas. Sizing: T1. (v2 forced)",
    },
    {
        "id": 1006,
        "rule_code": "Aa23",
        "name": "EMA9+EMA50 ascendentes",
        "description": "EMA9 y EMA50 ambas ascendentes, ADX >= mínimo del régimen y precio no sobre-extendido (Zona Fib <= 3).",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 3,
        "confidence": "medium",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema9_angle", "operator": ">=", "value": 0},
            {"indicator": "ema50_angle", "operator": ">=", "value": 0},
            {"indicator": "adx_above_regime_min", "operator": "==", "value": True},
            {"indicator": "fib_zone_abs", "operator": "<=", "value": 3},
        ],
        "logic": "AND",
        "notes": "Sizing: T1. (v2 forced) Protegido contra sobre-extensión.",
    },
    {
        "id": 1004,
        "rule_code": "Aa24",
        "name": "EMA50+basis+Nivel1",
        "description": "EMA50 cruza arriba el basis y ema20_phase = nivel_1_long.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1, 2, 3],
        "conditions": [
            {"indicator": "ema4_cross_above_basis", "operator": "==", "value": True},
            {"indicator": "ema20_phase", "operator": "==", "value": "nivel_1_long"},
        ],
        "logic": "AND",
        "notes": "T1, habilitar T2/T3 con condición de precio decreciente. (v2 forced)",
    },
    {
        "id": 1011,
        "rule_code": "Aa25",
        "name": "Cruce EMA3 > EMA9 en Tendencia",
        "description": "Primer cruce al alza de EMA3 sobre EMA9 con filtro de tendencia (EMA9 > EMA20 o EMA3 > EMA20).",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1, 2, 3],
        "conditions": [
            {"indicator": "ema3_cross_ema9_up", "operator": "==", "value": True},
            {"indicator": "ema3_ema9_trend_ok", "operator": "==", "value": True},
            {"indicator": "ema3_above_ema9", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Nueva regla experimental de continuación.",
    },
    # ═══ SHORT RULES — RAMA B1 (EMA50 < EMA200, macro bajista) ═══
    {
        "id": 1010,
        "rule_code": "Bb11",
        "name": "SHORT ADX fuerte macro bajista",
        "description": "ADX > 40, ema20_phase nivel_2_short, -DI > +DI + 5.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 3,
        "confidence": "medium",
        "entry_trades": [1, 2],
        "conditions": [
            {"indicator": "ema20_angle", "operator": "<=", "value": 0},
            {"indicator": "adx", "operator": ">", "value": 40},
            {"indicator": "ema20_phase", "operator": "==", "value": "nivel_2_short"},
            {"indicator": "di_margin", "operator": ">", "value": 5},
        ],
        "logic": "AND",
        "notes": "Solo régimen riesgo_medio o bajo_riesgo. T1 + habilitar T2. (v2 forced)",
    },
    {
        "id": 1008,
        "rule_code": "Bb12",
        "name": "EMA50 cruza basis↓",
        "description": "EMA50 cruza hacia abajo el basis (VWMA). Short al primer Sell.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema4_cross_below_basis", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Comprar SHORT al primer Sell del PineScript. (v2 forced)",
    },
    {
        "id": 1009,
        "rule_code": "Bb13",
        "name": "EMA50≤basis+ADX+DI",
        "description": "EMA50 <= basis, ADX < 20, flat/nivel_1_short, DI cross bearish, ema20_angle <= 0.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 2,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema4_below_basis", "operator": "==", "value": True},
            {"indicator": "adx", "operator": "<", "value": 20},
            {"indicator": "ema20_phase", "operator": "in", "value": ["flat", "nivel_1_short"]},
            {"indicator": "di_cross_bearish", "operator": "==", "value": True},
            {"indicator": "ema20_angle", "operator": "<=", "value": 0},
        ],
        "logic": "AND",
        "notes": "Distribución temprana en consolidación. Sizing: T1. (v2 forced)",
    },
    # ═══ SHORT RULES — RAMA B2 (EMA50 > EMA200, macro alcista, contra-tendencia) ═══
    {
        "id": 1013,
        "rule_code": "Bb21",
        "name": "SHORT Bollinger lower (bajo riesgo)",
        "description": "ema20_angle <= 0, nivel_2_short, -DI > +DI + 10, close > banda inferior.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "below",
        "enabled": True,
        "regime_allowed": ["bajo_riesgo", "riesgo_medio", "alto_riesgo"],
        "priority": 3,
        "confidence": "medium",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema20_angle", "operator": "<=", "value": 0},
            {"indicator": "ema20_phase", "operator": "==", "value": "nivel_2_short"},
            {"indicator": "di_margin", "operator": ">", "value": 10},
            {"indicator": "close_above_lower", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Solo bajo_riesgo. RR mínimo 3.0. Sizing: T1. (v2 forced)",
    },
    {
        "id": 1011,
        "rule_code": "Bb22",
        "name": "Agotamiento upper_6",
        "description": "High cruzó upper_6 en últimas 2 velas + ADX > 40 + reversal confirmation.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "price_touched_upper_6", "operator": "==", "value": True},
            {"indicator": "adx", "operator": ">", "value": 40},
            {"indicator": "ema20_phase", "operator": "==", "value": "nivel_2_long"},
            {"indicator": "ema50_angle", "operator": "<=", "value": 0},
            {"indicator": "reversal_confirmation_short", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Solo T1, RR mínimo forzado 3.0. No requiere filtro de basis. (v2 forced)",
    },
    {
        "id": 1012,
        "rule_code": "Bb23",
        "name": "EMA50 cruza basis↓+EMA20",
        "description": "EMA50 cruza abajo el basis + ema20_angle <= 0.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "above",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 2,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema9_below_ema20", "operator": "==", "value": True},
            {"indicator": "ema20_angle", "operator": "<=", "value": 0},
            {"indicator": "rsi_14", "operator": ">=", "value": 40},
            {"indicator": "high_touched_ema20", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Estrategia Pullback Institucional: Toque a EMA20 en tendencia bajista con RSI sano. Aplica a Crypto y Forex.",
    },
    # ═══ HOT MOMENTUM RULES (15m) — RAMA HOT ═══
    {
        "id": 1018,
        "rule_code": "AaReb_5m",
        "name": "Cazador de Extremos LONG",
        "description": "Rebote fuerte en banda inferior, ignorando SAR y MTF",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 9,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "fib_zone", "operator": "<=", "value": -4},
            {"indicator": "sipv_buy", "operator": "==", "value": True},
            {"indicator": "ema3_slope_positive", "operator": "==", "value": True},
            {"indicator": "strong_contratrend_long", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Estrategia cazadora de pisos.",
    },
    {
        "id": 1016,
        "rule_code": "AaHot",
        "name": "HOT Momentum LONG",
        "description": "Entrada quirúrgica agresiva LONG con EMA ultra-cerca y ADX>22",
        "direction": "long",
        "market_type": ["forex_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 10,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "fresh_cross_long", "operator": "==", "value": True},
            {"indicator": "hot_mtf_ok_long", "operator": "==", "value": True},
            {"indicator": "bb_expanding_or_mtf_long_or_bottom", "operator": "==", "value": True},
            {"indicator": "bb_upper_slope_positive", "operator": "==", "value": True},
            {"indicator": "ema_alignment_long", "operator": "==", "value": True},
            {"indicator": "fib_zone", "operator": ">=", "value": -6},
            {"indicator": "fib_zone", "operator": "<=", "value": 2},
            {"indicator": "strong_contratrend_long", "operator": "==", "value": False},
            {"indicator": "rsi_ok_long", "operator": "==", "value": True},
            {"indicator": "not_in_ceiling", "operator": "==", "value": True},
            {"indicator": "ema_exhaustion", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Estrategia quirúrgica adaptada de Forex. Ultra rápida.",
    },
    {
        "id": 1017,
        "rule_code": "BbHot",
        "name": "HOT Momentum SHORT",
        "description": "Entrada quirúrgica agresiva SHORT con EMA ultra-cerca y ADX>22",
        "direction": "short",
        "market_type": ["forex_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 10,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "fresh_cross_short", "operator": "==", "value": True},
            {"indicator": "hot_mtf_ok_short", "operator": "==", "value": True},
            {"indicator": "bb_expanding_or_mtf_short_or_top", "operator": "==", "value": True},
            {"indicator": "bb_lower_slope_negative", "operator": "==", "value": True},
            {"indicator": "ema_alignment_short", "operator": "==", "value": True},
            {"indicator": "fib_zone", "operator": ">=", "value": -2},
            {"indicator": "fib_zone", "operator": "<=", "value": 6},
            {"indicator": "strong_contratrend_short", "operator": "==", "value": False},
            {"indicator": "rsi_ok_short", "operator": "==", "value": True},
            {"indicator": "not_in_floor", "operator": "==", "value": True},
            {"indicator": "ema_exhaustion", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Estrategia quirúrgica adaptada de Forex. Ultra rápida.",
    },
    {
        "id": 1040,
        "rule_code": "AaHotC",
        "name": "HOT Momentum LONG Cripto",
        "description": "Entrada quirúrgica agresiva LONG con EMA ultra-cerca y ADX>22",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 10,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "fresh_cross_long", "operator": "==", "value": True},
            {"indicator": "hot_mtf_ok_long", "operator": "==", "value": True},
            {"indicator": "bb_expanding_or_mtf_long_or_bottom", "operator": "==", "value": True},
            {"indicator": "bb_upper_slope_positive", "operator": "==", "value": True},
            {"indicator": "ema_alignment_long", "operator": "==", "value": True},
            {"indicator": "fib_zone", "operator": ">=", "value": -6},
            {"indicator": "fib_zone", "operator": "<=", "value": 2},
            {"indicator": "strong_contratrend_long", "operator": "==", "value": False},
            {"indicator": "rsi_ok_long", "operator": "==", "value": True},
            {"indicator": "not_in_ceiling", "operator": "==", "value": True},
            {"indicator": "ema_exhaustion", "operator": "==", "value": False},
            {"indicator": "ema9_above_ema20_15m", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Estrategia quirúrgica adaptada para Cripto con filtro EMA 15m.",
    },
    {
        "id": 1041,
        "rule_code": "BbHotC",
        "name": "HOT Momentum SHORT Cripto",
        "description": "Entrada quirúrgica agresiva SHORT con EMA ultra-cerca y ADX>22",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 10,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "fresh_cross_short", "operator": "==", "value": True},
            {"indicator": "hot_mtf_ok_short", "operator": "==", "value": True},
            {"indicator": "bb_expanding_or_mtf_short_or_top", "operator": "==", "value": True},
            {"indicator": "bb_lower_slope_negative", "operator": "==", "value": True},
            {"indicator": "ema_alignment_short", "operator": "==", "value": True},
            {"indicator": "fib_zone", "operator": ">=", "value": -2},
            {"indicator": "fib_zone", "operator": "<=", "value": 6},
            {"indicator": "strong_contratrend_short", "operator": "==", "value": False},
            {"indicator": "rsi_ok_short", "operator": "==", "value": True},
            {"indicator": "not_in_floor", "operator": "==", "value": True},
            {"indicator": "ema_exhaustion", "operator": "==", "value": False},
            {"indicator": "ema9_below_ema20_15m", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Estrategia quirúrgica adaptada para Cripto con filtro EMA 15m.",
    },
    {
        "id": 1019,
        "rule_code": "AaPullback",
        "name": "Pullback a EMA3 LONG",
        "description": "Entrada directa en retroceso a EMA3 con bandas abriéndose",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 9,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "pullback_long", "operator": "==", "value": True},
            {"indicator": "fib_zone", "operator": ">=", "value": -6},
            {"indicator": "fib_zone", "operator": "<=", "value": 3},
            {"indicator": "strong_contratrend_long", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Estrategia de continuación de momentum.",
    },
    {
        "id": 1020,
        "rule_code": "BbPullback",
        "name": "Pullback a EMA3 SHORT",
        "description": "Entrada directa en retroceso a EMA3 con bandas abriéndose",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_alto", "riesgo_medio", "bajo_riesgo"],
        "priority": 9,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "pullback_short", "operator": "==", "value": True},
            {"indicator": "fib_zone", "operator": ">=", "value": -3},
            {"indicator": "fib_zone", "operator": "<=", "value": 6},
            {"indicator": "strong_contratrend_short", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Estrategia de continuación de momentum.",
    },
    # ═══ SWING RULES (4h) — RAMA D ═══
    {
        "id": 1014,
        "rule_code": "Dd11",
        "name": "Swing LONG Extremo Banda",
        "description": "Precio tocó lower_6 o 5, market flat, orden LIMIT en target.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures", "options"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema20_phase", "operator": "in", "value": ["flat", "nivel_1_long", "nivel_1_short"]},
            {"indicator": "price_touched_lower_5_6", "operator": "==", "value": True},
            {"indicator": "ema_cross_long", "operator": "==", "value": True},
            {"indicator": "mtf_score", "operator": ">=", "value": -0.6},
            {"indicator": "reversal_confirmation_long", "operator": "==", "value": True},
            {"indicator": "strong_contratrend_long", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Swing trade; ejecuta LIMIT target.",
    },
    {
        "id": 1015,
        "rule_code": "Dd12",
        "name": "Swing SHORT Extremo Banda",
        "description": "Precio tocó upper_6 o 5, market flat, orden LIMIT en target.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures", "forex_futures", "options"],
        "ema50_vs_ema200": "any",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema20_phase", "operator": "in", "value": ["flat", "nivel_1_long", "nivel_1_short"]},
            {"indicator": "price_touched_upper_6", "operator": "==", "value": True},
            {"indicator": "ema_cross_short", "operator": "==", "value": True},
            {"indicator": "mtf_score", "operator": "<=", "value": 0.6},
            {"indicator": "reversal_confirmation_short", "operator": "==", "value": True},
            {"indicator": "strong_contratrend_short", "operator": "==", "value": False},
        ],
        "logic": "AND",
        "notes": "Swing trade; ejecuta LIMIT target.",
    },
    # ═══ SCALPING 5M RULES (Aa30 / Bb30) ═══
    {
        "id": 1030,
        "rule_code": "Aa30",
        "name": "LONG 5m Breakout Scalping",
        "description": "EMA Stack Alcista en 5m con confirmación de ángulos, MACRO alcista y expansión BB.",
        "direction": "long",
        "market_type": ["forex_futures", "stocks_spot"],
        "ema50_vs_ema200": "bullish",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo", "alto_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema3_above_ema9_5m", "operator": "==", "value": True},
            {"indicator": "ema9_above_ema20_5m", "operator": "==", "value": True},
            {"indicator": "ema9_above_ema20", "operator": "==", "value": True},
            {"indicator": "ema9_angle", "operator": ">", "value": 0},
            {"indicator": "ema20_angle", "operator": ">", "value": 0},
            {"indicator": "ema3_above_ema9_1h", "operator": "==", "value": True},
            {"indicator": "bb_upper_slope_positive", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Estrategia Fast Track de 5 minutos.",
    },
    {
        "id": 1031,
        "rule_code": "Bb30",
        "name": "SHORT 5m Breakout Scalping",
        "description": "EMA Stack Bajista en 5m con confirmación de ángulos, MACRO bajista y expansión BB.",
        "direction": "short",
        "market_type": ["forex_futures", "stocks_spot"],
        "ema50_vs_ema200": "bearish",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo", "alto_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema3_below_ema9_5m", "operator": "==", "value": True},
            {"indicator": "ema9_below_ema20_5m", "operator": "==", "value": True},
            {"indicator": "ema9_below_ema20", "operator": "==", "value": True},
            {"indicator": "ema9_angle", "operator": "<", "value": 0},
            {"indicator": "ema20_angle", "operator": "<", "value": 0},
            {"indicator": "ema3_below_ema9_1h", "operator": "==", "value": True},
            {"indicator": "bb_lower_slope_negative", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Estrategia Fast Track de 5 minutos.",
    },
    {
        "id": 1032,
        "rule_code": "Aa30C",
        "name": "LONG 5m Crypto Breakout",
        "description": "EMA Stack Alcista en 5m con confirmación de ADX para Crypto y expansión BB.",
        "direction": "long",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "bullish",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo", "alto_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema3_above_ema9_5m", "operator": "==", "value": True},
            {"indicator": "ema9_above_ema20_5m", "operator": "==", "value": True},
            {"indicator": "ema9_above_ema20", "operator": "==", "value": True},
            {"indicator": "ema9_angle", "operator": ">", "value": 0},
            {"indicator": "ema20_angle", "operator": ">", "value": 0},
            {"indicator": "adx", "operator": ">=", "value": 20},
            {"indicator": "bb_upper_slope_positive", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "notes": "Estrategia Fast Track de 5 minutos filtrada con ADX > 20.",
    },
    {
        "id": 1033,
        "rule_code": "Bb30C",
        "name": "SHORT 5m Crypto Breakout",
        "description": "EMA Stack Bajista en 5m con confirmación de ADX para Crypto.",
        "direction": "short",
        "market_type": ["crypto_spot", "crypto_futures"],
        "ema50_vs_ema200": "bearish",
        "enabled": True,
        "regime_allowed": ["riesgo_medio", "bajo_riesgo", "alto_riesgo"],
        "priority": 1,
        "confidence": "high",
        "entry_trades": [1],
        "conditions": [
            {"indicator": "ema3_below_ema9_5m", "operator": "==", "value": True},
            {"indicator": "ema9_below_ema20_5m", "operator": "==", "value": True},
            {"indicator": "ema9_below_ema20", "operator": "==", "value": True},
            {"indicator": "ema9_angle", "operator": "<", "value": 0},
            {"indicator": "ema20_angle", "operator": "<", "value": 0},
            {"indicator": "adx", "operator": ">=", "value": 20},
        ],
        "logic": "AND",
        "notes": "Estrategia Fast Track de 5 minutos filtrada con ADX > 20.",
    },
]


def evaluate_rule_conditions(
    rule: dict,
    market_data: dict,
) -> bool:
    """
    Evaluate all conditions of a single rule against current market data.

    Parameters
    ----------
    rule : rule dict with 'conditions' and 'logic' keys
    market_data : dict with all indicator values calculated from the pipeline

    Returns
    -------
    True if the rule conditions are met
    """
    conditions = rule.get("conditions", [])
    logic = rule.get("logic", "AND")

    if not conditions:
        return False

    results = []
    for cond in conditions:
        indicator = cond["indicator"]
        operator = cond["operator"]
        expected = cond["value"]

        actual = market_data.get(indicator)
        if actual is None:
            results.append(False)
            continue

        result = _evaluate_condition(actual, operator, expected)
        results.append(result)

    if logic == "AND":
        return all(results)
    elif logic == "OR":
        return any(results)
    return False


def _evaluate_condition(actual, operator: str, expected) -> bool:
    """Evaluate a single condition."""
    try:
        if operator == "==":
            return actual == expected
        elif operator == "!=":
            return actual != expected
        elif operator == ">":
            return float(actual) > float(expected)
        elif operator == ">=":
            return float(actual) >= float(expected)
        elif operator == "<":
            return float(actual) < float(expected)
        elif operator == "<=":
            return float(actual) <= float(expected)
        elif operator == "in":
            return actual in expected
        elif operator == "not_in":
            return actual not in expected
        else:
            return False
    except (TypeError, ValueError):
        return False


def build_market_data_dict(
    df: pd.DataFrame,
    fib_levels: dict,
    regime: dict,
) -> dict:
    """
    Build the market_data dict used by the rule engine from the indicator DataFrame.

    Parameters
    ----------
    df : DataFrame with all indicators calculated
    fib_levels : dict from extract_fib_levels()
    regime : dict from classify_market_risk()

    Returns
    -------
    dict with all indicator values needed for rule evaluation
    """
    last = df.iloc[-1]
    adx_min = regime.get("active_params", {}).get("adx_min", 20)

    adx_val = float(last.get("adx", 0)) if pd.notna(last.get("adx")) else 0.0
    adx_floor_ok = adx_val >= 15

    data = {
        # EMA angles
        "ema9_angle": float(last.get("ema9_angle", 0)) if pd.notna(last.get("ema9_angle")) else 0.0,
        "ema20_angle": float(last.get("ema20_angle", 0)) if pd.notna(last.get("ema20_angle")) else 0.0,
        "ema50_angle": float(last.get("ema50_angle", 0)) if pd.notna(last.get("ema50_angle")) else 0.0,
        # ADX
        "adx": float(last.get("adx", 0)) if pd.notna(last.get("adx")) else 0.0,
        "adx_above_regime_min": float(last.get("adx", 0)) >= adx_min if pd.notna(last.get("adx")) else False,
        
        # Nuevos controles PULLBACK (Agregados vía UI conditions)
        "rsi_14": float(last.get("rsi1", last.get("rsi_14", 50.0))) if pd.notna(last.get("rsi1", last.get("rsi_14"))) else 50.0,
        "high_touched_ema20": float(last.get("high", 0)) >= float(last.get("ema3", last.get("ema_20", 999999))) if pd.notna(last.get("high")) else False,
        "ema9_below_ema20": float(last.get("ema2", last.get("ema_9", 0))) < float(last.get("ema3", last.get("ema_20", 0))) if pd.notna(last.get("ema2")) else False,
        "ema3_above_ema9": float(last.get("ema1", last.get("ema_3", 0))) > float(last.get("ema2", last.get("ema_9", 0))) if pd.notna(last.get("ema1", last.get("ema_3"))) else False,
        "ema9_above_ema20": float(last.get("ema2", last.get("ema_9", 0))) > float(last.get("ema3", last.get("ema_20", 0))) if pd.notna(last.get("ema2", last.get("ema_9"))) else False,
        "ema3_below_ema9": float(last.get("ema1", last.get("ema_3", 0))) < float(last.get("ema2", last.get("ema_9", 0))) if pd.notna(last.get("ema1", last.get("ema_3"))) else False,

        # 5m indicators injected from scheduler
        "ema3_above_ema9_5m": float(last.get("ema3_5m", 0)) > float(last.get("ema9_5m", 0)) if pd.notna(last.get("ema3_5m")) else False,
        "ema9_above_ema20_5m": float(last.get("ema9_5m", 0)) > float(last.get("ema20_5m", 0)) if pd.notna(last.get("ema9_5m")) else False,
        "ema3_below_ema9_5m": float(last.get("ema3_5m", 0)) < float(last.get("ema9_5m", 0)) if pd.notna(last.get("ema3_5m")) else False,
        "ema9_below_ema20_5m": float(last.get("ema9_5m", 0)) < float(last.get("ema20_5m", 0)) if pd.notna(last.get("ema9_5m")) else False,
        "bb_upper_5m_opens": bool(last.get("bb_upper_5m_opens", False)),
        "bb_lower_5m_opens": bool(last.get("bb_lower_5m_opens", False)),
        
        # DI
        "plus_di": float(last.get("plus_di", 0)) if pd.notna(last.get("plus_di")) else 0.0,
        "minus_di": float(last.get("minus_di", 0)) if pd.notna(last.get("minus_di")) else 0.0,
        "di_cross_bullish": bool(last.get("di_cross_bullish", False)),
        "di_cross_bearish": bool(last.get("di_cross_bearish", False)),
        "di_margin": float(last.get("minus_di", 0)) - float(last.get("plus_di", 0)),
        # MTF Trends
        "mtf_4h_trend": str(last.get("mtf_4h_trend", "neutral")),
        "mtf_1d_trend": str(last.get("mtf_1d_trend", "neutral")),
        # EMA20 phase
        "ema20_phase": str(last.get("ema20_phase", "flat")),
        # EMA crosses
        "ema4_cross_above_basis": bool(last.get("ema4_cross_above_basis", False)),
        "ema4_cross_below_basis": bool(last.get("ema4_cross_below_basis", False)),
        "ema4_above_basis": float(last.get("ema4", 0)) > float(last.get("basis", 0)) if pd.notna(last.get("ema4")) and pd.notna(last.get("basis")) else False,
        "ema4_below_basis": float(last.get("ema4", 0)) < float(last.get("basis", 0)) if pd.notna(last.get("ema4")) and pd.notna(last.get("basis")) else False,
        # Fibonacci zones
        "fib_zone": fib_levels.get("zone", 0),
        "fib_zone_abs": abs(fib_levels.get("zone", 0)),
        "close_near_basis": (
            float(last["close"]) <= float(last.get("basis", 0)) * 1.005
            if pd.notna(last.get("basis"))
            else False
        ),
        # Price touching zones (lookback 3 bars)
        "price_touched_lower_5_6": _price_touched_lower_zones(df),
        "price_touched_upper_6": _price_touched_upper_6(df),
        # Reversal confirmations (SIPV equivalent)
        "reversal_confirmation_long": bool(
            last.get("is_dragonfly", False)
            or last.get("low_higher_than_prev", False)
            or last.get("is_hammer", False)
            or last.get("is_bullish_engulfing", False)
            or last.get("is_doji", False)
        ),
        "reversal_confirmation_short": bool(
            last.get("is_gravestone", False)
            or (last.get("is_red_candle", False) and fib_levels.get("zone", 0) >= 5)
            or last.get("high_lower_than_prev", False)
            or last.get("is_bearish_engulfing", False)
            or last.get("is_doji", False)
        ),
        # Volume
        "vol_entry_ok": bool(last.get("vol_entry_ok", False)),
        "vol_decreasing": bool(last.get("vol_decreasing", False)),
        "vol_increasing": bool(last.get("vol_increasing", False)),
        "spike_detected": bool(last.get("spike_detected", False)),
        "spike_ratio": float(last.get("spike_ratio", 0.0)),
        # Variables para Aa_HOT / Bb_HOT
        "adx_floor_ok": adx_floor_ok,
        "sar_15m_ok_long": int(last.get("sar_trend", 0)) > 0 if pd.notna(last.get("sar_trend")) else False,
        "sar_15m_ok_short": int(last.get("sar_trend", 0)) < 0 if pd.notna(last.get("sar_trend")) else False,
        "bb_expanding": bool(last.get("bb_expanding", False)),
    }

    ema3 = float(last.get("ema1", last.get("ema_3", 0))) if pd.notna(last.get("ema1")) or pd.notna(last.get("ema_3")) else 0.0
    ema9 = float(last.get("ema2", last.get("ema_9", 0))) if pd.notna(last.get("ema2")) or pd.notna(last.get("ema_9")) else 0.0
    ema_dist_pct = abs(ema3 - ema9) / ema9 * 100 if ema9 > 0 else 100
    ema_close_enough = ema_dist_pct <= 0.05
    ema_close_enough_03 = ema_dist_pct <= 0.03
    mtf_score = float(last.get("mtf_score", 0)) if pd.notna(last.get("mtf_score")) else 0.0

    bb_exp = bool(last.get("bb_expanding", False))
    ema_exhaustion = (ema_dist_pct > 0.15) and not bb_exp

    high_price = float(last.get("high", 0)) if pd.notna(last.get("high")) else 0.0
    low_price = float(last.get("low", 0)) if pd.notna(last.get("low")) else 0.0
    upper_2 = float(last.get("upper_2", 99999)) if pd.notna(last.get("upper_2")) else 99999.0
    lower_2 = float(last.get("lower_2", 0)) if pd.notna(last.get("lower_2")) else 0.0

    rsi_14_val = 50.0
    if len(df) >= 14:
        from ta.momentum import RSIIndicator
        close_series = pd.to_numeric(df["close"], errors="coerce")
        rsi_14_val = float(RSIIndicator(close=close_series, window=14).rsi().iloc[-1])

    # V9: Cross Age — cuantas velas de 15m desde el ultimo cruce EMA3/EMA9
    ema3_cross_age = 999
    ema_col1 = "ema1" if "ema1" in df.columns else "ema_3"
    ema_col2 = "ema2" if "ema2" in df.columns else "ema_9"
    if ema_col1 in df.columns and ema_col2 in df.columns and len(df) >= 5:
        ema3_s = pd.to_numeric(df[ema_col1], errors="coerce")
        ema9_s = pd.to_numeric(df[ema_col2], errors="coerce")
        for i in range(len(ema3_s) - 1, 0, -1):
            if pd.notna(ema3_s.iloc[i]) and pd.notna(ema9_s.iloc[i]) and pd.notna(ema3_s.iloc[i-1]) and pd.notna(ema9_s.iloc[i-1]):
                curr_above = ema3_s.iloc[i] > ema9_s.iloc[i]
                prev_above = ema3_s.iloc[i-1] > ema9_s.iloc[i-1]
                if curr_above != prev_above:
                    ema3_cross_age = len(ema3_s) - 1 - i
                    break

    # V9: Slope — pendiente del EMA3 (ultimas 3 velas)
    ema3_slope = 0.0
    ema3_slope_prev = 0.0
    if ema_col1 in df.columns and len(df) >= 3:
        ema3_s = pd.to_numeric(df[ema_col1], errors="coerce")
        if pd.notna(ema3_s.iloc[-1]) and pd.notna(ema3_s.iloc[-2]) and pd.notna(ema3_s.iloc[-3]):
            ema3_slope = float(ema3_s.iloc[-1] - ema3_s.iloc[-2])
            ema3_slope_prev = float(ema3_s.iloc[-2] - ema3_s.iloc[-3])

    # V9: Fresh cross conditions (cross age ≤3 OR accelerating slope)
    fresh_cross_long_by_age = (ema3_cross_age <= 3) and (ema3 > ema9)
    slope_entry_long = (ema3_slope > 0) and (ema3_slope > ema3_slope_prev) and (ema3 > ema9)
    fresh_cross_short_by_age = (ema3_cross_age <= 3) and (ema3 < ema9)
    slope_entry_short = (ema3_slope < 0) and (ema3_slope < ema3_slope_prev) and (ema3 < ema9)

    ema20 = float(last.get("ema3", last.get("ema_20", 0))) if pd.notna(last.get("ema3")) or pd.notna(last.get("ema_20")) else 0.0
    ema50 = float(last.get("ema4", last.get("ema_50", 0))) if pd.notna(last.get("ema4")) or pd.notna(last.get("ema_50")) else 0.0
    
    bb_upper_slope_positive = False
    bb_lower_slope_negative = False
    bb_lower_slope_positive = False
    bb_upper_col = "bb_upper" if "bb_upper" in df.columns else ("upper_6" if "upper_6" in df.columns else None)
    bb_lower_col = "bb_lower" if "bb_lower" in df.columns else ("lower_6" if "lower_6" in df.columns else None)
    if bb_upper_col and len(df) >= 2:
        bb_upper_s = pd.to_numeric(df[bb_upper_col], errors="coerce")
        if pd.notna(bb_upper_s.iloc[-1]) and pd.notna(bb_upper_s.iloc[-2]):
            bb_upper_slope_positive = bb_upper_s.iloc[-1] > bb_upper_s.iloc[-2]
    if bb_lower_col and len(df) >= 3:
        bb_lower_s = pd.to_numeric(df[bb_lower_col], errors="coerce")
        if pd.notna(bb_lower_s.iloc[-1]) and pd.notna(bb_lower_s.iloc[-2]) and pd.notna(bb_lower_s.iloc[-3]):
            bb_lower_slope_negative = bb_lower_s.iloc[-1] < bb_lower_s.iloc[-2]
            bb_lower_slope_positive = (bb_lower_s.iloc[-1] >= bb_lower_s.iloc[-2]) and (bb_lower_s.iloc[-2] >= bb_lower_s.iloc[-3])

    ema3_ema9_trend_ok = (ema9 > ema20) or (ema3 > ema20)
    
    ema3_cruce_up = False
    if ema_col1 in df.columns and ema_col2 in df.columns and len(df) >= 5:
        ema3_s = pd.to_numeric(df[ema_col1], errors="coerce")
        ema9_s = pd.to_numeric(df[ema_col2], errors="coerce")
        # 3-candle lookback crossover check
        for i in range(1, 4):
            idx = -i
            if pd.notna(ema3_s.iloc[idx]) and pd.notna(ema9_s.iloc[idx]) and pd.notna(ema3_s.iloc[idx-1]) and pd.notna(ema9_s.iloc[idx-1]):
                curr_above = ema3_s.iloc[idx] > ema9_s.iloc[idx]
                prev_above = ema3_s.iloc[idx-1] > ema9_s.iloc[idx-1]
                if curr_above and not prev_above:
                    ema3_cruce_up = True
                    break

    data.update({
        "ema_cross_short": (ema3 < ema9) or ema_close_enough,
        "ema_cross_long": (ema3 > ema9) or ema_close_enough,
        "ema_cross_short_hot": (ema3 < ema9) or ema_close_enough_03,
        "ema_cross_long_hot": (ema3 > ema9) or ema_close_enough_03,
        "fresh_cross_long": fresh_cross_long_by_age or slope_entry_long,
        "fresh_cross_short": fresh_cross_short_by_age or slope_entry_short,
        "ema3_slope_positive": ema3_slope >= 0,
        
        "sipv_buy": bool(
            last.get("is_dragonfly", False)
            or last.get("low_higher_than_prev", False)
            or last.get("is_hammer", False)
            or last.get("is_bullish_engulfing", False)
            or last.get("is_doji", False)
        ),
        "sipv_sell": bool(
            last.get("is_gravestone", False)
            or last.get("high_lower_than_prev", False)
            or last.get("is_bearish_engulfing", False)
            or last.get("is_doji", False)
        ),

        "bb_expanding_or_mtf_long": bb_exp or mtf_score >= 0.5,
        "bb_expanding_or_mtf_short": bb_exp or mtf_score <= -0.5,
        "bb_expanding_or_mtf_long_or_bottom": bb_exp or mtf_score >= 0.5 or (fib_levels.get("zone", 0) <= -4),
        "bb_expanding_or_mtf_short_or_top": bb_exp or mtf_score <= -0.5 or (fib_levels.get("zone", 0) >= 4),
        "mtf_score": mtf_score,
        "hot_mtf_ok_long": (mtf_score > -0.4) if (fib_levels.get("zone", 0) <= -4) else (mtf_score > 0),
        "hot_mtf_ok_short": (mtf_score < 0.4) if (fib_levels.get("zone", 0) >= 4) else (mtf_score < 0),
        "hot_sar_ok_long": True if (fib_levels.get("zone", 0) <= -4) else (int(last.get("sar_trend", 0)) > 0 if pd.notna(last.get("sar_trend")) else False),
        "hot_sar_ok_short": True if (fib_levels.get("zone", 0) >= 4) else (int(last.get("sar_trend", 0)) < 0 if pd.notna(last.get("sar_trend")) else False),
        "strong_contratrend_long": float(last.get("adx", 0)) > 35 and mtf_score <= -0.5,
        "strong_contratrend_short": float(last.get("adx", 0)) > 35 and mtf_score >= 0.5,
        "rsi_ok_long": rsi_14_val <= 65,
        "rsi_ok_short": rsi_14_val >= 35,
        "not_in_ceiling": float(last.get("close", 0)) <= upper_2 if upper_2 > 0 else True,
        "not_in_floor": float(last.get("close", 0)) >= lower_2 if lower_2 > 0 else True,
        "close_below_upper": float(last["close"]) < upper_2 if upper_2 > 0 else True,
        "close_above_lower": float(last["close"]) > lower_2 if lower_2 > 0 else True,
        "ema_exhaustion": ema_exhaustion,
        "ema3_cross_ema9_up": ema3_cruce_up,
        "ema3_ema9_trend_ok": ema3_ema9_trend_ok,
        "pullback_long": bool(
            bb_exp 
            and (ema3 > ema9) 
            and (low_price <= ema3 * 1.002) 
            and (float(last["close"]) >= ema3 * 0.998)
        ),
        "pullback_short": bool(
            bb_exp 
            and (ema3 < ema9) 
            and (high_price >= ema3 * 0.998) 
            and (float(last["close"]) <= ema3 * 1.002)
        ),
        "bb_upper_slope_positive": bb_upper_slope_positive,
        "bb_lower_slope_negative": bb_lower_slope_negative,
        "bb_lower_slope_positive": bb_lower_slope_positive,
        "ema_alignment_long": (ema3 > ema9) and (ema9 > ema20),
        "ema_alignment_short": (ema3 < ema9) and (ema9 < ema20) and (ema20 < ema50),
    })

    return data


def _price_touched_lower_zones(df: pd.DataFrame, lookback: int = 3) -> bool:
    """Check if price touched lower_5 or lower_6 in last N candles."""
    for i in range(lookback):
        idx = -(i + 1)
        if idx < -len(df):
            break
        row = df.iloc[idx]
        low = float(row["low"])
        lower_5 = float(row.get("lower_5", 0)) if pd.notna(row.get("lower_5")) else None
        lower_6 = float(row.get("lower_6", 0)) if pd.notna(row.get("lower_6")) else None
        if lower_5 and low <= lower_5:
            return True
        if lower_6 and low <= lower_6:
            return True
    return False


def _price_touched_upper_6(df: pd.DataFrame, lookback: int = 2) -> bool:
    """Check if high touched upper_6 in last N candles."""
    for i in range(lookback):
        idx = -(i + 1)
        if idx < -len(df):
            break
        row = df.iloc[idx]
        high = float(row["high"])
        upper_6 = float(row.get("upper_6", 0)) if pd.notna(row.get("upper_6")) else None
        if upper_6 and high >= upper_6:
            return True
    return False


from app.core.memory_store import BOT_STATE

def get_rules_from_memory() -> list:
    """Return rules from BOT_STATE memory cache. Load if empty."""
    if not BOT_STATE.rules_cache:
        log_info(MODULE, "Rules cache empty, loading from Supabase once.")
        BOT_STATE.rules_cache = _load_rules_from_supabase()
    return BOT_STATE.rules_cache

def load_rules_to_memory():
    """Explicitly reload rules to memory."""
    BOT_STATE.rules_cache = _load_rules_from_supabase()
    log_info(MODULE, f"Loaded {len(BOT_STATE.rules_cache)} rules to memory.")

def evaluate_all_rules(
    df: pd.DataFrame,
    fib_levels: dict,
    regime: dict,
    pinescript_signal: Optional[str] = None,
    rules: Optional[list] = None,
    cycle_id: Optional[str] = None,
    cfg: Optional[dict] = None,
    direction: Optional[str] = None,
    source_tf: str = "15m",
) -> Optional[dict]:
    # ...
    market_data = build_market_data_dict(df, fib_levels, regime)
    last = df.iloc[-1]
    ema50 = float(last.get("ema4", 0)) if pd.notna(last.get("ema4")) else 0.0
    ema200 = float(last.get("ema5", 0)) if pd.notna(last.get("ema5")) else 0.0
    macro = "above" if ema50 > ema200 else "below"

    if rules is None:
        rules = get_rules_from_memory()
        if not rules:
            rules = DEFAULT_RULES
    
    # Use signal_max_age_bars from cfg or default 3
    # If source_tf is 4h or 30m, we allow older bars within 15m cycle
    max_age = cfg.get("signal_max_age_bars", 3) if cfg else 3
    if source_tf == "4h":
        max_age = 16 # Full 4h candle
    elif source_tf == "30m":
        max_age = 4
        
    signal_age = int(last.get("signal_age", 0))
    if pinescript_signal in ["Buy", "Sell"] and source_tf == "15m" and signal_age > max_age:
        # For 15m, strict age check
        return None
    elif pinescript_signal in ["Buy", "Sell"] and source_tf != "15m" and signal_age > max_age:
        # For higher TFs, still check age but against their respective limits
        return None

    # Determine which direction to evaluate
    if direction in ["long", "short"]:
        direction_filter = direction
        if pinescript_signal not in ["Buy", "Sell"]:
            pinescript_signal = "Buy" if direction == "long" else "Sell"
    elif pinescript_signal == "Buy":
        direction_filter = "long"
    elif pinescript_signal == "Sell":
        direction_filter = "short"
    else:
        # No signal and no direction override — check MACD 4C
        if bool(last.get("macd_buy", False)):
            direction_filter = "long"
            pinescript_signal = "Buy"
        elif bool(last.get("macd_sell", False)):
            direction_filter = "short"
            pinescript_signal = "Sell"
        else:
            direction_filter = None

    # Check Pullback direct activation if no direction was resolved yet
    if direction_filter is None:
        if bool(market_data.get("pullback_long", False)):
            direction_filter = "long"
            pinescript_signal = "Buy" # Fake signal to pass filters
        elif bool(market_data.get("pullback_short", False)):
            direction_filter = "short"
            pinescript_signal = "Sell" # Fake signal to pass filters

    # HOT Autonomous Trigger: AaHot/BbHot can self-activate without MACD/TradingView
    if direction_filter is None:
        if market_data.get("ema_alignment_long") and market_data.get("bb_upper_slope_positive"):
            direction_filter = "long"
            pinescript_signal = "Buy"
        elif market_data.get("ema_alignment_short") and market_data.get("bb_lower_slope_negative"):
            direction_filter = "short"
            pinescript_signal = "Sell"
        else:
            return None

    # Inject dynamic SAR or Signal logic for AaHot / BbHot
    market_data["sar_or_signal_long"] = bool((int(last.get("sar_trend", 0)) > 0 if pd.notna(last.get("sar_trend")) else False) or (pinescript_signal == "Buy"))
    market_data["sar_or_signal_short"] = bool((int(last.get("sar_trend", 0)) < 0 if pd.notna(last.get("sar_trend")) else False) or (pinescript_signal == "Sell"))

    # Filter rules
    filtered = [
        r
        for r in rules
        if r.get("enabled", True)
        and r.get("direction") == direction_filter
        and (r.get("ema50_vs_ema200", "any") in [macro, "any"])
        and regime["category"] in r.get("regime_allowed", ["bajo_riesgo", "riesgo_medio", "alto_riesgo"])
    ]

    # Sort by priority (lower = higher priority)
    filtered.sort(key=lambda r: r.get("priority", 99))

    # --- BLOQUEO DE FASE Y SOBRE-EXTENSIÓN (FIBONACCI) ---
    ema20_phase = market_data.get("ema20_phase", "flat")
    fib_zone = market_data.get("fib_zone", 0)
    
    # Evaluate each rule
    for rule in filtered:
        # 1. Bloqueo para LONG
        if direction_filter == "long" and rule.get("rule_code") != "AaHot":
            if "short" in ema20_phase or fib_zone >= 4:
                continue

        # 2. Bloqueo para SHORT
        if direction_filter == "short" and rule.get("rule_code") != "BbHot":
            if "long" in ema20_phase or fib_zone <= -4:
                continue
        if evaluate_rule_conditions(rule, market_data):
            log_info(
                MODULE,
                f"Rule {rule['rule_code']} matched: {rule['name']}",
                {
                    "rule_code": rule["rule_code"],
                    "direction": direction_filter,
                    "confidence": rule.get("confidence"),
                    "regime": regime["category"],
                },
                cycle_id,
            )
            # CORRECCIÓN 2: Scoring logic para reglas estándar
            base_score = 0.50
            spike_bonus = 0.0
            if rule['rule_code'] in ("Aa22", "Bb22"):
                # Obtenemos spike_detected desde market_data (inyectado previamente o desde el dict)
                if market_data.get("spike_detected", False):
                    spike_bonus = 0.20
            
            return {
                "rule": rule,
                "direction": direction_filter,
                "pinescript_signal": pinescript_signal,
                "market_data": market_data,
                "macro": macro,
                "score": base_score + spike_bonus
            }

    return None


def evaluate_cc21_long_scalp(
    df:        pd.DataFrame,
    snap:      dict,   # market_snapshot row
    signal:    str,    # 'Buy' o ''
) -> dict:
    """
    Cc21 — LONG Scalp:
      SAR 4h en fase LONG
      + SAR 15m cambió a LONG en ventana (sar_ini_high_15m_window)
      + Señal PineScript 'Buy'

    Scoring (CORRECCIÓN 2):
      Base: 0.50
      Spike Bonus: +0.20
    """
    # Condición 1: SAR 4h LONG
    sar_4h_long = snap.get('sar_trend_4h', 0) == 1

    # Condición 2: SAR 15m cambió a LONG (ventana de 3 velas)
    sar_15m_window = bool(snap.get('sar_ini_high_15m_window', False))

    # Condición 3: Señal PineScript Buy
    pinescript_buy = signal == 'Buy'

    # CORRECCIÓN 2: Spike opcional con bonus
    base_score = 0.50
    spike_bonus = 0.20 if snap.get('spike_detected') else 0.00
    score = base_score + spike_bonus

    if (sar_4h_long and
            sar_15m_window and
            pinescript_buy):
        return {
            'triggered': True,
            'rule_code': 'Cc21',
            'score':     score,
            'reason':    f'SAR 4h LONG + SAR 15m ventana + Buy (spike bonus: {spike_bonus})'
        }

    return {'triggered': False}

def evaluate_cc11_short_scalp(
    df:        pd.DataFrame,
    snap:      dict,
    signal:    str,
) -> dict:
    """
    Cc11 — SHORT Scalp:
      SAR 4h en fase SHORT
      + SAR 15m cambió a SHORT en ventana (sar_ini_low_15m_window)
      + Señal PineScript 'Sell'
    """
    sar_4h_short = snap.get('sar_trend_4h', 0) == -1

    # SAR 15m cambió a SHORT (ventana de 3 velas)
    sar_15m_window = bool(snap.get('sar_ini_low_15m_window', False))

    pinescript_sell = signal == 'Sell'

    # CORRECCIÓN 2: Spike opcional con bonus
    base_score = 0.50
    spike_bonus = 0.20 if snap.get('spike_detected') else 0.00
    score = base_score + spike_bonus

    if (sar_4h_short and
            sar_15m_window and
            pinescript_sell):
        return {
            'triggered': True,
            'rule_code': 'Cc11',
            'score':     score,
            'reason':    f'SAR 4h SHORT + SAR 15m ventana + Sell (spike bonus: {spike_bonus})'
        }

    return {'triggered': False}

def _load_rules_from_supabase() -> list:
    """Load enabled trading rules from Supabase."""
    try:
        sb = get_supabase()
        result = (
            sb.table("trading_rules")
            .select("*")
            .eq("enabled", True)
            .eq("current", True)
            .order("priority")
            .execute()
        )
        if result.data:
            return result.data
    except Exception as e:
        log_warning(MODULE, f"Failed to load rules from Supabase: {e}")
    return []


async def seed_default_rules(supabase_client) -> None:
    """
    Seed the default rules into Supabase using UPSERT logic.
    Always updates if conditions or relevant fields changed,
    incrementing the version number.
    """
    try:
        # 1. Fetch existing rules to compare versions/conditions
        existing_res = supabase_client.table("trading_rules").select("id, version, conditions, notes").execute()
        existing_map = {r['id']: r for r in existing_res.data} if existing_res.data else {}

        seeded_count = 0
        for rule in DEFAULT_RULES:
            rule_id = rule["id"]
            new_conditions = rule.get("conditions", [])
            new_notes = rule.get("notes", "")
            
            existing = existing_map.get(rule_id)
            
            # Prepare row
            row = {
                "id": rule_id,
                "rule_code": rule["rule_code"],
                "name": rule["name"],
                "description": rule.get("description", ""),
                "direction": rule["direction"],
                "market_type": rule.get("market_type", []),
                "ema50_vs_ema200": rule.get("ema50_vs_ema200", "any"),
                "enabled": rule.get("enabled", True),
                "regime_allowed": rule.get("regime_allowed", []),
                "priority": rule.get("priority", 99),
                "confidence": rule.get("confidence", "medium"),
                "entry_trades": rule.get("entry_trades", [1]),
                "conditions": new_conditions,
                "logic": rule.get("logic", "AND"),
                "notes": new_notes,
                "current": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            if existing:
                # Always update rules to ensure rule_code matches ID during this migration
                # We also check if conditions OR notes changed to increment version
                if existing['conditions'] != new_conditions or existing['notes'] != new_notes:
                    row["version"] = int(existing.get("version", 1)) + 1
                else:
                    row["version"] = int(existing.get("version", 1))
                
                supabase_client.table("trading_rules").upsert(row).execute()
                seeded_count += 1
            else:
                # New rule
                row["version"] = 1
                row["created_at"] = datetime.now(timezone.utc).isoformat()
                supabase_client.table("trading_rules").upsert(row).execute()
                seeded_count += 1

        log_info(MODULE, f"Successfully seeded/updated {seeded_count} trading rules")
    except Exception as e:
        log_error(MODULE, f"Failed to seed/update default rules: {e}")
