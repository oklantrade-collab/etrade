"""
eTrade — ETI Autonomous Options Dispatcher (Ross Cameron Scalping)
====================================================================
Motor de ejecución autónoma para recomendaciones ETI en Opciones.
Conecta las señales del Radar Cuántico ETI con el bucle de ejecución de mercado,
aplicando la microestructura de scalping de Ross Cameron:
- Micro-pullback hacia EMA9/VWAP
- First Candle New High (CALL) / First Candle New Low (PUT)
- RVOL >= 1.35x y alineación tendencial con VWAP
- Despacho automático a opt_paper_trades y a stocks_orders (TWS IB Bridge)
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
    3. Evalúa TA Gate (Modelo de Scalping Ross Cameron).
    4. Si se gatilla, ejecuta en opt_paper_trades y despacha a TWS (stocks_orders).
    """
    global _LAST_ETI_SYNC_TS

    is_open, reason_open = is_options_market_open()
    if not is_open and not force:
        return {"ok": True, "executed": 0, "reason": f"Mercado de opciones cerrado ({reason_open})"}

    sb = supabase or get_supabase()
    now_ts = time.time()

    # 1. Sincronización periódica con ETI (cada 5 minutos o si la memoria está vacía)
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

    open_trades = sb.table("opt_paper_trades").select("id, max_loss_total, symbol, status").eq("status", "open").execute().data or []
    current_open_risk = sum(float(t.get("max_loss_total") or 0.0) for t in open_trades)

    in_flight_buys = sb.table("stocks_orders")\
        .select("id, ticker, market_price, limit_price, shares, target_band, group_name")\
        .eq("direction", "buy")\
        .in_("status", ["pending", "processing"])\
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

        try:
            gate_res = evaluate_eti_ta_gate(sig)
        except Exception as e_gate:
            log_warning(MODULE, f"Error evaluando TA Gate para {sym}: {e_gate}")
            continue

        # Validar si cumple el modelo de Scalping de Ross Cameron (Prioridad 1)
        # O en su defecto el gatillo táctico validado por ETI
        is_ross_cameron = gate_res.is_triggered and (gate_res.selected_route == "PRIORITY_1_ROSS_CAMERON")
        if not is_ross_cameron:
            log_info(
                MODULE,
                f"⏳ {sym} ETI Standby: {gate_res.status_p1} | Spot: ${gate_res.current_price:.2f} | "
                f"VWAP: ${gate_res.current_vwap:.2f} | RVOL: {gate_res.current_rvol:.1f}x | {gate_res.reason}"
            )
            continue

        # 4. Señal Gatillada por Ross Cameron: Construir Ejecución
        log_info(MODULE, f"🚀 GATILLO AUTÓNOMO ROSS CAMERON: {sym} cumplió condición técnica! {gate_res.reason}")

        cand = sig.to_opportunities_candidate(current_price=gate_res.current_price)
        est_price = sig.options_contract.estimated_contract_price if sig.options_contract else 2.50
        qty = int(cand.get("qty") or 1)
        invested = est_price * 100.0 * qty

        if total_occupied_risk + invested > capital_limit:
            log_warning(MODULE, f"Presupuesto excedido para {sym} (${total_occupied_risk + invested:.2f} > ${capital_limit:.2f})")
            continue

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # Parámetros del contrato
        stk = sig.options_contract.strike if sig.options_contract else round(gate_res.current_price, 2)
        exp_raw = sig.options_contract.expiration_date if sig.options_contract else now_dt.strftime("%Y-%m-%d")
        exp_compact = exp_raw.replace("-", "")[:8]
        is_call = (cand.get("direction") == "bullish")
        rgt = "C" if is_call else "P"
        opt_target_band = f"OPT:{exp_compact}:{stk}:{rgt}"

        pos_data = {
            "symbol": sym,
            "strategy_type": cand["strategy_type"],
            "direction": cand["direction"],
            "status": "open",
            "qty": qty,
            "expiry": cand["expiry"],
            "entry_time": now_iso,
            "entry_debit": est_price,
            "entry_fills": [{
                "conid": None,
                "side": "buy",
                "closing_side": "sell",
                "right": rgt,
                "strike": stk,
                "bid": est_price * 0.98,
                "ask": est_price * 1.02,
                "fill_price": est_price,
                "slippage_applied": 0.02,
                "market_data_type": "LIVE",
                "fee_usd": 0.70 * qty
            }],
            "entry_costs": 0.70 * qty,
            "entry_total_invested": invested + (0.70 * qty),
            "max_loss_total": invested,
            "max_profit_total": invested * (sig.risk_management.take_profit_1_pct / 100.0),
            "breakeven": cand.get("breakeven"),
            "unrealized_pnl": 0.0,
            "last_mark_price": est_price,
            "last_mark_at": now_iso,
            "exit_plan": {
                **cand["exit_plan"],
                "execution_route": "PRIORITY_1_ROSS_CAMERON",
                "invalidation_underlying": sig.risk_management.invalidation_underlying,
                "is_zero_dte": True,
                "horizon": "SCALPING",
                "time_decay_guard_enabled": True,
            },
            "model_version": "ETI-ROSS-CAMERON-v1.0",
            "settings_version": "AUTONOMOUS",
        }

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
                "limit_price": round(est_price, 2),
                "direction": "buy",
                "shares": qty,
                "market_price": round(est_price, 2),
                "status": "pending",
                "created_at": now_iso,
            }).execute()
            log_info(MODULE, f"📡 Orden despachada a TWS Bridge: {sym} {opt_target_band} @ ${est_price:.2f}")
        except Exception as e_ord:
            log_warning(MODULE, f"Aviso despachando orden a stocks_orders: {e_ord}")

        # 7. Actualizar estado de la señal en disco
        update_eti_signal_status(sig.signal_id, "TRIGGERED", route_used="PRIORITY_1_ROSS_CAMERON")

        # 8. Feedback a ETI Cloud
        try:
            fb_coro = send_signal_feedback_to_eti(
                sig.signal_id,
                status="TRIGGERED_AND_FILLED",
                route_used="PRIORITY_1_ROSS_CAMERON",
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
            f"Ruta: PRIORITY_1_ROSS_CAMERON\n"
            f"Contrato: {opt_target_band} ({rgt} Strike ${stk})\n"
            f"Precio Entrada Estimado: ${est_price:.2f} | Cantidad: {qty}\n"
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
