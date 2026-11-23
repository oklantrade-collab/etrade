"""
eTrade v7.0 — AUTONOMOUS OPTIONS DISPATCHER (CALLs & PUTs -> TWS)
==================================================================
Despachador central para conectar las oportunidades detectadas por los escáneres
de mercado (Bull Expansion y Bear Rollover) directamente con Interactive Brokers TWS
a través del puente local en APOLO.

Flujo de Ejecución:
1. Recibe un candidato de alta convicción (CALL o PUT).
2. Filtro Anti-Sobreexposición / Anti-Duplicado (evita órdenes repetidas en el mismo subyacente).
3. Selecciona el contrato óptimo mediante opt_contract_picker (Strike ATM, Delta ~0.50, DTE 14-28d).
4. Registra el trade en opt_paper_trades para tracking de SL/TP institucional.
5. Inserta la orden en stocks_orders con status='pending' y target_band='OPT:...'.
6. ib_bridge_worker en APOLO detecta la orden y la transmite a TWS inmediatamente.
7. Notifica al usuario vía Telegram.
"""

from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone, timedelta
from typing import Dict, Any, Optional

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.core.structural_regime_engine import evaluate_structural_regime
from app.options.opt_contract_picker import fetch_and_select_best_option_contract
from app.options.exit_engine import is_ticker_in_options_cooldown

MODULE = "AUTONOMOUS_OPT_DISPATCHER"


def send_telegram_alert(message: str) -> None:
    """Envía alerta de Telegram de forma segura tanto en contexto síncrono como asíncrono."""
    try:
        from app.workers.alerts_service import send_telegram_message
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(message))
        except RuntimeError:
            asyncio.run(send_telegram_message(message))
    except Exception as e:
        log_warning(MODULE, f"No se pudo enviar alerta de Telegram: {e}")


def dispatch_autonomous_option_trade(
    candidate: Dict[str, Any],
    direction: str = "CALL",
    config: Optional[dict] = None,
    supabase: Any = None,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Despacha una orden de opción (CALL o PUT) basada en la calificación de un escáner.
    Retorna un diccionario con el resultado de la operación.
    """
    sb = supabase or get_supabase()
    cfg = config or {}
    ref_dt = now_dt or datetime.now(timezone.utc)

    ticker = str(candidate.get("ticker", "")).replace("/", "").replace(".", "").upper().strip()
    if not ticker:
        return {"success": False, "reason": "Ticker vacío"}

    underlying_price = float(candidate.get("price") or candidate.get("price_at_rank") or 0.0)
    rule_code = str(candidate.get("triggered_rule") or candidate.get("rule_code") or f"OPT_{direction.upper()}")
    opt_dir = "CALL" if direction.upper() in ("CALL", "BULLISH", "LONG") else "PUT"
    today_str = date.today().isoformat()

    try:
        from app.options.warrior_momentum_options import is_warrior_options_golden_window, MAX_CONTRACTS_PER_SYMBOL
        from app.options.settings_defaults import get_effective_max_risk_per_trade_usd

        # ── 0. VENTANA DE ORO, DISYUNTOR Y VETO MACRO DIARIO ──
        in_win, win_msg = is_warrior_options_golden_window(ref_dt)
        if not in_win:
            log_info(MODULE, f"⏸️ {ticker} ({opt_dir}) omitido fuera de Ventana de Oro 09:35-11:30 ET: {win_msg}")
            return {"success": False, "reason": f"Fuera de Ventana de Oro: {win_msg}"}

        try:
            from app.core.circuit_breaker import can_open_new_trade
            can_open, cb_reason = can_open_new_trade(ticker, sb=sb)
            if not can_open:
                log_warning(MODULE, f"⛔ {ticker} ({opt_dir}) bloqueado por Disyuntor: {cb_reason}")
                return {"success": False, "reason": cb_reason}
        except Exception:
            pass

        if opt_dir == "CALL":
            try:
                from app.core.structural_regime_engine import evaluate_macro_daily_bias
                macro_bias = evaluate_macro_daily_bias()
                if macro_bias.get("veto_calls"):
                    log_info(MODULE, f"⛔ {ticker} (CALL) bloqueado por Veto Macro Diario: {macro_bias.get('reason')}")
                    return {"success": False, "reason": macro_bias.get("reason")}
            except Exception:
                pass

        # ── 1. FILTRO ANTI-DUPLICADO & CONTROL DE EXPOSICIÓN ──
        # a) Verificar si ya existe posición abierta en opt_paper_trades para este subyacente y dirección
        pos_check = sb.table("opt_paper_trades")\
            .select("id, symbol, direction, status")\
            .eq("symbol", ticker)\
            .eq("status", "open")\
            .execute()

        active_positions = pos_check.data or []
        for pos in active_positions:
            pos_dir = str(pos.get("direction", "")).lower()
            target_dir = "bullish" if opt_dir == "CALL" else "bearish"
            if pos_dir == target_dir:
                log_info(MODULE, f"⏸️ Omitiendo despacho para {ticker}: Ya existe posición abierta en {opt_dir}.")
                return {"success": False, "reason": f"Posición {opt_dir} ya abierta para {ticker}"}

        # b) Verificar si ya hay una orden en vuelo hoy en stocks_orders
        orders_check = sb.table("stocks_orders")\
            .select("id, status, ticker")\
            .like("ticker", f"{ticker}:OPT:%")\
            .in_("status", ["pending", "processing", "submitted"])\
            .execute()

        if orders_check.data and len(orders_check.data) > 0:
            log_info(MODULE, f"⏸️ Omitiendo despacho para {ticker}: Ya hay una orden de opción en vuelo ({len(orders_check.data)} pendientes).")
            return {"success": False, "reason": f"Orden de opción ya en vuelo para {ticker}"}

        # c) Verificar Cooldown Dinámico tras Stop Loss (evita re-comprar de inmediato en el ciclo fallido)
        in_cd, cd_msg = is_ticker_in_options_cooldown(ticker, opt_dir)
        if in_cd:
            log_info(MODULE, f"⏸️ Omitiendo despacho para {ticker} ({opt_dir}): {cd_msg}")
            return {"success": False, "reason": f"Cooldown tras Stop Loss: {cd_msg}"}

        # ── 1.2 EVALUACIÓN SISTÉMICA DE RÉGIMEN ESTRUCTURAL (REGLAS 1, 2, 3, 4) ──
        st_reg = evaluate_structural_regime(ticker, underlying_price)
        if opt_dir == "CALL":
            if not st_reg.get("can_enter_call", True):
                veto_reason = st_reg.get("call_veto_reason") or "Filtro 1D no superado para CALL"
                log_info(MODULE, f"⛔ {ticker} (CALL) BLOQUEADO por Régimen Estructural: {veto_reason}")
                return {"success": False, "reason": f"Régimen Estructural: {veto_reason}"}
        else:
            if not st_reg.get("can_enter_put", True):
                veto_reason = st_reg.get("put_veto_reason") or "Filtro 1D no superado para PUT"
                log_info(MODULE, f"⛔ {ticker} (PUT) BLOQUEADO por Régimen Estructural: {veto_reason}")
                return {"success": False, "reason": f"Régimen Estructural: {veto_reason}"}

        # ── 1.5 GATEKEEPER ADUANA OPCIONES (Daily Runway 1D + RSI MTF + EMA3/EMA9 en 1H) ──
        # Ante un error de datos/red no se bloquea (fail-open con aviso); ante una decisión clara sí.
        try:
            from app.options.aduana_gap_runner_options import fetch_and_evaluate_options_gatekeeper
            gate = fetch_and_evaluate_options_gatekeeper(ticker, opt_dir, underlying_price)
            if not gate.get("approved", True):
                log_info(MODULE, f"⛔ {ticker} ({opt_dir}) BLOQUEADO por ADUANA Opciones [{gate.get('stage')}]: {gate.get('reason')}")
                return {"success": False, "reason": f"ADUANA Opciones [{gate.get('stage')}]: {gate.get('reason')}"}
            log_info(MODULE, f"✅ {ticker} ({opt_dir}) ADUANA Opciones: {gate.get('runway', {}).get('reason', gate.get('reason'))}")
        except Exception as e_gate:
            log_warning(MODULE, f"Aviso evaluando Gatekeeper ADUANA Opciones para {ticker}: {e_gate}")

        # ── 2. SELECCIÓN INTELIGENTE DE CONTRATO DESDE SETTINGS ("Riesgo máximo por operación" = $800) ──
        selection_mode = str(candidate.get("selection_mode", "GAP_RUNNER"))
        total_budget_usd = get_effective_max_risk_per_trade_usd(sb, cfg if "max_risk_per_trade_usd" in cfg else None)
        budget_tranche_1 = round(total_budget_usd, 2)
        log_info(MODULE, f"🔍 Buscando contrato óptimo de {opt_dir} para {ticker} [Modo: {selection_mode}] (Spot: ${underlying_price:.2f}, Tope Settings: ${total_budget_usd:.0f})...")

        best_contract, rej_reasons = fetch_and_select_best_option_contract(
            symbol=ticker,
            underlying_price=underlying_price,
            direction=opt_dir,
            budget_usd=budget_tranche_1,
            supabase=sb,
            selection_mode=selection_mode
        )

        if not best_contract:
            log_warning(MODULE, f"No se encontró contrato apto para {ticker} ({opt_dir}): {'; '.join(rej_reasons[:2])}")
            return {"success": False, "reason": "Sin contratos que cumplan criterios de liquidez/delta"}

        # ── 3. FORMATEO DE ORDEN Y PRECIOS ──
        opt_exp_compact = best_contract.expiry.strftime("%Y%m%d")
        opt_ticker_formatted = f"{ticker}:OPT:{opt_exp_compact}:{best_contract.strike}:{best_contract.right}"
        target_band_str = f"OPT:{opt_exp_compact}:{best_contract.strike}:{best_contract.right}"

        # P1: Límite estricto de contratos y tope en USD desde Settings ($800)
        contracts_to_buy = min(MAX_CONTRACTS_PER_SYMBOL, 2, max(1, getattr(best_contract, "tranche_1_contracts", 1)))
        # Plan de ejecución escalonada guiado por RVOL + spread (Adaptive Ladder)
        from app.options.order_execution_plan import compute_option_entry_plan
        _bid = float(getattr(best_contract, "bid", 0.0) or 0.0)
        _ask = float(getattr(best_contract, "ask", 0.0) or 0.0)
        _rvol = float(candidate.get("rvol") or candidate.get("rel_vol") or 1.0)
        entry_plan = compute_option_entry_plan(
            bid=_bid,
            ask=_ask,
            mid=float(getattr(best_contract, "mid", 0.0) or 0.0),
            rvol=_rvol,
        )
        opt_price = entry_plan["limit_price"]
        unit_cost_usd = opt_price * 100.0
        if unit_cost_usd > total_budget_usd + 1e-9:
            log_warning(MODULE, f"⛔ {ticker} ({opt_dir}) rechazado: 1 contrato (${unit_cost_usd:.2f}) excede Riesgo máximo por operación (${total_budget_usd:.2f}).")
            return {"success": False, "reason": f"1 contrato (${unit_cost_usd:.2f}) excede tope Settings (${total_budget_usd:.2f})"}
        if unit_cost_usd > 0 and (unit_cost_usd * contracts_to_buy) > total_budget_usd + 1e-9:
            contracts_to_buy = max(1, int(total_budget_usd // unit_cost_usd))

        total_invested = round(opt_price * 100 * contracts_to_buy, 2)
        now_iso = ref_dt.isoformat()
        expires_iso = (ref_dt + timedelta(seconds=float(entry_plan["ttl_sec"]) + 120.0)).isoformat()

        # Principio Broker-First: NO insertar optimísticamente en opt_paper_trades antes del fill.
        # `ib_bridge_worker` creará la posición en opt_paper_trades únicamente al confirmar el fill en TWS.
        strat_type = "long_call" if best_contract.right == "C" else "long_put"

        # ── 5. DESPACHO A stocks_orders (SEÑAL INMEDIATA A TWS VIA APOLO BRIDGE) ──
        order_payload = {
            "ticker": opt_ticker_formatted,
            "group_name": "OPTIONS_AUTONOMOUS",
            "rule_code": rule_code,
            "order_type": "limit",
            "direction": "buy",
            "shares": contracts_to_buy,
            "market_price": opt_price,
            "limit_price": opt_price,
            "rvol": entry_plan["rvol"],
            "expires_at": expires_iso,
            "target_band": target_band_str,
            "status": "pending",
            "created_at": now_iso
        }

        db_order = sb.table("stocks_orders").insert(order_payload).execute()
        order_id = db_order.data[0]["id"] if (db_order.data and len(db_order.data) > 0) else "OK"

        log_info(MODULE, f"🚀 ORDEN AUTÓNOMA DESPACHADA A TWS: {opt_ticker_formatted} | {contracts_to_buy}x @ ${opt_price:.2f} (Total: ${total_invested:.2f}) [OrderID: {order_id}]")

        # ── 6. NOTIFICACIÓN TELEGRAM ──
        emoji = "🟢" if opt_dir == "CALL" else "🔴"
        alert_text = (
            f"{emoji} [AUTONOMOUS OPTIONS DISPATCH] ORDEN ENVIADA A TWS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Subyacente: {ticker} (${underlying_price:.2f})\n"
            f"Operación: BUY {opt_dir} ({strat_type.upper()})\n"
            f"Contrato: Strike ${best_contract.strike} {best_contract.right} | Exp: {best_contract.expiry}\n"
            f"Cantidad: {contracts_to_buy} contrato(s) @ ${opt_price:.2f}\n"
            f"Inversión Total: ${total_invested:.2f}\n"
            f"Regla: {rule_code}\n"
            f"Convicción: {candidate.get('conviction', 'HIGH')}\n"
            f"Motivo: {candidate.get('entry_reason', 'Ignición de volatilidad')}\n"
            f"Puente: APOLO TWS Bridge (192.168.1.105:7497)"
        )
        send_telegram_alert(alert_text)

        return {
            "success": True,
            "order_id": order_id,
            "ticker": opt_ticker_formatted,
            "contracts": contracts_to_buy,
            "price": opt_price,
            "total_invested": total_invested
        }

    except Exception as e:
        log_error(MODULE, f"Error despachando opción autónoma para {ticker}: {e}")
        return {"success": False, "reason": str(e)}
