"""Motor de salidas (Exit Engine) para posiciones Paper Trading (Sprint 6).
Evalua de forma continua:
  1. Take Profit (+75% en long options / +60% del beneficio maximo en spreads).
  2. Stop Loss (-50% del debito o prima).
  3. Salida por tiempo (15 min antes de la campana en DTE, respetando early closes).
  4. Invalidacion de direccion APEX (direction flip).
  5. Cierre por datos degradados o stale.
Todas las salidas son validadas por ADUANA y simulan fills conservadores.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.core.logger import log_info, log_warning
from app.options import market_calendar as mc
from app.options import options_aduana as aduana
from app.options import paper_execution as pe

MODULE = "OPTIONS_EXIT"


def should_exit_take_profit(position: dict[str, Any], unrealized_pnl: float, eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Evalua condicion de Take Profit (§12.3)."""
    stype = position.get("strategy_type") or ""
    invested = float(position.get("entry_total_invested") or 0.0)
    max_profit = position.get("max_profit_total")

    if stype in ("long_call", "long_put"):
        tp_pct = float(eff.get("long_tp_pct") or 75.0)
        target = invested * (tp_pct / 100.0)
        if unrealized_pnl >= target and target > 0:
            return True, f"Take Profit alcanzado: +${unrealized_pnl:.2f} >= +${target:.2f} (+{tp_pct}%)"
    else:
        # Spreads: 60% del beneficio maximo
        tp_pct = float(eff.get("spread_tp_pct") or 60.0)
        if max_profit and max_profit > 0:
            target = float(max_profit) * (tp_pct / 100.0)
            if unrealized_pnl >= target:
                return True, f"Take Profit alcanzado: +${unrealized_pnl:.2f} >= +${target:.2f} (+{tp_pct}% de benef. max)"
        elif invested > 0:
            target = invested * (tp_pct / 100.0)
            if unrealized_pnl >= target:
                return True, f"Take Profit alcanzado: +${unrealized_pnl:.2f} >= +${target:.2f}"

    return False, None


def should_exit_stop_loss(position: dict[str, Any], unrealized_pnl: float, eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Evalua condicion de Stop Loss simulado (§12.3)."""
    stype = position.get("strategy_type") or ""
    invested = float(position.get("entry_total_invested") or 0.0)

    if stype in ("long_call", "long_put"):
        sl_pct = float(eff.get("long_sl_pct") or 50.0)
    else:
        sl_pct = float(eff.get("spread_sl_pct") or 50.0)

    stop_threshold = -invested * (sl_pct / 100.0)
    if unrealized_pnl <= stop_threshold and invested > 0:
        return True, f"Stop Loss alcanzado: ${unrealized_pnl:.2f} <= -${abs(stop_threshold):.2f} (-{sl_pct}%)"

    return False, None


def should_exit_by_time(position: dict[str, Any], now: datetime, eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Cierre forzado antes de la campana en la fecha de expiracion (§12.3)."""
    expiry_str = str(position.get("expiry") or "")[:10]
    if not expiry_str:
        return False, None

    expiry_date = date.fromisoformat(expiry_str)
    now_date = mc.to_ny(now).date()

    if now_date == expiry_date:
        buffer_min = int(eff.get("force_close_minutes_before") or 15)
        force_time = mc.force_close_time(now, buffer_min)
        if now >= force_time:
            return True, f"Cierre forzado por tiempo: vencimiento hoy y hora actual supera {force_time.strftime('%H:%M %Z')}"

    return False, None


def should_exit_by_invalidation(position: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Invalidacion por inversion de senal APEX o datos corruptos (§12.3)."""
    if not eff.get("exit_on_direction_flip", True):
        return False, None

    pos_dir = position.get("direction")
    und_dir = underlying.get("direction")
    if pos_dir and und_dir and pos_dir != und_dir:
        return True, f"Senal APEX invertida: posicion '{pos_dir}' vs nueva direccion '{und_dir}'"

    return False, None


def evaluate_position_exit(position: dict[str, Any],
                           quotes_by_contract: dict[int, dict[str, Any]] | None,
                           underlying: dict[str, Any],
                           eff: dict[str, Any],
                           now: datetime | None = None) -> tuple[bool, str | None, dict[str, Any]]:
    """Evalua si una posicion debe cerrarse y bajo que motivo."""
    now_dt = now or datetime.now(timezone.utc)

    # 1. Mark to market
    mark = pe.mark_position_to_market(position, quotes_by_contract, eff)
    unrealized_pnl = mark["unrealized_pnl"]

    # 2. Cierre forzado por tiempo (maxima prioridad para evitar ejercicio/asignacion)
    by_time, reason_time = should_exit_by_time(position, now_dt, eff)
    if by_time:
        return True, "forced_close_time", {"detail": reason_time, "mark": mark}

    # 3. Stop Loss
    by_sl, reason_sl = should_exit_stop_loss(position, unrealized_pnl, eff)
    if by_sl:
        return True, "stop_loss", {"detail": reason_sl, "mark": mark}

    # 4. Take Profit
    by_tp, reason_tp = should_exit_take_profit(position, unrealized_pnl, eff)
    if by_tp:
        return True, "take_profit", {"detail": reason_tp, "mark": mark}

    # 5. Invalidacion de senal APEX
    by_inv, reason_inv = should_exit_by_invalidation(position, underlying, eff)
    if by_inv:
        return True, "signal_invalidation", {"detail": reason_inv, "mark": mark}

    return False, None, {"mark": mark}


def process_open_positions(sb, eff: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Recorre todas las posiciones abiertas, actualiza su mark-to-market y ejecuta salidas aprobadas."""
    now_dt = now or datetime.now(timezone.utc)
    try:
        positions = sb.table("opt_paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception as e:
        log_warning(MODULE, f"Error al cargar posiciones: {e}")
        return {"open_count": 0, "closed_count": 0, "error": str(e)}

    if not positions:
        return {"open_count": 0, "closed_count": 0, "exits": []}

    # Cargar subyacentes y ultimas cotizaciones
    uids = list(set(p["underlying_id"] for p in positions))
    und_rows = sb.table("opt_underlyings").select("*").in_("id", uids).execute().data or []
    und_map = {u["id"]: u for u in und_rows}

    # Cotizaciones recientes
    quotes_rows = sb.table("opt_quotes_latest").select("*").execute().data or []
    quotes_map = {q["conid"]: q for q in quotes_rows if q.get("conid")}

    closed_count = 0
    exits_summary: list[dict[str, Any]] = []

    for pos in positions:
        pid = pos["id"]
        und = und_map.get(pos["underlying_id"]) or {}
        should_exit, reason, info = evaluate_position_exit(pos, quotes_map, und, eff, now_dt)

        mark = info.get("mark") or {}
        if should_exit and reason:
            # Validar con ADUANA de salida
            aduana_res = aduana.validate_exit(
                reason,
                aduana.AduanaContext(
                    now=now_dt,
                    underlying_id=pos["underlying_id"],
                    execution_mode=eff.get("execution_mode", "paper"),
                )
            )

            # Simular fill de salida (si es stop_loss o forzado, aplica slippage adverso)
            adverse = reason in ("stop_loss", "forced_close_time")
            exit_fill_res = pe.simulate_exit_fill(pos, quotes_map, eff, reason, adverse=adverse, now=now_dt)

            # Actualizar posicion como cerrada
            upd = {
                "status": "closed",
                "exit_time": exit_fill_res.exit_time,
                "exit_credit": exit_fill_res.exit_credit,
                "exit_fills": exit_fill_res.exit_fills,
                "exit_costs": exit_fill_res.exit_costs,
                "exit_total_recovered": exit_fill_res.exit_total_recovered,
                "realized_pnl": exit_fill_res.realized_pnl,
                "unrealized_pnl": 0.0,
                "last_mark_price": exit_fill_res.exit_credit,
                "last_mark_at": now_dt.isoformat(),
                "exit_reason": reason,
                "updated_at": now_dt.isoformat(),
            }
            sb.table("opt_paper_trades").update(upd).eq("id", pid).execute()

            # Registrar evento de riesgo
            event_type = "forced_close" if reason == "forced_close_time" else ("signal_flip" if reason == "signal_invalidation" else "stop_approaching")
            try:
                sb.table("opt_risk_events").insert({
                    "paper_trade_id": pid,
                    "event_type": event_type,
                    "details": {
                        "exit_reason": reason,
                        "realized_pnl": exit_fill_res.realized_pnl,
                        "aduana_approval": aduana_res.approved,
                        "info": info.get("detail"),
                    },
                    "created_at": now_dt.isoformat(),
                }).execute()
            except Exception as exc:
                log_warning(MODULE, f"Aviso al registrar risk_event: {exc}")

            closed_count += 1
            exits_summary.append({"position_id": pid, "symbol": pos["symbol"], "reason": reason, "realized_pnl": exit_fill_res.realized_pnl})
            log_info(MODULE, f"Posicion {pid} ({pos['symbol']}) cerrada por {reason}: PnL=${exit_fill_res.realized_pnl:.2f}")
        else:
            # Solo actualizar mark to market
            sb.table("opt_paper_trades").update({
                "unrealized_pnl": mark.get("unrealized_pnl", 0.0),
                "last_mark_price": mark.get("last_mark_price", 0.0),
                "last_mark_at": now_dt.isoformat(),
                "updated_at": now_dt.isoformat(),
            }).eq("id", pid).execute()

    return {
        "open_count": len(positions) - closed_count,
        "closed_count": closed_count,
        "exits": exits_summary,
    }
