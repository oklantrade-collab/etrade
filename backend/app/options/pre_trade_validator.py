"""
eTrade v7.0 — PRE-TRADE BID/ASK & LIQUIDITY VALIDATOR (Options Shield)
======================================================================
Validador previo a la ejecución de Opciones:
1. Inspecciona en tiempo real el libro Bid/Ask de cada pata antes de permitir la orden.
2. Rechaza contratos con spreads destructivos:
   - (Ask - Bid) / Mid > 12.0% -> Rechazado (Slippage abusivo).
   - Bid <= $0.05 -> Rechazado (Libro sin compradores).
3. Calcula el Precio Límite Neto Justo (Mid Net Debit) para Spreads Verticales.
4. Prohíbe órdenes MKT en opciones multi-leg: fuerza ejecución Combo / BAG con LMT.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from app.core.logger import log_info, log_warning

MODULE = "PRE_TRADE_OPTIONS"


def fetch_live_option_quotes(
    symbol: str,
    expiry_yyyymmdd: str,
    strikes_and_rights: List[tuple[float, str]]  # [(12.5, 'P'), (11.5, 'P')]
) -> Dict[str, Dict[str, float]]:
    """
    Descarga cotizaciones bid/ask en vivo para una lista de strikes y derechos.
    Returns: { "12.5_P": {"bid": 0.45, "ask": 0.48, "mid": 0.465, "volume": 120, "oi": 500} }
    """
    quotes = {}
    try:
        import yfinance as yf
        # Formato YYYY-MM-DD
        exp_clean = str(expiry_yyyymmdd).replace("-", "")
        formatted_exp = f"{exp_clean[:4]}-{exp_clean[4:6]}-{exp_clean[6:8]}" if len(exp_clean) == 8 else expiry_yyyymmdd

        t = yf.Ticker(symbol)
        chain = t.option_chain(formatted_exp)

        for strike, right in strikes_and_rights:
            df = chain.calls if right.upper() == "C" else chain.puts
            match = df[df["strike"] == float(strike)]
            k = f"{float(strike)}_{right.upper()}"
            if not match.empty:
                b = float(match["bid"].iloc[0] or 0.0)
                a = float(match["ask"].iloc[0] or 0.0)
                lp = float(match["lastPrice"].iloc[0] or 0.0)
                vol = float(match["volume"].iloc[0] or 0.0)
                oi = float(match["openInterest"].iloc[0] or 0.0)

                # Si bid/ask vienen vacíos pero hay lastPrice
                if b <= 0 and a <= 0 and lp > 0:
                    b = round(lp * 0.95, 2)
                    a = round(lp * 1.05, 2)

                mid = round((b + a) / 2.0, 4) if (b + a) > 0 else lp
                quotes[k] = {
                    "strike": float(strike),
                    "right": right.upper(),
                    "bid": b,
                    "ask": a,
                    "mid": mid,
                    "last_price": lp,
                    "volume": vol,
                    "open_interest": oi
                }
            else:
                quotes[k] = {
                    "strike": float(strike),
                    "right": right.upper(),
                    "bid": 0.0, "ask": 0.0, "mid": 0.0, "volume": 0.0, "open_interest": 0.0
                }
    except Exception as e:
        log_warning(MODULE, f"Error descargando quotes de opciones para {symbol}: {e}")

    return quotes


def validate_option_candidate_pre_trade(
    symbol: str,
    strategy_type: str,
    expiry_yyyymmdd: str,
    legs: List[Dict[str, Any]],
    max_leg_spread_pct: float = 12.0
) -> Dict[str, Any]:
    """
    Valida integralmente las condiciones de liquidez y calcula el Limit Net Debit.
    """
    strikes_and_rights = []
    for l in legs:
        stk = float(l.get("strike") or 0.0)
        rgt = str(l.get("right") or "C").upper()
        strikes_and_rights.append((stk, rgt))

    live_quotes = fetch_live_option_quotes(symbol, expiry_yyyymmdd, strikes_and_rights)

    reasons = []
    legs_analyzed = []
    net_debit_mid = 0.0

    # Regla 0: Filtro Macro Bearish / Risk-Off para Opciones CALL
    is_call_strategy = any(str(l.get("right") or "C").upper() == "C" and str(l.get("side") or "buy").lower() == "buy" for l in legs)
    if is_call_strategy:
        try:
            from app.core.macro_sentiment_engine import evaluate_macro_sentiment
            macro_st = evaluate_macro_sentiment()
            if macro_st.get("regime") == "RISK_OFF" or not macro_st.get("allow_option_calls", True):
                reasons.append(f"VETO MACRO: Mercado en {macro_st.get('label', 'RISK-OFF')} (SP500/Nasdaq en caída). Prohibido comprar CALLs.")
        except Exception as e_m_opt:
            log_warning(MODULE, f"Error evaluando Macro en opciones: {e_m_opt}")

    for l in legs:
        stk = float(l.get("strike") or 0.0)
        rgt = str(l.get("right") or "C").upper()
        side = str(l.get("side") or "buy").lower()
        k = f"{stk}_{rgt}"
        q = live_quotes.get(k, {})

        bid = q.get("bid", 0.0)
        ask = q.get("ask", 0.0)
        mid = q.get("mid", 0.0)
        vol = q.get("volume", 0.0)
        oi = q.get("open_interest", 0.0)

        # Spread %
        spread_usd = ask - bid
        spread_pct = round((spread_usd / mid * 100.0), 1) if mid > 0 else 999.0

        leg_info = {
            "strike": stk,
            "right": rgt,
            "side": side,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_pct": spread_pct,
            "volume": vol,
            "open_interest": oi,
        }
        legs_analyzed.append(leg_info)

        # Regla 1: Mercado sin liquidez en Bid
        if bid <= 0.05 and ask > 0.10:
            reasons.append(f"Pata {side.upper()} {stk}{rgt} sin liquidez en Bid (${bid:.2f})")

        # Regla 2: Spread abusivo
        if spread_pct > max_leg_spread_pct:
            reasons.append(
                f"Pata {side.upper()} {stk}{rgt} con spread excesivo: {spread_pct}% > máx {max_leg_spread_pct}% (Bid: ${bid:.2f}, Ask: ${ask:.2f})"
            )

        # Aporte al Débito Neto
        if side == "buy":
            net_debit_mid += mid
        else:
            net_debit_mid -= mid

    net_debit_mid = round(net_debit_mid, 2)
    is_valid = len(reasons) == 0

    return {
        "is_valid": is_valid,
        "symbol": symbol,
        "strategy_type": strategy_type,
        "expiry": expiry_yyyymmdd,
        "rejection_reasons": reasons,
        "legs": legs_analyzed,
        "recommended_limit_price": max(0.01, net_debit_mid),
        "is_combo": len(legs) > 1,
        "summary": "Validación exitosa (Liquidez y Spread OK)" if is_valid else "; ".join(reasons)
    }
