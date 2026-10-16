"""
eTrade Stocks — Alpha Runner Scanner & 5m Momentum Engine
==========================================================
Escanea y clasifica en tiempo real los Top Gainers del mercado estadounidense:
1. Filtra ETFs inversos 2X, derivados y cascarones ilíquidos (<1M vol, <$15M cap).
2. Calcula la Fuerza Compradora en 5 minutos (velocidad y dirección de empuje).
3. Pondera el Catalizador de Noticias (Tier 1 FDA/Patentes +25, Tier 2 Earnings +15, Tier 3 PR +10).
4. Determina el Semáforo Visual de Entrada:
   - PULLBACK (🟢 Comprable): En soporte saludable (no en pico).
   - CLIMAX (🟡 Esperar): En el techo del día o sobreextendido.
   - MONITORING (⚪ Monitoreando): En consolidación.
5. Doble Canal: Conexión primaria con IBKR TWS Bridge, respaldo con Yahoo Finance.
"""

import time
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import pandas as pd

from app.core.logger import log_info, log_warning, log_error
from app.stocks.news_catalyst_service import fetch_stock_news
from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv

MODULE = "ALPHA_RUNNER_SCANNER"

_SCAN_CACHE = {
    "timestamp": 0.0,
    "data": [],
}
CACHE_TTL = 45.0  # 45 segundos para mantenerlo súper fluido


def _is_ib_connected() -> bool:
    """Verifica si el bridge de IBKR en APOLO está reportando latencia en los últimos 60s."""
    try:
        from app.stocks.stocks_order_executor import is_ib_bridge_alive
        return is_ib_bridge_alive()
    except Exception:
        return False


_DAILY_BB_CACHE: Dict[str, tuple] = {}  # { ticker: (timestamp, sma20, bb_upper, bb_lower) }

def get_daily_bollinger_metrics(ticker: str, current_price: float) -> tuple:
    """Calcula SMA20, BB Upper y room_to_bb_upper en gráfico diario (1D) con cache de 1 hora."""
    clean_ticker = ticker.replace("/", "").replace(".", "").upper().strip()
    now_ts = time.time()
    cached = _DAILY_BB_CACHE.get(clean_ticker)
    if cached and (now_ts - cached[0] < 3600):
        sma20, bb_upper, bb_lower = cached[1], cached[2], cached[3]
    else:
        try:
            import yfinance as yf
            t = yf.Ticker(clean_ticker)
            df_daily = t.history(period="60d", interval="1d")
            if df_daily is not None and len(df_daily) >= 20:
                c = df_daily["Close"]
                sma20 = float(c.rolling(20).mean().iloc[-1])
                std20 = float(c.rolling(20).std().iloc[-1])
                bb_upper = float(sma20 + (2.0 * std20))
                bb_lower = float(sma20 - (2.0 * std20))
                _DAILY_BB_CACHE[clean_ticker] = (now_ts, sma20, bb_upper, bb_lower)
            else:
                sma20, bb_upper, bb_lower = current_price, current_price * 1.3, current_price * 0.7
        except Exception:
            sma20, bb_upper, bb_lower = current_price, current_price * 1.3, current_price * 0.7

    room_to_bb = ((bb_upper - current_price) / current_price * 100.0) if current_price > 0 else 0.0
    return round(sma20, 2), round(bb_upper, 2), round(room_to_bb, 1)


def calculate_semaphore_and_buying_force(
    price: float,
    change_pct: float,
    day_high: float,
    day_low: float,
    open_price: float,
    volume: int,
    avg_volume: int,
    news_bonus: int = 0,
    is_ema3_1h_ascending: bool = True,
    ema3_slope_1h: float = 0.0,
    is_ema3_above_ema9: bool = True,
    sipv_upper_rejection: bool = False,
    delta_p_5m: Optional[float] = None,
    gap_pct: Optional[float] = None,
    candle_1_green: bool = True,
    adx_5m: float = 25.0,
    plus_di_5m: float = 25.0,
    minus_di_5m: float = 15.0,
    open_ge_close: bool = True,
    room_to_bb_upper_1d: Optional[float] = None,
    sma20_1d: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calcula la Fuerza Compradora (0-100), Semáforo Visual y Rank Score:
    - 🔴 DESCENDING: EMA3 de 1H plana o en caída (penalización severa -45 pts, prohibido comprar).
    - ⚪ BELOW_EMA9: EMA3 <= EMA9 en 1H (penalización -10 pts, sin confirmación alcista horaria).
    - 🟡 EXHAUSTION_GAP: Gap Up > +25% (penalización -20 pts, riesgo de dilución/clímax pre-market, Filtro Anti-LQDA).
    - 🟢 SWEET_SPOT: Gap orgánico (+5% a +25%) con vela 1 verde, +DI > -DI y ADX >= 18 (bonus +30 pts, Caso WFF).
    - 🟡 CLIMAX: Sobreextendida en el High o con rechazo SIPV superior.
    - 🟢 PULLBACK: Acción en tendencia fuerte con EMA3 1H ascendente y sobre EMA9 con descanso controlado (1.5% a 7.5%).
    - ⚪ MONITORING: En rango normal.
    """
    if price <= 0:
        return {
            "buying_force_5m": 50,
            "delta_p_5m": 0.0,
            "semaphore": "MONITORING",
            "semaphore_label": "⚪ MONITOREO",
            "semaphore_color": "#94A3B8",
            "semaphore_tip": "Sin datos de precio",
            "rank_score": 50.0,
            "rvol": 1.0,
        }

    # 1. Posición dentro del rango del día (0.0 a 1.0)
    day_range = max(1e-4, day_high - day_low)
    dist_from_high_pct = ((day_high - price) / price * 100.0) if price > 0 else 0.0
    range_pos = (price - day_low) / day_range

    # 2. RVOL (Volumen Relativo)
    rvol = (volume / max(1, avg_volume)) if avg_volume > 0 else 1.0

    # 3. Estimación de delta 5m si no viene explícito
    if delta_p_5m is None:
        delta_p_5m = round(min(5.0, max(-3.0, (change_pct * 0.08) * (1.0 if range_pos >= 0.5 else -0.5))), 2)

    # 4. Fuerza Compradora 5m (0 a 100)
    momentum_subscore = min(35.0, max(0.0, change_pct * 0.4))
    range_subscore = range_pos * 25.0
    rvol_subscore = min(20.0, rvol * 4.0)
    news_subscore = min(20.0, news_bonus * 0.8)

    raw_buying_force = momentum_subscore + range_subscore + rvol_subscore + news_subscore

    # Castigo severo si el delta de 5m es negativo (presión vendedora activa en la ventana):
    if delta_p_5m < 0:
        penalty_5m = min(40.0, abs(delta_p_5m) * 15.0)
        raw_buying_force -= penalty_5m

    # Castigo severo si la EMA3 de 1H está plana o descendente:
    if not is_ema3_1h_ascending:
        raw_buying_force = min(raw_buying_force * 0.5, 30.0)
    elif not is_ema3_above_ema9:
        # Tope de fuerza si aún no ha roto por encima de EMA9 en 1H
        raw_buying_force = min(raw_buying_force, 45.0)
    has_room_to_bb = (room_to_bb_upper_1d is not None and room_to_bb_upper_1d >= 20.0)
    is_super_runner_expansion = (
        gap_pct is not None and gap_pct >= 5.0 and has_room_to_bb and rvol >= 1.5 and plus_di_5m >= minus_di_5m
    )

    # Castigo o bonificación de fuerza compradora para Gaps:
    if is_super_runner_expansion:
        # SUPER-RUNNER EXPANSION: No se castiga la fuerza compradora; tiene autopista en 1D y volumen institucional
        raw_buying_force += min(25.0, room_to_bb_upper_1d * 0.25)
    elif gap_pct is not None and gap_pct > 25.0:
        # Castigo de fuerza compradora para Gaps excesivos por sobreextensión en apertura (sin espacio 1D)
        raw_buying_force = min(raw_buying_force, 45.0)

    buying_force = int(round(min(100.0, max(5.0, raw_buying_force))))

    # 5. Determinación del Semáforo Visual y Ajuste al Ranking
    # CASO A: EMA3 DE 1H PLANA O DESCENDENTE (Prioridad de bloqueo)
    if not is_ema3_1h_ascending:
        semaphore = "DESCENDING"
        sem_label = "🔴 EMA3 1H DESCENDENTE (AGOTAMIENTO)"
        sem_color = "#EF4444"
        sem_tip = f"EMA3 de 1H cayendo ({ema3_slope_1h:+.4f}). Fase de distribución. PROHIBIDO COMPRAR."
        setup_bonus = -45.0
    # CASO A.2: EMA3 1H <= EMA9 1H (SIN CONFIRMACIÓN ALCISTA EN 1H)
    elif not is_ema3_above_ema9:
        semaphore = "BELOW_EMA9"
        sem_label = "⚪ BAJO EMA9 1H (SIN CRUCE)"
        sem_color = "#94A3B8"
        sem_tip = "EMA3 <= EMA9 en 1H. Falta cruce alcista y confirmación de tendencia en 1 hora. Entrada no permitida."
        setup_bonus = -10.0
    # CASO A.2.5: SUPER-RUNNER EXPANSION (OPEN GAP UP CON ESPACIO LIBRE A BOLLINGER SUPERIOR 1D)
    elif is_super_runner_expansion and candle_1_green:
        semaphore = "EXPANSION_RUNNER"
        sem_label = f"🟢 SUPER-RUNNER EXPANSION (+{room_to_bb_upper_1d:.0f}% A BB 1D)"
        sem_color = "#10B981"
        sem_tip = f"Open Gap Up (+{gap_pct:.1f}%) con autopista libre hasta la Banda Superior de Bollinger 1D (+{room_to_bb_upper_1d:.1f}%). Reversión desde el fondo confirmada con RVOL {rvol:.1f}x. COMPRA HABILITADA."
        setup_bonus = 35.0
    # CASO A.3: CANDADO GAP EXHAUSTION (> 25% EN APERTURA / FILTRO ANTI-LQDA)
    elif gap_pct is not None and gap_pct > 25.0:
        semaphore = "EXHAUSTION_GAP"
        sem_label = f"🟡 CLÍMAX GAP (+{gap_pct:.1f}% > 25%)"
        sem_color = "#F59E0B"
        sem_tip = f"Gap de apertura excesivo (+{gap_pct:.1f}% > 25%). Riesgo extremo de agotamiento y dilución pre-market (Filtro Anti-LQDA). Prohibido comprar en primeros 45m."
        setup_bonus = -20.0
    # CASO B: RECHAZO SIPV EN TECHO (Mecha superior prominente en 1H)
    elif sipv_upper_rejection:
        semaphore = "CLIMAX"
        sem_label = "🟡 CLÍMAX / RECHAZO SIPV"
        sem_color = "#F59E0B"
        sem_tip = "Rechazo SIPV en el techo de la hora (mecha superior prominente). Venta institucional, esperar pullback."
        setup_bonus = -15.0
    # CASO C: SOBREEXTENSIÓN EN MÁXIMO DEL DÍA (< 1.5% del High)
    elif change_pct >= 20.0 and dist_from_high_pct < 1.5:
        semaphore = "CLIMAX"
        sem_label = "🟡 CLÍMAX (ESPERAR)"
        sem_color = "#F59E0B"
        sem_tip = f"En techo absoluto (${day_high:.2f}). Riesgo de comprar clímax de distribución. Esperar pullback."
        setup_bonus = -10.0
    # CASO D.1: SWEET SPOT GAP (+5% A +25% CON IMPULSO 5M CONFIRMADO - CASO WFF)
    elif (gap_pct is not None and 5.0 <= gap_pct <= 25.0) and candle_1_green and (plus_di_5m >= minus_di_5m) and adx_5m >= 18.0 and buying_force >= 60 and open_ge_close:
        semaphore = "SWEET_SPOT"
        sem_label = "🟢 SWEET SPOT CONTINUATION (1/3)"
        sem_color = "#10B981"
        sem_tip = f"Gap orgánico (+{gap_pct:.1f}%). Vela 1 verde con +DI>-DI y ADX={adx_5m:.0f} confirmando. Habilitada entrada escalonada en 3 tercios (Caso WFF)."
        setup_bonus = 30.0
    # CASO D.2: PULLBACK SALUDABLE CON EMA3 1H ASCENDENTE Y EMA3 > EMA9
    elif change_pct >= 8.0 and (1.5 <= dist_from_high_pct <= 7.5):
        semaphore = "PULLBACK"
        sem_label = "🟢 PULLBACK COMPRABLE"
        sem_color = "#10B981"
        sem_tip = f"Descanso saludable (-{dist_from_high_pct:.1f}% del pico) con EMA3 1H ascendente y sobre EMA9. Oportunidad en soporte."
        setup_bonus = 25.0
    else:
        semaphore = "MONITORING"
        sem_label = "⚪ MONITOREO"
        sem_color = "#94A3B8"
        sem_tip = f"Consolidando en ${price:.2f}. Sin señal clara de entrada o sobreextensión."
        setup_bonus = 0.0

    # 6. Rank Score Final (0 a 100)
    final_rank_score = round(min(100.0, max(1.0, (buying_force * 0.50) + (news_bonus * 0.5) + min(15.0, rvol * 3.0) + setup_bonus)), 1)

    return {
        "buying_force_5m": buying_force,
        "delta_p_5m": delta_p_5m,
        "semaphore": semaphore,
        "semaphore_label": sem_label,
        "semaphore_color": sem_color,
        "semaphore_tip": sem_tip,
        "rank_score": final_rank_score,
        "rvol": round(rvol, 2),
    }


def scan_top_gainers_live(limit: int = 25) -> List[Dict[str, Any]]:
    """
    Escanea en tiempo real los Top Gainers del mercado US:
    - Mínimo 1M de volumen.
    - $1.00 <= Precio <= $100.00.
    - Market Cap >= $15M.
    - Excluye ETFs apalancados 2X y derivados.
    """
    global _SCAN_CACHE
    now = time.time()

    # Retornar de cache si aún está vigente
    if _SCAN_CACHE["data"] and (now - _SCAN_CACHE["timestamp"] < CACHE_TTL):
        return _SCAN_CACHE["data"][:limit]

    candidates = []

    # 1. Intentar escáner en tiempo real con Yahoo Finance Screener
    try:
        from yfinance.screener import EquityQuery, screen

        query = EquityQuery('AND', [
            EquityQuery('EQ', ['region', 'us']),
            EquityQuery('GT', ['dayvolume', 1_000_000]),
            EquityQuery('GT', ['intradayprice', 1.0]),
            EquityQuery('LT', ['intradayprice', 100.0]),
            EquityQuery('GT', ['intradaymarketcap', 15_000_000]),
        ])

        fetch_size = max(35, limit + 10)
        res = screen(query, size=fetch_size, sortField='percentchange', sortAsc=False)
        raw_quotes = res.get('quotes', []) or []

        log_info(MODULE, f"Escaneados {len(raw_quotes)} tickers brutos de Yahoo Screener")

        for item in raw_quotes:
            sym = item.get('symbol', '').strip().upper()
            if not sym or '.' in sym or '-' in sym:
                continue

            name = item.get('shortName') or item.get('longName') or sym
            
            # Filtro de palabras clave en nombre para descartar ETFs residuales
            lower_name = name.lower()
            if any(k in lower_name for k in ['2x', '3x', 'etf', 'short', 'ultra', 'bear', 'invesco', 'ishares', 'proshares', 'direxion', 'tradr', 'yieldmax']):
                continue

            price = float(item.get('regularMarketPrice') or item.get('intradayprice') or 0.0)
            chg_pct = float(item.get('regularMarketChangePercent') or 0.0)
            vol = int(item.get('regularMarketVolume') or item.get('dayvolume') or 0)
            avg_vol = int(item.get('averageDailyVolume3Month') or max(1, vol // 2))
            mcap = float(item.get('marketCap') or item.get('intradaymarketcap') or 0.0)
            high = float(item.get('regularMarketDayHigh') or price)
            low = float(item.get('regularMarketDayLow') or price)
            open_p = float(item.get('regularMarketOpen') or price)

            # Noticia y catalizador
            news_info = fetch_stock_news(sym)
            news_bonus = news_info.get("bonus_points", 0)

            # Vela de 1H en formación y análisis SIPV + 5m
            live_1h = get_live_1h_candle_and_sipv(sym, price)

            # Cálculo del Gap de apertura respecto al cierre previo
            prev_close = float(item.get('regularMarketPreviousClose') or (price / (1.0 + (chg_pct / 100.0)) if chg_pct != -100 else price))
            gap_pct = round(((open_p - prev_close) / prev_close * 100.0), 2) if prev_close > 0 else 0.0

            # Métricas 1D (Bandas de Bollinger en gráfico Diario para medir espacio de expansión)
            sma20_1d, bb_upper_1d, room_to_bb = get_daily_bollinger_metrics(sym, price)

            # Fuerza compradora y semáforo
            metrics = calculate_semaphore_and_buying_force(
                price=price,
                change_pct=chg_pct,
                day_high=high,
                day_low=low,
                open_price=open_p,
                volume=vol,
                avg_volume=avg_vol,
                news_bonus=news_bonus,
                is_ema3_1h_ascending=live_1h.get("is_ema3_1h_ascending", True),
                ema3_slope_1h=live_1h.get("ema3_slope_1h", 0.0),
                is_ema3_above_ema9=live_1h.get("is_ema3_above_ema9", False),
                sipv_upper_rejection=live_1h.get("sipv_upper_rejection", False),
                gap_pct=gap_pct,
                candle_1_green=live_1h.get("is_candle_1_green", True),
                adx_5m=live_1h.get("adx_5m", 25.0),
                plus_di_5m=live_1h.get("plus_di_5m", 25.0),
                minus_di_5m=live_1h.get("minus_di_5m", 15.0),
                open_ge_close=live_1h.get("open_ge_close_prev", True),
                room_to_bb_upper_1d=room_to_bb,
                sma20_1d=sma20_1d,
            )

            candidates.append({
                "ticker": sym,
                "company_name": name,
                "price": round(price, 2),
                "change_pct": round(chg_pct, 2),
                "volume": vol,
                "avg_volume": avg_vol,
                "rvol": metrics["rvol"],
                "market_cap": mcap,
                "day_high": round(high, 2),
                "day_low": round(low, 2),
                # Métricas de Ranking y Semáforo
                "rank_score": metrics["rank_score"],
                "buying_force_5m": metrics["buying_force_5m"],
                "delta_p_5m": metrics["delta_p_5m"],
                "semaphore": metrics["semaphore"],
                "semaphore_label": metrics["semaphore_label"],
                "semaphore_color": metrics["semaphore_color"],
                "semaphore_tip": metrics["semaphore_tip"],
                "gap_pct": gap_pct,
                "room_to_bb_upper_1d": room_to_bb,
                "bb_upper_1d": bb_upper_1d,
                "sma20_1d": sma20_1d,
                "is_expansion_runner": (metrics["semaphore"] == "EXPANSION_RUNNER"),
                # Vela 1H en Formación & SIPV + 5m
                "is_ema3_1h_ascending": live_1h.get("is_ema3_1h_ascending", True),
                "is_ema3_1h_descending": live_1h.get("is_ema3_1h_descending", False),
                "is_ema3_above_ema9": live_1h.get("is_ema3_above_ema9", False),
                "ema3_slope_1h": live_1h.get("ema3_slope_1h", 0.0),
                "ema3_1h_live": live_1h.get("ema3_1h_live", 0.0),
                "ema9_1h": live_1h.get("ema9_1h", 0.0),
                "sipv_upper_rejection": live_1h.get("sipv_upper_rejection", False),
                "sipv_lower_absorption": live_1h.get("sipv_lower_absorption", False),
                "sipv_status_reason": live_1h.get("status_reason", ""),
                "adx_5m": live_1h.get("adx_5m", 25.0),
                "plus_di_5m": live_1h.get("plus_di_5m", 25.0),
                "minus_di_5m": live_1h.get("minus_di_5m", 15.0),
                "is_candle_1_green": live_1h.get("is_candle_1_green", True),
                "open_ge_close": live_1h.get("open_ge_close_prev", True),
                # Noticia / Catalizador
                "has_news": news_info.get("has_news", False),
                "catalyst_badge": news_info.get("catalyst_badge"),
                "badge_color": news_info.get("badge_color"),
                "news_bonus": news_bonus,
                "top_headline": news_info.get("top_headline", ""),
                "top_headline_es": news_info.get("top_headline_es", news_info.get("top_headline", "")),
                "catalyst_summary_es": news_info.get("catalyst_summary_es", ""),
                "top_url": news_info.get("top_url", ""),
                "articles_count": len(news_info.get("articles", [])),
                "pool_type": "ALPHA_RUNNER",
                "source": "live_top_gainers",
                "last_scan_time": datetime.now(timezone.utc).strftime("%H:%M UTC")
            })

    except Exception as e:
        log_error(MODULE, f"Error en escaneo de Top Gainers: {e}")

    # Ordenar estrictamente por rank_score descendente
    candidates.sort(key=lambda x: x["rank_score"], reverse=True)

    # Asignar posición numérica de Rank (#1, #2, #3...)
    for idx, c in enumerate(candidates, 1):
        c["rank"] = idx

    _SCAN_CACHE["timestamp"] = now
    _SCAN_CACHE["data"] = candidates

    return candidates[:limit]
