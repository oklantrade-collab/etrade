"""
eTrader v5.0 — Interactive Brokers Bridge Worker (APOLO Local Bridge)
=====================================================================
Este worker corre localmente en tu computadora "APOLO" para enlazar
Interactive Brokers TWS (Paper Trading, puerto 7497) con Supabase y Vercel.

¿Por qué corre en APOLO?
1. IBKR exige autenticación diaria y 2FA en Trader Workstation (TWS).
2. TWS abre un socket local en 127.0.0.1:7497.
3. Como APOLO tiene IP dinámica, este worker hace conexión SALIENTE hacia
   Supabase, eliminando la necesidad de IP fija, puertos abiertos o DDNS.
"""
import os
import sys
import time
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

# Añadir raíz de backend al PYTHONPATH y cargar .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.core.time_utils import parse_iso_utc
from app.data.ib_provider import get_ib_connection, IB_AVAILABLE

MODULE = "ib_bridge"

# Mapa local para relacionar orderId de IB con id de Supabase
# { ib_order_id: supabase_order_row }
PENDING_IB_ORDERS = {}
# Seguimiento de ciclo de vida activo (Chaser + TTL) para órdenes vivas en TWS
WORKING_IB_ORDERS = {}
ACTIVE_BRIDGE = None

TERMINAL_ORDER_ERROR_CODES = {103, 110, 200, 201, 202, 203, 321, 388, 399}
LIQUID_OPT_UNDERLYINGS = {
    "SPY", "QQQ", "NVDA", "AAPL", "TSLA", "AMD",
    "META", "AMZN", "GOOGL", "IWM", "PLTR",
}


def _update_order_status(
    sb,
    order_id,
    status: str,
    cancel_reason: str | None = None,
    allowed_statuses: list[str] | None = None,
) -> None:
    """Actualiza estado de orden en stocks_orders guardando `cancel_reason` si la columna existe."""
    if not sb or order_id is None:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {"status": status, "updated_at": now_iso}
    if cancel_reason:
        payload["cancel_reason"] = str(cancel_reason)[:120]
    try:
        q = sb.table("stocks_orders").update(payload).eq("id", order_id)
        if allowed_statuses:
            q = q.in_("status", allowed_statuses)
        q.execute()
    except Exception:
        fallback = {"status": status, "updated_at": now_iso}
        try:
            q = sb.table("stocks_orders").update(fallback).eq("id", order_id)
            if allowed_statuses:
                q = q.in_("status", allowed_statuses)
            q.execute()
        except Exception:
            try:
                q = sb.table("stocks_orders").update({"status": status}).eq("id", order_id)
                if allowed_statuses:
                    q = q.in_("status", allowed_statuses)
                q.execute()
            except Exception:
                pass


def on_ib_order_error(req_id: int, error_code: int, error_msg: str):
    """Callback para rechazos terminales de TWS que a veces no emiten orderStatus(Cancelled)."""
    if int(error_code) not in TERMINAL_ORDER_ERROR_CODES:
        return
    if req_id not in PENDING_IB_ORDERS:
        return

    order_ctx = PENDING_IB_ORDERS.get(req_id) or {}
    target_status = "cancelled" if int(error_code) == 202 else "failed"
    cancel_reason = f"IB_ERROR_{int(error_code)}"
    ticker = str(order_ctx.get("ticker") or "UNKNOWN").upper()
    direction = str(order_ctx.get("direction") or "buy").lower()
    shares = abs(int(float(order_ctx.get("shares") or 1)))
    target_b = str(order_ctx.get("target_band") or "").strip().upper()
    group_u = str(order_ctx.get("group_name") or "").strip().upper()
    is_opt_order = (
        ":OPT:" in ticker or ticker.startswith("OPT:")
        or ":OPT:" in target_b or target_b.startswith("OPT:") or "OPT:" in target_b
        or group_u in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS")
    )

    log_warning(MODULE, f"⛔ [TWS ERROR #{req_id}] Code={error_code} ({ticker} {direction.upper()}) -> {target_status}: {error_msg}")

    try:
        sb = get_supabase()
        _update_order_status(
            sb,
            order_ctx.get("id"),
            target_status,
            cancel_reason=cancel_reason,
            allowed_statuses=["pending", "processing", "submitted"],
        )
        if (not is_opt_order) and direction == "sell" and ACTIVE_BRIDGE and hasattr(ACTIVE_BRIDGE, "_in_flight_sells"):
            cur_inf = ACTIVE_BRIDGE._in_flight_sells.get(ticker, 0)
            ACTIVE_BRIDGE._in_flight_sells[ticker] = max(0, cur_inf - shares)
        elif is_opt_order and direction == "sell":
            from app.options.broker_sync import parse_option_order_contract_key, _row_contract_key
            order_ck = parse_option_order_contract_key(ticker, target_b)
            if order_ck:
                open_rows = sb.table("opt_paper_trades").select("*").eq("symbol", order_ck[0]).eq("status", "open").execute().data or []
                now_iso = datetime.now(timezone.utc).isoformat()
                for r in open_rows:
                    r_ck = _row_contract_key(r)
                    if r_ck[1] == order_ck[1] and abs(r_ck[2] - order_ck[2]) <= 0.05 and r_ck[3] == order_ck[3]:
                        plan = dict(r.get("exit_plan") or {})
                        if plan.get("closing_pending"):
                            plan["closing_pending"] = False
                            sb.table("opt_paper_trades").update({"exit_plan": plan, "updated_at": now_iso}).eq("id", r["id"]).execute()
    except Exception as e:
        log_warning(MODULE, f"Aviso procesando on_ib_order_error para #{req_id}: {e}")
    finally:
        PENDING_IB_ORDERS.pop(req_id, None)
        WORKING_IB_ORDERS.pop(req_id, None)


def send_telegram_alert(message: str):
    """Envío seguro de alertas Telegram."""
    try:
        from app.workers.alerts_service import send_telegram_message
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(message))
        except RuntimeError:
            asyncio.run(send_telegram_message(message))
    except Exception:
        pass


def on_ib_order_status(order_id: int, status_info: dict):
    """Callback invocado por IB TWS cuando una orden cambia de estado."""
    status = status_info.get("status")
    filled = status_info.get("filled", 0)
    avg_price = status_info.get("avg_fill_price", 0.0)

    log_info(MODULE, f"🔔 TWS Callback: Order #{order_id} -> Estado={status.upper()} (Filled={filled} @ ${avg_price:.2f})")

    if order_id not in PENDING_IB_ORDERS:
        return

    order_ctx = PENDING_IB_ORDERS[order_id]
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = order_ctx.get("ticker", "UNKNOWN")
    direction = order_ctx.get("direction", "buy").lower()
    shares = int(order_ctx.get("shares", filled or 1))

    target_b = str(order_ctx.get("target_band") or "").strip().upper()
    ticker_u = str(ticker or "").strip().upper()
    group_u = str(order_ctx.get("group_name") or "").strip().upper()
    is_opt_order = (
        ":OPT:" in ticker_u or ticker_u.startswith("OPT:") or
        ":OPT:" in target_b or target_b.startswith("OPT:") or "OPT:" in target_b or
        group_u in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS")
    )

    # Si la orden fue completada (FILLED)
    if status == "filled":
        exec_price = avg_price if avg_price > 0 else float(order_ctx.get("market_price") or 0)
        target_price = float(order_ctx.get("limit_price") or order_ctx.get("market_price") or exec_price)
        slippage_usd = round(exec_price - target_price, 4) if direction == "buy" else round(target_price - exec_price, 4)
        slippage_pct = round((slippage_usd / target_price * 100.0), 2) if target_price > 0 else 0.0

        log_info(MODULE, f"📊 Fills Reconciliation: Ticker={ticker} {direction.upper()} | Exec=${exec_price:.2f} Target=${target_price:.2f} | Slippage=${slippage_usd:+.2f} ({slippage_pct:+.2f}%)")

        # 1. Actualizar orden en stocks_orders
        try:
            try:
                sb.table("stocks_orders").update({
                    "status": "filled",
                    "filled_price": exec_price,
                    "slippage_usd": slippage_usd,
                    "slippage_pct": slippage_pct,
                    "filled_at": now_iso
                }).eq("id", order_ctx["id"]).execute()
            except Exception:
                sb.table("stocks_orders").update({
                    "status": "filled",
                    "filled_price": exec_price,
                    "filled_at": now_iso
                }).eq("id", order_ctx["id"]).execute()
        except Exception as e:
            log_error(MODULE, f"Error actualizando orden {order_ctx['id']} en Supabase: {e}")

        # 2. Si fue BUY: Crear o actualizar posición en stocks_positions (o opt_paper_trades si es opción)
        if direction == "buy":
            try:
                if is_opt_order:
                    try:
                        und_sym = ticker_u.split(":")[0].replace("OPT", "").strip(":")
                        exp_d = "20261026"
                        strike_num = 0.0
                        is_call = True
                        if "OPT:" in target_b:
                            parts = target_b.split(":")
                            if len(parts) == 4 and parts[0] == "OPT":
                                exp_d = parts[1]
                                strike_num = float(parts[2])
                                is_call = parts[3].upper() == "C"
                            elif len(parts) >= 5:
                                und_sym = parts[0] if parts[0] != "OPT" else parts[1]
                                exp_d = parts[2]
                                strike_num = float(parts[3])
                                is_call = parts[4].upper() == "C"
                        elif ":OPT:" in ticker_u or ticker_u.startswith("OPT:"):
                            parts = ticker_u.split(":")
                            if len(parts) >= 5:
                                und_sym = parts[0] if parts[0] != "OPT" else parts[1]
                                exp_d = parts[2]
                                strike_num = float(parts[3])
                                is_call = parts[-1].upper() == "C"

                        formatted_exp = f"{exp_d[:4]}-{exp_d[4:6]}-{exp_d[6:8]}" if len(exp_d) == 8 else exp_d
                        from app.options.broker_sync import _row_contract_key
                        target_ck = (und_sym, formatted_exp, round(strike_num, 2), "C" if is_call else "P")
                        existing_opts = sb.table("opt_paper_trades").select("*").eq("symbol", und_sym).eq("status", "open").execute().data or []
                        same_contract_row = next((r for r in existing_opts if _row_contract_key(r) == target_ck), None)
                        if same_contract_row:
                            old_q = int(same_contract_row.get("qty") or 0)
                            old_d = float(same_contract_row.get("entry_debit") or exec_price)
                            new_q = old_q + shares
                            new_d = round(((old_d * old_q) + (exec_price * shares)) / new_q, 4) if new_q > 0 else exec_price
                            new_inv = round(new_d * 100.0 * new_q, 2)
                            sb.table("opt_paper_trades").update({
                                "qty": new_q,
                                "entry_debit": new_d,
                                "entry_total_invested": new_inv,
                                "max_loss_total": new_inv,
                                "last_mark_price": exec_price,
                                "last_mark_at": now_iso,
                                "updated_at": now_iso,
                            }).eq("id", same_contract_row["id"]).execute()
                            log_info(MODULE, f"✅ Piramidación de opción confirmada en TWS para {und_sym}: {new_q}x @ ${new_d:.2f}")
                        else:
                            cid = None
                            conid = None
                            try:
                                c_res = sb.table("opt_contracts").select("id, conid").eq("expiry", formatted_exp).eq("strike", strike_num).eq("right", "C" if is_call else "P").limit(1).execute()
                                if c_res.data:
                                    cid = c_res.data[0].get("id")
                                    conid = c_res.data[0].get("conid")
                            except Exception:
                                pass

                            u_id = 1
                            try:
                                u_res = sb.table("opt_underlyings").select("id").eq("symbol", und_sym).limit(1).execute()
                                if u_res.data:
                                    u_id = u_res.data[0]["id"]
                            except Exception:
                                pass

                            fills = [{
                                "contract_id": cid,
                                "conid": conid,
                                "side": "buy",
                                "closing_side": "sell",
                                "right": "C" if is_call else "P",
                                "strike": strike_num,
                                "bid": exec_price,
                                "ask": exec_price,
                                "fill_price": exec_price,
                                "slippage_applied": 0.0,
                                "market_data_type": "LIVE",
                                "fee_usd": 0.70,
                            }]

                            sb.table("opt_paper_trades").insert({
                                "underlying_id": u_id,
                                "symbol": und_sym,
                                "strategy_type": "long_call" if is_call else "long_put",
                                "direction": "bullish" if is_call else "bearish",
                                "status": "open",
                                "qty": shares,
                                "expiry": formatted_exp,
                                "entry_time": now_iso,
                                "entry_debit": exec_price,
                                "entry_fills": fills,
                                "entry_costs": round(0.70 * shares, 2),
                                "last_mark_price": exec_price,
                                "last_mark_at": now_iso,
                                "unrealized_pnl": 0.0,
                                "entry_total_invested": round(shares * exec_price * 100, 2),
                                "max_loss_total": round(shares * exec_price * 100, 2),
                                "max_profit_total": 9999.0,
                                "breakeven": round(strike_num + exec_price, 2) if is_call else round(strike_num - exec_price, 2),
                                "exit_plan": {
                                    "trailing_sl_type": "INITIAL",
                                    "highest_premium_seen": exec_price,
                                    "stop_loss_premium": round(exec_price * 0.70, 4),
                                    "rule_code": order_ctx.get("rule_code"),
                                    "time_decay_guard_enabled": True,
                                    "is_zero_dte": True,
                                    "horizon": "SCALPING",
                                    "last_eval_at": now_iso
                                },
                                "model_version": "ib_live_paper",
                                "created_at": now_iso,
                                "updated_at": now_iso
                            }).execute()
                            log_info(MODULE, f"✅ Trade de opción registrado en opt_paper_trades para {und_sym}")
                    except Exception as opt_err:
                        log_warning(MODULE, f"No se pudo guardar en opt_paper_trades: {opt_err}")
                else:
                    # Verificar si ya existe posición abierta/closing para acciones (soporte DCA LONG o cobertura SHORT)
                    pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).in_("status", ["open", "closing"]).execute()
                    if pos_res.data:
                        pos = pos_res.data[0]
                        old_shares = abs(int(pos.get("shares") or 0))
                        old_avg = float(pos.get("avg_price") or 0)
                        if str(pos.get("direction") or "long").lower() in ("short", "sell"):
                            rem_sh = old_shares - shares
                            if rem_sh > 0:
                                sb.table("stocks_positions").update({
                                    "shares": rem_sh,
                                    "shares_remaining": rem_sh,
                                    "current_price": exec_price,
                                    "status": "open",
                                    "updated_at": now_iso
                                }).eq("id", pos["id"]).execute()
                                log_info(MODULE, f"✅ Cobertura PARCIAL SHORT confirmada por Broker para {ticker}: {shares} recompradas, quedan {rem_sh}")
                            else:
                                pnl_usd = round((old_avg - exec_price) * old_shares, 2)
                                pnl_pct = round(((old_avg - exec_price) / old_avg * 100), 2) if old_avg > 0 else 0.0
                                sb.table("trades_journal").insert({
                                    "ticker": ticker,
                                    "shares": old_shares,
                                    "entry_price": old_avg,
                                    "exit_price": exec_price,
                                    "entry_date": pos.get("first_buy_at") or now_iso,
                                    "exit_date": now_iso,
                                    "pnl_usd": pnl_usd,
                                    "pnl_pct": pnl_pct,
                                    "result": "win" if pnl_usd >= 0 else "loss",
                                    "exit_reason": "IB_BROKER_CONFIRMED_BUY_COVER",
                                    "trade_type": pos.get("group_name") or "STOCKS_IB"
                                }).execute()
                                sb.table("stocks_positions").update({
                                    "status": "closed",
                                    "shares": 0,
                                    "shares_remaining": 0,
                                    "current_price": exec_price,
                                    "unrealized_pnl": pnl_usd,
                                    "unrealized_pnl_pct": pnl_pct,
                                    "sl_close_reason": "broker_confirmed_buy_cover",
                                    "updated_at": now_iso
                                }).eq("id", pos["id"]).execute()
                                log_info(MODULE, f"✅ Cierre TOTAL SHORT confirmado por Broker para {ticker} en Supabase (PnL: ${pnl_usd:+.2f})")
                        else:
                            total_shares = old_shares + shares
                            new_avg = ((old_avg * old_shares) + (exec_price * shares)) / total_shares if total_shares > 0 else exec_price

                            sb.table("stocks_positions").update({
                                "shares": total_shares,
                                "avg_price": round(new_avg, 4),
                                "total_cost": round(total_shares * new_avg, 2),
                                "current_price": exec_price,
                                "updated_at": now_iso
                            }).eq("id", pos["id"]).execute()
                            log_info(MODULE, f"✅ Posición DCA actualizada para {ticker}: {total_shares} acc @ ${new_avg:.2f}")
                    else:
                        atr_fb = exec_price * 0.02
                        sl_p = round(exec_price - (atr_fb * 2.0), 2)
                        tp_p = round(exec_price + (atr_fb * 5.0), 2)

                        sb.table("stocks_positions").insert({
                            "ticker": ticker,
                            "direction": "long",
                            "shares": shares,
                            "avg_price": exec_price,
                            "total_cost": round(shares * exec_price, 2),
                            "current_price": exec_price,
                            "stop_loss": sl_p,
                            "trailing_sl_price": sl_p,
                            "highest_price_reached": exec_price,
                            "take_profit": tp_p,
                            "group_name": order_ctx.get("group_name", "IB_PAPER"),
                            "first_buy_at": now_iso,
                            "status": "open",
                            "updated_at": now_iso
                        }).execute()
                        log_info(MODULE, f"✅ Nueva posición creada en Supabase para {ticker}: {shares} acc @ ${exec_price:.2f} (SL: ${sl_p:.2f}, TP: ${tp_p:.2f})")

            except Exception as pos_e:
                log_error(MODULE, f"Error creando/actualizando posición para {ticker}: {pos_e}")

        # 3. Si fue SELL: Ejecutar cierre parcial o total confirmado con el broker
        elif direction == "sell":
            try:
                if is_opt_order:
                    # Cierre de opción confirmado con datos reales del broker
                    try:
                        from app.options.broker_sync import parse_option_order_contract_key, _row_contract_key
                        order_ck = parse_option_order_contract_key(ticker_u, target_b)
                        und_sym = order_ck[0] if order_ck else ticker_u.split(":")[0].replace("OPT", "").strip(":")
                        opt_pos_res = sb.table("opt_paper_trades").select("*").eq("symbol", und_sym).eq("status", "open").execute()
                        open_matches = [
                            r for r in (opt_pos_res.data or [])
                            if not order_ck or (
                                _row_contract_key(r)[0] == order_ck[0]
                                and _row_contract_key(r)[1] == order_ck[1]
                                and abs(_row_contract_key(r)[2] - order_ck[2]) <= 0.05
                                and _row_contract_key(r)[3] == order_ck[3]
                            )
                        ]
                        already_closed_recently = False
                        target_rows = open_matches
                        if not target_rows:
                            recent_res = sb.table("opt_paper_trades").select("*").eq("symbol", und_sym).order("id", desc=True).limit(50).execute()
                            for r in (recent_res.data or []):
                                r_ck = _row_contract_key(r)
                                if not order_ck or (r_ck[0] == order_ck[0] and r_ck[1] == order_ck[1] and abs(r_ck[2] - order_ck[2]) <= 0.05 and r_ck[3] == order_ck[3]):
                                    target_rows = [r]
                                    already_closed_recently = (r.get("status") == "closed")
                                    break

                        for opos in target_rows:
                            entry_debit = float(opos.get("entry_debit") or 0.0)
                            cur_qty = int(opos.get("qty") or 1)
                            sell_qty = min(cur_qty, max(1, int(filled or shares or cur_qty)))
                            rem_opt_qty = cur_qty - sell_qty
                            total_inv = float(opos.get("entry_total_invested") or (entry_debit * 100 * cur_qty))
                            sold_inv = round(total_inv * (sell_qty / cur_qty), 2) if cur_qty > 0 else total_inv
                            fee = round(0.70 * sell_qty, 2)
                            recovered = round((exec_price * 100 * sell_qty) - fee, 2)
                            leg_realized = round(recovered - sold_inv, 2)
                            prev_realized = float(opos.get("realized_pnl") or 0.0)
                            total_realized = round(prev_realized + leg_realized, 2)
                            pnl_pct = round(((exec_price - entry_debit) / entry_debit * 100), 2) if entry_debit > 0 else 0.0
                            plan = dict(opos.get("exit_plan") or {})
                            plan["closing_pending"] = False

                            if rem_opt_qty > 0:
                                # Venta PARCIAL confirmada por el broker
                                if plan.get("pending_is_partial"):
                                    plan["partial_tp_taken"] = True
                                    plan["trailing_sl_type"] = "EMA9_15M"
                                plan.pop("pending_is_partial", None)
                                plan.pop("pending_qty_to_close", None)
                                sb.table("opt_paper_trades").update({
                                    "qty": rem_opt_qty,
                                    "entry_total_invested": round(max(0.0, total_inv - sold_inv), 2),
                                    "realized_pnl": total_realized,
                                    "last_mark_price": exec_price,
                                    "last_mark_at": now_iso,
                                    "exit_plan": plan,
                                    "updated_at": now_iso,
                                }).eq("id", opos["id"]).execute()
                                log_info(MODULE, f"✅ Toma PARCIAL confirmada por Broker para {und_sym}: {sell_qty} vendidas @ ${exec_price:.2f}, quedan {rem_opt_qty} (PnL tramo: ${leg_realized:+.2f})")
                                continue

                            raw_reason = plan.get("pending_exit_reason") or opos.get("exit_reason") or ("take_profit" if total_realized >= 0 else "stop_loss")
                            if raw_reason == "take_profit" and total_realized < 0:
                                final_reason = "stop_loss"
                            elif raw_reason == "stop_loss" and total_realized > 0:
                                final_reason = "take_profit"
                            else:
                                final_reason = raw_reason
                            plan["closed_at"] = now_iso

                            upd_payload = {
                                "status": "closed",
                                "exit_credit": exec_price,
                                "exit_costs": fee,
                                "exit_total_recovered": recovered,
                                "realized_pnl": total_realized,
                                "unrealized_pnl": 0.0,
                                "last_mark_price": exec_price,
                                "last_mark_at": now_iso,
                                "exit_reason": final_reason,
                                "exit_plan": plan,
                                "updated_at": now_iso,
                                "exit_fills": [{
                                    "side": "buy",
                                    "closing_side": "sell",
                                    "fill_price": exec_price,
                                    "bid": exec_price,
                                    "ask": exec_price,
                                    "fee_usd": fee,
                                    "market_data_type": "LIVE"
                                }]
                            }
                            if not opos.get("exit_time"):
                                upd_payload["exit_time"] = now_iso
                            sb.table("opt_paper_trades").update(upd_payload).eq("id", opos["id"]).execute()
                            log_info(MODULE, f"opt_paper_trades ID {opos['id']} ({und_sym}) cerrado confirmado por Broker a ${exec_price:.2f} (PnL: ${total_realized:.2f})")

                            if not already_closed_recently:
                                try:
                                    from app.core.circuit_breaker import record_trade_completion
                                    record_trade_completion(und_sym, total_realized, sb=sb)
                                except Exception:
                                    pass

                            if not already_closed_recently:
                                try:
                                    sb.table("trades_journal").insert({
                                        "ticker": und_sym,
                                        "shares": sell_qty,
                                        "entry_price": entry_debit,
                                        "exit_price": exec_price,
                                        "entry_date": opos.get("entry_time") or now_iso,
                                        "exit_date": now_iso,
                                        "pnl_usd": total_realized,
                                        "pnl_pct": pnl_pct,
                                        "result": "win" if total_realized >= 0 else "loss",
                                        "exit_reason": plan.get("detailed_exit_reason") or "IB_BROKER_CONFIRMED_SELL",
                                        "trade_type": "OPTIONS_GAP_RUNNER"
                                    }).execute()
                                except Exception as tj_err:
                                    log_warning(MODULE, f"Aviso insertando en trades_journal para opción {und_sym}: {tj_err}")
                    except Exception as opt_close_e:
                        log_warning(MODULE, f"Error actualizando opt_paper_trades en SELL: {opt_close_e}")
                else:
                    pos_res = sb.table("stocks_positions").select("*").eq("ticker", ticker).in_("status", ["open", "closing"]).execute()
                    for pos in (pos_res.data or []):
                        entry_p = float(pos.get("avg_price") or 0)
                        pos_sh = int(pos.get("shares") or 0)
                        rem_sh = pos_sh - shares

                        if rem_sh > 0:
                            # Venta PARCIAL confirmada por el broker
                            pnl_usd = round((exec_price - entry_p) * shares, 2)
                            pnl_pct = round(((exec_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0
                            sb.table("stocks_positions").update({
                                "shares": rem_sh,
                                "shares_remaining": rem_sh,
                                "current_price": exec_price,
                                "status": "open",
                                "updated_at": now_iso
                            }).eq("id", pos["id"]).execute()
                            log_info(MODULE, f"✅ Venta PARCIAL confirmada por Broker para {ticker}: {shares} vendidas, quedan {rem_sh}")
                        else:
                            # Cierre TOTAL confirmado por el broker
                            pnl_usd = round((exec_price - entry_p) * pos_sh, 2)
                            pnl_pct = round(((exec_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0
                            sb.table("trades_journal").insert({
                                "ticker": ticker,
                                "shares": pos_sh,
                                "entry_price": entry_p,
                                "exit_price": exec_price,
                                "entry_date": pos.get("first_buy_at") or now_iso,
                                "exit_date": now_iso,
                                "pnl_usd": pnl_usd,
                                "pnl_pct": pnl_pct,
                                "result": "win" if pnl_usd >= 0 else "loss",
                                "exit_reason": "IB_BROKER_CONFIRMED_SELL",
                                "trade_type": pos.get("group_name") or "STOCKS_IB"
                            }).execute()

                            # Propuesta #3: Registrar cierre en Disyuntor Diario
                            try:
                                from app.core.circuit_breaker import record_trade_completion
                                record_trade_completion(ticker, pnl_usd)
                            except Exception as cb_err:
                                log_warning(MODULE, f"Aviso registrando disyuntor en broker fill: {cb_err}")
                            sb.table("stocks_positions").update({
                                "status": "closed",
                                "shares": 0,
                                "shares_remaining": 0,
                                "current_price": exec_price,
                                "unrealized_pnl": pnl_usd,
                                "unrealized_pnl_pct": pnl_pct,
                                "sl_close_reason": "broker_confirmed_sell",
                                "updated_at": now_iso
                            }).eq("id", pos["id"]).execute()
                            log_info(MODULE, f"✅ Cierre TOTAL confirmado por Broker para {ticker} en Supabase")
            except Exception as close_e:
                log_error(MODULE, f"Error procesando SELL {ticker} en Supabase: {close_e}")

        # Notificar por Telegram
        send_telegram_alert(
            f"🎯 [IBKR PAPER] ORDEN EJECUTADA\n"
            f"Ticker: {ticker} ({direction.upper()})\n"
            f"Acciones: {shares}\n"
            f"Precio Ejecución: ${exec_price:.2f}\n"
            f"IB Order ID: #{order_id}"
        )

        # Descontar del libro de in-flight sells si fue venta
        if ACTIVE_BRIDGE and hasattr(ACTIVE_BRIDGE, '_in_flight_sells') and direction == "sell":
            cur_inf = ACTIVE_BRIDGE._in_flight_sells.get(ticker.upper(), 0)
            ACTIVE_BRIDGE._in_flight_sells[ticker.upper()] = max(0, cur_inf - shares)

        # Limpiar de seguimiento activo
        PENDING_IB_ORDERS.pop(order_id, None)
        WORKING_IB_ORDERS.pop(order_id, None)

        # Solicitar reconciliación asíncrona fuera del hilo callback de TWS para no bloquear socket/EClient
        if ACTIVE_BRIDGE:
            ACTIVE_BRIDGE._reconcile_requested = True

    elif status in ["cancelled", "inactive"]:
        try:
            _update_order_status(
                sb,
                order_ctx.get("id"),
                "cancelled",
                cancel_reason=order_ctx.get("_cancel_reason_hint") or "TWS_CANCELLED",
                allowed_statuses=["pending", "processing", "submitted"],
            )
            if (not is_opt_order) and direction == "sell" and ACTIVE_BRIDGE and hasattr(ACTIVE_BRIDGE, "_in_flight_sells"):
                cur_inf = ACTIVE_BRIDGE._in_flight_sells.get(ticker.upper(), 0)
                ACTIVE_BRIDGE._in_flight_sells[ticker.upper()] = max(0, cur_inf - shares)
            if is_opt_order and direction == "sell":
                from app.options.broker_sync import parse_option_order_contract_key, _row_contract_key
                order_ck = parse_option_order_contract_key(ticker_u, target_b)
                if order_ck:
                    open_rows = sb.table("opt_paper_trades").select("*").eq("symbol", order_ck[0]).eq("status", "open").execute().data or []
                    for r in open_rows:
                        r_ck = _row_contract_key(r)
                        if r_ck[1] == order_ck[1] and abs(r_ck[2] - order_ck[2]) <= 0.05 and r_ck[3] == order_ck[3]:
                            plan = dict(r.get("exit_plan") or {})
                            if plan.get("closing_pending"):
                                plan["closing_pending"] = False
                                sb.table("opt_paper_trades").update({"exit_plan": plan, "updated_at": now_iso}).eq("id", r["id"]).execute()
        except Exception:
            pass
        PENDING_IB_ORDERS.pop(order_id, None)
        WORKING_IB_ORDERS.pop(order_id, None)


import socket

def get_default_ib_host() -> str:
    hostname = socket.gethostname().upper()
    # Si este script corre directamente en APOLO, conectar por localhost
    if "APOLO" in hostname:
        return "127.0.0.1"
    # Si corre desde otra máquina, buscar variable o apuntar a APOLO en la LAN
    env_host = os.getenv("IB_HOST")
    if env_host:
        return env_host
    # Probar si 127.0.0.1:7497 está escuchando, de lo contrario fallback a APOLO (192.168.1.105)
    s = socket.socket()
    s.settimeout(0.5)
    if s.connect_ex(("127.0.0.1", 7497)) == 0:
        s.close()
        return "127.0.0.1"
    s.close()
    return "192.168.1.105"


class IBBridgeWorker:
    """Worker permanente para el puente APOLO <-> IBKR TWS <-> Supabase."""

    def __init__(self, host=None, port=None, client_id=None):
        global ACTIVE_BRIDGE
        self.host = host or get_default_ib_host()
        self.port = port or int(os.getenv("IB_PORT", "7497"))
        self.client_id = client_id or int(os.getenv("IB_CLIENT_ID", "26"))
        self.ib = None
        self.running = True
        self._reconcile_requested = False
        ACTIVE_BRIDGE = self

    def initialize_ib(self) -> bool:
        """Establece conexión inicial con TWS en el puerto 7497 con auto-fallback de Client ID."""
        if not IB_AVAILABLE:
            log_error(MODULE, "❌ La librería 'ibapi' no está instalada en este entorno.")
            return False

        # Si el client_id base está bloqueado por una sesión residual de TWS, probar los siguientes 5 IDs
        for offset in range(5):
            cid = self.client_id + offset
            try:
                import app.data.ib_provider as ib_mod
                ib_mod._ib_instance = None  # Instancia fresca para cada intento
                self.ib = ib_mod.get_ib_connection()
                self.ib.set_order_callback(on_ib_order_status)
                if hasattr(self.ib, "set_error_callback"):
                    self.ib.set_error_callback(on_ib_order_error)
                log_info(MODULE, f"🔌 Intentando conectar a TWS en {self.host}:{self.port} (Client ID: {cid})...")
                connected = self.ib.connect_tws(host=self.host, port=self.port, client_id=cid)
                if connected:
                    self.client_id = cid
                    log_info(MODULE, f"✅ ¡Conexión exitosa con Interactive Brokers TWS! (Client ID: {cid}) (Cuentas: {self.ib.accounts or 'Detectando...'})")
                    self._start_micro_pullback_scalper_if_needed()
                    return True
                else:
                    self.ib.disconnect_tws()
            except Exception as e:
                log_error(MODULE, f"❌ Error conectando a TWS con client_id {cid}: {e}")

        log_warning(MODULE, "⚠️ No se pudo conectar a TWS tras varios intentos. Asegúrate de que TWS esté abierto en modo PAPER (puerto 7497).")
        return False

    def _start_micro_pullback_scalper_if_needed(self):
        """Inicia el escáner y motor de micro-pullbacks en APOLO si está explícitamente habilitado."""
        if os.getenv("ENABLE_MICRO_SCALPER", "false").lower() != "true":
            return
        if getattr(self, "_scalp_scanner_started", False):
            return
        self._scalp_scanner_started = True

        import threading

        def _run_scanner_loop():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def _runner():
                    from app.stocks.micro_pullback_scanner import get_micro_pullback_scanner
                    scanner = get_micro_pullback_scanner()
                    scanner.start()
                    log_info(MODULE, "⚡ Motor In-Memory Micro-Pullback ACTIVADO en APOLO (TWS Local).")
                    while getattr(scanner, "is_running", True):
                        await asyncio.sleep(1)

                loop.run_until_complete(_runner())
            except Exception as e:
                log_error(MODULE, f"Error en thread de Micro-Pullback Scalper: {e}")

        th = threading.Thread(target=_run_scanner_loop, daemon=True, name="micro-pullback-apolo")
        th.start()

    def update_heartbeat(self):
        """Actualiza el estado de vida del puente en Supabase."""
        try:
            sb = get_supabase()
            is_connected = bool(self.ib and self.ib.connected)
            accounts_str = ",".join(self.ib.accounts) if (self.ib and self.ib.accounts) else "Paper-Session"
            payload = {
                "connected": is_connected,
                "host_name": "APOLO",
                "tws_port": self.port,
                "mode": "PAPER",
                "accounts": accounts_str,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            # Upsert en stocks_config con on_conflict='key'
            sb.table("stocks_config").upsert({
                "key": "ib_bridge_heartbeat",
                "value": str(payload),
                "description": "Estado en tiempo real del agente IBKR Bridge en APOLO",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }, on_conflict="key").execute()
        except Exception as e:
            log_warning(MODULE, f"Error reportando heartbeat a Supabase: {e}")

    def process_pending_orders(self):
        """Busca órdenes pendientes en Supabase y las despacha a TWS."""
        if not self.ib or not self.ib.connected:
            return

        try:
            sb = get_supabase()
            # Buscar órdenes que requieran ejecución por el broker
            res = sb.table("stocks_orders")\
                .select("*")\
                .eq("status", "pending")\
                .order("created_at", desc=True)\
                .limit(20)\
                .execute()

            orders = res.data or []
            now_dt = datetime.now(timezone.utc)
            for order in orders:
                order_id = order["id"]
                ticker = order["ticker"]
                direction = order.get("direction", "buy").lower()
                order_type = order.get("order_type", "market").lower()
                shares = int(order.get("shares") or 5)
                price = float(order.get("limit_price") or order.get("market_price") or 0.0)
                trigger_price = float(order.get("trigger_price") or price or 0.0)

                # Validar vencimiento / TTL de la orden para evitar despachar señales viejas
                c_str = order.get("created_at")
                exp_str = order.get("expires_at")
                is_expired = False
                if exp_str:
                    try:
                        exp_dt = parse_iso_utc(exp_str)
                        if exp_dt and exp_dt < now_dt:
                            is_expired = True
                    except Exception:
                        pass
                elif c_str:
                    try:
                        c_dt = parse_iso_utc(c_str)
                        if c_dt:
                            age_min = (now_dt - c_dt).total_seconds() / 60.0
                            if age_min > 15.0:
                                is_expired = True
                    except Exception:
                        pass

                if is_expired:
                    sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                    log_info(MODULE, f"⌛ Orden {order_id} ({ticker}) cancelada por vencimiento / TTL ({direction.upper()} {shares}x).")
                    continue

                log_info(MODULE, f"🔍 Evaluando orden pendiente para TWS: {direction.upper()} {shares}x {ticker} ({order_type.upper()})")

                try:
                    from ibapi.order import Order

                    # Reconocer si es un contrato de opción (CALL/PUT) o acción
                    contract = None
                    is_option = False
                    target_b = str(order.get("target_band") or "").strip().upper()
                    ticker_u = str(ticker or "").strip().upper()
                    group_u = str(order.get("group_name") or "").strip().upper()

                    is_option_candidate = (
                        ":OPT:" in ticker_u or ticker_u.startswith("OPT:") or
                        ":OPT:" in target_b or target_b.startswith("OPT:") or "OPT:" in target_b or
                        group_u in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS")
                    )

                    if is_option_candidate:
                        try:
                            # 1. Intentar target_band si contiene OPT
                            if "OPT:" in target_b:
                                parts = target_b.split(":")
                                if len(parts) == 4 and parts[0] == "OPT":
                                    # Formato: OPT:YYYYMMDD:STRIKE:RIGHT
                                    sym_p = ticker_u.split(":")[0]
                                    exp_p = parts[1]
                                    strike_p = float(parts[2])
                                    right_p = parts[3]
                                    contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                                    is_option = True
                                elif len(parts) >= 5:
                                    sym_p = parts[0] if parts[0] != "OPT" else parts[1]
                                    exp_p = parts[2]
                                    strike_p = float(parts[3])
                                    right_p = parts[4]
                                    contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                                    is_option = True

                            # 2. Si no se obtuvo de target_band, intentar ticker
                            if not contract and ("OPT:" in ticker_u or ":OPT:" in ticker_u):
                                parts = ticker_u.split(":")
                                if len(parts) >= 5:
                                    sym_p = parts[0] if parts[0] != "OPT" else parts[1]
                                    exp_p = parts[2]
                                    strike_p = float(parts[3])
                                    right_p = parts[4]
                                    contract = self.ib.us_option_contract(sym_p, exp_p, strike_p, right_p)
                                    is_option = True

                            if contract:
                                log_info(MODULE, f"🎯 Contrato de OPCIÓN identificado: {contract.symbol} {contract.lastTradeDateOrContractMonth} Strike ${contract.strike} Right={contract.right}")
                        except Exception as opt_parse_err:
                            log_warning(MODULE, f"Aviso al parsear contrato de opción ({ticker_u}, target={target_b}): {opt_parse_err}")

                    # Si era candidata de opción pero no se pudo construir el contrato, cancelar para evitar operar acciones por error
                    if is_option_candidate and not contract:
                        msg = f"⚠️ [OPTION PARSE GUARD] Orden {order_id} ({ticker_u}, target={target_b}) no pudo resolver contrato de opción. Cancelando orden para evitar operar acciones por error."
                        log_warning(MODULE, msg)
                        sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                        continue

                    # ── GUARDIA DE MERCADO PARA OPCIONES ──
                    if is_option:
                        from app.core.market_hours import is_options_market_open
                        is_opt_open, opt_reason = is_options_market_open()
                        if not is_opt_open:
                            log_warning(MODULE, f"⏸️ [MARKET GATE] Mercado de opciones cerrado ({opt_reason}). Orden {ticker_u} ({direction}) no despachada a TWS para evitar rechazo del broker.")
                            continue

                    allow_ah = False
                    if not is_option and direction.lower() == "buy":
                        try:
                            sc_res = sb.table("stocks_config").select("value").eq("key", "allow_after_hours").limit(1).execute()
                            sc_rows = sc_res.data if hasattr(sc_res, "data") and isinstance(sc_res.data, list) else []
                            if sc_rows and isinstance(sc_rows[0], dict):
                                val_ah = sc_rows[0].get("value")
                                allow_ah = (val_ah is True) or str(val_ah).strip().lower() in ("true", "1", "yes")
                        except Exception:
                            allow_ah = False
                        if not allow_ah:
                            from app.core.market_hours import is_market_open
                            is_stk_open, stk_reason = is_market_open()
                            if not is_stk_open:
                                log_warning(MODULE, f"⏸️ [STOCK MARKET GATE] Mercado regular cerrado ({stk_reason}) y allow_after_hours=False. Cancelando BUY {ticker_u}.")
                                oid_db = order.get("id")
                                if oid_db:
                                    _update_order_status(sb, oid_db, "cancelled", cancel_reason="MARKET_CLOSED")
                                continue

                    # ── BLOQUEO ANTI-SHORT PARA ACCIONES (NUNCA APLICA A OPCIONES) ──
                    reserved_sell_shares = 0
                    if not is_option and not contract:
                        if direction == "sell":
                            broker_pos_map = self.ib.request_broker_positions(timeout=3.0) or getattr(self.ib, "_positions", {}) or {}
                            broker_pos = broker_pos_map.get(ticker.upper())

                            confirmed_shares = float(broker_pos.get("shares", 0.0)) if broker_pos else 0.0
                            if not hasattr(self, '_in_flight_sells'):
                                self._in_flight_sells = {}
                            already_in_flight = self._in_flight_sells.get(ticker.upper(), 0)
                            available_shares = max(0, int(confirmed_shares) - already_in_flight)

                            if available_shares <= 0:
                                msg = f"⛔ [ANTI-SHORT SHIELD] Orden SELL para {ticker} ({shares} acc) CANCELADA: Broker tiene {confirmed_shares} acc y ya hay {already_in_flight} en proceso de venta. Cero acciones disponibles."
                                log_warning(MODULE, msg)
                                _update_order_status(sb, order_id, "cancelled", cancel_reason="ANTI_SHORT_ZERO_POS")
                                self._reconcile_requested = True
                                send_telegram_alert(msg)
                                continue

                            if shares > available_shares:
                                log_warning(MODULE, f"⚠️ [CLAMP SHARES] Ajustando venta de {ticker} de {shares} a {available_shares} acc para no entrar en corto.")
                                shares = available_shares

                            self._in_flight_sells[ticker.upper()] = already_in_flight + shares
                            reserved_sell_shares = shares

                        contract = self.ib.us_stock_contract(ticker)

                    # ── BLINDAJE ANTI-SHORT Y TIPO DE ORDEN PARA OPCIONES ──
                    if is_option:
                        if direction == "sell":
                            # Verificar que realmente tengamos la opción en TWS antes de enviar SELL
                            broker_pos_map = self.ib.request_broker_positions(timeout=3.0) or getattr(self.ib, "_positions", {}) or {}
                            held_opt_qty = 0
                            for pk, pv in broker_pos_map.items():
                                if pv.get("sec_type") == "OPT" and str(pv.get("underlying") or "").upper() == contract.symbol.upper():
                                    if str(pv.get("expiry") or "").replace("-", "") == str(contract.lastTradeDateOrContractMonth or "").replace("-", ""):
                                        if abs(float(pv.get("strike") or 0) - float(contract.strike or 0)) <= 0.05 and str(pv.get("right") or "").upper() == str(contract.right or "").upper():
                                            held_opt_qty = int(round(float(pv.get("shares") or 0)))
                                            break
                            if held_opt_qty <= 0:
                                log_warning(MODULE, f"⛔ [OPTION ANTI-SHORT] Orden SELL {ticker_u} ({target_b}) cancelada: 0 contratos abiertos en TWS.")
                                _update_order_status(sb, order_id, "cancelled", cancel_reason="ANTI_SHORT_ZERO_POS")
                                self._reconcile_requested = True
                                continue
                            if shares > held_opt_qty:
                                shares = held_opt_qty
                            # Evitar Error 201 cancelando primero cualquier orden BUY opuesta abierta sobre el mismo contrato
                            try:
                                if hasattr(self.ib, "cancel_opposing_option_orders"):
                                    c_cancelled = self.ib.cancel_opposing_option_orders(
                                        contract.symbol,
                                        contract.lastTradeDateOrContractMonth,
                                        contract.strike,
                                        contract.right,
                                        closing_action="SELL",
                                    )
                                    if c_cancelled > 0:
                                        time.sleep(0.4)
                            except Exception as c_err:
                                log_warning(MODULE, f"Aviso cancelando órdenes opuestas en TWS: {c_err}")
                            # Para cierres SELL de opciones: usar MKT para garantizar salida inmediata en TWS
                            order_type = "market"
                        else:
                            eff_price = price if price > 0 else float(order.get("limit_price") or order.get("market_price") or 0.0)
                            if eff_price <= 0:
                                log_warning(MODULE, f"⚠️ Orden BUY de opción {ticker_u} sin precio límite válido. Cancelando.")
                                sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", order_id).execute()
                                continue
                            order_type = "limit"
                            price = eff_price

                    # Marcar en proceso solo tras pasar guardias y horario de mercado (evita zombis en 'processing')
                    sb.table("stocks_orders").update({"status": "processing"}).eq("id", order_id).execute()
                    log_info(MODULE, f"🚀 Enviando orden a TWS: {direction.upper()} {shares}x {ticker} ({order_type.upper()})")

                    rvol_val = float(order.get("rvol") or 1.0)
                    exec_plan = None
                    if is_option and direction.lower() == "buy":
                        from app.options.order_execution_plan import compute_option_entry_plan, snap_option_tick
                        from app.options.settings_defaults import get_effective_max_risk_per_trade_usd

                        q_key_pre = f"{contract.symbol}:OPT:{contract.lastTradeDateOrContractMonth}:{round(float(contract.strike or 0.0), 2)}:{contract.right}"
                        live_q = {}
                        try:
                            if hasattr(self.ib, "get_contract_quote"):
                                live_q = self.ib.get_contract_quote(contract, q_key_pre, timeout=1.5) or {}
                        except Exception:
                            live_q = {}

                        l_bid = float(live_q.get("bid") or 0.0)
                        l_ask = float(live_q.get("ask") or 0.0)
                        max_risk_usd = get_effective_max_risk_per_trade_usd(sb, None)

                        if l_bid > 0 and l_ask > 0 and l_ask >= l_bid:
                            l_mid = (l_bid + l_ask) / 2.0
                            spread_pct = ((l_ask - l_bid) / l_mid * 100.0) if l_mid > 0 else 0.0
                            if spread_pct > 15.0:
                                log_warning(MODULE, f"⛔ [LIVE SPREAD GATE] Spread OPRA {spread_pct:.1f}% > 15% para {ticker_u} ({target_b}). Cancelando BUY.")
                                _update_order_status(sb, order_id, "cancelled", cancel_reason="WIDE_LIVE_SPREAD")
                                continue
                            if (l_ask * 100.0) > max_risk_usd + 1e-9:
                                log_warning(MODULE, f"⛔ [LIVE ASK RISK CAP] 1x {ticker_u} Ask=${l_ask:.2f} (${l_ask*100:.2f}) excede tope ${max_risk_usd:.2f}. Cancelando BUY.")
                                _update_order_status(sb, order_id, "cancelled", cancel_reason="EXCEEDS_MAX_RISK_LIVE_ASK")
                                continue
                            if (l_ask * 100.0 * shares) > max_risk_usd + 1e-9:
                                shares = max(1, int(max_risk_usd // (l_ask * 100.0)))
                            exec_plan = compute_option_entry_plan(
                                bid=l_bid, ask=l_ask, mid=l_mid, rvol=rvol_val, no_opra_fallback=False
                            )
                            price = exec_plan["limit_price"]
                        else:
                            no_opra_mode = "lmt_wide_120s"
                            try:
                                m_res = sb.table("stocks_config").select("value").eq("key", "opt_no_opra_exec_mode").limit(1).execute()
                                m_rows = getattr(m_res, "data", None)
                                if isinstance(m_rows, list) and m_rows and isinstance(m_rows[0], dict) and m_rows[0].get("value"):
                                    no_opra_mode = str(m_rows[0]["value"]).strip().lower()
                            except Exception:
                                no_opra_mode = "lmt_wide_120s"

                            if (
                                no_opra_mode == "mkt_liquid"
                                and str(contract.symbol or "").upper() in LIQUID_OPT_UNDERLYINGS
                                and (price * 100.0 * shares) <= min(max_risk_usd, 740.0)
                            ):
                                order_type = "market"
                                exec_plan = {"max_chase_price": price, "reprice_after_sec": 999.0, "ttl_sec": 60.0}
                            else:
                                exec_plan = compute_option_entry_plan(
                                    bid=0.0, ask=price, mid=price, rvol=rvol_val, no_opra_fallback=True
                                )

                        if exec_plan and shares > 0 and order_type == "limit":
                            cap_by_risk = snap_option_tick(max_risk_usd / (100.0 * shares), mode="floor")
                            if cap_by_risk > 0:
                                exec_plan["max_chase_price"] = max(price, min(float(exec_plan["max_chase_price"]), cap_by_risk))

                    ib_ord = Order()
                    ib_ord.eTradeOnly = False
                    ib_ord.firmQuoteOnly = False
                    ib_ord.outsideRth = bool(allow_ah and not is_option)
                    ib_ord.tif = "DAY"
                    ib_ord.action = direction.upper()
                    ib_ord.totalQuantity = shares
                    
                    if order_type in ("stop", "stp", "buy_stop") and trigger_price > 0:
                        ib_ord.orderType = "STP"
                        ib_ord.auxPrice = round(trigger_price, 2)
                    elif order_type in ("stop_limit", "stp_lmt") and trigger_price > 0:
                        ib_ord.orderType = "STP LMT"
                        ib_ord.auxPrice = round(trigger_price, 2)
                        ib_ord.lmtPrice = round(price if price > 0 else (trigger_price * 1.005), 2)
                    elif order_type == "limit" and price > 0:
                        ib_ord.orderType = "LMT"
                        if is_option:
                            from app.options.order_execution_plan import snap_option_tick
                            price = snap_option_tick(price, mode="nearest")
                            ib_ord.lmtPrice = price
                        else:
                            ib_ord.lmtPrice = round(price, 2)
                    else:
                        ib_ord.orderType = "MKT"

                    ib_ord.transmit = True
                    ib_order_id = self.ib.get_next_order_id()

                    # Guardar referencia para el callback y seguimiento Chaser/TTL/MKT Watchdog
                    PENDING_IB_ORDERS[ib_order_id] = order
                    if (
                        (direction.lower() == "buy" and ib_ord.orderType == "LMT")
                        or (is_option and direction.lower() == "sell")
                        or (not is_option and ib_ord.orderType == "MKT")
                    ):
                        lmt_base = float(getattr(ib_ord, "lmtPrice", 0.0) or price or 0.01)
                        q_key = (
                            f"{contract.symbol}:OPT:{contract.lastTradeDateOrContractMonth}:{round(float(contract.strike or 0.0), 2)}:{contract.right}"
                            if is_option
                            else str(contract.symbol or ticker_u).upper()
                        )
                        default_ttl = (
                            45.0
                            if (not is_option and ib_ord.orderType == "MKT")
                            else (90.0 if direction.lower() == "sell" else (exec_plan["ttl_sec"] if exec_plan else 60.0))
                        )
                        WORKING_IB_ORDERS[ib_order_id] = {
                            "order_ctx": order,
                            "contract": contract,
                            "ib_ord": ib_ord,
                            "order_type": ib_ord.orderType,
                            "quote_key": q_key,
                            "placed_at": time.time(),
                            "last_reprice_at": time.time(),
                            "reprice_count": 0,
                            "max_chase_price": exec_plan["max_chase_price"] if exec_plan else round(lmt_base * 1.05, 2),
                            "reprice_after_sec": exec_plan["reprice_after_sec"] if exec_plan else 20.0,
                            "ttl_sec": default_ttl,
                            "is_option": is_option,
                            "direction": direction.lower(),
                        }

                    # Colocar la orden en TWS
                    self.ib.placeOrder(ib_order_id, contract, ib_ord)
                    try:
                        sb.table("stocks_orders").update({"status": "submitted"}).eq("id", order_id).execute()
                    except Exception:
                        pass
                    log_info(MODULE, f"📋 Orden enviada con éxito a TWS con ID #{ib_order_id} (Tipo={ib_ord.orderType}, LMT=${getattr(ib_ord, 'lmtPrice', 0):.2f})")

                except Exception as ord_err:
                    if reserved_sell_shares > 0 and hasattr(self, '_in_flight_sells'):
                        cur_inf = self._in_flight_sells.get(ticker.upper(), 0)
                        self._in_flight_sells[ticker.upper()] = max(0, cur_inf - reserved_sell_shares)
                    log_error(MODULE, f"Error despachando orden {order_id} a TWS: {ord_err}")
                    sb.table("stocks_orders").update({"status": "failed"}).eq("id", order_id).execute()

        except Exception as e:
            log_error(MODULE, f"Error revisando órdenes pendientes: {e}")

    def reconcile_broker_portfolio(self):
        """
        Consulta las posiciones reales en Interactive Brokers TWS (Paper)
        y reconcilia la tabla stocks_positions en Supabase para que predomine
        el Broker sobre cualquier estado local ("El Broker es la verdad absoluta").
        """
        if not self.ib or not self.ib.connected:
            return

        try:
            sb = get_supabase()
            broker_positions = self.ib.request_broker_positions(timeout=6.0)
            if not getattr(self.ib, "_positions_sync_ok", True) and not broker_positions:
                log_warning(MODULE, "⏸️ Omitiendo reconciliación: TWS no confirmó positionEnd y snapshot está vacío.")
                return
            now_iso = datetime.now(timezone.utc).isoformat()

            # Guardar el snapshot del portfolio real en stocks_config
            try:
                sb.table("stocks_config").upsert({
                    "key": "ib_broker_portfolio",
                    "value": str(broker_positions),
                    "description": "Cartera de posiciones reales en Interactive Brokers TWS",
                    "updated_at": now_iso
                }, on_conflict="key").execute()
            except Exception:
                pass

            # ── 1. SEPARAR EN STOCKS Y OPTIONS ──
            broker_stocks = {}
            broker_options = {}
            for sym, b_data in broker_positions.items():
                qty = float(b_data.get("shares") or 0)
                if qty == 0:
                    continue
                sec_type = str(b_data.get("sec_type") or "").upper()
                if sec_type == "OPT" or ":OPT:" in sym or b_data.get("right") or b_data.get("strike"):
                    broker_options[sym] = b_data
                else:
                    broker_stocks[sym] = b_data

            # ── 2. RECONCILIAR STOCKS_POSITIONS (SÓLO ACCIONES REALES) ──
            sb_pos_res = sb.table("stocks_positions").select("*").in_("status", ["open", "closing"]).execute()
            sb_open_stocks = {}
            
            # Identificar símbolos de opciones abiertas en el broker
            broker_opt_symbols = {str(opt_b.get("underlying") or k.split(":")[0]).upper() for k, opt_b in broker_options.items()}

            for p in (sb_pos_res.data or []):
                p_ticker = str(p.get("ticker", "")).upper()
                # Si una opción se coló en stocks_positions (o su subyacente como SPY cuando solo es opción):
                is_opt = p.get("group_name") in ("OPTIONS", "OPEN_GAP_RUNNER_OPT", "OPTIONS_AUTONOMOUS") or ":OPT:" in p_ticker or p_ticker.startswith("OPT:") or "OPT:" in str(p.get("target_band") or "")
                is_opt_underlying_only = (p_ticker in broker_opt_symbols and p_ticker not in broker_stocks)

                if is_opt or is_opt_underlying_only:
                    sb.table("stocks_positions").delete().eq("id", p["id"]).execute()
                    log_info(MODULE, f"🧹 [LIMPIEZA] Opción/Subyacente {p_ticker} eliminada de stocks_positions.")
                else:
                    sb_open_stocks[p["ticker"]] = p

            from app.stocks.position_monitor import compute_dynamic_stock_trailing_sl
            for sym, b_data in broker_stocks.items():
                signed_qty = int(round(float(b_data["shares"])))
                if signed_qty == 0:
                    continue
                direction = "short" if signed_qty < 0 else "long"
                qty = abs(signed_qty)
                avg_cost = float(b_data["avg_cost"])

                cur_p = float(b_data.get("market_price") or (self.ib._prices.get(sym, 0.0) if hasattr(self.ib, '_prices') else 0.0) or 0.0)
                if cur_p <= 0 and sym in sb_open_stocks:
                    old_cp = float(sb_open_stocks[sym].get("current_price") or 0.0)
                    if old_cp > 0 and abs(old_cp - avg_cost) > 0.0001:
                        cur_p = old_cp
                if cur_p <= 0:
                    cur_p = avg_cost

                atr_fb = max(0.05, cur_p * 0.02)
                if direction == "short":
                    sl_calc = round(avg_cost + (atr_fb * 2.0), 2)
                    tp_calc = round(max(0.01, avg_cost - (atr_fb * 5.0)), 2)
                    calc_pnl = round((avg_cost - cur_p) * qty, 2)
                    pnl_pct = round(((avg_cost - cur_p) / avg_cost * 100), 2) if avg_cost > 0 else 0.0
                else:
                    sl_calc = round(max(0.01, avg_cost - (atr_fb * 2.0)), 2)
                    tp_calc = round(avg_cost + (atr_fb * 5.0), 2)
                    calc_pnl = round((cur_p - avg_cost) * qty, 2)
                    pnl_pct = round(((cur_p - avg_cost) / avg_cost * 100), 2) if avg_cost > 0 else 0.0
                tws_pnl = b_data.get("unrealized_pnl")
                pnl_usd = round(float(tws_pnl), 2) if (tws_pnl is not None and abs(float(tws_pnl)) > 0.0001) else calc_pnl

                if sym in sb_open_stocks:
                    existing_pos = sb_open_stocks[sym]
                    old_shares = int(existing_pos.get("shares") or 0)
                    old_avg = float(existing_pos.get("avg_price") or 0)
                    old_cur = float(existing_pos.get("current_price") or 0)
                    old_pnl = float(existing_pos.get("unrealized_pnl") or 0)
                    old_dir = str(existing_pos.get("direction") or "long").lower()
                    cur_sl_v = float(existing_pos.get("stop_loss") or 0.0)

                    # Preservar 'closing' solo si hay orden de cierre fresca (<=120s) en vuelo
                    keep_closing = False
                    if existing_pos.get("status") == "closing":
                        try:
                            close_dir = "buy" if direction == "short" else "sell"
                            act_close = sb.table("stocks_orders").select("id, created_at").eq("ticker", sym).eq("direction", close_dir).in_("status", ["pending", "processing", "submitted"]).order("created_at", desc=True).limit(1).execute()
                            if act_close.data and act_close.data[0].get("created_at"):
                                ac_dt = parse_iso_utc(act_close.data[0]["created_at"])
                                if ac_dt and (datetime.now(timezone.utc) - ac_dt).total_seconds() <= 120.0:
                                    keep_closing = True
                        except Exception:
                            pass

                    new_hi = round(max(float(existing_pos.get("highest_price_reached") or 0.0), avg_cost, cur_p), 4)
                    old_lo = float(existing_pos.get("lowest_price_reached") or 0.0)
                    new_lo = round(min(old_lo, avg_cost, cur_p) if old_lo > 0 else min(avg_cost, cur_p), 4)
                    dyn_sl, dyn_reason = compute_dynamic_stock_trailing_sl(
                        entry_price=avg_cost,
                        current_price=cur_p,
                        highest_price=new_hi,
                        current_sl=cur_sl_v,
                        side=direction,
                        lowest_price=new_lo,
                    )
                    sl_improved = bool(dyn_reason)

                    if (
                        old_shares != qty
                        or old_dir != direction
                        or abs(old_avg - avg_cost) > 0.01
                        or abs(old_cur - cur_p) >= 0.001
                        or abs(old_pnl - pnl_usd) >= 0.01
                        or sl_improved
                        or (existing_pos.get("status") == "closing" and not keep_closing)
                    ):
                        update_payload = {
                            "status": "closing" if keep_closing else "open",
                            "direction": direction,
                            "shares": qty,
                            "shares_remaining": qty,
                            "avg_price": round(avg_cost, 4),
                            "total_cost": round(qty * avg_cost, 2),
                            "current_price": round(cur_p, 4),
                            "unrealized_pnl": pnl_usd,
                            "unrealized_pnl_pct": pnl_pct,
                            "highest_price_reached": new_hi,
                            "lowest_price_reached": new_lo,
                            "updated_at": now_iso
                        }
                        if not cur_sl_v or cur_sl_v <= 0:
                            update_payload["stop_loss"] = sl_calc
                            update_payload["trailing_sl_price"] = sl_calc
                        elif sl_improved:
                            update_payload["stop_loss"] = dyn_sl
                            update_payload["trailing_sl_price"] = dyn_sl
                            update_payload["sl_type"] = "trailing_ratchet"
                            update_payload["sl_activation_reason"] = str(dyn_reason)[:100]
                        if not existing_pos.get("take_profit") or float(existing_pos.get("take_profit")) <= 0:
                            update_payload["take_profit"] = tp_calc

                        sb.table("stocks_positions").update(update_payload).eq("id", existing_pos["id"]).execute()
                        log_info(MODULE, f"🔄 [SYNC STOCKS] {sym} ({direction.upper()}): {qty} acc | Avg=${avg_cost:.2f} | Actual=${cur_p:.2f} | PnL=${pnl_usd:+.2f} ({pnl_pct:+.2f}%)")
                else:
                    # HEALING: Comprobar si existía una posición cerrada recientemente
                    recent_closed = sb.table("stocks_positions")\
                        .select("*")\
                        .eq("ticker", sym)\
                        .order("updated_at", desc=True)\
                        .limit(1)\
                        .execute()
                    
                    if recent_closed.data:
                        # Reactivar la fila existente en lugar de duplicar y dejar basura en CLOSED HISTORY
                        target_row = recent_closed.data[0]
                        target_id = target_row["id"]
                        hi_heal = round(max(float(target_row.get("highest_price_reached") or 0.0), avg_cost, cur_p), 4)
                        lo_heal = round(min(float(target_row.get("lowest_price_reached") or avg_cost), avg_cost, cur_p), 4)
                        cur_sl_h = float(target_row.get("stop_loss") or 0.0) or sl_calc
                        dyn_sl_h, dyn_reason_h = compute_dynamic_stock_trailing_sl(
                            entry_price=avg_cost, current_price=cur_p, highest_price=hi_heal,
                            current_sl=cur_sl_h, side=direction, lowest_price=lo_heal,
                        )
                        heal_sl = dyn_sl_h if dyn_reason_h else cur_sl_h
                        heal_payload = {
                            "status": "open",
                            "direction": direction,
                            "shares": qty,
                            "shares_remaining": qty,
                            "avg_price": round(avg_cost, 4),
                            "total_cost": round(qty * avg_cost, 2),
                            "current_price": cur_p,
                            "unrealized_pnl": pnl_usd,
                            "unrealized_pnl_pct": pnl_pct,
                            "highest_price_reached": hi_heal,
                            "lowest_price_reached": lo_heal,
                            "stop_loss": heal_sl,
                            "trailing_sl_price": heal_sl,
                            "sl_close_reason": None,
                            "exit_triggered_by": None,
                            "updated_at": now_iso
                        }
                        sb.table("stocks_positions").update(heal_payload).eq("id", target_id).execute()
                        
                        # Eliminar únicamente posibles entradas ficticias recientes (<15 min) de trades_journal
                        try:
                            cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
                            sb.table("trades_journal").delete().eq("ticker", sym).gte("exit_date", cutoff_iso).execute()
                        except Exception:
                            pass
                        log_info(MODULE, f"♻️ [HEALING] Posición {sym} ({direction.upper()}) reabierta en Supabase (validada con broker: {qty} acc @ ${avg_cost:.2f})")
                    else:
                        hi_init = round(max(avg_cost, cur_p), 4)
                        lo_init = round(min(avg_cost, cur_p), 4)
                        dyn_sl_i, dyn_reason_i = compute_dynamic_stock_trailing_sl(
                            entry_price=avg_cost, current_price=cur_p, highest_price=hi_init,
                            current_sl=sl_calc, side=direction, lowest_price=lo_init,
                        )
                        init_sl = dyn_sl_i if dyn_reason_i else sl_calc
                        new_pos = {
                            "ticker": sym,
                            "direction": direction,
                            "shares": qty,
                            "shares_remaining": qty,
                            "avg_price": round(avg_cost, 4),
                            "total_cost": round(qty * avg_cost, 2),
                            "current_price": cur_p,
                            "unrealized_pnl": pnl_usd,
                            "unrealized_pnl_pct": pnl_pct,
                            "stop_loss": init_sl,
                            "trailing_sl_price": init_sl,
                            "highest_price_reached": hi_init,
                            "lowest_price_reached": lo_init,
                            "take_profit": tp_calc,
                            "group_name": "IB_PAPER",
                            "first_buy_at": now_iso,
                            "status": "open",
                            "updated_at": now_iso
                        }
                        sb.table("stocks_positions").insert(new_pos).execute()
                        log_info(MODULE, f"📥 [SYNC STOCKS] Acción del Broker agregada a Supabase: {sym} ({direction.upper()}) {qty} acc @ ${avg_cost:.2f}")

            # CONFIRMACIÓN BROKER: Cerrar en stocks_positions cualquier acción que el broker confirme que ya NO existe
            for sym, p_data in sb_open_stocks.items():
                if sym not in broker_stocks:
                    is_short_p = str(p_data.get("direction") or "long").lower() in ("short", "sell")
                    close_dir_p = "buy" if is_short_p else "sell"
                    open_dir_p = "sell" if is_short_p else "buy"
                    try:
                        fb_str = p_data.get("first_buy_at") or p_data.get("updated_at")
                        if fb_str:
                            fb_dt = parse_iso_utc(fb_str)
                            if fb_dt and (datetime.now(timezone.utc) - fb_dt).total_seconds() < 90.0:
                                continue
                        inflight_open = sb.table("stocks_orders").select("id").eq("ticker", sym).eq("direction", open_dir_p).in_("status", ["pending", "processing", "submitted"]).limit(1).execute()
                        if inflight_open.data:
                            continue
                    except Exception:
                        pass

                    real_exit_time = now_iso
                    real_exit_price = p_data.get("current_price") or p_data.get("avg_price")
                    sell_rule = "broker_sync"
                    try:
                        sell_ord = sb.table("stocks_orders")\
                            .select("filled_at, filled_price, rule_code")\
                            .eq("ticker", sym)\
                            .eq("direction", close_dir_p)\
                            .eq("status", "filled")\
                            .order("filled_at", desc=True)\
                            .limit(1)\
                            .execute()
                        if sell_ord.data and sell_ord.data[0].get("filled_at"):
                            real_exit_time = sell_ord.data[0]["filled_at"]
                            if sell_ord.data[0].get("filled_price"):
                                real_exit_price = float(sell_ord.data[0]["filled_price"])
                            if sell_ord.data[0].get("rule_code"):
                                sell_rule = sell_ord.data[0]["rule_code"]
                    except Exception as ord_e:
                        log_warning(MODULE, f"No se pudo consultar orden {close_dir_p} para {sym}: {ord_e}")

                    entry_p = float(p_data.get("avg_price") or 0.0)
                    pos_sh = abs(int(float(p_data.get("shares") or 0)))
                    if is_short_p:
                        pnl_usd = round((entry_p - real_exit_price) * pos_sh, 2)
                        pnl_pct = round(((entry_p - real_exit_price) / entry_p * 100), 2) if entry_p > 0 else 0.0
                    else:
                        pnl_usd = round((real_exit_price - entry_p) * pos_sh, 2)
                        pnl_pct = round(((real_exit_price - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0

                    # Si cerró con PnL negativo pero la orden decía TP/PROFIT (por slippage/spread en penny stocks), reflejarlo honestamente
                    journal_reason = sell_rule
                    if pnl_usd < 0 and ("TP" in sell_rule.upper() or "PROFIT" in sell_rule.upper()):
                        journal_reason = "SLIPPAGE_DEFENSIVE_EXIT"

                    sb.table("stocks_positions").update({
                        "status": "closed",
                        "current_price": real_exit_price,
                        "unrealized_pnl": pnl_usd,
                        "unrealized_pnl_pct": pnl_pct,
                        "sl_close_reason": journal_reason,
                        "updated_at": real_exit_time
                    }).eq("id", p_data["id"]).execute()

                    # Registrar permanentemente en trades_journal para Closed History (con deduplicación 120s)
                    try:
                        skip_journal_dup = False
                        try:
                            recent_tj = sb.table("trades_journal").select("id, exit_date, shares, exit_price").eq("ticker", sym).order("exit_date", desc=True).limit(3).execute()
                            rj_rows = recent_tj.data if hasattr(recent_tj, "data") and isinstance(recent_tj.data, list) else []
                            ex_cur_dt = parse_iso_utc(real_exit_time)
                            for rj in rj_rows:
                                if not isinstance(rj, dict):
                                    continue
                                ex_prev_dt = parse_iso_utc(rj.get("exit_date"))
                                same_sh = int(round(float(rj.get("shares") or 0))) == int(round(float(pos_sh or 0)))
                                same_px = abs(float(rj.get("exit_price") or 0.0) - float(real_exit_price or 0.0)) <= 0.02
                                near_tm = (
                                    ex_cur_dt is not None
                                    and ex_prev_dt is not None
                                    and abs((ex_cur_dt - ex_prev_dt).total_seconds()) <= 120.0
                                )
                                if same_sh and same_px and near_tm:
                                    skip_journal_dup = True
                                    break
                        except Exception:
                            skip_journal_dup = False

                        if not skip_journal_dup:
                            sb.table("trades_journal").insert({
                                "ticker": sym,
                                "shares": pos_sh,
                                "entry_price": entry_p,
                                "exit_price": real_exit_price,
                                "entry_date": p_data.get("first_buy_at") or real_exit_time,
                                "exit_date": real_exit_time,
                                "pnl_usd": pnl_usd,
                                "pnl_pct": pnl_pct,
                                "result": "win" if pnl_usd >= 0 else "loss",
                                "exit_reason": journal_reason,
                                "trade_type": p_data.get("group_name") or "STOCKS_IB"
                            }).execute()
                            try:
                                from app.core.circuit_breaker import record_trade_completion
                                record_trade_completion(sym, pnl_usd, sb=sb)
                            except Exception:
                                pass
                    except Exception as tj_err:
                        log_warning(MODULE, f"Aviso insertando en trades_journal para {sym}: {tj_err}")

                    log_info(MODULE, f"📤 [SYNC STOCKS] Acción cerrada en Supabase sincronizada con orden real ({real_exit_time}): {sym} (PnL: ${pnl_usd:.2f})")

            # ── 3. RECONCILIAR OPT_PAPER_TRADES (SINCRONIZACIÓN BIDIRECCIONAL CON BROKER TWS) ──
            try:
                opt_open_res = sb.table("opt_paper_trades").select("*").eq("status", "open").execute()
                open_opt_rows = opt_open_res.data or []

                def _fmt_exp(raw_e: str) -> str:
                    s = str(raw_e or "").strip().replace("-", "")
                    if len(s) == 8 and s.isdigit():
                        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
                    return str(raw_e or "")[:10]

                def _row_contract_key(row_d: dict) -> tuple:
                    sym_u = str(row_d.get("symbol") or "").upper()
                    exp_s = _fmt_exp(row_d.get("expiry") or "")
                    fills = row_d.get("entry_fills") or []
                    stk_f = float(fills[0].get("strike") or 0.0) if fills else 0.0
                    rgt_s = str(fills[0].get("right") or ("C" if "call" in str(row_d.get("strategy_type") or "").lower() else "P")).upper() if fills else ("C" if "call" in str(row_d.get("strategy_type") or "").lower() else "P")
                    return (sym_u, exp_s, round(stk_f, 2), rgt_s)

                sb_open_by_key = {}
                for r in open_opt_rows:
                    ck = _row_contract_key(r)
                    if ck not in sb_open_by_key:
                        sb_open_by_key[ck] = r
                    else:
                        sb.table("opt_paper_trades").delete().eq("id", r["id"]).execute()

                from app.options.broker_sync import (
                    find_existing_option_trade_for_contract,
                    get_in_flight_option_sell_keys,
                    sync_option_exit_plan,
                    is_within_options_sync_import_window,
                    is_within_options_late_liquidate_window,
                    enqueue_late_option_liquidation,
                )
                in_flight_sell_keys = get_in_flight_option_sell_keys(sb, max_age_sec=120.0)
                in_opt_import_window = is_within_options_sync_import_window()
                in_opt_late_liq_window = is_within_options_late_liquidate_window()

                active_broker_keys = set()
                for opt_key, b_data in broker_options.items():
                    qty = int(round(float(b_data.get("shares") or 0)))
                    if qty <= 0:
                        continue
                    und_sym = str(b_data.get("underlying") or opt_key.split(":")[0]).upper()
                    exp_iso = _fmt_exp(b_data.get("expiry") or "")
                    strike_v = round(float(b_data.get("strike") or 0.0), 2)
                    right_v = str(b_data.get("right") or "C").upper()
                    strat_v = "long_call" if right_v == "C" else "long_put"
                    dir_v = "bullish" if right_v == "C" else "bearish"
                    avg_cost_contract = float(b_data.get("avg_cost") or 0.0)
                    entry_debit = round(avg_cost_contract / 100.0, 4) if avg_cost_contract > 0 else 0.01
                    total_invested = round(avg_cost_contract * qty, 2) if avg_cost_contract > 0 else round(entry_debit * 100.0 * qty, 2)
                    conid_v = b_data.get("conid")

                    ck = (und_sym, exp_iso, strike_v, right_v)
                    active_broker_keys.add(ck)
                    if ck in in_flight_sell_keys:
                        continue

                    mark_p = float(b_data.get("market_price") or (self.ib._prices.get(opt_key, 0.0) if hasattr(self.ib, '_prices') else 0.0) or 0.0)
                    if mark_p <= 0 and ck in sb_open_by_key:
                        old_mp = float(sb_open_by_key[ck].get("last_mark_price") or 0.0)
                        if old_mp > 0 and abs(old_mp - entry_debit) > 0.0001:
                            mark_p = old_mp
                    if mark_p <= 0:
                        mark_p = entry_debit

                    tws_opt_pnl = b_data.get("unrealized_pnl")
                    calc_opt_pnl = round((mark_p - entry_debit) * 100.0 * qty, 2)
                    opt_pnl_usd = round(float(tws_opt_pnl), 2) if (tws_opt_pnl is not None and abs(float(tws_opt_pnl)) > 0.0001) else calc_opt_pnl

                    if ck in sb_open_by_key:
                        ex_row = sb_open_by_key[ck]
                        old_mp = float(ex_row.get("last_mark_price") or 0.0)
                        old_opnl = float(ex_row.get("unrealized_pnl") or 0.0)
                        old_plan = dict(ex_row.get("exit_plan") or {})
                        und_price = float(
                            (broker_stocks.get(und_sym) or {}).get("market_price")
                            or (self.ib._prices.get(und_sym, 0.0) if hasattr(self.ib, "_prices") else 0.0)
                            or old_plan.get("last_underlying_price")
                            or old_plan.get("entry_underlying_price")
                            or 0.0
                        )
                        ex_plan = sync_option_exit_plan(
                            old_plan,
                            entry_debit,
                            mark_p,
                            has_active_sell=(ck in in_flight_sell_keys),
                            is_put=(right_v == "P"),
                            underlying_price=und_price,
                        )
                        if (
                            int(ex_row.get("qty") or 0) != qty
                            or abs(float(ex_row.get("entry_debit") or 0) - entry_debit) > 0.02
                            or abs(old_mp - mark_p) >= 0.001
                            or abs(old_opnl - opt_pnl_usd) >= 0.01
                            or ex_plan != old_plan
                        ):
                            sb.table("opt_paper_trades").update({
                                "qty": qty,
                                "entry_debit": entry_debit,
                                "entry_total_invested": total_invested,
                                "max_loss_total": total_invested,
                                "last_mark_price": round(mark_p, 4),
                                "last_mark_at": now_iso,
                                "unrealized_pnl": opt_pnl_usd,
                                "exit_plan": ex_plan,
                                "updated_at": now_iso
                            }).eq("id", ex_row["id"]).execute()
                            log_info(MODULE, f"🔄 [SYNC OPTIONS] {und_sym} {exp_iso} {strike_v}{right_v}: {qty}x | Entry=${entry_debit:.2f} | Mark=${mark_p:.2f} | PnL=${opt_pnl_usd:+.2f}")
                    else:
                        uid = 1
                        try:
                            u_res = sb.table("opt_underlyings").select("id").eq("symbol", und_sym).limit(1).execute()
                            if u_res.data:
                                uid = u_res.data[0]["id"]
                            else:
                                ins_u = sb.table("opt_underlyings").insert({"symbol": und_sym, "optionable": True, "data_state": "LIVE"}).execute()
                                if ins_u.data:
                                    uid = ins_u.data[0]["id"]
                        except Exception:
                            pass

                        leg_fill = [{
                            "conid": conid_v,
                            "side": "buy",
                            "closing_side": "sell",
                            "right": right_v,
                            "strike": strike_v,
                            "bid": entry_debit,
                            "ask": entry_debit,
                            "fill_price": entry_debit,
                            "slippage_applied": 0.0,
                            "market_data_type": "LIVE",
                            "fee_usd": 0.70,
                        }]

                        target_heal, is_zombie_closed = find_existing_option_trade_for_contract(sb, ck, strat_v, limit=200)

                        if is_zombie_closed:
                            if in_opt_late_liq_window:
                                dispatched = enqueue_late_option_liquidation(sb, und_sym, exp_iso, strike_v, right_v, qty, mark_p)
                                log_warning(MODULE, f"🚨 [LATE SYNC AUTO-LIQUIDATE] {und_sym} {exp_iso} {strike_v}{right_v} en TWS (15:30-15:59 ET) pese a cooldown anti-zombi; SELL MKT despachada={dispatched}.")
                                continue
                            warn_cache = getattr(self, "_zombie_warn_ts", None)
                            if warn_cache is None:
                                warn_cache = {}
                                self._zombie_warn_ts = warn_cache
                            now_ts_w = time.time()
                            if now_ts_w - warn_cache.get(ck, 0.0) >= 300.0:
                                warn_cache[ck] = now_ts_w
                                log_warning(MODULE, f"⏸️ [SYNC OPTIONS] Cooldown anti-zombi reciente para {qty}x de {und_sym} {exp_iso} {strike_v}{right_v}.")
                            continue
                        elif in_opt_late_liq_window:
                            dispatched = enqueue_late_option_liquidation(sb, und_sym, exp_iso, strike_v, right_v, qty, mark_p)
                            log_warning(MODULE, f"🚨 [LATE SYNC AUTO-LIQUIDATE] {und_sym} {exp_iso} {strike_v}{right_v} detectada en TWS (15:30-15:59 ET); SELL MKT despachada={dispatched}.")
                            continue
                        elif target_heal:
                            heal_old_plan = dict(target_heal.get("exit_plan") or {})
                            und_price = float(
                                (broker_stocks.get(und_sym) or {}).get("market_price")
                                or (self.ib._prices.get(und_sym, 0.0) if hasattr(self.ib, "_prices") else 0.0)
                                or heal_old_plan.get("last_underlying_price")
                                or heal_old_plan.get("entry_underlying_price")
                                or 0.0
                            )
                            healed_plan = sync_option_exit_plan(
                                heal_old_plan,
                                entry_debit,
                                mark_p,
                                has_active_sell=False,
                                is_put=(right_v == "P"),
                                underlying_price=und_price,
                            )
                            if not in_opt_import_window:
                                healed_plan["late_import_force_close"] = True
                                healed_plan["imported_outside_window"] = True
                                log_warning(MODULE, f"⚠️ [SYNC OPTIONS OUTSIDE WINDOW] {und_sym} {exp_iso} {strike_v}{right_v} re-sincronizada fuera de 09:30-15:30 ET; marcada con late_import_force_close=True.")
                            heal_opt = {
                                "status": "open",
                                "qty": qty,
                                "expiry": exp_iso,
                                "entry_debit": entry_debit,
                                "entry_fills": leg_fill,
                                "entry_total_invested": total_invested,
                                "max_loss_total": total_invested,
                                "last_mark_price": round(mark_p, 4),
                                "last_mark_at": now_iso,
                                "unrealized_pnl": opt_pnl_usd,
                                "exit_plan": healed_plan,
                                "updated_at": now_iso
                            }
                            if target_heal.get("status") == "closed":
                                heal_opt.update({
                                    "exit_time": None,
                                    "exit_reason": None,
                                    "exit_credit": None,
                                    "exit_total_recovered": None,
                                    "realized_pnl": 0.0,
                                })
                            sb.table("opt_paper_trades").update(heal_opt).eq("id", target_heal["id"]).execute()
                            log_info(MODULE, f"🔄 [SYNC OPTIONS] Opción {und_sym} {exp_iso} {strike_v}{right_v} sincronizada/reabierta desde TWS ({qty}x @ ${entry_debit:.2f})")
                        else:
                            und_price = float(
                                (broker_stocks.get(und_sym) or {}).get("market_price")
                                or (self.ib._prices.get(und_sym, 0.0) if hasattr(self.ib, "_prices") else 0.0)
                                or 0.0
                            )
                            init_plan = sync_option_exit_plan(
                                None,
                                entry_debit,
                                mark_p,
                                has_active_sell=False,
                                is_put=(right_v == "P"),
                                underlying_price=und_price,
                            )
                            if not in_opt_import_window:
                                init_plan["late_import_force_close"] = True
                                init_plan["imported_outside_window"] = True
                                log_warning(MODULE, f"⚠️ [SYNC OPTIONS OUTSIDE WINDOW] {und_sym} {exp_iso} {strike_v}{right_v} importada fuera de 09:30-15:30 ET; marcada con late_import_force_close=True.")
                            sb.table("opt_paper_trades").insert({
                                "underlying_id": uid,
                                "symbol": und_sym,
                                "strategy_type": strat_v,
                                "direction": dir_v,
                                "status": "open",
                                "qty": qty,
                                "expiry": exp_iso,
                                "entry_time": now_iso,
                                "entry_debit": entry_debit,
                                "entry_fills": leg_fill,
                                "entry_costs": round(0.70 * qty, 2),
                                "entry_total_invested": total_invested,
                                "max_loss_total": total_invested,
                                "max_profit_total": round(total_invested * 2.0, 2),
                                "breakeven": round(strike_v + entry_debit, 2) if right_v == "C" else round(strike_v - entry_debit, 2),
                                "unrealized_pnl": opt_pnl_usd,
                                "last_mark_price": round(mark_p, 4),
                                "last_mark_at": now_iso,
                                "exit_plan": init_plan,
                                "model_version": "v1.0-tws-sync",
                                "settings_version": 1,
                                "updated_at": now_iso
                            }).execute()
                            log_info(MODULE, f"📥 [SYNC OPTIONS] Opción del Broker agregada: {und_sym} {exp_iso} {strike_v}{right_v} ({qty}x @ ${entry_debit:.2f} | Mark=${mark_p:.2f} | PnL=${opt_pnl_usd:+.2f})")

                # Cerrar o limpiar en opt_paper_trades cualquier posición que NO esté en el broker
                for ck, opt_t in sb_open_by_key.items():
                    if ck not in active_broker_keys:
                        sym = opt_t["symbol"]
                        try:
                            et_str = opt_t.get("entry_time") or opt_t.get("updated_at")
                            if et_str:
                                et_dt = parse_iso_utc(et_str)
                                # Periodo de gracia inviolable de 90s para que TWS refleje la posicion
                                if et_dt and (datetime.now(timezone.utc) - et_dt).total_seconds() < 90.0:
                                    continue
                            inflight_opt = sb.table("stocks_orders").select("id").eq("ticker", sym).eq("direction", "buy").in_("status", ["pending", "processing", "submitted"]).limit(1).execute()
                            if inflight_opt.data:
                                continue
                        except Exception:
                            pass

                        if ck in in_flight_sell_keys:
                            continue

                        exp_c = ck[1].replace("-", "")
                        tb_match = f"OPT:{exp_c}:{ck[2]}:{ck[3]}"
                        filled_buy = sb.table("stocks_orders").select("id").eq("ticker", sym).eq("direction", "buy").eq("status", "filled").limit(1).execute()
                        if not filled_buy.data and opt_t.get("model_version") != "v1.0-tws-sync":
                            sb.table("opt_paper_trades").delete().eq("id", opt_t["id"]).execute()
                            log_info(MODULE, f"🧹 [CLEAN OPTIONS] Opción no ejecutada en TWS eliminada de opt_paper_trades: {sym} {tb_match}")
                        else:
                            last_m = float(opt_t.get("last_mark_price") or opt_t.get("entry_debit") or 0.0)
                            exit_t_iso = now_iso
                            try:
                                entry_t_raw = opt_t.get("entry_time")
                                q_sell = (
                                    sb.table("stocks_orders")
                                    .select("filled_price, filled_at")
                                    .eq("ticker", sym[:10])
                                    .eq("target_band", tb_match)
                                    .eq("direction", "sell")
                                    .eq("status", "filled")
                                )
                                if entry_t_raw and hasattr(q_sell, "gte"):
                                    q_sell = q_sell.gte("filled_at", str(entry_t_raw))
                                sell_ord = q_sell.order("filled_at", desc=True).limit(1).execute()
                                s_rows = sell_ord.data if hasattr(sell_ord, "data") and isinstance(sell_ord.data, list) else []
                                if s_rows and isinstance(s_rows[0], dict):
                                    cand_sell = s_rows[0]
                                    f_dt = parse_iso_utc(cand_sell.get("filled_at"))
                                    e_dt_chk = parse_iso_utc(entry_t_raw)
                                    fill_valid = True
                                    if e_dt_chk is not None and cand_sell.get("filled_at") is not None:
                                        fill_valid = (f_dt is not None and f_dt >= e_dt_chk)
                                    if fill_valid:
                                        if cand_sell.get("filled_price"):
                                            last_m = float(cand_sell["filled_price"])
                                        if cand_sell.get("filled_at"):
                                            exit_t_iso = cand_sell["filled_at"]
                            except Exception:
                                pass
                            e_deb = float(opt_t.get("entry_debit") or last_m)
                            t_qty = int(opt_t.get("qty") or 1)
                            t_rec = round(last_m * 100.0 * t_qty, 2)
                            r_pnl = round((last_m - e_deb) * 100.0 * t_qty, 2)
                            plan = dict(opt_t.get("exit_plan") or {})
                            plan["closing_pending"] = False
                            pending_reason = plan.get("pending_exit_reason") or "manual_simulated"
                            if pending_reason == "take_profit" and r_pnl < 0:
                                pending_reason = "stop_loss"
                            elif pending_reason == "stop_loss" and r_pnl > 0:
                                pending_reason = "take_profit"
                            sb.table("opt_paper_trades").update({
                                "status": "closed",
                                "exit_reason": pending_reason,
                                "exit_credit": last_m,
                                "exit_total_recovered": t_rec,
                                "realized_pnl": r_pnl,
                                "unrealized_pnl": 0.0,
                                "exit_time": exit_t_iso,
                                "exit_plan": plan,
                                "updated_at": now_iso
                            }).eq("id", opt_t["id"]).execute()
                            log_info(MODULE, f"📤 [SYNC OPTIONS] Opción {sym} cerrada por confirmación TWS (Crédito: ${last_m:.2f}, PnL: ${r_pnl:.2f}).")
                            try:
                                from app.core.circuit_breaker import record_trade_completion
                                record_trade_completion(sym, r_pnl, sb=sb)
                            except Exception:
                                pass
            except Exception as opt_sync_e:
                log_warning(MODULE, f"Error reconciliando opt_paper_trades: {opt_sync_e}")

        except Exception as sync_e:
            log_error(MODULE, f"Error en reconciliación con el broker: {sync_e}")

    def manage_working_orders(self, sweep_orphans: bool = False):
        """
        Gestiona el ciclo de vida de órdenes abiertas en TWS:
        - Fase A (Chaser + TTL): re-cotiza órdenes BUY LMT que no llenaron dentro del techo de slippage
          y cancela en TWS al vencer su TTL (45-60s).
        - Fase B (Orphan Sweep): consulta `reqAllOpenOrders` y cancela órdenes API huérfanas
          (client_id > 0) que permanecen sin fill >= 60s en TWS.
        """
        if not self.ib or not self.ib.connected:
            return

        now_ts = time.time()
        sb = get_supabase()

        # ── FASE A: Órdenes rastreadas en WORKING_IB_ORDERS ──
        if WORKING_IB_ORDERS:
            from app.options.order_execution_plan import compute_reprice_limit

            for ib_oid, info in list(WORKING_IB_ORDERS.items()):
                order_ctx = info["order_ctx"]
                order_id = order_ctx.get("id")
                ticker = order_ctx.get("ticker", "UNKNOWN")
                elapsed = now_ts - float(info.get("placed_at") or now_ts)
                ttl_sec = float(info.get("ttl_sec") or 60.0)

                if info.get("direction") == "sell":
                    # Watchdog para salidas SELL que llevan >= ttl_sec sin fill: cancelar esperando confirmación si sigue en TWS
                    if elapsed >= ttl_sec:
                        tws_live = {}
                        has_open_req = hasattr(self.ib, "request_open_orders")
                        try:
                            if has_open_req:
                                tws_live = self.ib.request_open_orders(timeout=1.5) or {}
                        except Exception:
                            tws_live = {}
                        try:
                            self.ib.cancelOrder(int(ib_oid))
                        except Exception:
                            pass
                        WORKING_IB_ORDERS.pop(ib_oid, None)
                        still_open_tws = has_open_req and (int(ib_oid) in tws_live or ib_oid in tws_live)
                        if still_open_tws:
                            p_entry = PENDING_IB_ORDERS.get(ib_oid)
                            if p_entry is None:
                                try:
                                    p_entry = PENDING_IB_ORDERS.get(int(ib_oid))
                                except Exception:
                                    p_entry = None
                            if isinstance(p_entry, dict):
                                p_entry["_cancel_requested_at"] = now_ts
                                p_entry["_cancel_reason_hint"] = "SELL_WATCHDOG_TIMEOUT"
                            log_warning(MODULE, f"⏰ [SELL WATCHDOG] Cancelación solicitada para SELL #{ib_oid} ({ticker}) tras {elapsed:.0f}s (aún abierto en TWS; PENDING retenido).")
                        else:
                            if order_id:
                                _update_order_status(sb, order_id, "cancelled", cancel_reason="SELL_WATCHDOG_TIMEOUT", allowed_statuses=["pending", "processing", "submitted"])
                            if not info.get("is_option") and hasattr(self, "_in_flight_sells"):
                                sell_sh = int(float(order_ctx.get("shares") or 0))
                                cur_inf = self._in_flight_sells.get(str(ticker).upper(), 0)
                                self._in_flight_sells[str(ticker).upper()] = max(0, cur_inf - sell_sh)
                            elif info.get("is_option"):
                                try:
                                    from app.options.broker_sync import parse_option_order_contract_key, _row_contract_key
                                    order_ck = parse_option_order_contract_key(str(ticker).upper(), str(order_ctx.get("target_band") or "").upper())
                                    if order_ck:
                                        open_rows = sb.table("opt_paper_trades").select("*").eq("symbol", order_ck[0]).eq("status", "open").execute().data or []
                                        for r in open_rows:
                                            r_ck = _row_contract_key(r)
                                            if r_ck[1] == order_ck[1] and abs(r_ck[2] - order_ck[2]) <= 0.05 and r_ck[3] == order_ck[3]:
                                                plan = dict(r.get("exit_plan") or {})
                                                if plan.get("closing_pending"):
                                                    plan["closing_pending"] = False
                                                    sb.table("opt_paper_trades").update({"exit_plan": plan, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", r["id"]).execute()
                                except Exception:
                                    pass
                            PENDING_IB_ORDERS.pop(ib_oid, None)
                            log_warning(MODULE, f"⏰ [SELL WATCHDOG] Orden SELL #{ib_oid} ({ticker}) ausente en TWS tras {elapsed:.0f}s; cerrada para reintento.")
                    continue

                if info.get("direction") != "buy":
                    continue

                is_stk_mkt = (not info.get("is_option", True)) and str(info.get("order_type") or "").upper() == "MKT"
                if is_stk_mkt:
                    if elapsed >= ttl_sec:
                        try:
                            self.ib.cancelOrder(int(ib_oid))
                        except Exception as c_e:
                            log_warning(MODULE, f"Aviso cancelando orden STK MKT #{ib_oid}: {c_e}")
                        WORKING_IB_ORDERS.pop(ib_oid, None)
                        p_entry = PENDING_IB_ORDERS.get(ib_oid)
                        if p_entry is None:
                            try:
                                p_entry = PENDING_IB_ORDERS.get(int(ib_oid))
                            except Exception:
                                p_entry = None
                        if isinstance(p_entry, dict):
                            p_entry["_cancel_requested_at"] = now_ts
                            p_entry["_cancel_reason_hint"] = "STK_MKT_WATCHDOG"
                        log_warning(MODULE, f"⏰ [STK MKT WATCHDOG] Cancelación solicitada en TWS para BUY MKT #{ib_oid} ({ticker}) tras {elapsed:.0f}s sin fill.")
                    continue

                if elapsed >= ttl_sec:
                    try:
                        self.ib.cancelOrder(int(ib_oid))
                    except Exception as c_e:
                        log_warning(MODULE, f"Aviso cancelando orden #{ib_oid} por TTL: {c_e}")
                    WORKING_IB_ORDERS.pop(ib_oid, None)
                    p_entry = PENDING_IB_ORDERS.get(ib_oid)
                    if p_entry is None:
                        try:
                            p_entry = PENDING_IB_ORDERS.get(int(ib_oid))
                        except Exception:
                            p_entry = None
                    if isinstance(p_entry, dict):
                        p_entry["_cancel_requested_at"] = now_ts
                        p_entry["_cancel_reason_hint"] = "TTL_EXPIRED"
                    log_info(MODULE, f"⌛ [TTL EXPIRED] Cancelación solicitada en TWS para BUY #{ib_oid} ({ticker}) tras {elapsed:.0f}s sin fill (PENDING retenido hasta callback TWS).")
                    continue

                reprice_after = float(info.get("reprice_after_sec") or 20.0)
                if (now_ts - float(info.get("last_reprice_at") or now_ts)) >= reprice_after and int(info.get("reprice_count") or 0) < 2:
                    q = {}
                    if info.get("is_option") and hasattr(self.ib, "get_contract_quote"):
                        q = self.ib.get_contract_quote(info["contract"], info["quote_key"], timeout=1.2)
                    cur_lmt = float(getattr(info["ib_ord"], "lmtPrice", 0.0) or 0.0)
                    res = compute_reprice_limit(
                        current_lmt=cur_lmt,
                        max_chase_price=float(info.get("max_chase_price") or cur_lmt * 1.05),
                        live_bid=float(q.get("bid") or 0.0),
                        live_ask=float(q.get("ask") or 0.0),
                        reprice_count=int(info.get("reprice_count") or 0),
                    )
                    if res["action"] == "cancel_chase_exceeded":
                        try:
                            self.ib.cancelOrder(int(ib_oid))
                        except Exception:
                            pass
                        WORKING_IB_ORDERS.pop(ib_oid, None)
                        p_entry = PENDING_IB_ORDERS.get(ib_oid)
                        if p_entry is None:
                            try:
                                p_entry = PENDING_IB_ORDERS.get(int(ib_oid))
                            except Exception:
                                p_entry = None
                        if isinstance(p_entry, dict):
                            p_entry["_cancel_requested_at"] = now_ts
                            p_entry["_cancel_reason_hint"] = "CHASE_CAP"
                        log_info(MODULE, f"🛑 [CHASE CAP] Cancelación solicitada en TWS para BUY #{ib_oid} ({ticker}): {res['reason']} (PENDING retenido hasta callback TWS).")
                    elif res["action"] == "replace":
                        new_lmt = float(res["new_lmt"])
                        info["ib_ord"].lmtPrice = new_lmt
                        try:
                            self.ib.placeOrder(int(ib_oid), info["contract"], info["ib_ord"])
                            info["reprice_count"] = int(info.get("reprice_count") or 0) + 1
                            info["last_reprice_at"] = now_ts
                            if order_id:
                                sb.table("stocks_orders").update({"limit_price": new_lmt}).eq("id", order_id).execute()
                            log_info(MODULE, f"🔄 [LADDER REPRICE #{info['reprice_count']}] Orden #{ib_oid} ({ticker}): {res['reason']}")
                        except Exception as rp_e:
                            log_warning(MODULE, f"Error re-cotizando orden #{ib_oid} ({ticker}): {rp_e}")

        # ── FASE B: Barrido de órdenes API huérfanas en TWS ──
        if sweep_orphans and hasattr(self.ib, "request_open_orders"):
            try:
                tws_open = self.ib.request_open_orders(timeout=3.0) or {}
                if not hasattr(self, "_orphan_first_seen"):
                    self._orphan_first_seen = {}

                # Limpiar PENDING_IB_ORDERS con cancelación pendiente >= 120s si ya no figuran abiertas en TWS
                for p_oid, p_data in list(PENDING_IB_ORDERS.items()):
                    if not isinstance(p_data, dict):
                        continue
                    creq = p_data.get("_cancel_requested_at")
                    if creq is not None and (now_ts - float(creq)) >= 120.0:
                        try:
                            p_oid_int = int(p_oid)
                        except Exception:
                            p_oid_int = p_oid
                        t_entry = tws_open.get(p_oid_int) or tws_open.get(p_oid)
                        t_stat = str((t_entry or {}).get("status") or "").lower()
                        still_open = bool(t_entry) and t_stat not in ("cancelled", "filled", "inactive")
                        if not still_open:
                            PENDING_IB_ORDERS.pop(p_oid, None)
                            db_oid = p_data.get("order_id") or p_data.get("db_id") or p_data.get("id")
                            if db_oid:
                                _update_order_status(
                                    sb,
                                    db_oid,
                                    "cancelled",
                                    cancel_reason=p_data.get("_cancel_reason_hint") or "STALE_CANCEL_CLEANUP",
                                    allowed_statuses=["pending", "processing", "submitted"],
                                )

                # Limpiar IDs que ya no están abiertos en TWS
                for old_oid in list(self._orphan_first_seen.keys()):
                    if old_oid not in tws_open:
                        self._orphan_first_seen.pop(old_oid, None)

                for oid, o_info in tws_open.items():
                    o_status = str(o_info.get("status") or "").lower()
                    if o_status in ("cancelled", "filled", "inactive", "pendingcancel"):
                        continue
                    if oid in WORKING_IB_ORDERS:
                        continue
                    # Preservar órdenes manuales creadas desde TWS GUI (client_id == 0)
                    if int(o_info.get("client_id") or 0) <= 0:
                        continue

                    first_seen = self._orphan_first_seen.setdefault(oid, now_ts)
                    if (now_ts - first_seen) >= 60.0:
                        try:
                            self.ib.cancelOrder(int(oid))
                            self._orphan_first_seen.pop(oid, None)
                            log_info(
                                MODULE,
                                f"🧹 [ORPHAN SWEEP] Cancelada orden huérfana #{oid} "
                                f"({o_info.get('action')} {o_info.get('symbol')} {o_info.get('sec_type')}) tras >=60s sin fill."
                            )
                        except Exception as oc_e:
                            log_warning(MODULE, f"Aviso cancelando huérfana #{oid}: {oc_e}")
            except Exception as sw_e:
                log_warning(MODULE, f"Error en barrido de órdenes abiertas TWS: {sw_e}")

        if sweep_orphans:
            try:
                self.cleanup_stuck_processing_orders(max_age_sec=180.0)
            except Exception as st_e:
                log_warning(MODULE, f"Aviso en cleanup_stuck_processing_orders: {st_e}")

    def cleanup_stuck_processing_orders(self, max_age_sec: float = 180.0, now_dt=None) -> list:
        """
        Watchdog V3: libera órdenes de `stocks_orders` atascadas en `status='processing'`
        por más de `max_age_sec` (default 180s) sin orden activa en memoria TWS.
        """
        cleaned_ids = []
        try:
            sb = get_supabase()
            if not sb:
                return cleaned_ids
            res = (
                sb.table("stocks_orders")
                .select("id, ticker, direction, status, created_at, updated_at")
                .eq("status", "processing")
                .limit(50)
                .execute()
            )
            rows = res.data if hasattr(res, "data") and isinstance(res.data, list) else []
            if not rows:
                return cleaned_ids

            active_db_ids = set()
            for container in (PENDING_IB_ORDERS, WORKING_IB_ORDERS):
                for _k, _v in list(container.items()):
                    if isinstance(_v, dict):
                        oid_val = _v.get("order_id") or _v.get("db_id") or _v.get("id")
                        if oid_val is not None:
                            active_db_ids.add(oid_val)

            ref_now = now_dt or datetime.now(timezone.utc)
            if ref_now.tzinfo is None:
                ref_now = ref_now.replace(tzinfo=timezone.utc)

            for r in rows:
                if not isinstance(r, dict):
                    continue
                db_id = r.get("id")
                if db_id is None or db_id in active_db_ids:
                    continue
                ts_dt = parse_iso_utc(r.get("updated_at") or r.get("created_at"))
                if ts_dt is None:
                    continue
                age_sec = (ref_now - ts_dt).total_seconds()
                if age_sec >= float(max_age_sec):
                    try:
                        _update_order_status(
                            sb,
                            db_id,
                            "cancelled",
                            cancel_reason="STUCK_PROCESSING_WATCHDOG",
                            allowed_statuses=["processing"],
                        )
                        cleaned_ids.append(db_id)
                        log_warning(
                            MODULE,
                            f"🧹 [STUCK ORDER WATCHDOG] Orden ID {db_id} ({r.get('ticker')} {r.get('direction')}) "
                            f"atascada en 'processing' {age_sec:.0f}s -> marcada 'cancelled'."
                        )
                    except Exception as u_e:
                        log_warning(MODULE, f"Error liberando orden processing ID {db_id}: {u_e}")
        except Exception as e:
            log_warning(MODULE, f"Error en cleanup_stuck_processing_orders: {e}")
        return cleaned_ids

    @staticmethod
    def _get_watched_bridge_files() -> list[str]:
        """Rutas críticas del puente en APOLO cuyo cambio en disco exige auto-reinicio."""
        files = [os.path.abspath(__file__)]
        try:
            import app.data.ib_provider as ib_mod
            if getattr(ib_mod, "__file__", None):
                files.append(os.path.abspath(ib_mod.__file__))
        except Exception:
            pass
        try:
            import app.options.order_execution_plan as oep_mod
            if getattr(oep_mod, "__file__", None):
                files.append(os.path.abspath(oep_mod.__file__))
        except Exception:
            pass
        try:
            import app.options.broker_sync as bs_mod
            if getattr(bs_mod, "__file__", None):
                files.append(os.path.abspath(bs_mod.__file__))
        except Exception:
            pass
        return files

    @classmethod
    def _get_max_bridge_mtime(cls, files: list[str] | None = None) -> float:
        paths = files if files is not None else cls._get_watched_bridge_files()
        mtimes = []
        for p in paths:
            try:
                if p and os.path.exists(p):
                    mtimes.append(os.path.getmtime(p))
            except Exception:
                pass
        return max(mtimes) if mtimes else 0.0

    def run_loop(self):
        """Bucle principal de ejecución del puente."""
        print("=" * 65)
        print("  eTrade v5.0 — Interactive Brokers Bridge (Host: APOLO)")
        print("  Modalidad: PAPER TRADING (Puerto: 7497)")
        print("=" * 65)

        self.initialize_ib()

        last_heartbeat = 0
        last_reconcile = 0
        last_order_manage = 0
        last_orphan_sweep = 0
        last_reconnect_attempt = time.time()
        reconnect_cooldown = 15  # Intentar reconectar a TWS cada 15 segundos
        watched_files = self._get_watched_bridge_files()
        initial_mtime = self._get_max_bridge_mtime(watched_files)

        while self.running:
            try:
                # Auto-reload multi-archivo si cualquiera de los módulos críticos cambió en disco
                try:
                    if self._get_max_bridge_mtime(watched_files) > initial_mtime + 1.0:
                        log_info(MODULE, "🔄 Código del bridge/proveedor actualizado en disco. Reiniciando proceso...")
                        if self.ib:
                            self.ib.disconnect_tws()
                        sys.exit(0)
                except SystemExit:
                    raise
                except Exception:
                    pass
                # 1. Comprobar salud de conexión con TWS (con cooldown para no saturar)
                if not self.ib or not self.ib.connected:
                    now = time.time()
                    if now - last_reconnect_attempt >= reconnect_cooldown:
                        last_reconnect_attempt = now
                        log_warning(MODULE, "TWS no conectado. Reintentando conexión con TWS (puerto 7497)...")
                        self.initialize_ib()

                # 2. Heartbeat cada 15 segundos hacia Supabase
                if time.time() - last_heartbeat > 15:
                    self.update_heartbeat()
                    last_heartbeat = time.time()

                # 2.5 Reconciliación continua o solicitada tras fill/cancel asíncrono
                if self.ib and self.ib.connected and (
                    getattr(self, "_reconcile_requested", False) or (time.time() - last_reconcile > 15)
                ):
                    self._reconcile_requested = False
                    self.reconcile_broker_portfolio()
                    last_reconcile = time.time()

                # 3. Procesar órdenes pendientes y gestionar ciclo de vida Chaser/TTL/Orphans
                if self.ib and self.ib.connected:
                    self.process_pending_orders()
                    now_m = time.time()
                    if now_m - last_order_manage >= 5:
                        do_sweep = (now_m - last_orphan_sweep >= 20)
                        self.manage_working_orders(sweep_orphans=do_sweep)
                        last_order_manage = now_m
                        if do_sweep:
                            last_orphan_sweep = now_m

                time.sleep(2)

            except KeyboardInterrupt:
                print("\nDeteniendo IB Bridge Worker de manera ordenada...")
                self.running = False
                if self.ib:
                    self.ib.disconnect_tws()
                break
            except Exception as e:
                log_error(MODULE, f"Error imprevisto en loop del bridge: {e}")
                time.sleep(5)


if __name__ == "__main__":
    bridge = IBBridgeWorker()
    bridge.run_loop()
