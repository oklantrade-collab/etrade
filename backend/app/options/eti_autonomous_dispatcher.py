"""
eTrade — ETI Autonomous Options Dispatcher (Ross Cameron Scalping)
====================================================================
Motor de ejecución autónoma para recomendaciones ETI en Opciones.
Conecta las señales del Radar Cuántico ETI con el bucle de ejecución de mercado,
aplicando la microestructura de scalping de Ross Cameron:
- Micro-pullback hacia EMA9/VWAP
- First Candle New High (CALL) / First Candle New Low (PUT)
- RVOL >= min_rvol y alineación tendencial con VWAP
- Selección real de contrato en cadena viva (0DTE_SCALP) + Tope MAX_CONTRACTS_PER_SYMBOL = 3
- Ventana de Oro (09:35-11:30 ET) para señales PRE_MARKET / 0DTE y Guardarraíl O-13
- Despacho Broker-First a stocks_orders (TWS IB Bridge)
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase
from app.core.market_hours import is_options_market_open
from app.options.eti_storage import get_active_eti_signals, update_eti_signal_status
from app.options.eti_signal_consumer import sync_signals_from_live_eti, send_signal_feedback_to_eti
from app.options.eti_ta_gate import evaluate_eti_ta_gate
from app.options.opt_contract_picker import fetch_and_select_best_option_contract
from app.options.warrior_momentum_options import is_warrior_options_golden_window, MAX_CONTRACTS_PER_SYMBOL
from app.workers.alerts_service import send_telegram_message

MODULE = "ETI_OPTIONS_DISPATCHER"
_LAST_ETI_SYNC_TS = 0.0


def _send_telegram_opt(message: str):
    """Envía alerta Telegram asíncrona sin bloquear la ejecución."""
    try:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(message))
        except RuntimeError:
            asyncio.run(send_telegram_message(message))
    except Exception:
        pass


async def run_eti_autonomous_options_cycle(
    supabase=None,
    config: Optional[Dict[str, Any]] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Ciclo de supervisión y disparo autónomo para señales ETI en Opciones.
    1. Verifica horario de mercado de opciones (salvo force=True).
    2. Sincroniza señales activas si es necesario.
    3. Valida Guardarraíles (O-13, Circuit Breaker y Ventana de Oro 09:35-11:30 ET).
    4. Evalúa TA Gate (Modelo de Scalping Ross Cameron).
    5. Selecciona contrato líquido real vía opt_contract_picker (0DTE_SCALP) y despacha a TWS.
    """
    global _LAST_ETI_SYNC_TS

    is_open, reason_open = is_options_market_open()
    if not is_open and not force:
        return {"ok": True, "executed": 0, "reason": f"Mercado de opciones cerrado ({reason_open})"}

    sb = supabase or get_supabase()
    now_ts = time.time()

    # 1. Sincronización periódica con ETI (cada 30s en mercado o si la memoria está vacía)
    active_signals = get_active_eti_signals()
    sync_interval = 30.0 if (is_open or force) else 300.0
    if not active_signals or (now_ts - _LAST_ETI_SYNC_TS >= sync_interval):
        _LAST_ETI_SYNC_TS = now_ts
        try:
            log_info(MODULE, "🔄 Sincronizando señales activas desde servicio ETI en vivo...")
            sync_res = await sync_signals_from_live_eti()
            log_info(MODULE, f"ETI Sync completado: {sync_res.get('ingested_count', 0)} señales ingestadas.")
            active_signals = get_active_eti_signals()
        except Exception as e_sync:
            log_warning(MODULE, f"Aviso sincronizando señales con ETI: {e_sync}")

    if not active_signals:
        return {"ok": True, "executed": 0, "reason": "No hay señales ETI activas para evaluar."}

    # 2. Control de Capacidad y Riesgo Máximo
    cfg = config or {}
    max_positions = int(cfg.get("max_open_positions", 3))
    capital_limit = float(cfg.get("max_open_risk_usd", 5000.0))
    skip_time_window = bool(cfg.get("skip_time_window_check", False) or force)
    allow_est_fallback = bool(cfg.get("allow_estimated_contract_fallback", False))

    open_trades = sb.table("opt_paper_trades").select("id, max_loss_total, symbol, status").eq("status", "open").execute().data or []
    current_open_risk = sum(float(t.get("max_loss_total") or 0.0) for t in open_trades)

    in_flight_buys = sb.table("stocks_orders")\
        .select("id, ticker, market_price, limit_price, shares, target_band, group_name")\
        .eq("direction", "buy")\
        .in_("status", ["pending", "processing", "submitted"])\
        .execute().data or []

    opt_in_flight = [
        o for o in in_flight_buys
        if "OPT:" in str(o.get("target_band") or "") or "OPT" in str(o.get("group_name") or "")
    ]
    in_flight_risk = sum(
        float(o.get("limit_price") or o.get("market_price") or 0.0) * int(o.get("shares") or 1) * 100.0
        for o in opt_in_flight
    )

    total_occupied_slots = len(open_trades) + len(opt_in_flight)
    total_occupied_risk = current_open_risk + in_flight_risk

    if total_occupied_slots >= max_positions or total_occupied_risk >= capital_limit:
        return {
            "ok": True,
            "executed": 0,
            "reason": f"Cupo máximo alcanzado ({total_occupied_slots}/{max_positions} slots, Riesgo: ${total_occupied_risk:.2f}/${capital_limit:.2f})"
        }

    active_symbols = set(t.get("symbol") for t in open_trades if t.get("symbol"))
    active_symbols.update(o.get("ticker") for o in opt_in_flight if o.get("ticker"))

    executed_count = 0

    # 3. Evaluación de cada señal ETI activa contra la microestructura de Ross Cameron
    for sig in active_signals:
        if total_occupied_slots >= max_positions:
            break

        sym = sig.symbol
        if sym in active_symbols:
            continue

        # 3.A Control de Guardarraíles ETI (O-13 / Circuit Breaker)
        if (not sig.safety_guardrails.execution_allowed) or sig.safety_guardrails.circuit_breaker_active:
            log_info(MODULE, f"⛔ {sym} bloqueado por Safety Guardrails ETI (execution_allowed={sig.safety_guardrails.execution_allowed}).")
            continue

        cat_summary = str(sig.causal_context.catalyst_summary or "")
        if "ALLOW_PUTS_ONLY" in cat_summary and sig.strategy.bias == "BULLISH":
            log_info(MODULE, f"⛔ {sym} CALL bloqueado por Guardarraíl O-13 (ALLOW_PUTS_ONLY).")
            continue

        # 3.B Ventana de Oro Única (09:35-11:30 ET) para TODAS las señales ETI + Disyuntor
        if not skip_time_window:
            in_win, win_msg = is_warrior_options_golden_window()
            if not in_win:
                log_info(MODULE, f"⏸️ {sym} ETI omitido fuera de Ventana de Oro: {win_msg}")
                continue

        try:
            from app.core.circuit_breaker import can_open_new_trade
            can_open, cb_reason = can_open_new_trade(sym, sb=sb)
            if not can_open:
                log_info(MODULE, f"⛔ {sym} ETI bloqueado por Disyuntor: {cb_reason}")
                continue
        except Exception:
            pass

        try:
            gate_res = evaluate_eti_ta_gate(sig)
        except Exception as e_gate:
            log_warning(MODULE, f"Error evaluando TA Gate para {sym}: {e_gate}")
            continue

        # Validar si cumple el modelo de Scalping de Ross Cameron (Prioridad 1)
        # O en su defecto el gatillo táctico validado por ETI
        is_ross_cameron = gate_res.is_triggered and (gate_res.selected_route in ("PRIORITY_1_ROSS_CAMERON", "OPTION_2_FALLBACK_ETI"))
        if not is_ross_cameron:
            log_info(
                MODULE,
                f"⏳ {sym} ETI Standby: {gate_res.status_p1} | Spot: ${gate_res.current_price:.2f} | "
                f"VWAP: ${gate_res.current_vwap:.2f} | RVOL: {gate_res.current_rvol:.1f}x | {gate_res.reason}"
            )
            continue

        # 4. Señal Gatillada por Ross Cameron: Selección Real de Contrato Líquido
        log_info(MODULE, f"🚀 GATILLO AUTÓNOMO ROSS CAMERON: {sym} cumplió condición técnica! {gate_res.reason}")

        cand = sig.to_opportunities_candidate(current_price=gate_res.current_price)
        is_call = (cand.get("direction") == "bullish")
        opt_dir = "CALL" if is_call else "PUT"

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        from app.options.settings_defaults import get_effective_max_risk_per_trade_usd
        max_risk_usd = get_effective_max_risk_per_trade_usd(sb, cfg if "max_risk_per_trade_usd" in cfg else None)

        best_contract, rej_reasons = fetch_and_select_best_option_contract(
            symbol=sym,
            underlying_price=gate_res.current_price,
            direction=opt_dir,
            budget_usd=min(max_risk_usd, capital_limit * 0.25),
            supabase=sb,
            selection_mode="0DTE_SCALP"
        )

        if best_contract is not None:
            stk = best_contract.strike
            exp_raw = best_contract.expiry.isoformat()
            rgt = best_contract.right
            est_price = best_contract.ask if best_contract.ask > 0 else best_contract.mid
            qty = max(1, min(MAX_CONTRACTS_PER_SYMBOL, int(best_contract.tranche_1_contracts or 1)))
        elif allow_est_fallback:
            est_price = sig.options_contract.estimated_contract_price if sig.options_contract else 2.50
            qty = max(1, min(MAX_CONTRACTS_PER_SYMBOL, int(cand.get("qty") or 1)))
            stk = sig.options_contract.strike if sig.options_contract else round(gate_res.current_price, 2)
            exp_raw = sig.options_contract.expiration_date if sig.options_contract else now_dt.strftime("%Y-%m-%d")
            rgt = "C" if is_call else "P"
        else:
            log_warning(MODULE, f"⏸️ [{sym}] ETI gatillado pero sin contrato real líquido en cadena ({rej_reasons[:2]}). Orden omitida para evitar rechazo TWS.")
            continue

        unit_cost_usd = float(est_price or 0.0) * 100.0
        if unit_cost_usd > max_risk_usd + 1e-9:
            log_warning(MODULE, f"⛔ [{sym}] 1 contrato (${unit_cost_usd:.2f}) excede tope Settings (${max_risk_usd:.2f}). Orden omitida.")
            continue
        if unit_cost_usd > 0 and (unit_cost_usd * qty) > max_risk_usd + 1e-9:
            qty = max(1, int(max_risk_usd // unit_cost_usd))

        invested = est_price * 100.0 * qty
        if total_occupied_risk + invested > capital_limit:
            log_warning(MODULE, f"Presupuesto excedido para {sym} (${total_occupied_risk + invested:.2f} > ${capital_limit:.2f})")
            continue

        from datetime import timedelta
        from app.options.order_execution_plan import compute_option_entry_plan

        exp_compact = exp_raw.replace("-", "")[:8]
        opt_target_band = f"OPT:{exp_compact}:{stk}:{rgt}"
        rvol_val = float(getattr(gate_res, "current_rvol", 1.0) or 1.0)
        if best_contract is not None:
            entry_plan = compute_option_entry_plan(
                bid=float(getattr(best_contract, "bid", 0.0) or 0.0),
                ask=float(getattr(best_contract, "ask", 0.0) or 0.0),
                mid=float(getattr(best_contract, "mid", 0.0) or est_price),
                rvol=rvol_val,
            )
        else:
            entry_plan = compute_option_entry_plan(bid=0.0, ask=est_price, mid=est_price, rvol=rvol_val)
        limit_exec_price = entry_plan["limit_price"]
        expires_iso = (now_dt + timedelta(seconds=float(entry_plan["ttl_sec"]) + 120.0)).isoformat()

        # 5. Principio Broker-First: NO insertar optimísticamente en opt_paper_trades.
        # La posición se creará en opt_paper_trades ÚNICAMENTE cuando el broker confirme el fill
        # a través de ib_bridge_worker (on_ib_order_status / reconcile_broker_portfolio).

        # 6. Despachar a stocks_orders para ejecución por ib_bridge_worker (TWS)
        try:
            sb.table("stocks_orders").insert({
                "ticker": sym[:10],
                "target_band": opt_target_band,
                "group_name": "OPTIONS_AUTONOMOUS",
                "rule_code": "ROSS_CAMERON_ETI",
                "order_type": "limit",
                "limit_price": limit_exec_price,
                "direction": "buy",
                "shares": qty,
                "market_price": round(est_price, 2),
                "rvol": entry_plan["rvol"],
                "expires_at": expires_iso,
                "status": "pending",
                "created_at": now_iso,
            }).execute()
            log_info(MODULE, f"📡 Orden despachada a TWS Bridge: {sym} {opt_target_band} | {qty}x @ LMT ${limit_exec_price:.2f} (RVOL={entry_plan['rvol']}x, {entry_plan['tier']})")
        except Exception as e_ord:
            log_warning(MODULE, f"Aviso despachando orden a stocks_orders: {e_ord}")

        # 7. Actualizar estado de la señal en disco
        update_eti_signal_status(sig.signal_id, "TRIGGERED", route_used=gate_res.selected_route)

        # 8. Feedback a ETI Cloud
        try:
            fb_coro = send_signal_feedback_to_eti(
                sig.signal_id,
                status="TRIGGERED_AND_FILLED",
                route_used=gate_res.selected_route,
                fill_price=est_price,
                slippage_pct=0.5,
                notes=f"Auto-Disparo Ross Cameron Scalping: {gate_res.reason}. TP1: +{sig.risk_management.take_profit_1_pct}%"
            )
            asyncio.create_task(fb_coro)
        except Exception as e_fb:
            log_warning(MODULE, f"Aviso enviando feedback a ETI: {e_fb}")

        # 9. Alerta Institucional Telegram
        _send_telegram_opt(
            f"🎯 [ETI AUTONOMOUS OPTIONS] Disparo Ross Cameron Ejecutado\n"
            f"Ticker: {sym} ({sig.strategy.bias} 0DTE)\n"
            f"Ruta: {gate_res.selected_route}\n"
            f"Contrato: {opt_target_band} ({rgt} Strike ${stk})\n"
            f"Precio LMT: ${limit_exec_price:.2f} | Cantidad: {qty}\n"
            f"Stop Forrester: ${sig.risk_management.invalidation_underlying:.2f} | SL Prima: {sig.risk_management.stop_loss_contract_pct}%\n"
            f"Motivo Técnico: {gate_res.reason}\n"
            f"Estado: Orden PENDING enviada al Broker TWS para confirmación de fill."
        )

        total_occupied_slots += 1
        total_occupied_risk += invested
        active_symbols.add(sym)
        executed_count += 1

    return {
        "ok": True,
        "executed": executed_count,
        "active_evaluated": len(active_signals)
    }
