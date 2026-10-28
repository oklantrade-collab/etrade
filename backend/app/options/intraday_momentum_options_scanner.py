"""
eTrade v7.5 — INTRADAY MOMENTUM OTM -> ITM OPTIONS SCANNER
===========================================================
Escáner especializado para capturar explosiones de Gamma Intradía en opciones OTM
que ingresan o se dirigen velozmente a ITM en la Canasta Élite de Alta Beta.

Criterios de Entrada Institucionales:
1. Universo: Canasta Élite (AMD, AAPL, AMZN, QQQ, NVDA, META, TSLA, COIN).
   - Beta 60d >= 1.35 vs SPY.
   - ADR% >= 2.5%.
   - Spread de opciones <= 3.5% (o <= $0.05).
   - Excluye sistemáticamente ETFs lentos (SPY, DIA, IWM), pesadas (MSFT) y spreads anchos (MARA).
2. Ventana de Oro Institucional: Exclusivamente entre 09:45 y 11:45 ET (bloqueo en mediodía y tarde).
3. Regla 'Protect the Win': 1 trade ganador por símbolo por día (bloqueo tras ganancia >= +10%).
4. Candado Anti-Earnings: Bloquea si reporta hoy After-Hours o mañana Pre-Market (prevención IV Crush).
5. Impulso Post-Earnings / Catalizador Tier 1/2: Bonificación de +20 pts y prioridad máxima.
6. Choke Point 1H (Inviolable): EMA3 > EMA9 en 1H para CALLs / EMA3 < EMA9 en 1H para PUTs (Fail-Closed).
7. ORB 15M (Opening Range Breakout): Ruptura del máximo/mínimo de los primeros 15 minutos (09:30-09:45 ET).
8. VWAP Dinámico: Cotizando por encima de VWAP intradía para CALLs / por debajo para PUTs.
9. Aceleración de Volumen: RVOL >= 1.4x o Ráfaga de volumen 5m (>= 1.25x promedio de 20 periodos).
10. Selección de Contrato OTM_MOMENTUM:
    - Strike: OTM inmediato (1% a 3.5% de distancia del spot).
    - Delta: 0.25 a 0.42 (Target: 0.35).
    - DTE: 0 a 7 días (semanal para máxima aceleración Gamma).
    - Spread bid/ask <= 3.5%.
11. Plan de Salida:
    - TP1: +50% ganancia en la prima (vender 50% contratos, mover SL a Breakeven).
    - TP2: +100% ganancia en la prima (vender 30% contratos).
    - Breakeven Lock: Activado tras avance de prima >= +12.0%.
    - Salidas de Agotamiento: EMA3 1H frena o EMA3 15m < EMA9 15m (CALLs) / EMA3 15m > EMA9 15m (PUTs).
    - Hard SL: -35% en la prima del contrato.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.core.market_hours import is_market_open
from app.data.yfinance_provider import YFinanceProvider
from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
from app.options.opt_contract_picker import fetch_and_select_best_option_contract
from app.options.autonomous_options_dispatcher import dispatch_autonomous_option_trade
from app.options.aduana_gap_runner_options import compute_vwap, _safe_col, is_optionable

MODULE = "INTRADAY_MOMENTUM_OPT"

# Canasta Élite de opciones con alta aceleración de volatilidad (Beta >= 1.35, ADR >= 2.5%, Spreads estrechos)
CORE_MOMENTUM_OPTION_SYMBOLS = [
    "AMD", "AAPL", "AMZN", "QQQ", "NVDA", "META", "TSLA", "COIN"
]


def is_institutional_golden_window(dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Verifica si el horario actual está dentro de la Ventana de Oro Institucional (09:45 a 11:45 ET).
    Bloquea aperturas en el mediodía (11:45-13:30) y tarde para evitar volumen plano y Theta decay.
    """
    try:
        from zoneinfo import ZoneInfo
        now_et = (dt or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    except Exception:
        now_et = dt or (datetime.now(timezone.utc) - timedelta(hours=4))

    t = now_et.time()
    t_start = datetime.strptime("09:45", "%H:%M").time()
    t_end = datetime.strptime("11:45", "%H:%M").time()

    if t < t_start:
        return False, f"Pre-apertura/ORB 15M en formación ({now_et.strftime('%H:%M')} ET < 09:45 ET)"
    elif t > t_end:
        return False, f"Fuera de Ventana de Oro ({now_et.strftime('%H:%M')} ET > 11:45 ET, bloqueo preventivo de mediodía)"
    return True, f"Ventana de Oro activa ({now_et.strftime('%H:%M')} ET)"


def evaluate_options_universe_eligibility(
    symbol: str,
    beta: Optional[float] = None,
    adr_pct: Optional[float] = None,
    spread_pct: Optional[float] = None,
    price: Optional[float] = None
) -> Tuple[bool, str]:
    """
    Filtro cuantitativo de elegibilidad para el universo Gamma Ignition:
    1. Beta >= 1.35 vs S&P 500 (o ETF líder como QQQ). Excluye SPY, DIA, MSFT.
    2. ADR% >= 2.5%. Excluye acciones de rango estrecho.
    3. Bid-Ask Spread <= 3.5%. Excluye MARA.
    4. Precio >= $30.00. Excluye penny stocks.
    """
    sym = symbol.strip().upper()
    if sym in CORE_MOMENTUM_OPTION_SYMBOLS:
        return True, f"{sym}: Miembro verificado de Canasta Élite Gamma Ignition"

    if sym in ("SPY", "DIA", "IWM", "MSFT", "MARA", "OPEN", "DJT", "LUNR"):
        return False, f"{sym}: Excluido por bajo Beta (<1.35), baja aceleración o spreads anchos (>3.5%)"

    if beta is not None and beta < 1.35 and sym != "QQQ":
        return False, f"{sym}: Beta insuficiente ({beta:.2f} < 1.35)"

    if adr_pct is not None and adr_pct < 2.5:
        return False, f"{sym}: ADR% estrecho ({adr_pct:.1f}% < 2.5%)"

    if spread_pct is not None and spread_pct > 3.5:
        return False, f"{sym}: Spread de opciones excesivo ({spread_pct:.1f}% > 3.5%)"

    if price is not None and price < 30.0:
        return False, f"{sym}: Precio bajo subyacente (${price:.2f} < $30.00)"

    return True, f"{sym}: Cumple criterios cuantitativos de universo élite"


def is_symbol_protected_by_win(symbol: str, supabase: Any = None) -> Tuple[bool, str]:
    """
    Regla 'Protect the Win': Si el activo ya cerró una posición hoy con ganancia >= +10%,
    se activa un candado diario para evitar sobre-operar y devolver beneficios en la consolidación.
    """
    sb = supabase or get_supabase()
    if not sb:
        return False, "Sin conexión a base de datos"

    try:
        try:
            from zoneinfo import ZoneInfo
            today_str = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        except Exception:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        res = sb.table("options_positions").select("id, status, pnl_pct, realized_pnl, closed_at") \
            .eq("symbol", symbol.upper()) \
            .eq("status", "CLOSED") \
            .gte("closed_at", f"{today_str}T00:00:00") \
            .execute()

        closed_trades = res.data or []
        for t in closed_trades:
            pnl_p = float(t.get("pnl_pct") or 0.0)
            realized = float(t.get("realized_pnl") or 0.0)
            if pnl_p >= 10.0 or realized > 100.0:
                return True, f"{symbol}: Ya generó ganancia hoy (+{pnl_p:.1f}% / +${realized:.2f}). Candado 'Protect the Win' activo."
    except Exception as e:
        log_warning(MODULE, f"Aviso verificando Protect the Win para {symbol}: {e}")

    return False, f"{symbol}: Sin ganancias previas hoy"


def evaluate_options_catalyst_status(symbol: str) -> Dict[str, Any]:
    """
    Evalúa noticias y calendario corporativo (Earnings):
    1. Bloqueo anti-earnings si reporta hoy After-Hours o mañana Pre-Market (riesgo IV Crush).
    2. Bonificación de +20 pts si es día de reacción post-earnings o noticia Tier 1/2.
    """
    try:
        from app.stocks.news_catalyst_service import get_news_catalyst
        cat = get_news_catalyst(symbol)
    except Exception as e:
        log_warning(MODULE, f"Aviso al consultar noticias para {symbol}: {e}")
        cat = {}

    score_bonus = 0.0
    has_earnings = bool(cat.get("has_earnings_event", False))
    earnings_timing = str(cat.get("earnings_timing", "")).lower()

    if has_earnings and earnings_timing in ("today_after_market", "tomorrow_pre_market", "after_market"):
        return {
            "is_blocked": True,
            "block_reason": f"Earnings inminentes ({earnings_timing}). Riesgo crítico de IV Crush en opciones semanales.",
            "score_bonus": 0.0,
            "catalyst_tag": "PRE_EARNINGS_RISK"
        }

    tag = ""
    if has_earnings and earnings_timing in ("today_pre_market", "yesterday_after_market", "past"):
        score_bonus += 20.0
        tag = "POST_EARNINGS_MOMENTUM"

    tier = str(cat.get("tier", "")).lower()
    if tier == "tier_1":
        score_bonus = max(score_bonus, 20.0)
        tag = tag or f"TIER_1_NEWS_{str(cat.get('category', 'CATALYST')).upper().replace(' ', '_')}"
    elif tier == "tier_2":
        score_bonus = max(score_bonus, 15.0)
        tag = tag or f"TIER_2_NEWS_{str(cat.get('category', 'CATALYST')).upper().replace(' ', '_')}"

    return {
        "is_blocked": False,
        "block_reason": "",
        "score_bonus": score_bonus,
        "catalyst_tag": tag,
        "news_title": cat.get("headline", "")
    }


def evaluate_intraday_momentum_breakout(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_1h: Optional[pd.DataFrame] = None,
    is_ema3_above_ema9_1h: Optional[bool] = None,
    catalyst_bonus: float = 0.0,
    catalyst_tag: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evalúa si un activo presenta ruptura de momentum intradía (ORB + VWAP + Volumen)
    con alineación de tendencia 1H (Fail-Closed).
    """
    sym = symbol.strip().upper()
    res: Dict[str, Any] = {
        "symbol": sym,
        "is_qualified": False,
        "direction": None,
        "score": 0.0,
        "triggers": [],
        "reason": "",
        "metrics": {},
        "current_price": 0.0,
        "orb_high_15m": 0.0,
        "orb_low_15m": 0.0,
        "vwap": 0.0,
        "rvol": 1.0,
    }

    if df_5m is None or len(df_5m) < 6 or df_15m is None or len(df_15m) < 2:
        res["reason"] = f"{sym}: Datos OHLCV insuficientes para ORB (5m < 6 o 15m < 2)"
        return res

    c5 = _safe_col(df_5m, "close")
    o5 = _safe_col(df_5m, "open")
    h5 = _safe_col(df_5m, "high")
    l5 = _safe_col(df_5m, "low")
    v5 = _safe_col(df_5m, "volume")

    h15 = _safe_col(df_15m, "high")
    l15 = _safe_col(df_15m, "low")

    current_price = float(c5.iloc[-1])
    open_last_5m = float(o5.iloc[-1])
    is_green_5m = current_price >= open_last_5m
    is_red_5m = current_price <= open_last_5m

    # 1. Rango de Apertura 15M (ORB)
    orb_high_15m = float(h15.iloc[0])
    orb_low_15m = float(l15.iloc[0])

    # 2. VWAP Intradía 5M
    vwap_s = compute_vwap(df_5m)
    current_vwap = float(vwap_s.iloc[-1]) if len(vwap_s) > 0 else current_price

    # 3. Volumen y RVOL en 5M
    v5_clean = v5.dropna()
    avg_v5 = float(v5_clean.iloc[-20:].mean()) if len(v5_clean) >= 20 else 1000.0
    last_v5 = float(v5_clean.iloc[-1]) if len(v5_clean) > 0 else 0.0
    volume_burst_5m = (last_v5 >= avg_v5 * 1.25) and (last_v5 > 2500)
    cum_vol = float(v5_clean.sum())
    rvol_est = round(max(1.0, cum_vol / max(1.0, avg_v5 * len(v5_clean))), 2)

    # 4. Estado de Tendencia 1H (Fail-Closed Choke Point)
    ema_1h_state = is_ema3_above_ema9_1h
    if ema_1h_state is None and df_1h is not None and len(df_1h) >= 20:
        c1h = _safe_col(df_1h, "close")
        ema3_1h = float(c1h.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9_1h = float(c1h.ewm(span=9, adjust=False).mean().iloc[-1])
        ema_1h_state = bool(ema3_1h > ema9_1h)

    res["current_price"] = current_price
    res["orb_high_15m"] = orb_high_15m
    res["orb_low_15m"] = orb_low_15m
    res["vwap"] = round(current_vwap, 2)
    res["rvol"] = rvol_est

    # ── EVALUACIÓN CONDICIONAL PARA CALL ──
    # a) 1H EMA3 > EMA9 obligatorio (Fail-Closed)
    # b) Ruptura o test firme de ORB High (Precio >= ORB High * 0.998)
    # c) Sobre VWAP
    # d) Vela 5m verde y volumen acelerando
    if (
        ema_1h_state is True
        and current_price >= (orb_high_15m * 0.998)
        and current_price >= current_vwap
        and is_green_5m
        and (volume_burst_5m or rvol_est >= 1.4 or catalyst_bonus > 0.0)
    ):
        score = 70.0
        triggers = ["ORB_15M_BREAKOUT", "VWAP_SUPPORT", "1H_EMA3_GT_EMA9"]
        if current_price > orb_high_15m:
            score += 15.0
            triggers.append("ORB_CLEAR_BREAK")
        if volume_burst_5m:
            score += 10.0
            triggers.append("5M_VOLUME_BURST")
        if rvol_est >= 2.0:
            score += 5.0
            triggers.append("HIGH_RVOL")
        if catalyst_bonus > 0.0:
            score += catalyst_bonus
            if catalyst_tag:
                triggers.append(catalyst_tag)

        score = min(100.0, score)

        res.update({
            "is_qualified": True,
            "direction": "CALL",
            "score": round(score, 1),
            "triggers": triggers,
            "reason": f"Impulso Alcista ORB 15M + VWAP ($ {current_price:.2f} >= ORB ${orb_high_15m:.2f}) con 1H EMA3>EMA9 y RVOL={rvol_est:.1f}x",
            "metrics": {
                "price": current_price,
                "orb_high": orb_high_15m,
                "vwap": round(current_vwap, 2),
                "rvol": rvol_est,
                "dist_orb_pct": round(((current_price - orb_high_15m) / orb_high_15m) * 100.0, 2),
                "is_ema3_gt_ema9_1h": True,
                "catalyst_bonus": catalyst_bonus
            }
        })
        return res

    # ── EVALUACIÓN CONDICIONAL PARA PUT ──
    # a) 1H EMA3 <= EMA9 (bajista en 1H)
    # b) Ruptura o test firme de ORB Low (Precio <= ORB Low * 1.002)
    # c) Bajo VWAP
    # d) Vela 5m roja y volumen acelerando
    if (
        ema_1h_state is False
        and current_price <= (orb_low_15m * 1.002)
        and current_price <= current_vwap
        and is_red_5m
        and (volume_burst_5m or rvol_est >= 1.4 or catalyst_bonus > 0.0)
    ):
        score = 70.0
        triggers = ["ORB_15M_BREAKDOWN", "VWAP_RESISTANCE", "1H_EMA3_LE_EMA9"]
        if current_price < orb_low_15m:
            score += 15.0
            triggers.append("ORB_CLEAR_BREAKDOWN")
        if volume_burst_5m:
            score += 10.0
            triggers.append("5M_VOLUME_BURST")
        if rvol_est >= 2.0:
            score += 5.0
            triggers.append("HIGH_RVOL")
        if catalyst_bonus > 0.0:
            score += catalyst_bonus
            if catalyst_tag:
                triggers.append(catalyst_tag)

        score = min(100.0, score)

        res.update({
            "is_qualified": True,
            "direction": "PUT",
            "score": round(score, 1),
            "triggers": triggers,
            "reason": f"Impulso Bajista ORB 15M + VWAP ($ {current_price:.2f} <= ORB ${orb_low_15m:.2f}) con 1H EMA3<EMA9 y RVOL={rvol_est:.1f}x",
            "metrics": {
                "price": current_price,
                "orb_low": orb_low_15m,
                "vwap": round(current_vwap, 2),
                "rvol": rvol_est,
                "dist_orb_pct": round(((orb_low_15m - current_price) / orb_low_15m) * 100.0, 2),
                "is_ema3_gt_ema9_1h": False,
                "catalyst_bonus": catalyst_bonus
            }
        })
        return res

    res["reason"] = f"No cumple condiciones de ignición ORB (Price=${current_price:.2f}, ORB=[${orb_low_15m:.2f}-${orb_high_15m:.2f}], VWAP=${current_vwap:.2f}, 1H_Bull={ema_1h_state})"
    return res


async def run_intraday_momentum_options_scan(
    symbols: Optional[List[str]] = None,
    budget_usd: float = 1000.0,
    auto_dispatch: bool = True,
    supabase: Any = None
) -> Dict[str, Any]:
    """
    Ejecuta el escaneo de momentum intradía enfocado en capturar opciones OTM
    con alto potencial de penetrar a ITM.
    Aplica:
    - Ventana de Oro Institucional (09:45 a 11:45 ET).
    - Canasta Élite y Filtro de Elegibilidad Cuantitativo.
    - Regla 'Protect the Win' (evita sobre-operar símbolos ya ganadores hoy).
    - Candado Anti-Earnings (IV Crush) y Bonificación Post-Earnings/Noticias.
    """
    is_open, status_txt = is_market_open()
    if not is_open:
        log_info(MODULE, f"Mercado cerrado ({status_txt}). Omitiendo escaneo intradía de opciones OTM.")
        return {"ok": False, "reason": "Market closed", "status": status_txt}

    # 1. Validación de Ventana de Oro Institucional (09:45 a 11:45 ET)
    in_golden_window, win_msg = is_institutional_golden_window()
    if not in_golden_window:
        log_info(MODULE, f"⏸️ {win_msg}. Omitiendo apertura de nuevas posiciones para evitar trampa de mediodía/tarde.")
        return {"ok": False, "reason": win_msg, "status": "OUTSIDE_GOLDEN_WINDOW"}

    sb = supabase or get_supabase()
    provider = YFinanceProvider()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    universe = list(symbols or CORE_MOMENTUM_OPTION_SYMBOLS)
    log_info(MODULE, f"⚡ Iniciando escaneo Intraday Momentum OTM -> ITM para {len(universe)} activos élite (Ventana de Oro)...")

    qualified_opportunities: List[Dict[str, Any]] = []

    for sym in universe:
        try:
            # 2. Filtro Cuantitativo de Universo
            is_elig, elig_msg = evaluate_options_universe_eligibility(sym)
            if not is_elig:
                log_info(MODULE, f"Omitiendo {sym}: {elig_msg}")
                continue

            if not is_optionable(sym, sb):
                continue

            # 3. Regla 'Protect the Win' (1 ganador y candado diario)
            is_protected, prot_msg = is_symbol_protected_by_win(sym, sb)
            if is_protected:
                log_info(MODULE, f"🛡️ {prot_msg}")
                continue

            # 4. Evaluación de Catalizador / Calendario de Earnings
            cat_status = evaluate_options_catalyst_status(sym)
            if cat_status.get("is_blocked"):
                log_info(MODULE, f"🚫 {sym} bloqueado: {cat_status.get('block_reason')}")
                continue

            df_5m = await provider.get_ohlcv(sym, interval="5m", period="5d")
            df_15m = await provider.get_ohlcv(sym, interval="15m", period="10d")

            if df_5m is None or len(df_5m) < 6 or df_15m is None or len(df_15m) < 2:
                continue

            # 5. Obtener estado 1H (Broker-First fail-closed)
            h1_status = get_live_1h_candle_and_sipv(sym)
            is_bullish_1h = bool(h1_status.get("is_ema3_above_ema9", False))

            # 6. Evaluar condiciones de ruptura intradía con bonificación de catalizador
            eval_res = evaluate_intraday_momentum_breakout(
                symbol=sym,
                df_5m=df_5m,
                df_15m=df_15m,
                is_ema3_above_ema9_1h=is_bullish_1h,
                catalyst_bonus=cat_status.get("score_bonus", 0.0),
                catalyst_tag=cat_status.get("catalyst_tag")
            )

            if not eval_res.get("is_qualified"):
                continue

            direction = str(eval_res.get("direction"))
            cur_price = eval_res["current_price"]

            # 7. Selección quirúrgica de contrato OTM (Delta ~0.35, DTE 0-7d, Spread <= 3.5%)
            best_contract, rej = fetch_and_select_best_option_contract(
                symbol=sym,
                underlying_price=cur_price,
                direction=direction,
                budget_usd=budget_usd,
                supabase=sb,
                selection_mode="OTM_MOMENTUM"
            )

            if not best_contract:
                log_info(MODULE, f"Sin contrato semanal OTM adecuado para {sym} ({direction}): {'; '.join(rej[:1])}")
                continue

            otm_dist = abs(best_contract.strike - cur_price) / cur_price * 100.0
            log_info(
                MODULE,
                f"🎯 OPORTUNIDAD OTM -> ITM DETECTADA: {sym} {direction} | Spot: ${cur_price:.2f} -> "
                f"Strike ${best_contract.strike} (Dist: {otm_dist:.1f}% OTM, Delta: {best_contract.delta:+.2f}, "
                f"Exp: {best_contract.expiry}, DTE: {best_contract.dte}d, Prima: ${best_contract.mid:.2f}, "
                f"Spread: {best_contract.spread_pct:.1f}%) [Catalyst: {cat_status.get('catalyst_tag') or 'NONE'}]"
            )

            opp_data = {
                "ticker": sym,
                "price": cur_price,
                "direction": direction,
                "selection_mode": "OTM_MOMENTUM",
                "triggered_rule": f"MOMENTUM_OTM_ITM_{direction}",
                "conviction": "HIGH",
                "score": eval_res.get("score", 75.0),
                "entry_reason": eval_res.get("reason"),
                "catalyst_tag": cat_status.get("catalyst_tag"),
                "selected_contract": {
                    "strike": best_contract.strike,
                    "right": best_contract.right,
                    "expiry": best_contract.expiry.isoformat(),
                    "dte": best_contract.dte,
                    "delta": best_contract.delta,
                    "bid": best_contract.bid,
                    "ask": best_contract.ask,
                    "mid": best_contract.mid,
                    "spread_pct": best_contract.spread_pct,
                    "cost_per_contract": best_contract.cost_per_contract
                },
                "otm_distance_pct": round(otm_dist, 2),
                "tactical_targets": {
                    "tp1_price_est": round(best_contract.mid * 1.50, 2),
                    "tp2_price_est": round(best_contract.mid * 2.00, 2),
                    "sl_price_est": round(best_contract.mid * 0.65, 2)
                }
            }

            qualified_opportunities.append(opp_data)

            # 8. Despacho Autónomo directo si auto_dispatch está habilitado
            if auto_dispatch:
                try:
                    dispatch_res = dispatch_autonomous_option_trade(
                        candidate=opp_data,
                        direction=direction,
                        config={"options_trade_budget_usd": budget_usd},
                        supabase=sb
                    )
                    opp_data["dispatch_result"] = dispatch_res
                except Exception as e_disp:
                    log_warning(MODULE, f"Aviso al auto-despachar {sym}: {e_disp}")

        except Exception as e_sym:
            log_warning(MODULE, f"Error escaneando {sym}: {e_sym}")
            continue

    log_info(MODULE, f"🏁 Escaneo Intraday OTM finalizado. {len(qualified_opportunities)} oportunidades calificadas.")

    return {
        "ok": True,
        "opportunities_count": len(qualified_opportunities),
        "opportunities": qualified_opportunities,
        "timestamp": now_iso
    }
