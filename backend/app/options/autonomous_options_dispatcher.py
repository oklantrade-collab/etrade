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
from datetime import date, datetime, timezone
from typing import Dict, Any, Optional

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.options.opt_contract_picker import fetch_and_select_best_option_contract

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
    supabase: Any = None
) -> Dict[str, Any]:
    """
    Despacha una orden de opción (CALL o PUT) basada en la calificación de un escáner.
    Retorna un diccionario con el resultado de la operación.
    """
    sb = supabase or get_supabase()
    cfg = config or {}

    ticker = str(candidate.get("ticker", "")).replace("/", "").replace(".", "").upper().strip()
    if not ticker:
        return {"success": False, "reason": "Ticker vacío"}

    underlying_price = float(candidate.get("price") or candidate.get("price_at_rank") or 0.0)
    rule_code = str(candidate.get("triggered_rule") or candidate.get("rule_code") or f"OPT_{direction.upper()}")
    opt_dir = "CALL" if direction.upper() in ("CALL", "BULLISH", "LONG") else "PUT"
    today_str = date.today().isoformat()

    try:
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
            .in_("status", ["pending", "submitted"])\
            .execute()

        if orders_check.data and len(orders_check.data) > 0:
            log_info(MODULE, f"⏸️ Omitiendo despacho para {ticker}: Ya hay una orden de opción en vuelo ({len(orders_check.data)} pendientes).")
            return {"success": False, "reason": f"Orden de opción ya en vuelo para {ticker}"}

        # ── 2. SELECCIÓN INTELIGENTE DE CONTRATO (ATM, DELTA ~0.50, DTE 14-28d) ──
        budget_usd = float(cfg.get("options_trade_budget_usd", 1000.0))
        log_info(MODULE, f"🔍 Buscando contrato óptimo de {opt_dir} para {ticker} (Spot: ${underlying_price:.2f}, Budget: ${budget_usd:.0f})...")

        best_contract, rej_reasons = fetch_and_select_best_option_contract(
            symbol=ticker,
            underlying_price=underlying_price,
            direction=opt_dir,
            budget_usd=budget_usd,
            supabase=sb
        )

        if not best_contract:
            log_warning(MODULE, f"No se encontró contrato apto para {ticker} ({opt_dir}): {'; '.join(rej_reasons[:2])}")
            return {"success": False, "reason": "Sin contratos que cumplan criterios de liquidez/delta"}

        # ── 3. FORMATEO DE ORDEN Y PRECIOS ──
        opt_exp_compact = best_contract.expiry.strftime("%Y%m%d")
        opt_ticker_formatted = f"{ticker}:OPT:{opt_exp_compact}:{best_contract.strike}:{best_contract.right}"
        target_band_str = f"OPT:{opt_exp_compact}:{best_contract.strike}:{best_contract.right}"

        contracts_to_buy = max(1, getattr(best_contract, "tranche_1_contracts", 1))
        opt_price = best_contract.ask if best_contract.ask > 0 else (best_contract.mid if best_contract.mid > 0 else 1.0)
        total_invested = round(opt_price * 100 * contracts_to_buy, 2)
        now_iso = datetime.now(timezone.utc).isoformat()

        # ── 4. PERSISTENCIA EN opt_paper_trades (SUPERVISIÓN & EXITS) ──
        strat_type = "long_call" if best_contract.right == "C" else "long_put"
        trade_dir = "bullish" if best_contract.right == "C" else "bearish"
        breakeven_p = round(best_contract.strike + opt_price, 2) if best_contract.right == "C" else round(best_contract.strike - opt_price, 2)

        paper_trade_payload = {
            "symbol": ticker,
            "strategy_type": strat_type,
            "direction": trade_dir,
            "status": "open",
            "qty": contracts_to_buy,
            "expiry": best_contract.expiry.isoformat(),
            "entry_time": now_iso,
            "entry_debit": opt_price,
            "entry_costs": round(0.70 * contracts_to_buy, 2),
            "entry_total_invested": total_invested,
            "max_loss_total": total_invested,
            "max_profit_total": 9999.0,
            "breakeven": breakeven_p,
            "last_mark_price": opt_price,
            "last_mark_at": now_iso,
            "unrealized_pnl": 0.0,
            "exit_plan": {
                "initial_sl": candidate.get("stop_loss_trigger") or round(underlying_price * 0.96, 2),
                "target_ceiling": candidate.get("tactical_target_ceiling"),
                "target_floor": candidate.get("tactical_target_floor"),
                "rule_code": rule_code,
                "entry_reason": candidate.get("entry_reason", f"Autonomous {opt_dir}"),
                "last_eval_at": now_iso
            },
            "entry_fills": [{
                "conid": best_contract.conid,
                "contract_id": best_contract.contract_id,
                "strike": best_contract.strike,
                "right": best_contract.right,
                "bid": best_contract.bid,
                "ask": best_contract.ask,
                "fill_price": opt_price,
                "side": "buy",
                "closing_side": "sell",
                "market_data_type": "REALTIME"
            }],
            "model_version": "autonomous_opt_v7",
            "created_at": now_iso,
            "updated_at": now_iso
        }

        sb.table("opt_paper_trades").insert(paper_trade_payload).execute()

        # ── 5. DESPACHO A stocks_orders (SEÑAL INMEDIATA A TWS VIA APOLO BRIDGE) ──
        order_payload = {
            "ticker": opt_ticker_formatted,
            "group_name": "OPTIONS_AUTONOMOUS",
            "rule_code": rule_code,
            "order_type": "limit",  # Option Shield: LMT al precio de referencia para blindar contra slippage
            "direction": "buy",
            "shares": contracts_to_buy,
            "market_price": opt_price,
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
