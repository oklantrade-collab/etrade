"""
Módulo de Cierre Proactivo — Aa51/Bb51/Aa52/Bb52

Detecta reversión de mercado ANTES de que
el SL se active y cierra posiciones con
ganancia positiva.

Opera en el ciclo de 5m para todos los mercados:
  - Crypto (Binance Futures)
  - Forex (cTrader)
  - Stocks (IB TWS)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from app.core.logger import log_info, log_error
from app.core.market_hours import get_nyc_now
from datetime import time

# ── Umbrales de ganancia mínima ───────────────
MIN_PROFIT_THRESHOLDS = {
    'crypto_futures': 0.003,  # 0.30%
    'forex_futures':  0.0005, # 5 pips aprox
    'stocks_spot':    0.002,  # 0.20%
    'crypto_spot':    0.002,
}

# Umbral para cierre urgente (Aa52/Bb52)
URGENT_PROFIT_THRESHOLD = 0.010  # 1.0%

# Tamaño mínimo de vela 4H (cuerpo)
MIN_CANDLE_BODY_PCT = 0.005  # 0.5%


def safe_float(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except (ValueError, TypeError):
        return default


def safe_int(v, default=0):
    try:
        if v is None: return default
        return int(float(v))
    except (ValueError, TypeError):
        return default

MODULE = "PROACTIVE_EXIT"

def analyze_4h_candle(
    df_4h: pd.DataFrame,
    direction: str  # 'bearish' o 'bullish'
) -> dict:
    """
    Analiza la última vela de 4H confirmada
    para detectar si es bajista o alcista.
    """
    if df_4h is None or len(df_4h) < 2:
        return {
            'confirmed':   False,
            'candle_type': 'neutral',
            'body_pct':    0.0,
            'reason':      'Datos insuficientes'
        }

    # Usar la última vela CERRADA (no la actual)
    # La penúltima es la última vela completa
    try:
        last_closed = df_4h.iloc[-2]
        prev        = df_4h.iloc[-3] if len(df_4h) >= 3 else df_4h.iloc[-2]

        def _f(v):
            try: return float(v) if v is not None else 0.0
            except: return 0.0

        open_price  = safe_float(last_closed.get('open', last_closed.get('Open')))
        close_price = safe_float(last_closed.get('close', last_closed.get('Close')))
        high_price  = safe_float(last_closed.get('high', last_closed.get('High')))
        low_price   = safe_float(last_closed.get('low', last_closed.get('Low')))

        if open_price <= 0:
            return {
                'confirmed':   False,
                'candle_type': 'neutral',
                'body_pct':    0.0,
                'reason':      'Precio open inválido'
            }

        # Calcular tamaño del cuerpo
        body_pct = abs(close_price - open_price) / open_price

        # Detectar tipo de vela
        is_bearish = (close_price < open_price and body_pct >= MIN_CANDLE_BODY_PCT)
        is_bullish = (close_price > open_price and body_pct >= MIN_CANDLE_BODY_PCT)

        # Confirmación estructural adicional
        prev_low  = safe_float(prev.get('low', prev.get('Low')))
        prev_high = safe_float(prev.get('high', prev.get('High')))
        lower_low   = low_price < prev_low
        higher_high = high_price > prev_high

        if direction == 'bearish':
            confirmed = is_bearish
            structural_confirm = lower_low
            candle_type = 'bearish' if is_bearish else 'neutral'
        else:  # bullish
            confirmed = is_bullish
            structural_confirm = higher_high
            candle_type = 'bullish' if is_bullish else 'neutral'

        return {
            'confirmed':          confirmed,
            'structural_confirm': structural_confirm,
            'candle_type':        candle_type,
            'body_pct':           round(body_pct * 100, 4),
            'open':               open_price,
            'close':              close_price,
            'high':               high_price,
            'low':                low_price,
            'reason': (
                f'Vela {candle_type} '
                f'cuerpo={body_pct*100:.2f}% '
                f'{"+ estructura" if structural_confirm else ""}'
            )
        }
    except Exception as e:
        return {'confirmed': False, 'candle_type': 'neutral', 'body_pct': 0.0, 'reason': str(e)}


def calculate_position_pnl(
    position:      dict,
    current_price: float,
    market_type:   str = 'crypto_futures'
) -> dict:
    """
    Calcula el P&L actual de una posición.
    """
    def _f(v, d=0.0):
        try: return float(v) if v is not None else d
        except: return d

    entry = _f(position.get('avg_entry_price', position.get('entry_price', 0)))
    side  = str(position.get('side', 'long')).lower()
    size  = _f(position.get('size', position.get('lots', 1)), 1.0)

    if entry <= 0 or current_price <= 0:
        return {
            'pnl_pct':    0.0,
            'pnl_usd':    0.0,
            'has_profit': False,
            'is_urgent':  False,
            'pnl_pips':   0.0,
        }

    # Calcular P&L porcentual
    if side in ('long', 'buy'):
        pnl_pct = (current_price - entry) / entry
    else:  # short, sell
        pnl_pct = (entry - current_price) / entry

    # Calcular P&L en USD (simplificado)
    pnl_usd  = pnl_pct * entry * size
    pnl_pips = 0.0

    # Para Forex: calcular en pips
    if market_type == 'forex_futures':
        pip_sizes = {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDJPY': 0.01, 'XAUUSD': 0.01,
        }
        symbol   = position.get('symbol', '')
        pip_size = pip_sizes.get(symbol, 0.0001)
        if side in ('long', 'buy'):
            pnl_pips = (current_price - entry) / pip_size
        else:
            pnl_pips = (entry - current_price) / pip_size

    # Determinar umbrales
    threshold = MIN_PROFIT_THRESHOLDS.get(market_type, 0.003)
    has_profit = pnl_pct >= threshold
    is_urgent  = pnl_pct >= URGENT_PROFIT_THRESHOLD

    return {
        'pnl_pct':    round(pnl_pct * 100, 4),
        'pnl_usd':    round(pnl_usd, 4),
        'has_profit': has_profit,
        'is_urgent':  is_urgent,
        'pnl_pips':   round(pnl_pips, 1),
        'threshold':  round(threshold * 100, 3),
    }


def evaluate_proactive_exit(
    position:      dict,
    current_price: float,
    snap:          dict,
    df_4h:         pd.DataFrame,
    market_type:   str = 'crypto_futures'
) -> dict:
    """
    Evalúa si corresponde cerrar la posición proactivamente.
    """
    side = str(position.get('side', 'long')).lower()
    is_long = side in ('long', 'buy')
    
    # ── NUEVO: Protección Fin de Día (EOD) ──
    try:
        nyc_now = get_nyc_now()
        current_time = nyc_now.time()
        # Cerrar todo lo HOT/Scalping en los últimos 5 min para evitar GAPs nocturnos
        # Solo para Stocks. Forex (24/5) y Crypto (24/7) prefieren evitar cierres forzados por horario.
        if market_type == 'stocks_spot' and time(15, 55) <= current_time <= time(16, 5):
            return {
                'should_close': True,
                'rule_code':    'AaEOD' if is_long else 'BbEOD',
                'reason':       'Protección EOD: Cierre preventivo antes del fin de jornada para evitar GAPs.',
                'pnl':          calculate_position_pnl(position, current_price, market_type),
                'urgency':      'urgent'
            }
    except Exception as e:
        log_error(MODULE, f"Error en protección EOD: {e}")

    # ── NUEVO: Protección por Zona Extrema (UPPER_6) ──
    # Se requiere profit mínimo y señal SIPV para evitar cierres prematuros en spikes.
    fib_zone = safe_int(snap.get('fibonacci_zone', 0))
    pnl = calculate_position_pnl(position, current_price, market_type)
    
    # SIPV 15m SELL check
    pine_signal = str(snap.get('pinescript_signal', '')).lower()
    sipv_sell = (is_long and pine_signal == 'sell') or (not is_long and pine_signal == 'buy')

    if ((is_long and fib_zone >= 5) or (not is_long and fib_zone <= -5)) and pnl['has_profit'] and sipv_sell:
        return {
            'should_close': True,
            'rule_code':    'AaEXT' if is_long else 'BbEXT',
            'reason':       f'Zona Extrema {fib_zone} + Señal SIPV + Profit. Asegurando ganancias.',
            'pnl':          pnl,
            'urgency':      'urgent'
        }

    # ── NUEVO: Protección por Agotamiento de EMAs (EMA_EXHAUSTION) ──
    # Cuando EMA3 y EMA9 se pegan después de un movimiento fuerte, indica posible reversión.
    ema_exh = bool(snap.get('ema_exhaustion', False))
    if ema_exh and pnl['has_profit']:
        return {
            'should_close': True,
            'rule_code':    'AaEXH' if is_long else 'BbEXH',
            'reason':       'Agotamiento detectado: EMAs 3/9 se han comprimido significativamente. Asegurando ganancias.',
            'pnl':          pnl,
            'urgency':      'normal'
        }

    # ── Calcular P&L actual ───────────────────
    pnl = calculate_position_pnl(position, current_price, market_type)

    # ── Evaluar las 3 condiciones ─────────────

    # C1: PineScript signal
    pine_signal = str(snap.get('pinescript_signal', ''))
    if is_long:
        c1_pine = pine_signal.lower() == 'sell'
        pine_expected = 'Sell'
    else:
        c1_pine = pine_signal.lower() == 'buy'
        pine_expected = 'Buy'

    # C2: SAR negativo/positivo (15m preference)
    sar_trend = safe_int(snap.get('sar_trend_15m', snap.get('sar_trend_4h', 0)))
    if is_long:
        c2_sar = sar_trend < 0
    else:
        c2_sar = sar_trend > 0

    # C3: Vela 4H confirmada
    candle_direction = 'bearish' if is_long else 'bullish'
    candle_analysis  = analyze_4h_candle(df_4h, candle_direction)
    c3_candle = candle_analysis['confirmed']

    # C4 opcional: MTF revirtiendo
    def _safe_f(v):
        try: return float(v) if v is not None else 0.0
        except: return 0.0
    
    mtf = _safe_f(snap.get('mtf_score', 0))
    if is_long:
        c4_mtf = mtf < 0.20
    else:
        c4_mtf = mtf > -0.20

    conditions = {
        'c1_pine': {'passed': c1_pine, 'name': f'PineScript = {pine_expected}', 'value': pine_signal, 'weight': 0.30},
        'c2_sar': {'passed': c2_sar, 'name': f'SAR {"negativo" if is_long else "positivo"}', 'value': sar_trend, 'weight': 0.30},
        'c3_candle': {'passed': c3_candle, 'name': f'Vela 4H {candle_direction}', 'value': candle_analysis.get('reason', ''), 'weight': 0.25},
        'c4_mtf': {'passed': c4_mtf, 'name': 'MTF revirtiendo', 'value': mtf, 'optional': True, 'weight': 0.15},
    }

    # ── Evaluar reglas ────────────────────────
    triple_confirmed = c1_pine and c2_sar and c3_candle
    double_confirmed = (
        (c1_pine and c2_sar) or (c1_pine and c3_candle) or (c2_sar and c3_candle)
    )
    # Reversión técnica fuerte: Pine + SAR (lo que el usuario reportó)
    technical_reversal = c1_pine and c2_sar
    
    urgent_exit = double_confirmed and pnl['is_urgent']
    
    # Umbral de pérdida aceptable para cierre técnico preventivo
    # Evita "acumular mucha pérdida" cuando el mercado se gira claramente
    max_preventive_loss_pips = -3.0
    max_preventive_loss_pct  = -0.001 # -0.10%

    if triple_confirmed and pnl['has_profit']:
        rule_code   = 'Aa51' if is_long else 'Bb51'
        should_close = True
        urgency     = 'normal'
        reason      = f'Triple confirmación detectada. P&L: +{pnl["pnl_pct"]:.3f}%'
    elif urgent_exit:
        rule_code   = 'Aa52' if is_long else 'Bb52'
        should_close = True
        urgency     = 'urgent'
        reason      = f'Cierre urgente (2/3 cond + ganancia >1%). P&L: +{pnl["pnl_pct"]:.3f}%'
    elif technical_reversal:
        # Si hay confirmación de Pine + SAR, cerramos incluso con ganancia mínima o pérdida pequeña
        is_forex = market_type == 'forex_futures'
        loss_ok = (pnl['pnl_pips'] >= max_preventive_loss_pips) if is_forex else (pnl['pnl_pct']/100 >= max_preventive_loss_pct)
        
        if pnl['has_profit'] or loss_ok:
            rule_code   = 'Aa53' if is_long else 'Bb53'
            should_close = True
            urgency     = 'normal'
            reason      = f'Reversión técnica (Pine+SAR). P&L: {pnl["pnl_pips"] if is_forex else pnl["pnl_pct"]} {"pips" if is_forex else "%"}'
        else:
            should_close = False
            rule_code   = None
            urgency     = 'none'
            reason      = f'Reversión detectada pero pérdida excede umbral preventivo. Esperando SL/TP.'
    else:
        should_close = False
        rule_code   = None
        urgency     = 'none'
        reason      = f'Condiciones insuficientes. P&L: {pnl["pnl_pct"]:.3f}%'

    return {
        'should_close': should_close,
        'rule_code':    rule_code,
        'reason':       reason,
        'pnl':          pnl,
        'conditions':   conditions,
        'urgency':      urgency,
        'candle':       candle_analysis,
    }

