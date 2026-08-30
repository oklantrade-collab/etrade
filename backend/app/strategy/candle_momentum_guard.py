"""
Candle Momentum Guard — eTrader v5.0
===================================
Guardián de Salidas por Momentum de Velas (Crypto & Forex).

Controla y condiciona los 10 disparadores de salida del sistema:
  Crypto:
    1.1 Max Holding (hold_agresivo, hold_moderado, hold_explosivo)
    1.2 Early Profit Protect 5M (early_profit_protect_ema_5m)
    1.3 TP Bollinger Exhaustion (Bb33_BOLLINGER_EXHAU, range_bollinger_touch_exit)
    1.4 EREP Timeout 60m (erep_timeout_60m)
    1.5 Trailing Stop Prematuro (ts_close anticipado)
  Forex:
    2.1 SAR Phase Change (sar_phase_change_fx, sar_phase_change_fx_delayed)
    2.2 TP Escalonado Adaptativo (tp_forex_adaptive_v5_l2/l3 con pocos pips)
    2.3 Cruce de Ruido en 5M (signal_reversal_fx)
    2.4 EREP Breakeven P3 (cierre prematuro a $0)
    2.5 Weekend Close (Viernes 21:00 UTC - Prioridad de Seguridad Absoluta)

Lógica de Decisión:
  - PARA LONG:
      1.1 Tendencia Fuerte: EMA20 15M ascendente (>+0.02%) y EMA3 > EMA9 > EMA20 en 15M:
          BLOQUEA salidas excepto si:
            1.1.1 En 5M (cerrada): EMA3 < EMA9 < EMA20
            1.1.2 En 15M: Close > Bollinger Superior y EMA3 pendiente negativa
            1.1.3 En 15M: Distancia entre EMA3 y EMA9 <= 0.05%
      1.2 Lateral: EMA20 15M lateral/descendente (<=+0.02%) o Distancia <= 0.05% -> PERMITE salidas.
      1.3 Descendente: EMA20 15M descendente (<-0.02%) o EMA3 < EMA9 -> PERMITE salidas.

  - PARA SHORT: Simétrico e inverso.
  - ANTI-ROUND TRIP: Si PnL >= +4.0% (Crypto) o >= 25 pips (Forex) y precio perfora EMA9 15M -> PERMITE salida para asegurar ganancia.
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Tuple, Dict, Any, Optional

from app.core.logger import log_info, log_warning, log_error

MODULE = "MOMENTUM_GUARD"

# Cooldown en memoria para evitar spam de alertas en Telegram (clave: symbol_posId)
_BLOCKED_ALERT_COOLDOWN: Dict[str, float] = {}
COOLDOWN_SECONDS = 900  # 15 minutos entre alertas por posición


def _send_telegram_async(message: str):
    """Envía alerta a Telegram sin bloquear el hilo principal."""
    try:
        from app.workers.alerts_service import send_telegram_message
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            loop.create_task(send_telegram_message(message))
        else:
            asyncio.run(send_telegram_message(message))
    except Exception as e:
        log_warning(MODULE, f"Error enviando notificación telegram de Momentum Guard: {e}")


def calculate_ema_series(series: pd.Series, span: int) -> pd.Series:
    """Calcula la serie EMA para una columna de precios."""
    return series.ewm(span=span, adjust=False).mean()


def calculate_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calcula Bandas de Bollinger (Media, Superior, Inferior)."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return sma, upper, lower


def get_ema20_slope_pct(df_15m: pd.DataFrame, lookback: int = 3) -> float:
    """
    Calcula la pendiente porcentual de la EMA20 en 15M sobre las últimas `lookback` velas.
    Retorna porcentaje de cambio (ej. +0.05 para +0.05%).
    """
    if df_15m is None or len(df_15m) < (20 + lookback):
        return 0.0

    col = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else None)
    if not col:
        return 0.0

    closes = pd.to_numeric(df_15m[col], errors='coerce').dropna()
    if len(closes) < (20 + lookback):
        return 0.0

    ema20 = calculate_ema_series(closes, 20)
    ema20_curr = float(ema20.iloc[-1])
    ema20_prev = float(ema20.iloc[-1 - lookback])

    if ema20_prev <= 0:
        return 0.0

    slope_pct = ((ema20_curr - ema20_prev) / ema20_prev) * 100.0
    return float(slope_pct)


def get_ema3_slope_pct(df_15m: pd.DataFrame, lookback: int = 1) -> float:
    """Calcula la pendiente de la EMA3 en 15M (para detectar giros)."""
    if df_15m is None or len(df_15m) < (5 + lookback):
        return 0.0

    col = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else None)
    if not col:
        return 0.0

    closes = pd.to_numeric(df_15m[col], errors='coerce').dropna()
    if len(closes) < (5 + lookback):
        return 0.0

    ema3 = calculate_ema_series(closes, 3)
    ema3_curr = float(ema3.iloc[-1])
    ema3_prev = float(ema3.iloc[-1 - lookback])

    if ema3_prev <= 0:
        return 0.0

    return float(((ema3_curr - ema3_prev) / ema3_prev) * 100.0)


def get_ema_values(df: pd.DataFrame) -> Tuple[float, float, float]:
    """Extrae los valores más recientes de EMA3, EMA9 y EMA20."""
    if df is None or len(df) < 20:
        return 0.0, 0.0, 0.0

    col = 'close' if 'close' in df.columns else ('c' if 'c' in df.columns else None)
    if not col:
        return 0.0, 0.0, 0.0

    closes = pd.to_numeric(df[col], errors='coerce').dropna()
    if len(closes) < 20:
        return 0.0, 0.0, 0.0

    ema3 = float(calculate_ema_series(closes, 3).iloc[-1])
    ema9 = float(calculate_ema_series(closes, 9).iloc[-1])
    ema20 = float(calculate_ema_series(closes, 20).iloc[-1])

    return ema3, ema9, ema20


def calculate_rsi_series(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcula la serie RSI para una columna de precios."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def detect_rsi_divergence(df_15m: pd.DataFrame, is_long: bool, lookback: int = 15) -> Tuple[bool, str]:
    """
    Detecta divergencias regulares entre Precio y RSI en 15M (Propuesta 5).
    """
    if df_15m is None or len(df_15m) < (lookback + 14):
        return False, "Datos insuficientes para divergencia"

    col = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else None)
    if not col:
        return False, "Columna close ausente"

    closes = pd.to_numeric(df_15m[col], errors='coerce').dropna()
    rsi = calculate_rsi_series(closes, 14)
    
    recent_closes = closes.iloc[-lookback:]
    recent_rsi = rsi.iloc[-lookback:]

    if len(recent_closes) < lookback:
        return False, "Velas recientes insuficientes"

    mid = lookback // 2
    if is_long:
        p1_price = float(recent_closes.iloc[:mid].max())
        p2_price = float(recent_closes.iloc[mid:].max())
        p1_rsi = float(recent_rsi.iloc[:mid].max())
        p2_rsi = float(recent_rsi.iloc[mid:].max())

        if p2_price > p1_price and (p2_rsi < p1_rsi - 2.5) and p1_rsi > 55:
            return True, f"Divergencia Bajista Regular 15M (Precio: {p1_price:.2f}->{p2_price:.2f} | RSI: {p1_rsi:.1f}->{p2_rsi:.1f})"
    else:
        p1_price = float(recent_closes.iloc[:mid].min())
        p2_price = float(recent_closes.iloc[mid:].min())
        p1_rsi = float(recent_rsi.iloc[:mid].min())
        p2_rsi = float(recent_rsi.iloc[mid:].min())

        if p2_price < p1_price and (p2_rsi > p1_rsi + 2.5) and p1_rsi < 45:
            return True, f"Divergencia Alcista Regular 15M (Precio: {p1_price:.2f}->{p2_price:.2f} | RSI: {p1_rsi:.1f}->{p2_rsi:.1f})"

    return False, "Sin divergencia"


def get_anti_round_trip_threshold(symbol: str, is_forex: bool) -> float:
    """
    Retorna el umbral adaptativo para la protección Anti-Round Trip (Propuesta 1).
    - Crypto Tier 1 (BTC, ETH): +3.0%
    - Crypto Altcoins (SOL, ADA, etc.): +1.8%
    - Forex Majors: 15 pips
    - Forex Metales (XAUUSD): 40 pips
    """
    sym = (symbol or "").upper().replace("/", "")
    if is_forex:
        if "XAU" in sym or "GOLD" in sym:
            return 40.0
        return 15.0
    else:
        if sym in ["BTCUSDT", "ETHUSDT", "BTC", "ETH"]:
            return 3.0
        return 1.8


def should_allow_exit(
    position: dict,
    current_price: float,
    df_15m: Optional[pd.DataFrame],
    df_5m: Optional[pd.DataFrame] = None,
    exit_rule_id: str = "unknown",
    market_type: str = "crypto_futures",
    snap: Optional[dict] = None
) -> Tuple[bool, str]:
    """
    Determina si se debe PERMITIR (True) o BLOQUEAR (False) una salida.
    """
    symbol = position.get('symbol', 'UNKNOWN')
    pos_id = str(position.get('id', ''))
    side = str(position.get('side', 'long')).lower()
    is_long = side in ('long', 'buy')

    # ── REGLA ESPECIAL 2.5: WEEKEND CLOSE EN FOREX TIENE PRIORIDAD ABSOLUTA ──
    if exit_rule_id in ('weekend_close', 'WEEKEND_CLOSE', '2.5'):
        return True, "Weekend Close de Forex tiene prioridad absoluta de seguridad ante cierre interbancario."

    entry_p = float(position.get('avg_entry_price') or position.get('entry_price') or 0.0)
    if entry_p <= 0 or current_price <= 0:
        return True, "Precios inválidos; permitir salida por defecto."
    
    is_forex = "forex" in market_type.lower() or any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
    pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001

    if is_long:
        pnl_pct = ((current_price - entry_p) / entry_p) * 100.0
        pnl_pips = (current_price - entry_p) / pip_sz if pip_sz > 0 else 0.0
    else:
        pnl_pct = ((entry_p - current_price) / entry_p) * 100.0
        pnl_pips = (entry_p - current_price) / pip_sz if pip_sz > 0 else 0.0

    if pnl_pct <= 0:
        return True, f"Posición en pérdida ({pnl_pct:.2f}%); el guardián de momentum no bloquea salidas de control de riesgo."

    if df_15m is None or len(df_15m) < 20:
        return True, "Datos de 15M insuficientes para evaluar momentum; permitir salida."

    ema3_15, ema9_15, ema20_15 = get_ema_values(df_15m)
    slope_ema20 = get_ema20_slope_pct(df_15m, lookback=3)
    slope_ema3 = get_ema3_slope_pct(df_15m, lookback=1)
    dist_ema3_ema9_pct = (abs(ema3_15 - ema9_15) / current_price) * 100.0
    is_compressed = dist_ema3_ema9_pct <= 0.05

    ema3_5, ema9_5, ema20_5 = (0.0, 0.0, 0.0)
    if df_5m is not None and len(df_5m) >= 20:
        ema3_5, ema9_5, ema20_5 = get_ema_values(df_5m)

    col_15 = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else None)
    closes_15 = pd.to_numeric(df_15m[col_15], errors='coerce').dropna()
    _, bb_upper_15, bb_lower_15 = calculate_bollinger_bands(closes_15, period=20, num_std=2.0)
    upper_bb_val = float(bb_upper_15.iloc[-1]) if len(bb_upper_15) > 0 else 0.0
    lower_bb_val = float(bb_lower_15.iloc[-1]) if len(bb_lower_15) > 0 else 0.0

    # ── IDENTIFICACIÓN DE ESTRATEGIAS DE REBOTE (Band-to-Band Traversal) ──
    rule_code = str(position.get('rule_code') or position.get('strategy') or position.get('rule_entry') or '').upper()
    is_rebote_strategy = any(k in rule_code for k in ('REB', 'TRAVERSAL', 'CLIMAX', 'FLOOR', 'CEILING', 'PULLBACK', 'DD11', 'DD12', 'AA12', 'BB12', 'REBOTE'))

    # ── PROTECCIÓN ESPECIAL PARA REBOTE BANDA A BANDA ──
    if is_rebote_strategy:
        if is_long:
            # En LONG Rebote: proteger el recorrido hasta tocar la Banda Superior o sobrecompra
            is_target_reached = (upper_bb_val > 0 and current_price >= upper_bb_val * 0.998) or (pnl_pct >= 8.0)
            if is_target_reached:
                return True, f"Rebote Traversal LONG: Objetivo alcanzado en Banda Superior ({current_price:.4f} >= {upper_bb_val:.4f}). Salida con beneficio permitida."
            else:
                _handle_blocked_exit(symbol, pos_id, exit_rule_id, "LONG_REBOTE", pnl_pct, ema3_15, ema9_15, ema20_15, slope_ema20)
                return False, f"MOMENTUM_GUARD BLOQUEA '{exit_rule_id}': Acompañando Rebote Traversal hacia Bollinger Superior (PnL: +{pnl_pct:.2f}%)."
        else:
            # En SHORT Rebote: proteger el recorrido hasta tocar la Banda Inferior o sobreventa
            is_target_reached = (lower_bb_val > 0 and current_price <= lower_bb_val * 1.002) or (pnl_pct >= 8.0)
            if is_target_reached:
                return True, f"Rebote Traversal SHORT: Objetivo alcanzado en Banda Inferior ({current_price:.4f} <= {lower_bb_val:.4f}). Salida con beneficio permitida."
            else:
                _handle_blocked_exit(symbol, pos_id, exit_rule_id, "SHORT_REBOTE", pnl_pct, ema3_15, ema9_15, ema20_15, slope_ema20)
                return False, f"MOMENTUM_GUARD BLOQUEA '{exit_rule_id}': Acompañando Rebote Traversal hacia Bollinger Inferior (PnL: +{pnl_pct:.2f}%)."

    # ── PROTECCIÓN ANTI-ROUND TRIP V2 PURO (+4.0% en Crypto / 25 pips en Forex) ──
    art_threshold = 25.0 if is_forex else 4.0
    is_art_triggered = (pnl_pips >= art_threshold) if is_forex else (pnl_pct >= art_threshold)
    if is_art_triggered:
        if is_long and current_price < ema9_15:
            return True, f"Anti-Round Trip V2 activado: Ganancia alta (+{pnl_pct:.2f}%) y precio perforó EMA9 15M. Cerrando para asegurar ganancia."
        elif not is_long and current_price > ema9_15:
            return True, f"Anti-Round Trip V2 activado: Ganancia alta (+{pnl_pct:.2f}%) y precio superó EMA9 15M. Cerrando para asegurar ganancia."

    # ── DETECCIÓN DE DIVERGENCIA RSI 15M ──
    has_div, div_msg = detect_rsi_divergence(df_15m, is_long, lookback=15)

    # ════════════════════════════════════════════════════════════════════════
    # EVALUACIÓN PARA POSICIONES LONG
    # ════════════════════════════════════════════════════════════════════════
    if is_long:
        is_strong_trend = (slope_ema20 > 0.02) and (ema3_15 > ema9_15 > ema20_15)
        if is_strong_trend:
            # 1.1.1 Debilitamiento en 5M
            if (ema3_5 > 0 and ema9_5 > 0 and ema20_5 > 0) and (ema3_5 < ema9_5 < ema20_5):
                return True, f"Long 1.1.1: Debilitamiento rápido en 5M confirmado (EMA3={ema3_5:.4f} < EMA9={ema9_5:.4f} < EMA20={ema20_5:.4f}). Salida permitida."

            # 1.1.2 Bollinger Superior + Giro EMA3
            if (upper_bb_val > 0 and current_price > upper_bb_val) and (slope_ema3 < 0):
                return True, f"Long 1.1.2: Precio superó Bollinger Superior ({current_price:.4f} > {upper_bb_val:.4f}) y EMA3 giró a la baja ({slope_ema3:.3f}%). Salida permitida."

            # 1.1.3 Compresión
            if is_compressed:
                return True, f"Long 1.1.3: Compresión de EMAs 15M detectada ({dist_ema3_ema9_pct:.4f}% <= 0.05%). Salida permitida."

            # 1.1.4 Divergencia RSI
            if has_div:
                return True, f"Long 1.1.4: {div_msg}. Salida por divergencia técnica permitida."

            _handle_blocked_exit(symbol, pos_id, exit_rule_id, "LONG", pnl_pct, ema3_15, ema9_15, ema20_15, slope_ema20)
            return False, f"MOMENTUM_GUARD BLOQUEA '{exit_rule_id}': Tendencia 15M fuerte para LONG. Dejando correr ganancias (+{pnl_pct:.2f}%)."

        if (slope_ema20 <= 0.02) or is_compressed or has_div:
            return True, f"Long 1.2: Mercado lateral en 15M. Salida permitida."
        if (slope_ema20 < -0.02) or (ema3_15 < ema9_15):
            return True, f"Long 1.3: Tendencia 15M giró a la baja. Salida permitida."

    # ════════════════════════════════════════════════════════════════════════
    # EVALUACIÓN PARA POSICIONES SHORT (INVERSO)
    # ════════════════════════════════════════════════════════════════════════
    else:
        is_strong_trend_short = (slope_ema20 < -0.02) and (ema3_15 < ema9_15 < ema20_15)
        if is_strong_trend_short:
            # 2.1.1 Debilitamiento en 5M
            if (ema3_5 > 0 and ema9_5 > 0 and ema20_5 > 0) and (ema3_5 > ema9_5 > ema20_5):
                return True, f"Short 2.1.1: Rebote rápido en 5M confirmado. Salida permitida."

            # 2.1.2 Bollinger Inferior + Rebote EMA3
            if (lower_bb_val > 0 and current_price < lower_bb_val) and (slope_ema3 > 0):
                return True, f"Short 2.1.2: Precio perforó Bollinger Inferior ({current_price:.4f} < {lower_bb_val:.4f}) y EMA3 rebotó ({slope_ema3:.3f}%). Salida permitida."

            # 2.1.3 Compresión
            if is_compressed:
                return True, f"Short 2.1.3: Compresión de EMAs 15M detectada ({dist_ema3_ema9_pct:.4f}% <= 0.05%). Salida permitida."

            # 2.1.4 Divergencia RSI
            if has_div:
                return True, f"Short 2.1.4: {div_msg}. Salida por divergencia técnica permitida."

            _handle_blocked_exit(symbol, pos_id, exit_rule_id, "SHORT", pnl_pct, ema3_15, ema9_15, ema20_15, slope_ema20)
            return False, f"MOMENTUM_GUARD BLOQUEA '{exit_rule_id}': Tendencia 15M fuerte para SHORT. Dejando correr ganancias (+{pnl_pct:.2f}%)."

        if (slope_ema20 >= -0.02) or is_compressed or has_div:
            return True, f"Short 2.2: Mercado lateral en 15M. Salida permitida."
        if (slope_ema20 > 0.02) or (ema3_15 > ema9_15):
            return True, f"Short 2.3: Tendencia 15M giró al alza. Salida permitida."

    return True, "Condición neutral; permitir salida."

    return True, "Condición neutral; permitir salida."


def _handle_blocked_exit(
    symbol: str,
    pos_id: str,
    exit_rule_id: str,
    side: str,
    pnl_pct: float,
    ema3: float,
    ema9: float,
    ema20: float,
    slope: float
):
    """Registra en logs y envía alerta a Telegram con cooldown inteligente."""
    log_info(
        MODULE,
        f"🛡️ [BLOQUEO POR MOMENTUM] Salida '{exit_rule_id}' BLOQUEADA para {symbol} ({side}). "
        f"Tendencia 15M fuerte (EMA3={ema3:.4f}, EMA9={ema9:.4f}, EMA20={ema20:.4f}, pendiente={slope:.3f}%). "
        f"Dejando correr ganancias (PnL: +{pnl_pct:.2f}%)."
    )

    alert_key = f"{symbol}_{pos_id}_{exit_rule_id}"
    now = time.time()
    last_sent = _BLOCKED_ALERT_COOLDOWN.get(alert_key, 0.0)

    if (now - last_sent) >= COOLDOWN_SECONDS:
        _BLOCKED_ALERT_COOLDOWN[alert_key] = now
        msg = (
            f"🛡️ <b>MOMENTUM GUARD: SALIDA BLOQUEADA</b>\n\n"
            f"<b>Activo:</b> {symbol} ({side})\n"
            f"<b>Disparador rechazado:</b> <code>{exit_rule_id}</code>\n"
            f"<b>Ganancia actual:</b> +{pnl_pct:.2f}%\n"
            f"<b>Estructura 15M:</b> EMA3={ema3:.4f} | EMA9={ema9:.4f} | EMA20={ema20:.4f}\n"
            f"<b>Acción:</b> Tendencia intacta — dejando correr el trade para maximizar beneficio."
        )
        _send_telegram_async(msg)
