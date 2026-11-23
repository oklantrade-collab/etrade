"""
eTrade — Close All Open Options Engine
=======================================
Función centralizada para liquidar todas las posiciones de opciones abiertas
en opt_paper_trades y despachar las órdenes de venta a stocks_orders para que
el bridge de TWS en APOLO las ejecute en el broker a precio de mercado.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase


def close_all_open_options(sb=None, reason: str = "forced_close_time") -> Dict[str, Any]:
    """
    Cierra inmediatamente todas las posiciones abiertas en opt_paper_trades
    y despacha órdenes de venta MARKET a stocks_orders.
    """
    if sb is None:
        sb = get_supabase()

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    try:
        open_res = sb.table("opt_paper_trades").select("*").eq("status", "open").execute()
        open_positions = open_res.data or []
    except Exception as e:
        log_error("CLOSE_ALL", f"Error consultando posiciones abiertas: {e}")
        return {"success": False, "error": str(e)}

    if not open_positions:
        log_info("CLOSE_ALL", "ℹ️ No hay posiciones de opciones abiertas para cerrar.")
        return {"success": True, "closed_count": 0, "positions": []}

    log_info("CLOSE_ALL", f"🚨 Iniciando liquidación de {len(open_positions)} posiciones de opciones abiertas...")

    from app.options.broker_sync import request_broker_option_close

    closed_positions: List[Dict[str, Any]] = []
    pending_broker_count = 0

    for pos in open_positions:
        pid = pos["id"]
        sym = str(pos.get("symbol", "")).upper().strip()
        qty = int(pos.get("qty") or 1)
        exp = str(pos.get("expiry", "")).replace("-", "")[:8]
        entry_fills = pos.get("entry_fills") or []
        strike = entry_fills[0].get("strike") if entry_fills else None
        right = entry_fills[0].get("right") if entry_fills else ("C" if "call" in str(pos.get("strategy_type", "")).lower() else "P")

        last_mark = float(pos.get("last_mark_price") or pos.get("entry_debit") or 0.05)
        entry_deb = float(pos.get("entry_debit") or last_mark)
        realized_pnl = round((last_mark - entry_deb) * 100.0 * qty, 2)
        total_rec = round(last_mark * 100.0 * qty, 2)

        close_req = request_broker_option_close(
            sb=sb,
            pos=pos,
            qty_to_close=qty,
            exit_price_est=last_mark,
            mapped_reason="forced_close_time",
            detailed_reason=reason,
            detailed_text="MARKET_OPEN_LIQUIDATION",
            is_partial=False,
            group_name="OPTIONS",
            now_dt=now_dt,
        )
        if close_req.get("status") == "closing_pending":
            pending_broker_count += 1
            log_info("CLOSE_ALL", f"⏳ Posición {pid} ({sym} {exp} {strike}{right}) esperando confirmación SELL en TWS.")
            continue

        # 2. Actualizar estado a 'closed' en opt_paper_trades solo si TWS confirmó flat / sin bridge
        try:
            exit_plan = dict(pos.get("exit_plan") or {})
            exit_plan["closed_at"] = now_iso
            exit_plan["close_reason"] = "MARKET_OPEN_LIQUIDATION"

            sb.table("opt_paper_trades").update({
                "status": "closed",
                "exit_time": now_iso,
                "exit_credit": last_mark,
                "exit_total_recovered": total_rec,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": 0.0,
                "last_mark_price": last_mark,
                "last_mark_at": now_iso,
                "exit_reason": "forced_close_time",
                "exit_plan": exit_plan,
                "updated_at": now_iso
            }).eq("id", pid).execute()

            closed_positions.append({
                "id": pid,
                "symbol": sym,
                "qty": qty,
                "strike": strike,
                "right": right,
                "expiry": exp,
                "exit_credit": last_mark,
                "realized_pnl": realized_pnl
            })
            log_info("CLOSE_ALL", f"✅ Posición {pid} ({sym} {exp} {strike}{right}) cerrada con éxito. PnL: ${realized_pnl:+.2f}")
        except Exception as e_upd:
            log_error("CLOSE_ALL", f"Error actualizando posición {pid} a cerrada: {e_upd}")

    # 3. Notificación Telegram
    try:
        from app.workers.alerts_service import send_telegram_message
        import asyncio
        pnl_total = sum(p["realized_pnl"] for p in closed_positions)
        emo = "🟢" if pnl_total >= 0 else "🔴"
        tg_text = (
            f"🚨 <b>[eTrade] LIQUIDACIÓN DE TODAS LAS OPCIONES A LA APERTURA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Posiciones Cerradas (confirmadas):</b> {len(closed_positions)}\n"
            f"⏳ <b>Pendientes de Confirmación TWS:</b> {pending_broker_count}\n"
            f"{emo} <b>PnL Realizado Estimado:</b> ${pnl_total:+.2f} USD\n"
            f"📋 <b>Motivo:</b> Orden de Cierre de Mercado Programada\n"
            f"🕒 <b>Fecha/Hora UTC:</b> {now_iso}\n\n"
            f"<i>Órdenes SELL MARKET enviadas al bridge de TWS en APOLO.</i>"
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(tg_text))
        except RuntimeError:
            asyncio.run(send_telegram_message(tg_text))
    except Exception as e_tg:
        log_warning("CLOSE_ALL", f"Aviso enviando alerta Telegram: {e_tg}")

    return {
        "success": True,
        "closed_count": len(closed_positions),
        "pending_broker_count": pending_broker_count,
        "positions": closed_positions
    }
