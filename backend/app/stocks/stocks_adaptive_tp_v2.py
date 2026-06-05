"""
TP Adaptativo v2 para STOCKS (sin apalancamiento)

Lógica principal:
  SEMÁFORO 4H (SIPV):
    BUY  → evaluar bloques 50/25/25
    SELL → cierre total inmediato
    DOJI → modo conservador

  MOTOR EMA3/EMA9 (15m):
    EMA3 > EMA9 → momentum alcista → mantener
    EMA3 < EMA9 → momentum bajista → cerrar

  POSICIÓN EN BANDA FIBONACCI:
    Determina el nivel de decisión (Mid-Band)
    y cuándo avanzar al siguiente bloque.

  VELAS (OPEN vs CLOSE_anterior):
    Confirmación de dirección antes de cerrar.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.core.logger import log_info, log_error

ET = ZoneInfo('America/New_York')

# ── Configuración ─────────────────────────────
TP_V2_CONFIG = {
    # Mínimo shares para dividir en bloques
    'min_shares_for_blocks':   10,

    # Bloques
    'block1_pct': 0.50,
    'block2_pct': 0.25,
    'block3_pct': 0.25,

    # Volumen mínimo para validar EMA signal
    'rvol_min_for_ema':        0.8,

    # Protección anti-gap overnight
    'market_close_hour_et':    15,  # 15:50 ET
    'market_close_minute_et':  50,
    'anti_gap_reduction':      0.5,  # reducir 50%

    # Cuerpo mínimo para confirmar vela SIPV
    'candle_body_min_pct':     0.30,

    # Bollinger Band superior como límite B3
    'bb_upper_band':           'upper_bollinger',
}


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


# ═══════════════════════════════════════════
# MÓDULO 1 — CALCULAR EMA3/EMA9
# ═══════════════════════════════════════════

def calculate_ema(
    df:     pd.DataFrame,
    period: int,
    col:    str = 'close',
) -> float:
    """Calcula la EMA de N períodos."""
    if df is None or len(df) < period:
        return 0.0
    
    # Manejar nombres de columnas (yfinance usa Capitalizado)
    target_col = col
    if col not in df.columns:
        if col.capitalize() in df.columns:
            target_col = col.capitalize()
        else:
            # Si no existe ni minúscula ni capitalizada, retornar 0
            return 0.0

    series = pd.to_numeric(
        df[target_col], errors='coerce'
    ).dropna()
    if len(series) < period:
        return 0.0
    ema = series.ewm(
        span=period, adjust=False
    ).mean()
    return float(ema.iloc[-1])


def get_ema_trend(
    df:      pd.DataFrame,
    rvol:    float = 1.0,
) -> dict:
    """
    Calcula EMA3 y EMA9 en 15m y determina
    la tendencia del momentum.

    Considera el RVOL para validar la señal.
    """
    ema3 = calculate_ema(df, 3)
    ema9 = calculate_ema(df, 9)
    
    ema3_prev = 0.0
    if len(df) >= 4:
        # Calculate previous EMA3 to determine if it is curving down
        close_col = 'close' if 'close' in df.columns else 'Close'
        if close_col in df.columns:
             ema3_series = df[close_col].ewm(span=3, adjust=False).mean()
             ema3_prev = float(ema3_series.iloc[-2])

    if ema3 <= 0 or ema9 <= 0:
        return {
            'ema3':     0,
            'ema9':     0,
            'trend':    'neutral',
            'valid':    False,
            'reason':   'EMAs no calculables'
        }

    # Validar con RVOL
    min_rvol = TP_V2_CONFIG['rvol_min_for_ema']
    rvol_ok  = rvol >= min_rvol

    if ema3 > ema9:
        trend = 'up' if rvol_ok else 'up_weak'
    elif ema3 < ema9:
        trend = 'down' if rvol_ok else 'down_weak'
    else:
        trend = 'neutral'

    diff_pct = abs(ema3 - ema9) / ema9 * 100
    ema3_curving_down = ema3 < ema3_prev

    return {
        'ema3':     round(ema3, 4),
        'ema9':     round(ema9, 4),
        'trend':    trend,
        'diff_pct': round(diff_pct, 4),
        'valid':    rvol_ok,
        'rvol':     rvol,
        'is_up':    ema3 > ema9,
        'is_down':  ema3 < ema9,
        'ema3_curving_down': ema3_curving_down,
        'reason': (
            f'EMA3={ema3:.2f} '
            f'{">" if ema3>ema9 else "<"} '
            f'EMA9={ema9:.2f} '
            f'({trend})'
            + ('' if rvol_ok
               else f' ⚠️ RVOL bajo ({rvol:.1f}x)')
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 2 — SIPV (Señal de Vela)
# ═══════════════════════════════════════════

def get_sipv_signal(
    df:        pd.DataFrame,
    timeframe: str = '15m',
) -> dict:
    """
    Determina la señal SIPV de la última
    vela completa (la penúltima de df).

    Señales:
      buy:  vela alcista con cuerpo >= 30%
      sell: vela bajista con cuerpo >= 30%
      doji: vela sin dirección clara

    Para la vela VIGENTE usa el precio actual
    (no la última cerrada).
    """
    if df is None or len(df) < 2:
        return {
            'signal':   'doji',
            'strength': 0,
            'reason':   'Sin datos'
        }

    # Última vela CERRADA (penúltima del df)
    last  = df.iloc[-2]
    o     = float(last.get('open',  last.get('Open', 0)))
    h     = float(last.get('high',  last.get('High', 0)))
    l     = float(last.get('low',   last.get('Low', 0)))
    c     = float(last.get('close', last.get('Close', 0)))

    if h == l or o <= 0:
        return {
            'signal':   'doji',
            'strength': 0,
            'reason':   'Vela sin rango'
        }

    total_range  = h - l
    body         = c - o
    body_pct     = abs(body) / total_range if total_range > 0 else 0
    body_min     = TP_V2_CONFIG['candle_body_min_pct']

    # Vela vigente (última fila del df)
    curr          = df.iloc[-1]
    curr_o        = float(curr.get('open',  curr.get('Open', 0)))
    curr_c        = float(curr.get('close', curr.get('Close', 0)))
    curr_body     = curr_c - curr_o

    if body >= 0 and body_pct >= body_min:
        signal   = 'buy'
        strength = min(10, body_pct * 10)
    elif body < 0 and body_pct >= body_min:
        signal   = 'sell'
        strength = min(10, body_pct * 10)
    else:
        signal   = 'doji'
        strength = 0

    return {
        'signal':          signal,
        'strength':        round(strength, 2),
        'body_pct':        round(body_pct * 100, 1),
        'open':            o,
        'close':           c,
        'is_buy':          signal == 'buy',
        'is_sell':         signal == 'sell',
        'is_doji':         signal == 'doji',
        'curr_open':       curr_o,
        'curr_close_prov': curr_c,
        'curr_bullish':    curr_body > 0,
        'curr_bearish':    curr_body < 0,
        'timeframe':       timeframe,
        'reason': (
            f'SIPV {timeframe}: '
            f'{signal.upper()} '
            f'(cuerpo={body_pct*100:.1f}%)'
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 3 — DETECCIÓN DE BANDA FIBONACCI
#            Y MID-BAND
# ═══════════════════════════════════════════

def get_current_fib_band(
    price: float,
    snap:  dict,
) -> dict:
    """
    Determina en qué banda Fibonacci está
    el precio actualmente y calcula el
    Mid-Band entre esta y la siguiente.

    Mid_Band(x) = (Upper_x + Upper_{x+1}) / 2

    Returns:
      band:        int (1-6, 0=basis)
      band_price:  float
      next_band:   int
      next_price:  float
      mid_band:    float (punto de decisión)
      pct_to_next: float (% para llegar a next)
      above_mid:   bool (¿sobre la mitad?)
    """
    bands = {}
    for n in range(1, 7):
        val = safe_float(snap.get(f'upper_{n}', 0))
        if val > 0:
            bands[n] = val
    basis = safe_float(snap.get('basis', 0))

    # Determinar banda actual
    current_band = 0
    for n in sorted(bands.keys(), reverse=True):
        if price >= bands[n]:
            current_band = n
            break

    if current_band == 0:
        # Por debajo de upper_1 → zona basis/negativa
        band_price = basis if basis > 0 else price
        next_band  = 1
        next_price = bands.get(1, price * 1.02)
    elif current_band == 6:
        # Máximo → no hay next
        band_price = bands[6]
        next_band  = 6
        next_price = bands[6]
    else:
        band_price = bands[current_band]
        next_band  = current_band + 1
        next_price = bands.get(next_band, 0)

    # Mid-Band: mitad entre banda actual y siguiente
    if next_price > 0 and band_price > 0:
        mid_band = (band_price + next_price) / 2
        above_mid = price >= mid_band
        pct_to_next = (
            (next_price - price) / price * 100
        ) if price > 0 else 0
    else:
        mid_band    = band_price
        above_mid   = False
        pct_to_next = 0

    return {
        'band':        current_band,
        'band_price':  round(band_price, 4),
        'next_band':   next_band,
        'next_price':  round(next_price, 4),
        'mid_band':    round(mid_band, 4),
        'above_mid':   above_mid,
        'pct_to_next': round(pct_to_next, 2),
        'price':       round(price, 4),
        'reason': (
            f'Banda Upper_{current_band} '
            f'(${band_price:.2f}). '
            f'Mid={mid_band:.2f}. '
            f'{"Sobre" if above_mid else "Bajo"} '
            f'la mitad. '
            f'Next=Upper_{next_band}'
            f'({pct_to_next:.1f}% lejos)'
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 4 — LÓGICA DE OPEN VS CLOSE_ANTERIOR
# ═══════════════════════════════════════════

def check_open_vs_close_prev(
    df:   pd.DataFrame,
    side: str = 'long',
) -> dict:
    """
    Compara el OPEN de la vela vigente con
    el CLOSE de la vela anterior.

    Para BUY/LONG:
      OPEN >= CLOSE_prev → apertura alcista
        → mantener (momentum continúa)
      OPEN <= CLOSE_prev → apertura bajista
        → señal de cierre
    """
    if df is None or len(df) < 2:
        return {
            'open_bearish': False,
            'open_bullish': False,
            'reason':       'Sin datos'
        }

    prev_close  = float(df.iloc[-2].get('close', df.iloc[-2].get('Close', 0)))
    curr_open   = float(df.iloc[-1].get('open',  df.iloc[-1].get('Open', 0)))

    if prev_close <= 0 or curr_open <= 0:
        return {
            'open_bearish': False,
            'open_bullish': False,
            'reason':       'Datos inválidos'
        }

    if side in ('long', 'buy'):
        open_bearish = curr_open <= prev_close
        open_bullish = curr_open >= prev_close
    else:
        open_bearish = curr_open >= prev_close
        open_bullish = curr_open <= prev_close

    return {
        'curr_open':    curr_open,
        'prev_close':   prev_close,
        'open_bearish': open_bearish,
        'open_bullish': open_bullish,
        'diff_pips':    round(
            abs(curr_open - prev_close) * 10000, 1
        ),
        'reason': (
            f'OPEN={curr_open:.4f} '
            f'{"≤" if open_bearish else "≥"} '
            f'CLOSE_prev={prev_close:.4f} '
            f'→ {"BEARISH" if open_bearish else "BULLISH"}'
            if side in ('long','buy')
            else
            f'OPEN={curr_open:.4f} '
            f'{"≥" if open_bearish else "≤"} '
            f'CLOSE_prev={prev_close:.4f}'
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 5 — FUNCIÓN PRINCIPAL DE DECISIÓN
# ═══════════════════════════════════════════

def evaluate_stock_tp_v2(
    ticker:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_5m:         pd.DataFrame = None,
    df_4h:         pd.DataFrame = None,
    rvol:          float = 1.0,
    sar_15m:       int   = 1,
) -> dict:
    """
    Función principal de TP Adaptativo v2.
    """
    entry_price  = safe_float(position.get(
        'avg_price',
        position.get('entry_price', 0)
    ))
    total_shares = safe_int(position.get('shares', 0))
    shares_rem   = safe_int(position.get(
        'shares_remaining', total_shares
    ))
    b1_done      = bool(position.get(
        'tp_block1_executed', False
    ))
    b2_done      = bool(position.get(
        'tp_block2_executed', False
    ))
    b3_done      = bool(position.get(
        'tp_block3_executed', False
    ))
    b1_shares    = safe_int(position.get(
        'tp_block1_shares', 0
    ))
    b2_shares    = safe_int(position.get(
        'tp_block2_shares', 0
    ))
    b3_shares    = safe_int(position.get(
        'tp_block3_shares', 0
    ))

    # Ganancia actual
    gain_pct = (
        (current_price - entry_price)
        / entry_price * 100
    ) if entry_price > 0 else 0

    # ── NUEVO: Control de antigüedad mínima de la posición ──
    # Para evitar que señales estáticas e históricas (como SIPV de 15m)
    # cierren el trade inmediatamente tras comprar en fracciones de segundos.
    entry_time_str = position.get("first_buy_at") or position.get("entry_time")
    age_mins = 0.0
    if entry_time_str:
        try:
            # Normalizar ISO string
            entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
            age_mins = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
        except Exception:
            pass

    MIN_HOLDING_MINUTES = 15.0
    if age_mins < MIN_HOLDING_MINUTES:
        # Permitimos saltar la restricción únicamente si no hay ganancia (evaluado por seguridad en otros lados)
        # o si la posición tiene ganancias pero es demasiado joven, la obligamos a madurar.
        if gain_pct > 0:
            return {
                'action': 'hold',
                'gain_pct': round(gain_pct, 2),
                'debug_indicators': {},
                'reason': f'Posición joven ({age_mins:.1f}m < {MIN_HOLDING_MINUTES}m) — bloqueo de salida prematura para buscar ganancias importantes.'
            }

    # Sin ganancia → no evaluar TP
    if gain_pct <= 0:
        return {
            'action': 'hold',
            'gain_pct': round(gain_pct, 2),
            'debug_indicators': {},
            'reason':   'Sin ganancia — no evaluar TP'
        }

    # ── Calcular indicadores (necesarios para debug_indicators) ──
    ema      = get_ema_trend(df_15m, rvol)
    sipv_15m = get_sipv_signal(df_15m, '15m')
    sipv_4h  = get_sipv_signal(df_4h, '4h') \
               if df_4h is not None \
               else {'signal': 'doji', 'is_buy': True,
                     'is_sell': False, 'is_doji': True}
    fib      = get_current_fib_band(
        current_price, snap
    )
    ovc      = check_open_vs_close_prev(df_15m)

    # ── PASO 0: Shares suficientes ────────────
    min_shares = TP_V2_CONFIG[
        'min_shares_for_blocks'
    ]
    if total_shares < min_shares:
        # Con pocas shares, cierre total si hay señal
        if ema['is_down'] or sipv_4h['is_sell']:
            return {
                'action':  'close_total',
                'pct':     100,
                'shares':  shares_rem,
                'reason': (
                    f'Pocos shares ({total_shares}): '
                    f'cierre total. '
                    f'EMA={ema["trend"]} '
                    f'SIPV4H={sipv_4h["signal"]}'
                ),
            }
        return {
            'action':   'hold',
            'gain_pct': round(gain_pct, 2),
            'debug_indicators': {
                'ema': ema,
                'sipv_15m': sipv_15m,
                'sipv_4h': sipv_4h,
                'fib': fib
            },
            'reason':   f'Pocos shares — esperar señal'
        }

    # SAR positivo = alcista = 1
    sar_positive = safe_int(sar_15m, 1) > 0

    log_info('TP_v2',
        f'{ticker}: '
        f'EMA={ema["trend"]} | '
        f'SIPV4H={sipv_4h["signal"]} | '
        f'SIPV15m={sipv_15m["signal"]} | '
        f'Fib=Upper_{fib["band"]} | '
        f'SAR={"+" if sar_positive else "-"} | '
        f'gain={gain_pct:.2f}%'
    )

    # Indicator package for DB logging
    debug_indicators = {
        'ema': ema,
        'sipv_15m': sipv_15m,
        'sipv_4h': sipv_4h,
        'fib': fib
    }

    # ── PASO 1: SEMÁFORO 4H ───────────────────
    if sipv_4h['is_sell']:
        remaining = shares_rem if shares_rem > 0 \
                    else b2_shares + b3_shares
        return {
            'action':  'close_total',
            'pct':     100,
            'shares':  remaining,
            'trigger': 'sipv_4h_sell',
            'ema':     ema,
            'sipv_4h': sipv_4h,
            'debug_indicators': debug_indicators,
            'reason': (
                f'SEMÁFORO 4H ROJO: '
                f'SIPV 4H = SELL → '
                f'CIERRE TOTAL {remaining} shares. '
                f'Ganancia: +{gain_pct:.2f}%'
            ),
        }

    # ── PASO 2: SIPV 15m SELL (Reemplaza EMA down por solicitud de usuario) ──
    # Se expande el margen: no cerramos por simple cruce de EMA, sino por vela bajista confirmada.
    if sipv_15m['is_sell']:
        remaining = shares_rem if shares_rem > 0 \
                    else b2_shares + b3_shares
        return {
            'action':  'close_total',
            'pct':     100,
            'shares':  remaining,
            'trigger': 'sipv_15m_sell',
            'debug_indicators': debug_indicators,
            'reason': (
                f'SIPV 15m = SELL: '
                f'CIERRE TOTAL {remaining} shares por señal bajista confirmada.'
            ),
        }

    # ── PASO 1.5: REGLAS DE CIERRE DINÁMICO V5.3 ──
    # Condiciones de cierre solicitadas por el usuario:
    # Cerrar si: (EMA3 < EMA9) OR (CLOSE > UPPER_6) OR (RSI >= 75)
    #         OR (OPEN > BB_Upper AND CLOSE > OPEN)
    rsi_15m = float(snap.get('rsi_14', 50))
    bb_upper = float(snap.get('bb_upper', 999999))
    upper_6 = safe_float(snap.get('upper_6', 0))

    # Obtener OPEN y CLOSE de la vela vigente
    curr_open = 0.0
    curr_close = current_price
    if df_15m is not None and len(df_15m) >= 1:
        last_candle = df_15m.iloc[-1]
        curr_open = float(last_candle.get('open', last_candle.get('Open', 0)))
        curr_close = float(last_candle.get('close', last_candle.get('Close', current_price)))

    # Condición 1: EMA3 < EMA9 (Cruce bajista de momentum)
    ema_crossed_down = ema['is_down']

    # Condición 2: CLOSE > UPPER_6 (Sobre-extensión masiva - Fibonacci Band 6)
    close_above_upper6 = (upper_6 > 0 and curr_close > upper_6)

    # Condición 3: RSI >= 75 (Sobrecompra extrema intradía)
    rsi_extreme = (rsi_15m >= 75)

    # Condición 4: OPEN > BB_Upper AND CLOSE > OPEN
    # Vela abriendo por encima de la banda superior de Bollinger y cerrando verde
    # Esto indica agotamiento inminente (último impulso antes de reversión)
    candle_above_bb = (curr_open > bb_upper and curr_close > curr_open)

    # Condición extra: EMA3 convergiendo hacia EMA9 (squeeze descendente)
    ema_squeezing_down = ema['is_up'] and (ema['diff_pct'] < 5.0) and ema['ema3_curving_down']

    if ema_crossed_down or close_above_upper6 or rsi_extreme or candle_above_bb or ema_squeezing_down:
        remaining = shares_rem if shares_rem > 0 else b2_shares + b3_shares
        # Determinar qué condición activó el cierre
        if ema_crossed_down:
            trigger_name = "ema3_lt_ema9"
            reason_detail = f"EMA3 < EMA9 (Cruce bajista: {ema['ema3']:.2f} < {ema['ema9']:.2f})"
        elif close_above_upper6:
            trigger_name = "close_gt_upper6"
            reason_detail = f"CLOSE ${curr_close:.2f} > UPPER_6 ${upper_6:.2f} (Sobre-extensión máxima)"
        elif rsi_extreme:
            trigger_name = "rsi_gte_75"
            reason_detail = f"RSI = {rsi_15m:.1f} >= 75 (Sobrecompra extrema)"
        elif candle_above_bb:
            trigger_name = "open_gt_bb_upper"
            reason_detail = f"OPEN ${curr_open:.2f} > BB_Upper ${bb_upper:.2f} AND CLOSE > OPEN (Agotamiento)"
        else:
            trigger_name = "ema_squeezing_down"
            reason_detail = f"EMA3 convergiendo hacia EMA9 ({ema['diff_pct']:.1f}% separación, curving down)"

        return {
            'action':  'close_total',
            'pct':     100,
            'shares':  remaining,
            'trigger': trigger_name,
            'debug_indicators': debug_indicators,
            'reason': (
                f'EXIT RULE V5.3: {reason_detail}. '
                f'CIERRE TOTAL {remaining} shares. '
                f'Ganancia: +{gain_pct:.2f}%'
            ),
        }

    # Si EMA3 > EMA9 y no se cumplen las condiciones de salida, BLOQUEAMOS el cierre prematuro.
    if ema['is_up'] and not ema_squeezing_down:
         return {
             'action': 'hold',
             'trigger': 'ema_trailing_active',
             'debug_indicators': debug_indicators,
             'reason': f'Trailing Stop Activo: EMA3 > EMA9 ({ema["diff_pct"]:.1f}% separación). Manteniendo posición para maximizar ganancia.'
         }

    # ── CASO A: CLOSE >= UPPER_6 ──────────────
    if fib['band'] >= 6:
        res = _evaluate_upper6_logic(
            ticker, position, current_price,
            snap, df_15m, df_5m,
            ema, sipv_15m, sipv_4h, ovc, fib,
            sar_positive, gain_pct,
            b1_done, b2_done, b3_done,
            b1_shares, b2_shares, b3_shares,
            shares_rem,
        )
        res['debug_indicators'] = debug_indicators
        return res

    # ── CASO B: CLOSE entre BASIS y UPPER_5 ───
    else:
        res = _evaluate_mid_band_logic(
            ticker, position, current_price,
            snap, df_15m, df_5m,
            ema, sipv_15m, sipv_4h, ovc, fib,
            sar_positive, gain_pct,
            b1_done, b2_done, b3_done,
            b1_shares, b2_shares, b3_shares,
            shares_rem,
        )
        res['debug_indicators'] = debug_indicators
        return res


def _evaluate_upper6_logic(
    ticker, position, price, snap, df_15m, df_5m,
    ema, sipv_15m, sipv_4h, ovc, fib,
    sar_positive, gain_pct,
    b1_done, b2_done, b3_done,
    b1_shares, b2_shares, b3_shares, shares_rem,
) -> dict:
    # ── BLOQUE 1 (50%) ────────────────────────
    if not b1_done:
        if sipv_15m['is_buy']:
            if ovc['open_bearish']:
                return {
                    'action':  'close_block1',
                    'shares':  b1_shares,
                    'trigger': 'upper6_opt1_bearish_open',
                    'reason': (
                        f'UPPER_6 Opción1: '
                        f'SIPV15m=BUY pero '
                        f'OPEN({ovc["curr_open"]:.2f}) ≤ '
                        f'CLOSE_prev({ovc["prev_close"]:.2f}) '
                        f'→ CERRAR B1 50% ({b1_shares}sh)'
                    ),
                }
            else:
                return {
                    'action':  'hold',
                    'trigger': 'upper6_opt1_hold',
                    'reason': (
                        f'UPPER_6 Opción1: '
                        f'SIPV15m=BUY y '
                        f'OPEN({ovc["curr_open"]:.2f}) ≥ '
                        f'CLOSE_prev → MANTENER'
                    ),
                }

        elif sipv_15m['is_sell']:
            return {
                'action':  'close_block1',
                'shares':  b1_shares,
                'trigger': 'upper6_opt2_sipv_sell',
                'reason': (
                    f'UPPER_6 Opción2: '
                    f'SIPV15m=SELL + EMA3>EMA9 '
                    f'→ CERRAR B1 50% ({b1_shares}sh). '
                    f'Ganancia: +{gain_pct:.2f}%'
                ),
            }

        elif df_5m is not None:
            sipv_5m = get_sipv_signal(df_5m, '5m')
            if sipv_5m['is_sell']:
                return {
                    'action':  'close_block1',
                    'shares':  b1_shares,
                    'trigger': 'upper6_5m_sell',
                    'reason': (
                        f'UPPER_6: SIPV5m=SELL '
                        f'→ CERRAR B1 50% ({b1_shares}sh)'
                    ),
                }

        return {
            'action':  'hold',
            'reason':  f'UPPER_6: B1 pendiente — esperar señal'
        }

    # ── BLOQUE 2 (25%) ────────────────────────
    if b1_done and not b2_done:
        if sipv_15m['is_buy']:
            if ovc['open_bearish']:
                return {
                    'action':  'close_block2',
                    'shares':  b2_shares,
                    'trigger': 'upper6_b2_bearish_open',
                    'reason': (
                        f'B2 UPPER_6: '
                        f'EMA3>EMA9 + SIPV=BUY pero '
                        f'OPEN ≤ CLOSE_prev '
                        f'→ CERRAR B2 25% ({b2_shares}sh)'
                    ),
                }
            elif df_5m is not None:
                sipv_5m = get_sipv_signal(df_5m, '5m')
                if sipv_5m['is_sell']:
                    return {
                        'action':  'close_block2',
                        'shares':  b2_shares,
                        'trigger': 'upper6_b2_5m_sell',
                        'reason': (
                            f'B2 UPPER_6: '
                            f'OPEN ≥ CLOSE_prev pero '
                            f'SIPV5m=SELL '
                            f'→ CERRAR B2 ({b2_shares}sh)'
                        ),
                    }

            return {
                'action':  'hold',
                'reason':  'B2: EMA3>EMA9+BUY+OPEN_OK — mantener'
            }

        return {
            'action':  'hold',
            'reason':  'B2 pendiente — condiciones mixtas'
        }

    # ── BLOQUE 3 (25%) ────────────────────────
    if b1_done and b2_done and not b3_done:
        upper_5 = safe_float(snap.get('upper_5', 0))
        bb_upper = safe_float(snap.get(
            'upper_bollinger',
            snap.get('upper_2', 0)
        ))

        if upper_5 > 0 and price <= upper_5:
            return {
                'action':  'close_block3',
                'shares':  b3_shares,
                'trigger': 'b3_dropped_to_upper5',
                'reason': (
                    f'B3: Precio cayó de Upper_6 '
                    f'a Upper_5 (${upper_5:.2f}) '
                    f'→ CERRAR B3 ({b3_shares}sh)'
                ),
            }

        if bb_upper > 0 and price <= bb_upper:
            return {
                'action':  'close_block3',
                'shares':  b3_shares,
                'trigger': 'b3_dropped_to_bb',
                'reason': (
                    f'B3: Precio tocó BB superior '
                    f'(${bb_upper:.2f}) '
                    f'→ CERRAR B3 ({b3_shares}sh)'
                ),
            }

        return {
            'action':  'hold',
            'reason':  f'B3: EMA3>EMA9 — trailing activo'
        }

    return {'action': 'hold', 'reason': 'Todos bloques ejecutados'}


def _evaluate_mid_band_logic(
    ticker, position, price, snap, df_15m, df_5m,
    ema, sipv_15m, sipv_4h, ovc, fib,
    sar_positive, gain_pct,
    b1_done, b2_done, b3_done,
    b1_shares, b2_shares, b3_shares, shares_rem,
) -> dict:
    above_mid   = fib['above_mid']
    mid_band    = fib['mid_band']
    curr_band   = fib['band']
    pct_to_next = fib['pct_to_next']

    if ovc['open_bullish']:
        return {
            'action':  'hold',
            'trigger': 'open_bullish_15m',
            'fib':     fib,
            'reason': (
                f'Banda Upper_{curr_band}: '
                f'OPEN({ovc["curr_open"]:.2f}) ≥ '
                f'CLOSE_prev({ovc["prev_close"]:.2f}) '
                f'→ MANTENER'
            ),
        }

    if above_mid:
        if sar_positive:
            return {
                'action':  'hold',
                'trigger': 'ema_up_mid_sar_plus',
                'fib':     fib,
                'reason': (
                    f'Upper_{curr_band}: '
                    f'EMA3>EMA9 + sobre mid '
                    f'+ SAR+ → MANTENER '
                    f'(próxima banda: '
                    f'{pct_to_next:.1f}% lejos)'
                ),
            }
        else:
            return {
                'action':  'close_total',
                'pct':     100,
                'shares':  shares_rem,
                'trigger': 'ema_up_mid_sar_neg',
                'reason': (
                    f'Upper_{curr_band}: '
                    f'EMA3>EMA9 + sobre mid '
                    f'pero SAR- → '
                    f'CERRAR 100% ({shares_rem}sh). '
                    f'Ganancia: +{gain_pct:.2f}%'
                ),
            }
    else:
        if sar_positive:
            return {
                'action':  'hold',
                'trigger': 'ema_up_below_mid_sar_plus',
                'fib':     fib,
                'reason': (
                    f'Upper_{curr_band}: '
                    f'EMA3>EMA9 + bajo mid '
                    f'+ SAR+ → MANTENER '
                    f'(precio en ${price:.2f} '
                    f'vs mid ${mid_band:.2f})'
                ),
            }
        else:
            return {
                'action':  'close_total',
                'pct':     100,
                'shares':  shares_rem,
                'trigger': 'ema_up_below_mid_no_sar',
                'reason': (
                    f'Upper_{curr_band}: '
                    f'EMA3>EMA9 + bajo mid '
                    f'+ SAR- → '
                    f'CERRAR 100% ({shares_rem}sh)'
                ),
            }

# ═══════════════════════════════════════════
# PROTECCIÓN ANTI-GAP
# ═══════════════════════════════════════════

def check_overnight_protection(
    position:      dict,
    current_price: float,
    gain_pct:      float,
) -> dict:
    """
    Protección anti-gap overnight:
    Antes del cierre del mercado (15:50 ET),
    reducir posición al 50% si hay ganancia.
    """
    now_et   = datetime.now(ET)
    is_close = (
        now_et.hour == TP_V2_CONFIG['market_close_hour_et'] and
        now_et.minute >= TP_V2_CONFIG['market_close_minute_et']
    )

    if not is_close:
        return {'apply': False}

    shares_rem = safe_int(position.get(
        'shares_remaining',
        position.get('shares', 0)
    ))
    already    = bool(position.get(
        'anti_gap_applied', False
    ))

    if already or shares_rem <= 1:
        return {'apply': False}

    min_gain = 1.0
    if gain_pct < min_gain:
        return {
            'apply':  False,
            'reason': f'Ganancia {gain_pct:.2f}% < {min_gain}%'
        }

    shares_to_sell = int(
        shares_rem
        * TP_V2_CONFIG['anti_gap_reduction']
    )
    if shares_to_sell < 1:
        return {'apply': False}

    return {
        'apply':         True,
        'shares_to_sell': shares_to_sell,
        'reason': (
            f'ANTI-GAP OVERNIGHT: '
            f'15:50 ET + ganancia +{gain_pct:.2f}% '
            f'→ vender {shares_to_sell} shares (50%) '
            f'antes del cierre'
        ),
    }
