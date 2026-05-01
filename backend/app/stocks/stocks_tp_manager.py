"""
Take Profit Manager para STOCKS — 3 Bloques

Gestiona la toma de ganancias escalonada:
  Bloque 1 (50%): Upper_6 - Delta_ATR
  Bloque 2 (25%): Upper_6 + Delta_ATR
  Bloque 3 (25%): Trailing desde máximo

El Delta es dinámico según la fuerza de compra
medida con RVOL, MACD y posición vs EMA_20.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.core.logger import log_info, log_error, log_warning
from app.workers.alerts_service import send_telegram_message

MODULE = "TP_MANAGER"

# ── Configuración ─────────────────────────────
TP_CONFIG = {
    # Distribución de bloques
    'block1_pct':        0.50,   # 50%
    'block2_pct':        0.25,   # 25%
    'block3_pct':        0.25,   # 25%

    # Multiplicadores de ATR para el Delta
    'delta_strong':      0.5,    # fuerza fuerte → delta pequeño (esperar más)
    'delta_moderate':    1.0,    # fuerza moderada → delta estándar
    'delta_weak':        1.5,    # fuerza débil → delta grande (cerrar antes)

    # Trailing del bloque 3
    'block3_trail_pct':  0.03,   # 3% desde máximo
    'block3_trail_atr':  2.0,    # o 2× ATR desde máximo (el mayor de los dos)

    # Umbrales de fuerza de compra
    'rvol_strong':       2.0,
    'rvol_moderate':     1.2,
    'macd_threshold':    0.0,    # MACD histograma > 0 = positivo

    # Mínima ganancia para activar B1
    'min_gain_for_b1':   0.02,   # al menos 2% de ganancia antes de B1
}


# ═══════════════════════════════════════════
# CÁLCULO DE FUERZA DE COMPRA
# ═══════════════════════════════════════════

def calculate_buy_strength(snap: dict, df_daily: pd.DataFrame = None) -> dict:
    """
    Mide la fuerza de compra actual con 3 indicadores para determinar el Delta.

    Indicadores:
      1. RVOL: volumen relativo al promedio
      2. MACD: histograma positivo/negativo
      3. Precio vs EMA_20 (tendencia 4H/Daily)

    Retorna:
      strength: 'strong' | 'moderate' | 'weak'
      score:    float 0-3 (1 punto por indicador)
      details:  dict con cada indicador
    """
    score = 0
    details = {}

    # ── Indicador 1: RVOL ─────────────────────
    rvol = float(snap.get('rvol') or 1.0)
    if rvol >= TP_CONFIG['rvol_strong']:
        rvol_points = 1
        rvol_status = 'strong'
    elif rvol >= TP_CONFIG['rvol_moderate']:
        rvol_points = 0.5
        rvol_status = 'moderate'
    else:
        rvol_points = 0
        rvol_status = 'weak'

    score += rvol_points
    details['rvol'] = {'value': rvol, 'status': rvol_status, 'points': rvol_points}

    # ── Indicador 2: MACD Histograma ──────────
    macd_hist = float(snap.get('macd_histogram') or 0)
    macd_prev = float(snap.get('macd_histogram_prev') or 0)
    macd_growing = (macd_hist > TP_CONFIG['macd_threshold'] and macd_hist > macd_prev)

    if macd_growing:
        macd_points = 1
        macd_status = 'bullish_growing'
    elif macd_hist > 0:
        macd_points = 0.5
        macd_status = 'bullish_flat'
    else:
        macd_points = 0
        macd_status = 'bearish'

    score += macd_points
    details['macd'] = {'histogram': macd_hist, 'growing': macd_growing, 'status': macd_status}

    # ── Indicador 3: Precio vs EMA_20 ─────────
    price = float(snap.get('price') or 0)
    ema20 = float(snap.get('ema20') or snap.get('ema_20') or snap.get('basis') or 0)

    price_above_ema = (price > ema20 > 0)
    if price_above_ema:
        pct_above = (price - ema20) / ema20 * 100
        if pct_above >= 2.0:
            ema_points = 1
            ema_status = 'strong_above'
        else:
            ema_points = 0.5
            ema_status = 'slight_above'
    else:
        ema_points = 0
        ema_status = 'below'

    score += ema_points
    details['ema20'] = {'price': price, 'ema20': ema20, 'above': price_above_ema, 'status': ema_status}

    # ── Clasificar fuerza total ────────────────
    if score >= 2.5:
        strength = 'strong'
        delta_mult = TP_CONFIG['delta_strong']
    elif score >= 1.5:
        strength = 'moderate'
        delta_mult = TP_CONFIG['delta_moderate']
    else:
        strength = 'weak'
        delta_mult = TP_CONFIG['delta_weak']

    return {
        'strength': strength,
        'score': score,
        'delta_mult': delta_mult,
        'details': details,
    }


# ═══════════════════════════════════════════
# CALCULAR ATR (Average True Range)
# ═══════════════════════════════════════════

def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calcula el ATR de 14 períodos. Usa datos diarios (1D) para stocks."""
    if df is None or len(df) < period + 1:
        return 0.0

    df = df.copy()
    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    df['h-l'] = df['high'] - df['low']
    df['h-pc'] = abs(df['high'] - df['close'].shift(1))
    df['l-pc'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
    atr = float(df['tr'].rolling(period).mean().iloc[-1])
    return round(atr, 4)


# ═══════════════════════════════════════════
# CALCULAR LOS 3 BLOQUES DE TP
# ═══════════════════════════════════════════

def calculate_tp_blocks(
    ticker: str,
    entry_price: float,
    total_shares: int,
    snap: dict,
    df_daily: pd.DataFrame = None,
) -> dict:
    """
    Calcula los precios de los 3 bloques de TP.

    BLOQUE 1 (50%): Precio = Upper_6 - Delta (Delta = ATR_14 × delta_mult)
    BLOQUE 2 (25%): Precio = Upper_6 + Delta (o ajustado por fuerza)
    BLOQUE 3 (25%): Trailing desde el máximo alcanzado

    Retorna todos los precios y metadatos.
    """
    # Obtener Upper_6 de las bandas Fibonacci
    upper_6 = float(snap.get('upper_6') or 0)
    upper_5 = float(snap.get('upper_5') or 0)
    upper_4 = float(snap.get('upper_4') or 0)
    upper_3 = float(snap.get('upper_3') or 0)

    if upper_6 <= 0:
        log_warning(MODULE, f'{ticker}: Upper_6 no disponible')
        return {'error': 'Upper_6 no disponible'}

    # Calcular ATR
    atr = calculate_atr(df_daily, period=14)
    if atr <= 0:
        atr = entry_price * 0.02  # Fallback: 2% del precio

    # Calcular fuerza de compra
    strength_data = calculate_buy_strength(snap, df_daily)
    strength = strength_data['strength']
    delta_mult = strength_data['delta_mult']
    delta = atr * delta_mult

    # ── BLOQUE 1: Upper_4 (Banda conservadora) ─────────────
    # Usamos upper_4 (1.85 SD) como base para el primer retiro seguro
    b1_base = upper_4 if upper_4 > 0 else upper_6 * 0.95
    b1_price = b1_base - (delta * 0.5)
    
    min_gain = entry_price * (1 + TP_CONFIG['min_gain_for_b1'])
    if b1_price < min_gain:
        b1_price = min_gain
        b1_note = 'ajustado_min_gain'
    else:
        b1_note = 'bollinger_conservative'

    b1_shares = int(total_shares * TP_CONFIG['block1_pct'])

    # ── BLOQUE 2: Upper_5 (Banda Superior Bollinger 2.0 SD) ──
    # Sincronizamos con la Banda Superior sugerida por el usuario
    b2_base = upper_5 if upper_5 > 0 else upper_6
    
    if strength == 'strong':
        b2_price = b2_base + (delta * 0.5)
        b2_note = 'bollinger_upper_plus'
    elif strength == 'moderate':
        b2_price = b2_base
        b2_note = 'bollinger_upper_exact'
    else:
        b2_price = b2_base - (delta * 0.5)
        b2_note = 'bollinger_upper_early'

    if b2_price <= b1_price:
        b2_price = b1_price * 1.01
        b2_note += '_adjusted'

    b2_shares = int(total_shares * TP_CONFIG['block2_pct'])

    # ── BLOQUE 3: Trailing ────────────────────
    trail_pct = TP_CONFIG['block3_trail_pct']
    trail_atr_m = TP_CONFIG['block3_trail_atr']
    b3_shares = total_shares - b1_shares - b2_shares
    if b3_shares <= 0:
        b3_shares = 1

    return {
        'ticker': ticker,
        'entry_price': entry_price,
        'total_shares': total_shares,
        'atr_14': atr,
        'delta_value': round(delta, 4),
        'delta_method': f'atr_{strength}',
        'buy_strength': strength,
        'strength_score': strength_data['score'],
        'upper_6': upper_6,
        'block1': {
            'price': round(b1_price, 4),
            'shares': b1_shares,
            'pct': TP_CONFIG['block1_pct'],
            'note': b1_note,
            'upside': round((b1_price - entry_price) / entry_price * 100, 2),
        },
        'block2': {
            'price': round(b2_price, 4),
            'shares': b2_shares,
            'pct': TP_CONFIG['block2_pct'],
            'note': b2_note,
            'upside': round((b2_price - entry_price) / entry_price * 100, 2),
        },
        'block3': {
            'price': None,
            'shares': b3_shares,
            'pct': TP_CONFIG['block3_pct'],
            'trail_pct': trail_pct * 100,
            'trail_atr': trail_atr_m,
            'trail_ref': round(upper_6, 4),
            'note': 'trailing_dynamic',
        },
        # Campos para guardar directamente en BD
        'tp_block1_price': round(b1_price, 4),
        'tp_block2_price': round(b2_price, 4),
        'tp_block1_shares': b1_shares,
        'tp_block2_shares': b2_shares,
        'tp_block3_shares': b3_shares,
        'shares_remaining': total_shares,
    }


# ═══════════════════════════════════════════
# EVALUAR TP EN TIEMPO REAL (ciclo 5m)
# ═══════════════════════════════════════════

def evaluate_tp_blocks(
    position: dict,
    current_price: float,
    snap: dict,
    df_daily: pd.DataFrame = None,
) -> dict:
    """
    Evalúa en cada ciclo de 5m si se debe ejecutar alguno de los 3 bloques de TP.
    Retorna la acción a tomar.
    """
    entry_price = float(position.get('avg_price') or position.get('entry_price') or 0)
    b1_executed = bool(position.get('tp_block1_executed', False))
    b2_executed = bool(position.get('tp_block2_executed', False))
    b3_executed = bool(position.get('tp_block3_executed', False))
    b1_price = float(position.get('tp_block1_price') or 0)
    b2_price = float(position.get('tp_block2_price') or 0)
    b1_shares = int(position.get('tp_block1_shares') or 0)
    b2_shares = int(position.get('tp_block2_shares') or 0)
    b3_shares = int(position.get('tp_block3_shares') or 0)
    trail_high = float(position.get('tp_trailing_high') or current_price)
    atr = float(position.get('tp_atr_14') or (entry_price * 0.02))

    # Actualizar máximo alcanzado
    new_trail_high = max(trail_high, current_price)

    # Calcular trailing SL del bloque 3
    trail_pct = TP_CONFIG['block3_trail_pct']
    trail_atr = TP_CONFIG['block3_trail_atr']
    trail_by_pct = new_trail_high * (1 - trail_pct)
    trail_by_atr = new_trail_high - (trail_atr * atr)
    b3_trail_sl = max(trail_by_pct, trail_by_atr)
    b3_trail_sl = max(b3_trail_sl, entry_price)  # Nunca debajo de entry

    # ── BLOQUE 1: TP principal (50%) ──────────
    if not b1_executed and b1_price > 0:
        if current_price >= b1_price:
            return {
                'action': 'execute_block1',
                'block': 1,
                'shares': b1_shares,
                'price': current_price,
                'trigger_price': b1_price,
                'new_trail_high': new_trail_high,
                'b3_trail_sl': b3_trail_sl,
                'new_sl': entry_price,  # SL se mueve a entry (BE)
                'reason': f'B1 TP: precio {current_price:.2f} ≥ {b1_price:.2f} → vender {b1_shares} shares (50%)',
            }

    # ── BLOQUE 2: TP extendido (25%) ──────────
    if b1_executed and not b2_executed and b2_price > 0:
        current_strength = calculate_buy_strength(snap, df_daily)

        # Si fuerza cayó → cerrar B2 antes
        if current_strength['strength'] == 'weak' and current_price > b1_price * 1.005:
            return {
                'action': 'execute_block2_early',
                'block': 2,
                'shares': b2_shares,
                'price': current_price,
                'trigger_price': current_price,
                'new_trail_high': new_trail_high,
                'b3_trail_sl': b3_trail_sl,
                'new_sl': float(position.get('tp_block1_price') or entry_price),
                'reason': f'B2 TP early: fuerza débil ({current_strength["score"]:.1f}) → vender {b2_shares} shares',
            }

        if current_price >= b2_price:
            return {
                'action': 'execute_block2',
                'block': 2,
                'shares': b2_shares,
                'price': current_price,
                'trigger_price': b2_price,
                'new_trail_high': new_trail_high,
                'b3_trail_sl': b3_trail_sl,
                'new_sl': b1_price,
                'reason': f'B2 TP: precio {current_price:.2f} ≥ {b2_price:.2f} → vender {b2_shares} shares (25%)',
            }

    # ── BLOQUE 3: Trailing (25% restante) ─────
    if b1_executed and b2_executed and not b3_executed:
        # Opción A: Trailing SL hit
        if current_price <= b3_trail_sl and new_trail_high > b1_price:
            return {
                'action': 'execute_block3_trail',
                'block': 3,
                'shares': b3_shares,
                'price': current_price,
                'trigger_price': b3_trail_sl,
                'new_trail_high': new_trail_high,
                'b3_trail_sl': b3_trail_sl,
                'reason': f'B3 Trailing: precio bajó al trailing SL {b3_trail_sl:.2f} (max={new_trail_high:.2f})',
            }

        # Opción B: Señal SELL aparece
        pine_signal = str(snap.get('pinescript_signal', ''))
        fib_zone = int(snap.get('fibonacci_zone', 0))
        if pine_signal == 'Sell' or fib_zone >= 5:
            return {
                'action': 'execute_block3_signal',
                'block': 3,
                'shares': b3_shares,
                'price': current_price,
                'trigger_price': current_price,
                'new_trail_high': new_trail_high,
                'b3_trail_sl': b3_trail_sl,
                'reason': f'B3 señal: Pine={pine_signal} Fib={fib_zone} → vender {b3_shares} shares',
            }

    # ── Solo actualizar el trailing high ──────
    if new_trail_high > trail_high:
        return {
            'action': 'update_trailing',
            'new_trail_high': new_trail_high,
            'b3_trail_sl': b3_trail_sl,
            'reason': f'Trailing actualizado: {new_trail_high:.2f} (SL B3: {b3_trail_sl:.2f})',
        }

    return {
        'action': 'hold',
        'new_trail_high': new_trail_high,
        'b3_trail_sl': b3_trail_sl,
        'reason': 'Sin trigger activo',
    }


# ═══════════════════════════════════════════
# EJECUTAR VENTA PARCIAL
# ═══════════════════════════════════════════

async def execute_partial_sell(
    ticker: str,
    position: dict,
    block: int,
    shares: int,
    price: float,
    action: str,
    new_sl: float,
    new_trail_high: float,
    b3_trail_sl: float,
    supabase,
    ib_provider=None,
) -> dict:
    """Ejecuta la venta parcial de un bloque y actualiza la posición en Supabase."""
    pos_id = position.get('id')
    entry_price = float(position.get('avg_price') or position.get('entry_price') or 0)
    shares_rem = float(position.get('shares_remaining') or position.get('shares') or 0)

    # Calcular P&L del bloque
    pnl_per_share = price - entry_price
    pnl_total = pnl_per_share * shares
    pnl_pct = pnl_per_share / entry_price * 100 if entry_price > 0 else 0

    log_info(MODULE,
        f'✅ TP B{block} [{ticker}]: vender {shares} shares '
        f'@ ${price:.2f} | P&L: +${pnl_total:.2f} (+{pnl_pct:.2f}%)'
    )

    # Paper mode: solo registrar en BD
    mode = position.get('mode', 'paper')

    if mode == 'live' and ib_provider:
        try:
            order = await ib_provider.place_order(
                ticker=ticker, side='sell', order_type='market', shares=shares,
            )
            log_info(MODULE, f'IB order: {order}')
        except Exception as e:
            log_error(MODULE, f'Error IB order: {e}')

    # Actualizar posición en Supabase
    new_shares_rem = shares_rem - shares
    update_data = {
        f'tp_block{block}_executed': True,
        f'tp_block{block}_shares': shares,
        f'tp_block{block}_pnl': round(pnl_total, 4),
        'shares_remaining': new_shares_rem,
        'tp_trailing_high': new_trail_high,
        'tp_trailing_sl': b3_trail_sl,
        'current_price': price,
    }

    # Actualizar SL si se indicó
    if new_sl and new_sl > 0:
        update_data['sl_dynamic_price'] = new_sl
        update_data['stop_loss'] = new_sl

    # Si se vendieron todas las shares → cerrar
    if new_shares_rem <= 0:
        update_data['status'] = 'closed'
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        update_data['sl_close_reason'] = f'tp_b{block}_full'

    try:
        supabase.table('stocks_positions') \
            .update(update_data) \
            .eq('id', pos_id) \
            .execute()
    except Exception as e:
        log_error(MODULE, f'Error actualizando posición: {e}')

    # Registrar en stocks_orders
    try:
        supabase.table('stocks_orders').insert({
            'ticker': ticker,
            'order_type': 'market',
            'direction': 'sell',
            'shares': shares,
            'market_price': price,
            'rule_code': f'TP_B{block}',
            'status': 'filled',
            'filled_price': price,
            'filled_at': datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log_error(MODULE, f'Error registrando orden: {e}')

    # Telegram notification
    try:
        closed_msg = '🎯 Posición cerrada completamente' if new_shares_rem <= 0 else '⏳ Esperando siguiente bloque...'
        await send_telegram_message(
            f'✅ TP BLOQUE {block} [{ticker}]\n'
            f'Vendidas: {shares} shares\n'
            f'Precio: ${price:.2f}\n'
            f'Ganancia: +${pnl_total:.2f} (+{pnl_pct:.2f}%)\n'
            f'Shares restantes: {int(new_shares_rem)}\n'
            f'Nuevo SL: ${new_sl:.2f}\n'
            f'─────────────────\n'
            f'{closed_msg}'
        )
    except Exception as e:
        log_warning(MODULE, f'Telegram notification failed: {e}')

    return {
        'success': True,
        'block': block,
        'shares_sold': shares,
        'price': price,
        'pnl_usd': pnl_total,
        'pnl_pct': pnl_pct,
        'shares_remaining': new_shares_rem,
    }
