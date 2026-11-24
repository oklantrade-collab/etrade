"""
Sincronización autoritativa Broker-First (TWS -> Supabase) para Opciones y Acciones.
Garantiza que `opt_paper_trades` y `stocks_positions` sean una copia idéntica de
`ib_broker_portfolio` reportado por Interactive Brokers TWS (APOLO).
"""
from __future__ import annotations

import ast
import os
import time
from datetime import datetime, timezone
from typing import Any

from app.core.logger import log_info, log_warning
from app.core.time_utils import parse_iso_utc

MODULE = "BROKER_SYNC"
_LAST_SYNC_TS: float = 0.0


def _to_ny_dt(now_dt: datetime | None = None) -> datetime:
    from datetime import timedelta
    ref = parse_iso_utc(now_dt) if now_dt is not None else datetime.now(timezone.utc)
    if ref is None:
        ref = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return ref.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return ref - timedelta(hours=5)


def is_within_options_sync_import_window(now_dt: datetime | None = None) -> bool:
    """
    Verifica si el horario actual en Nueva York está dentro de la ventana permitida
    para importar nuevas posiciones de opciones desde TWS (09:30 a 15:30 ET, lunes a viernes).
    Evita re-importaciones fantasma al cierre (15:50 ET) o durante la noche (22:00 ET).
    """
    from datetime import time as dt_time
    dt_et = _to_ny_dt(now_dt)
    if dt_et.weekday() >= 5:
        return False
    t = dt_et.time()
    return dt_time(9, 30) <= t <= dt_time(15, 30)


def is_within_options_late_liquidate_window(now_dt: datetime | None = None) -> bool:
    """Retorna True en días hábiles entre 15:30:01 ET y 15:59:59 ET (cierre inmediato sin re-importar)."""
    from datetime import time as dt_time
    dt_et = _to_ny_dt(now_dt)
    if dt_et.weekday() >= 5:
        return False
    t = dt_et.time()
    return dt_time(15, 30) < t <= dt_time(15, 59, 59)


def enqueue_late_option_liquidation(
    sb,
    symbol: str,
    exp_iso: str,
    strike: float,
    right: str,
    qty: int,
    mark_price: float,
    now_dt: datetime | None = None,
) -> bool:
    """Despacha SELL MKT inmediato (dedup 45s) cuando TWS aún tiene contratos entre 15:30-15:59 ET."""
    now_ref = now_dt or datetime.now(timezone.utc)
    now_iso = now_ref.isoformat()
    sym_u = str(symbol or "").upper().strip()
    exp_c = str(exp_iso or "").replace("-", "")[:8]
    rgt_u = str(right or "C").upper().strip()
    tb = f"OPT:{exp_c}:{round(float(strike or 0.0), 2)}:{rgt_u}"
    try:
        existing = (
            sb.table("stocks_orders")
            .select("id, created_at, status")
            .eq("ticker", sym_u[:10])
            .eq("target_band", tb)
            .eq("direction", "sell")
            .in_("status", ["pending", "processing", "submitted"])
            .limit(5)
            .execute()
        )
        for ex in (getattr(existing, "data", None) or []):
            c_dt = parse_iso_utc(ex.get("created_at"))
            if c_dt is None or (now_ref - c_dt).total_seconds() <= 45.0:
                return False

        sb.table("stocks_orders").insert({
            "ticker": sym_u[:10],
            "target_band": tb,
            "group_name": "OPTIONS_EOD_LIQUIDATION",
            "rule_code": "OPT_LATE_SYNC_AUTO_LIQUIDATE",
            "order_type": "market",
            "direction": "sell",
            "shares": max(1, int(qty or 1)),
            "market_price": round(float(mark_price or 0.01), 4),
            "limit_price": round(max(0.01, float(mark_price or 0.05)), 2),
            "status": "pending",
            "created_at": now_iso,
        }).execute()
        log_warning(MODULE, f"🚨 [LATE SYNC LIQUIDATE 15:30-15:59 ET] Orden SELL MKT despachada sin retener: {sym_u} {tb} ({qty}x)")
        return True
    except Exception as e:
        log_warning(MODULE, f"Aviso encolando liquidación tardía para {sym_u} {tb}: {e}")
        return False


def _fmt_exp(raw_e: str) -> str:
    s = str(raw_e or "").strip().replace("-", "")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return str(raw_e or "")[:10]


def _row_contract_key(row_d: dict[str, Any]) -> tuple[str, str, float, str]:
    sym_u = str(row_d.get("symbol") or "").upper()
    exp_s = _fmt_exp(row_d.get("expiry") or "")
    fills = row_d.get("entry_fills") or []
    default_right = "C" if "call" in str(row_d.get("strategy_type") or "").lower() else "P"
    if fills and isinstance(fills, list) and isinstance(fills[0], dict):
        stk_f = float(fills[0].get("strike") or 0.0)
        rgt_s = str(fills[0].get("right") or default_right).upper()
    else:
        stk_f = 0.0
        rgt_s = default_right
    return (sym_u, exp_s, round(stk_f, 2), rgt_s)


def fetch_live_broker_portfolio_direct(sb) -> tuple[dict[str, Any], float]:
    """
    Consulta directamente a Interactive Brokers TWS (vía socket APOLO / local)
    cuando el snapshot en stocks_config tenga más de 25s de antigüedad o no exista.
    Garantiza que 'lo que existe en el Broker manda' sin depender de un proceso externo.
    """
    try:
        import socket
        # Pre-verificar socket con timeout estricto de 0.8s para no colgar procesos web
        target_host = os.getenv("IB_HOST", "192.168.1.105")
        target_port = int(os.getenv("IB_PORT", "7497"))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.8)
        check = s.connect_ex((target_host, target_port))
        s.close()
        if check != 0:
            return {}, 999999.0

        from app.data.ib_provider import get_ib_connection
        ib = get_ib_connection()
        if not ib:
            return {}, 999999.0
        if not ib.connected:
            # Usar client_id dinámico para consultas ad-hoc para no colisionar con 25 (Bridge) ni 31 (Worker)
            adhoc_cid = int(time.time() * 7) % 700 + 200
            ib.connect_tws(host=target_host, port=target_port, client_id=adhoc_cid)
        if ib.connected:
            positions = ib.request_broker_positions(timeout=3.5)
            now_iso = datetime.now(timezone.utc).isoformat()
            if positions is not None:
                try:
                    sb.table("stocks_config").upsert({
                        "key": "ib_broker_portfolio",
                        "value": str(positions),
                        "description": "Cartera de posiciones reales en Interactive Brokers TWS",
                        "updated_at": now_iso
                    }, on_conflict="key").execute()
                    sb.table("stocks_config").upsert({
                        "key": "ib_bridge_heartbeat",
                        "value": str({"connected": True, "host_name": getattr(ib, "host", target_host), "tws_port": target_port, "mode": "PAPER", "timestamp": now_iso}),
                        "description": "Estado en tiempo real del agente IBKR Bridge",
                        "updated_at": now_iso
                    }, on_conflict="key").execute()
                except Exception:
                    pass
                return positions, 0.0
    except Exception as e:
        log_warning(MODULE, f"Consulta directa a TWS no completada: {e}")
    return {}, 999999.0


def load_broker_portfolio_snapshot(sb, allow_direct_fetch: bool = True) -> tuple[dict[str, Any], float]:
    """
    Lee `ib_broker_portfolio` desde `stocks_config` y devuelve (portfolio_dict, age_seconds).
    Si el snapshot está ausente o tiene más de 25 segundos, intenta refrescarlo directamente con TWS.
    """
    portfolio = None
    age_sec = 999999.0
    try:
        res = sb.table("stocks_config").select("value, updated_at").eq("key", "ib_broker_portfolio").limit(1).execute()
        if res.data:
            row = res.data[0]
            raw_val = row.get("value") or "{}"
            upd_str = row.get("updated_at")
            if upd_str:
                u_dt = parse_iso_utc(upd_str)
                if u_dt is not None:
                    age_sec = max(0.0, (datetime.now(timezone.utc) - u_dt).total_seconds())
            portfolio = ast.literal_eval(raw_val) if isinstance(raw_val, str) else (raw_val or {})
    except Exception as e:
        log_warning(MODULE, f"No se pudo leer ib_broker_portfolio: {e}")

    # Si está ausente o tiene más de 25s de antigüedad, refrescar directamente de TWS
    if allow_direct_fetch and (portfolio is None or age_sec > 25.0):
        live_p, live_age = fetch_live_broker_portfolio_direct(sb)
        if live_p is not None and live_age < 10.0:
            return live_p, live_age

    if isinstance(portfolio, dict):
        return portfolio, age_sec
    return {}, 999999.0


def parse_option_order_contract_key(ticker: str, target_band: str = "") -> tuple[str, str, float, str] | None:
    """Extrae (symbol, YYYY-MM-DD, strike, right) desde ticker / target_band de stocks_orders."""
    t_u = str(ticker or "").strip().upper()
    tb_u = str(target_band or "").strip().upper()
    und_sym = t_u.split(":")[0].replace("OPT", "").strip(":")
    raw = tb_u if "OPT:" in tb_u else (t_u if "OPT:" in t_u else "")
    if not raw:
        return None
    parts = raw.split(":")
    try:
        if len(parts) == 4 and parts[0] == "OPT":
            exp_d, stk_s, rgt_s = parts[1], parts[2], parts[3]
        elif len(parts) >= 5:
            und_sym = parts[0] if parts[0] != "OPT" else parts[1]
            exp_d, stk_s, rgt_s = parts[2], parts[3], parts[-1]
        else:
            return None
        return (und_sym, _fmt_exp(exp_d), round(float(stk_s), 2), rgt_s.upper())
    except Exception:
        return None


def get_in_flight_option_sell_keys(sb, max_age_sec: float = 120.0) -> set[tuple[str, str, float, str]]:
    """Devuelve contratos OPT con orden SELL pendiente/en proceso reciente (< max_age_sec)."""
    keys: set[tuple[str, str, float, str]] = set()
    now_dt = datetime.now(timezone.utc)
    recent_sells = (
        sb.table("stocks_orders")
        .select("ticker, target_band, created_at, status")
        .eq("direction", "sell")
        .in_("status", ["pending", "processing", "submitted"])
        .execute()
        .data or []
    )
    for so in recent_sells:
        c_str = so.get("created_at")
        if not c_str:
            continue
        c_dt = parse_iso_utc(c_str)
        if c_dt is not None and (now_dt - c_dt).total_seconds() < max_age_sec:
            ck = parse_option_order_contract_key(so.get("ticker", ""), so.get("target_band", ""))
            if ck:
                keys.add(ck)
    return keys


def find_existing_option_trade_for_contract(sb, ck: tuple[str, str, float, str], strat_v: str, limit: int = 200) -> tuple[dict[str, Any] | None, bool]:
    """
    Busca trade previo del contrato.
    Solo bloquea reapertura (`is_zombie_closed=True`) como cooldown corto (<= 90s)
    cuando existe un cierre reciente respaldado por una orden SELL reciente/ejecutada en TWS.
    """
    und_sym, exp_iso, strike_v, right_v = ck
    recent_opt = (
        sb.table("opt_paper_trades")
        .select("*")
        .eq("symbol", und_sym)
        .eq("strategy_type", strat_v)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    target_row = None
    for cand_r in (recent_opt.data or []):
        if _row_contract_key(cand_r) == ck:
            if cand_r.get("status") == "open":
                return cand_r, False
            if target_row is None:
                target_row = cand_r
    if target_row and target_row.get("status") == "closed":
        exit_t_str = target_row.get("exit_time")
        tb_c = f"OPT:{exp_iso.replace('-', '')}:{strike_v}:{right_v}"
        if exit_t_str:
            try:
                newer_res = (
                    sb.table("stocks_orders")
                    .select("id")
                    .eq("ticker", und_sym)
                    .eq("target_band", tb_c)
                    .eq("direction", "buy")
                    .eq("status", "filled")
                    .gt("filled_at", exit_t_str)
                    .limit(1)
                    .execute()
                )
                if newer_res.data:
                    return None, False
            except Exception:
                pass

            # Solo bloquear reapertura como cooldown corto (<=90s) tras un SELL confirmado o en curso (<120s)
            try:
                now_dt = datetime.now(timezone.utc)
                exit_dt = parse_iso_utc(exit_t_str)
                if exit_dt is not None and 0.0 <= (now_dt - exit_dt).total_seconds() <= 90.0:
                    sell_res = (
                        sb.table("stocks_orders")
                        .select("id, created_at, filled_at, status")
                        .eq("ticker", und_sym)
                        .eq("target_band", tb_c)
                        .eq("direction", "sell")
                        .in_("status", ["filled", "pending", "processing", "submitted"])
                        .order("created_at", desc=True)
                        .limit(3)
                        .execute()
                    )
                    for so in (sell_res.data or []):
                        ts_ref = so.get("filled_at") or so.get("created_at")
                        if ts_ref:
                            s_dt = parse_iso_utc(ts_ref)
                            if s_dt is not None and (now_dt - s_dt).total_seconds() <= 120.0:
                                return target_row, True
            except Exception:
                pass
        return target_row, False
    return target_row, False


def sync_option_exit_plan(
    existing_plan: dict[str, Any] | None,
    entry_debit: float,
    mark_p: float,
    has_active_sell: bool = False,
    is_put: bool | None = None,
    underlying_price: float = 0.0,
) -> dict[str, Any]:
    """
    Inicializa y actualiza de forma estrictamente monotónica el `exit_plan` de opciones
    (watermark de prima, hard stop inicial -30%, Profit Guardian continuo y trailing subyacente PUT/CALL).
    """
    plan = dict(existing_plan or {})
    hi_prem = round(max(float(plan.get("highest_premium_seen") or 0.0), float(entry_debit or 0.0), float(mark_p or 0.0)), 4)
    if hi_prem > 0.0:
        plan["highest_premium_seen"] = hi_prem
    plan.setdefault("trailing_sl_type", "INITIAL")
    plan.setdefault("tp_half_pct", 20.0)
    plan.setdefault("take_profit_1_pct", 20.0)

    if float(plan.get("stop_loss_premium") or 0.0) <= 0.0 and entry_debit > 0.0:
        plan["stop_loss_premium"] = round(entry_debit * 0.70, 4)

    if entry_debit > 0.0 and mark_p > 0.0:
        try:
            from app.options.profit_guardian import evaluate_option_profit_ratchet
            prev_sl_p = float(plan.get("stop_loss_premium") or 0.0)
            pg_res = evaluate_option_profit_ratchet(
                entry_premium=entry_debit,
                current_premium=mark_p,
                highest_premium_seen=hi_prem,
                peak_pnl_pct=float(plan.get("highest_pnl_pct") or 0.0),
                prev_floor_premium=prev_sl_p,
            )
            if float(pg_res.get("floor_premium") or 0.0) > prev_sl_p:
                plan["stop_loss_premium"] = pg_res["floor_premium"]
                plan["profit_guardian_tier"] = pg_res.get("tier")
                if pg_res["floor_premium"] >= entry_debit:
                    plan["be_locked"] = True
        except Exception:
            pass

    und_p = float(underlying_price or 0.0)
    if und_p > 0.0 and is_put is not None:
        plan["last_underlying_price"] = round(und_p, 4)
        if float(plan.get("entry_underlying_price") or 0.0) <= 0.0:
            plan["entry_underlying_price"] = round(und_p, 4)
        entry_u = float(plan.get("entry_underlying_price") or und_p)
        try:
            from app.options.profit_guardian import compute_dynamic_underlying_trailing_sl
            dyn_u = compute_dynamic_underlying_trailing_sl(
                entry_underlying=entry_u,
                current_underlying=und_p,
                current_sl=float(plan.get("stop_loss_underlying") or 0.0),
                is_put=bool(is_put),
                lowest_underlying_seen=float(plan.get("lowest_underlying_seen") or 0.0),
                highest_underlying_seen=float(plan.get("highest_underlying_seen") or 0.0),
            )
            if is_put and float(dyn_u.get("lowest_underlying_seen") or 0.0) > 0.0:
                plan["lowest_underlying_seen"] = dyn_u["lowest_underlying_seen"]
            elif (not is_put) and float(dyn_u.get("highest_underlying_seen") or 0.0) > 0.0:
                plan["highest_underlying_seen"] = dyn_u["highest_underlying_seen"]
            if dyn_u.get("updated"):
                plan["stop_loss_underlying"] = dyn_u["stop_loss_underlying"]
                if dyn_u.get("trailing_sl_type"):
                    plan["trailing_sl_type"] = dyn_u["trailing_sl_type"]
                    if dyn_u["trailing_sl_type"] == "BE_LOCK_PLUS_1PCT":
                        plan["be_locked"] = True
            if not plan.get("initial_sl") and float(plan.get("stop_loss_underlying") or 0.0) > 0.0:
                plan["initial_sl"] = float(plan["stop_loss_underlying"])
        except Exception:
            pass

    if not has_active_sell and plan.get("closing_pending"):
        plan["closing_pending"] = False
    return plan


def is_option_held_in_broker(sb, symbol: str, expiry: str, strike: float, right: str) -> tuple[bool, int]:
    """
    Verifica si el contrato de opción existe con qty > 0 en `ib_broker_portfolio`.
    Devuelve (is_held, qty).
    """
    portfolio, age_sec = load_broker_portfolio_snapshot(sb)
    if not portfolio or age_sec > 900.0:
        # Si el snapshot no está disponible, permitir por fallback
        # P0/P1: Si el snapshot no está disponible o es viejo, no asumir tenencia (evitar órdenes fantasma)
        return False, 0

    sym_u = str(symbol or "").upper().strip()
    exp_iso = _fmt_exp(expiry)
    strike_r = round(float(strike or 0.0), 2)
    right_u = str(right or "C").upper().strip()

    for opt_key, b_data in portfolio.items():
        qty = int(round(float(b_data.get("shares") or 0)))
        if qty <= 0:
            continue
        sec_type = str(b_data.get("sec_type") or "").upper()
        if sec_type != "OPT" and ":OPT:" not in opt_key and not b_data.get("right"):
            continue
        b_sym = str(b_data.get("underlying") or opt_key.split(":")[0]).upper().strip()
        b_exp = _fmt_exp(b_data.get("expiry") or "")
        b_stk = round(float(b_data.get("strike") or 0.0), 2)
        b_rgt = str(b_data.get("right") or "C").upper().strip()
        if b_sym == sym_u and b_exp == exp_iso and abs(b_stk - strike_r) <= 0.05 and b_rgt == right_u:
            return True, qty

    return False, 0


def reconcile_with_ib_broker_portfolio(
    sb,
    min_interval_sec: float = 8.0,
    force: bool = False,
    allow_direct_fetch: bool = False,
    max_age_sec: float = 86400.0,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """
    Sincroniza `opt_paper_trades` y `stocks_positions` con `ib_broker_portfolio`
    para garantizar que lo que está en el Broker TWS sea exactamente lo que está
    abierto en el sistema.
    """
    global _LAST_SYNC_TS
    now_ts = time.time()
    if not force and (now_ts - _LAST_SYNC_TS < min_interval_sec):
        return {"skipped": True}

    portfolio, age_sec = load_broker_portfolio_snapshot(sb, allow_direct_fetch=allow_direct_fetch)
    if portfolio is None or age_sec > max_age_sec:
        return {"skipped": True, "reason": f"snapshot_stale_or_empty ({age_sec:.0f}s)"}

    snapshot_is_live = (age_sec <= 300.0)
    _LAST_SYNC_TS = now_ts
    now_dt = now_dt or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    in_opt_import_window = is_within_options_sync_import_window(now_dt)
    in_opt_late_liq_window = is_within_options_late_liquidate_window(now_dt)

    broker_stocks: dict[str, dict[str, Any]] = {}
    broker_options: dict[str, dict[str, Any]] = {}

    for sym_key, b_data in portfolio.items():
        qty = float(b_data.get("shares") or 0.0)
        if abs(qty) < 0.0001:
            continue
        sec_type = str(b_data.get("sec_type") or "").upper()
        if sec_type == "OPT" or ":OPT:" in sym_key or b_data.get("right") or b_data.get("strike"):
            if qty > 0:
                broker_options[sym_key] = b_data
        else:
            broker_stocks[str(b_data.get("symbol") or sym_key).upper()] = b_data

    # ── 1. RECONCILIAR OPT_PAPER_TRADES ──
    opt_synced = 0
    opt_closed = 0
    opt_late_liquidated = 0
    try:
        opt_open_res = sb.table("opt_paper_trades").select("*").eq("status", "open").execute()
        open_opt_rows = opt_open_res.data or []

        sb_open_by_key: dict[tuple[str, str, float, str], dict[str, Any]] = {}
        for r in open_opt_rows:
            ck = _row_contract_key(r)
            if ck not in sb_open_by_key:
                sb_open_by_key[ck] = r
            else:
                # Eliminar duplicado abierto del mismo contrato
                sb.table("opt_paper_trades").delete().eq("id", r["id"]).execute()

        in_flight_sell_keys = get_in_flight_option_sell_keys(sb, max_age_sec=120.0)

        active_broker_keys: set[tuple[str, str, float, str]] = set()
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

            mark_p = float(b_data.get("market_price") or 0.0)
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
                    (portfolio.get(und_sym) or broker_stocks.get(und_sym) or {}).get("market_price")
                    or old_plan.get("last_underlying_price")
                    or old_plan.get("entry_underlying_price")
                    or 0.0
                )
                new_plan = sync_option_exit_plan(
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
                    or new_plan != old_plan
                ):
                    sb.table("opt_paper_trades").update({
                        "qty": qty,
                        "entry_debit": entry_debit,
                        "entry_total_invested": total_invested,
                        "max_loss_total": total_invested,
                        "last_mark_price": round(mark_p, 4),
                        "last_mark_at": now_iso,
                        "unrealized_pnl": opt_pnl_usd,
                        "exit_plan": new_plan,
                        "updated_at": now_iso,
                    }).eq("id", ex_row["id"]).execute()
                    opt_synced += 1
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

                if is_zombie_closed and target_heal:
                    if in_opt_late_liq_window:
                        enqueue_late_option_liquidation(sb, und_sym, exp_iso, strike_v, right_v, qty, mark_p, now_dt=now_dt)
                        opt_late_liquidated += 1
                    else:
                        log_warning(MODULE, f"⏸️ [BROKER SYNC] Cooldown anti-zombi reciente para {und_sym} {exp_iso} {strike_v}{right_v} ({qty}x en TWS tras cierre reciente).")
                    continue

                if in_opt_late_liq_window:
                    if enqueue_late_option_liquidation(sb, und_sym, exp_iso, strike_v, right_v, qty, mark_p, now_dt=now_dt):
                        opt_late_liquidated += 1
                    continue

                if target_heal:
                    heal_old_plan = dict(target_heal.get("exit_plan") or {})
                    und_price = float(
                        (portfolio.get(und_sym) or broker_stocks.get(und_sym) or {}).get("market_price")
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
                        log_warning(MODULE, f"⚠️ [OUTSIDE IMPORT WINDOW] Reabriendo {und_sym} {exp_iso} {strike_v}{right_v} solo para visibilidad/cierre inmediato en apertura.")
                    heal_payload = {
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
                        "updated_at": now_iso,
                    }
                    if target_heal.get("status") == "closed":
                        heal_payload.update({
                            "exit_time": None,
                            "exit_reason": None,
                            "exit_credit": None,
                            "exit_total_recovered": None,
                            "realized_pnl": 0.0,
                        })
                    sb.table("opt_paper_trades").update(heal_payload).eq("id", target_heal["id"]).execute()
                    log_info(MODULE, f"🔄 [BROKER SYNC] Opción {und_sym} {exp_iso} {strike_v}{right_v} sincronizada/reabierta desde TWS ({qty}x @ ${entry_debit:.2f})")
                else:
                    und_price = float((portfolio.get(und_sym) or broker_stocks.get(und_sym) or {}).get("market_price") or 0.0)
                    init_plan = sync_option_exit_plan(
                        None,
                        entry_debit,
                        round(mark_p, 4),
                        has_active_sell=False,
                        is_put=(right_v == "P"),
                        underlying_price=und_price,
                    )
                    if not in_opt_import_window:
                        init_plan["late_import_force_close"] = True
                        init_plan["imported_outside_window"] = True
                        log_warning(MODULE, f"⚠️ [OUTSIDE IMPORT WINDOW] Importando {und_sym} {exp_iso} {strike_v}{right_v} marcado para cierre inmediato en apertura.")
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
                        "updated_at": now_iso,
                    }).execute()
                    log_info(MODULE, f"📥 [BROKER SYNC] Opción insertada desde TWS: {und_sym} {exp_iso} {strike_v}{right_v} ({qty}x @ ${entry_debit:.2f})")
                opt_synced += 1

        # Cerrar o eliminar en opt_paper_trades cualquier opción abierta que NO exista en TWS (solo con snapshot en vivo)
        for ck, opt_t in (sb_open_by_key.items() if snapshot_is_live else ()):
            if ck not in active_broker_keys:
                sym = opt_t["symbol"]
                try:
                    et_str = opt_t.get("entry_time") or opt_t.get("updated_at")
                    if et_str:
                        et_dt = parse_iso_utc(et_str)
                        if et_dt is not None and (now_dt - et_dt).total_seconds() < 90.0:
                            inflight_opt = (
                                sb.table("stocks_orders")
                                .select("id")
                                .eq("ticker", sym)
                                .eq("direction", "buy")
                                .in_("status", ["pending", "processing", "submitted"])
                                .limit(1)
                                .execute()
                            )
                            if inflight_opt.data:
                                continue
                except Exception:
                    pass

                if ck in in_flight_sell_keys:
                    continue

                exp_c = ck[1].replace("-", "")
                tb_match = f"OPT:{exp_c}:{ck[2]}:{ck[3]}"
                filled_buy = (
                    sb.table("stocks_orders")
                    .select("id")
                    .eq("ticker", sym)
                    .eq("target_band", tb_match)
                    .eq("direction", "buy")
                    .eq("status", "filled")
                    .limit(1)
                    .execute()
                )
                if not filled_buy.data and opt_t.get("model_version") != "v1.0-tws-sync":
                    sb.table("opt_paper_trades").delete().eq("id", opt_t["id"]).execute()
                    log_info(MODULE, f"🧹 [BROKER SYNC] Opción fantasma (no ejecutada en TWS) eliminada: {sym} {tb_match}")
                else:
                    last_m = float(opt_t.get("last_mark_price") or opt_t.get("entry_debit") or 0.0)
                    exit_t_iso = now_iso
                    entry_time_raw = opt_t.get("entry_time")
                    entry_dt_ref = parse_iso_utc(entry_time_raw)
                    try:
                        sell_q = (
                            sb.table("stocks_orders")
                            .select("filled_price, filled_at")
                            .eq("ticker", sym[:10])
                            .eq("target_band", tb_match)
                            .eq("direction", "sell")
                            .eq("status", "filled")
                        )
                        if entry_time_raw and hasattr(sell_q, "gte"):
                            sell_q = sell_q.gte("filled_at", str(entry_time_raw))
                        sell_ord = sell_q.order("filled_at", desc=True).limit(1).execute()
                        if sell_ord.data:
                            row_s = sell_ord.data[0]
                            s_fill_dt = parse_iso_utc(row_s.get("filled_at"))
                            if s_fill_dt is not None and (entry_dt_ref is None or s_fill_dt >= entry_dt_ref):
                                if row_s.get("filled_price"):
                                    last_m = float(row_s["filled_price"])
                                exit_t_iso = str(row_s["filled_at"])
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
                        "updated_at": now_iso,
                    }).eq("id", opt_t["id"]).execute()
                    try:
                        from app.core.circuit_breaker import record_trade_completion
                        record_trade_completion(
                            sym,
                            r_pnl,
                            sb=sb,
                            entry_time=opt_t.get("entry_time") or opt_t.get("created_at"),
                            exit_time=exit_t_iso,
                        )
                    except Exception:
                        pass
                    log_info(MODULE, f"📤 [BROKER SYNC] Opción cerrada por confirmación TWS: {sym} {tb_match} (Crédito: ${last_m:.2f}, PnL: ${r_pnl:.2f})")
                opt_closed += 1

    except Exception as e_opt:
        log_warning(MODULE, f"Error sincronizando opt_paper_trades con TWS: {e_opt}")

    # ── 2. RECONCILIAR STOCKS_POSITIONS ──
    stk_synced = 0
    try:
        sb_pos_res = sb.table("stocks_positions").select("*").in_("status", ["open", "closing"]).execute()
        sb_open_stocks: dict[str, dict[str, Any]] = {}
        for p in (sb_pos_res.data or []):
            tk = str(p.get("ticker") or "").upper()
            if tk not in sb_open_stocks:
                sb_open_stocks[tk] = p
            else:
                sb.table("stocks_positions").delete().eq("id", p["id"]).execute()

        from app.stocks.position_monitor import compute_dynamic_stock_trailing_sl
        for sym, b_data in broker_stocks.items():
            signed_qty = int(round(float(b_data.get("shares") or 0)))
            if signed_qty == 0:
                continue
            direction = "short" if signed_qty < 0 else "long"
            qty = abs(signed_qty)
            avg_cost = float(b_data.get("avg_cost") or 0.0)
            cur_p = float(b_data.get("market_price") or 0.0)
            if cur_p <= 0 and sym in sb_open_stocks:
                old_cp = float(sb_open_stocks[sym].get("current_price") or 0.0)
                if old_cp > 0 and abs(old_cp - avg_cost) > 0.0001:
                    cur_p = old_cp
            if cur_p <= 0:
                cur_p = avg_cost
            tws_pnl = b_data.get("unrealized_pnl")
            if direction == "short":
                calc_pnl = round((avg_cost - cur_p) * qty, 2)
                pnl_pct = round(((avg_cost - cur_p) / avg_cost * 100.0), 2) if avg_cost > 0 else 0.0
            else:
                calc_pnl = round((cur_p - avg_cost) * qty, 2)
                pnl_pct = round(((cur_p - avg_cost) / avg_cost * 100.0), 2) if avg_cost > 0 else 0.0
            pnl_usd = round(float(tws_pnl), 2) if (tws_pnl is not None and abs(float(tws_pnl)) > 0.0001) else calc_pnl

            if sym in sb_open_stocks:
                ex_p = sb_open_stocks[sym]
                old_cur = float(ex_p.get("current_price") or 0.0)
                old_pnl = float(ex_p.get("unrealized_pnl") or 0.0)
                old_dir = str(ex_p.get("direction") or "long").lower()
                cur_sl_v = float(ex_p.get("stop_loss") or 0.0)
                new_hi = round(max(float(ex_p.get("highest_price_reached") or 0.0), avg_cost, cur_p), 4)
                prev_lo = float(ex_p.get("lowest_price_reached") or 0.0)
                new_lo = round(min(prev_lo, avg_cost, cur_p) if prev_lo > 0 else min(avg_cost, cur_p), 4)
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
                    int(ex_p.get("shares") or 0) != qty
                    or old_dir != direction
                    or abs(float(ex_p.get("avg_price") or 0) - avg_cost) > 0.02
                    or abs(old_cur - cur_p) >= 0.001
                    or abs(old_pnl - pnl_usd) >= 0.01
                    or sl_improved
                ):
                    upd_stk = {
                        "status": "closing" if ex_p.get("status") == "closing" else "open",
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
                        "updated_at": now_iso,
                    }
                    if sl_improved:
                        upd_stk["stop_loss"] = dyn_sl
                        upd_stk["trailing_sl_price"] = dyn_sl
                        upd_stk["sl_type"] = "trailing_ratchet"
                        upd_stk["sl_activation_reason"] = str(dyn_reason)[:100]
                    sb.table("stocks_positions").update(upd_stk).eq("id", ex_p["id"]).execute()
                    stk_synced += 1
            else:
                # Evitar reinsertar si hubo un cierre reciente (<45s) y TWS aún no refresca el snapshot
                skip_recent_close = False
                if snapshot_is_live:
                    try:
                        recent_closed = (
                            sb.table("stocks_positions")
                            .select("id, updated_at, sl_close_reason")
                            .eq("ticker", sym)
                            .eq("status", "closed")
                            .order("updated_at", desc=True)
                            .limit(1)
                            .execute()
                        )
                        if recent_closed.data and recent_closed.data[0].get("updated_at"):
                            rc_dt = parse_iso_utc(recent_closed.data[0]["updated_at"])
                            if rc_dt is not None and (now_dt - rc_dt).total_seconds() < 45.0:
                                skip_recent_close = True
                    except Exception:
                        pass
                if skip_recent_close:
                    continue

                atr_fb = max(0.05, avg_cost * 0.02)
                if direction == "short":
                    sl_calc = round(avg_cost + (atr_fb * 2.0), 2)
                    tp_calc = round(max(0.01, avg_cost - (atr_fb * 5.0)), 2)
                    lo_init = min(avg_cost, round(cur_p, 4))
                    hi_init = max(avg_cost, round(cur_p, 4))
                else:
                    sl_calc = round(max(0.01, avg_cost - (atr_fb * 2.0)), 2)
                    tp_calc = round(avg_cost + (atr_fb * 5.0), 2)
                    hi_init = max(avg_cost, round(cur_p, 4))
                    lo_init = min(avg_cost, round(cur_p, 4))
                dyn_sl_i, dyn_reason_i = compute_dynamic_stock_trailing_sl(
                    entry_price=avg_cost,
                    current_price=cur_p,
                    highest_price=hi_init,
                    current_sl=sl_calc,
                    side=direction,
                    lowest_price=lo_init,
                )
                init_sl = dyn_sl_i if dyn_reason_i else sl_calc
                sb.table("stocks_positions").insert({
                    "ticker": sym,
                    "direction": direction,
                    "shares": qty,
                    "shares_remaining": qty,
                    "avg_price": round(avg_cost, 4),
                    "total_cost": round(qty * avg_cost, 2),
                    "current_price": round(cur_p, 4),
                    "unrealized_pnl": pnl_usd,
                    "unrealized_pnl_pct": pnl_pct,
                    "stop_loss": init_sl,
                    "trailing_sl_price": init_sl,
                    "highest_price_reached": hi_init,
                    "lowest_price_reached": lo_init,
                    "take_profit": tp_calc,
                    "sl_type": "trailing_ratchet" if dyn_reason_i else "backstop",
                    "group_name": "IB_PAPER",
                    "first_buy_at": now_iso,
                    "status": "open",
                    "updated_at": now_iso,
                }).execute()
                stk_synced += 1

        for sym, p_data in (sb_open_stocks.items() if snapshot_is_live else ()):
            if sym not in broker_stocks:
                try:
                    fb_str = p_data.get("first_buy_at") or p_data.get("updated_at")
                    if fb_str:
                        fb_dt = parse_iso_utc(fb_str)
                        if fb_dt is not None and (now_dt - fb_dt).total_seconds() < 60.0:
                            continue
                except Exception:
                    pass
                entry_p = float(p_data.get("avg_price") or 0.0)
                cur_p = float(p_data.get("current_price") or entry_p)
                pos_sh = abs(int(float(p_data.get("shares") or 0)))
                is_short = str(p_data.get("direction") or "long").lower() in ("short", "sell")
                close_dir = "buy" if is_short else "sell"
                sell_rule = "broker_sync"

                fb_raw = p_data.get("first_buy_at")
                fb_dt_ref = parse_iso_utc(fb_raw)
                try:
                    sell_q = sb.table("stocks_orders")\
                        .select("filled_at, filled_price, rule_code")\
                        .eq("ticker", sym)\
                        .eq("direction", close_dir)\
                        .eq("status", "filled")
                    if fb_raw and hasattr(sell_q, "gte"):
                        sell_q = sell_q.gte("filled_at", str(fb_raw))
                    sell_ord = sell_q.order("filled_at", desc=True).limit(1).execute()
                    if sell_ord.data and sell_ord.data[0].get("filled_at"):
                        s_dt_f = parse_iso_utc(sell_ord.data[0].get("filled_at"))
                        if s_dt_f is not None and (fb_dt_ref is None or s_dt_f >= fb_dt_ref):
                            if sell_ord.data[0].get("filled_price"):
                                cur_p = float(sell_ord.data[0]["filled_price"])
                            if sell_ord.data[0].get("rule_code"):
                                sell_rule = sell_ord.data[0]["rule_code"]
                except Exception:
                    pass

                if is_short:
                    pnl_usd = round((entry_p - cur_p) * pos_sh, 2)
                    pnl_pct = round(((entry_p - cur_p) / entry_p * 100), 2) if entry_p > 0 else 0.0
                else:
                    pnl_usd = round((cur_p - entry_p) * pos_sh, 2)
                    pnl_pct = round(((cur_p - entry_p) / entry_p * 100), 2) if entry_p > 0 else 0.0

                sb.table("stocks_positions").update({
                    "status": "closed",
                    "current_price": cur_p,
                    "unrealized_pnl": pnl_usd,
                    "unrealized_pnl_pct": pnl_pct,
                    "sl_close_reason": sell_rule,
                    "updated_at": now_iso,
                }).eq("id", p_data["id"]).execute()
    except Exception as e_stk:
        log_warning(MODULE, f"Error sincronizando stocks_positions con TWS: {e_stk}")

    return {
        "ok": True,
        "opt_synced": opt_synced,
        "opt_closed": opt_closed,
        "opt_late_liquidated": opt_late_liquidated,
        "stk_synced": stk_synced,
    }


def is_option_closing_pending(sb, pos: dict[str, Any], max_pending_sec: float = 120.0) -> bool:
    """
    Indica si una posición de opción ya tiene un cierre en curso esperando fill del broker.
    Si el pedido superó `max_pending_sec` (ej. puente offline u orden atascada), permite reintento.
    """
    plan = pos.get("exit_plan") or {}
    if not plan.get("closing_pending"):
        return False

    req_str = plan.get("closing_requested_at")
    if req_str:
        req_dt = parse_iso_utc(req_str)
        if req_dt is not None:
            age_s = (datetime.now(timezone.utc) - req_dt).total_seconds()
            if age_s <= max_pending_sec:
                return True
            return False

    ck = _row_contract_key(pos)
    exp_c = ck[1].replace("-", "")
    tb = f"OPT:{exp_c}:{ck[2]}:{ck[3]}"
    try:
        active_sell = (
            sb.table("stocks_orders")
            .select("id")
            .eq("ticker", ck[0][:10])
            .eq("target_band", tb)
            .eq("direction", "sell")
            .in_("status", ["pending", "processing", "submitted"])
            .limit(1)
            .execute()
        )
        return bool(active_sell.data)
    except Exception:
        return False


def request_broker_option_close(
    sb,
    pos: dict[str, Any],
    qty_to_close: int,
    exit_price_est: float,
    mapped_reason: str,
    detailed_reason: str,
    detailed_text: str = "",
    is_partial: bool = False,
    group_name: str = "OPTIONS_AUTONOMOUS",
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """
    Protocolo Broker-First para cierre de opciones:
    - Si el bridge IB está activo o el contrato existe en TWS (o el snapshot no es fresco):
      encola la orden SELL en `stocks_orders` y marca `exit_plan['closing_pending'] = True`
      SIN pasar `opt_paper_trades.status` a 'closed' hasta recibir el fill de TWS.
    - Sólo devuelve `broker_already_flat` si el snapshot TWS es fresco (<=900s) y confirma 0 contratos
      (o si no hay bridge activo y TWS no tiene posición).
    """
    now_ref = now_dt or datetime.now(timezone.utc)
    now_iso = now_ref.isoformat()
    sym = str(pos.get("symbol") or "").upper().strip()
    ck = _row_contract_key(pos)
    expiry_str = str(pos.get("expiry") or ck[1] or "")
    exp_c = expiry_str.replace("-", "")[:8]
    strike = ck[2]
    right = ck[3]
    opt_tb = f"OPT:{exp_c}:{strike}:{right}"

    portfolio, age_sec = load_broker_portfolio_snapshot(sb, allow_direct_fetch=False)
    snapshot_fresh = bool(portfolio is not None and age_sec <= 180.0)
    held_in_tws, tws_qty = is_option_held_in_broker(sb, sym, expiry_str, strike, right) if snapshot_fresh else (False, 0)

    # Si TWS confirma explícitamente (snapshot fresco <= 180s) que no existe posición, se puede cerrar local
    if snapshot_fresh and not held_in_tws:
        return {"status": "broker_already_flat", "held_in_tws": False, "tws_qty": 0}

    sell_qty = min(int(qty_to_close), int(tws_qty)) if (held_in_tws and tws_qty > 0) else int(qty_to_close)
    sell_qty = max(1, sell_qty)

    order_enqueued = False
    try:
        existing_sell = (
            sb.table("stocks_orders")
            .select("id, created_at, status")
            .eq("ticker", sym[:10])
            .eq("target_band", opt_tb)
            .eq("direction", "sell")
            .in_("status", ["pending", "processing", "submitted"])
            .limit(5)
            .execute()
        )
        has_fresh_sell = False
        for ex_o in (existing_sell.data or []):
            is_stale = False
            c_dt = parse_iso_utc(ex_o.get("created_at"))
            if c_dt is not None and (now_ref - c_dt).total_seconds() > 120.0:
                is_stale = True
            if is_stale and ex_o.get("id"):
                try:
                    sb.table("stocks_orders").update({"status": "cancelled"}).eq("id", ex_o["id"]).execute()
                except Exception:
                    pass
            else:
                has_fresh_sell = True
        if not has_fresh_sell:
            px_clean = round(float(exit_price_est or 0.0), 2)
            sb.table("stocks_orders").insert({
                "ticker": sym[:10],
                "target_band": opt_tb,
                "group_name": group_name,
                "rule_code": "APEX_AUTO",
                "order_type": "market",
                "direction": "sell",
                "shares": sell_qty,
                "market_price": float(exit_price_est or 0.0),
                "limit_price": px_clean if px_clean > 0 else 0.05,
                "status": "pending",
                "created_at": now_iso,
            }).execute()
            order_enqueued = True
            log_info(MODULE, f"📤 [BROKER CLOSE] Orden SELL MARKET encolada para confirmación TWS: {sym} {opt_tb} ({sell_qty}x) [{detailed_reason}]")
    except Exception as ord_e:
        log_warning(MODULE, f"Aviso encolando orden SELL para {sym} {opt_tb}: {ord_e}")

    plan = dict(pos.get("exit_plan") or {})
    plan["closing_pending"] = True
    plan["closing_requested_at"] = now_iso
    plan["pending_exit_reason"] = mapped_reason
    plan["detailed_exit_reason"] = detailed_reason
    plan["detailed_exit_text"] = detailed_text
    plan["pending_is_partial"] = bool(is_partial)
    plan["pending_qty_to_close"] = sell_qty

    try:
        sb.table("opt_paper_trades").update({
            "exit_plan": plan,
            "updated_at": now_iso,
        }).eq("id", pos["id"]).execute()
    except Exception as upd_e:
        log_warning(MODULE, f"Aviso marcando closing_pending en opt_paper_trades #{pos.get('id')}: {upd_e}")

    return {
        "status": "closing_pending",
        "order_enqueued": order_enqueued,
        "sell_qty": sell_qty,
        "target_band": opt_tb,
    }
