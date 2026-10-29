"""
Sincronización autoritativa Broker-First (TWS -> Supabase) para Opciones y Acciones.
Garantiza que `opt_paper_trades` y `stocks_positions` sean una copia idéntica de
`ib_broker_portfolio` reportado por Interactive Brokers TWS (APOLO).
"""
from __future__ import annotations

import ast
import time
from datetime import datetime, timezone
from typing import Any

from app.core.logger import log_info, log_warning

MODULE = "BROKER_SYNC"
_LAST_SYNC_TS: float = 0.0


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


def load_broker_portfolio_snapshot(sb) -> tuple[dict[str, Any], float]:
    """
    Lee `ib_broker_portfolio` desde `stocks_config` y devuelve (portfolio_dict, age_seconds).
    """
    try:
        res = sb.table("stocks_config").select("value, updated_at").eq("key", "ib_broker_portfolio").limit(1).execute()
        if not res.data:
            return {}, 999999.0
        row = res.data[0]
        raw_val = row.get("value") or "{}"
        upd_str = row.get("updated_at")
        age_sec = 999999.0
        if upd_str:
            try:
                u_dt = datetime.fromisoformat(str(upd_str).replace("Z", "+00:00"))
                age_sec = max(0.0, (datetime.now(timezone.utc) - u_dt).total_seconds())
            except Exception:
                pass
        portfolio = ast.literal_eval(raw_val) if isinstance(raw_val, str) else (raw_val or {})
        if isinstance(portfolio, dict):
            return portfolio, age_sec
    except Exception as e:
        log_warning(MODULE, f"No se pudo leer ib_broker_portfolio: {e}")
    return {}, 999999.0


def is_option_held_in_broker(sb, symbol: str, expiry: str, strike: float, right: str) -> tuple[bool, int]:
    """
    Verifica si el contrato de opción existe con qty > 0 en `ib_broker_portfolio`.
    Devuelve (is_held, qty).
    """
    portfolio, age_sec = load_broker_portfolio_snapshot(sb)
    if not portfolio or age_sec > 900.0:
        # Si el snapshot no está disponible, permitir por fallback
        return True, 0

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


def reconcile_with_ib_broker_portfolio(sb, min_interval_sec: float = 8.0, force: bool = False) -> dict[str, Any]:
    """
    Sincroniza `opt_paper_trades` y `stocks_positions` con `ib_broker_portfolio`
    para garantizar que lo que está en el Broker TWS sea exactamente lo que está
    abierto en el sistema.
    """
    global _LAST_SYNC_TS
    now_ts = time.time()
    if not force and (now_ts - _LAST_SYNC_TS < min_interval_sec):
        return {"skipped": True}

    portfolio, age_sec = load_broker_portfolio_snapshot(sb)
    if not portfolio or age_sec > 600.0:
        return {"skipped": True, "reason": f"snapshot_stale_or_empty ({age_sec:.0f}s)"}

    _LAST_SYNC_TS = now_ts
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    broker_stocks: dict[str, dict[str, Any]] = {}
    broker_options: dict[str, dict[str, Any]] = {}

    for sym_key, b_data in portfolio.items():
        qty = float(b_data.get("shares") or 0.0)
        # Ignorar posiciones en 0 o cortos residuales (< 0) en la vista long
        if qty <= 0:
            continue
        sec_type = str(b_data.get("sec_type") or "").upper()
        if sec_type == "OPT" or ":OPT:" in sym_key or b_data.get("right") or b_data.get("strike"):
            broker_options[sym_key] = b_data
        else:
            broker_stocks[str(b_data.get("symbol") or sym_key).upper()] = b_data

    # ── 1. RECONCILIAR OPT_PAPER_TRADES ──
    opt_synced = 0
    opt_closed = 0
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

        # Verificar órdenes SELL de opciones en vuelo (< 45 segundos) para no reabrir mientras TWS está ejecutando el cierre
        recent_sells = (
            sb.table("stocks_orders")
            .select("ticker, target_band, created_at, status")
            .eq("direction", "sell")
            .in_("status", ["pending", "processing"])
            .execute()
            .data or []
        )
        in_flight_sell_keys: set[tuple[str, str, float, str]] = set()
        for so in recent_sells:
            tb = str(so.get("target_band") or "").upper()
            c_str = so.get("created_at")
            if "OPT:" in tb and c_str:
                try:
                    c_dt = datetime.fromisoformat(str(c_str).replace("Z", "+00:00"))
                    if (now_dt - c_dt).total_seconds() < 45.0:
                        parts = tb.split(":")
                        if len(parts) == 4 and parts[0] == "OPT":
                            in_flight_sell_keys.add((
                                str(so.get("ticker") or "").upper(),
                                _fmt_exp(parts[1]),
                                round(float(parts[2]), 2),
                                parts[3].upper()
                            ))
                except Exception:
                    pass

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

            if ck in sb_open_by_key:
                ex_row = sb_open_by_key[ck]
                if int(ex_row.get("qty") or 0) != qty or abs(float(ex_row.get("entry_debit") or 0) - entry_debit) > 0.02:
                    sb.table("opt_paper_trades").update({
                        "qty": qty,
                        "entry_debit": entry_debit,
                        "entry_total_invested": total_invested,
                        "max_loss_total": total_invested,
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

                recent_opt = (
                    sb.table("opt_paper_trades")
                    .select("*")
                    .eq("symbol", und_sym)
                    .eq("strategy_type", strat_v)
                    .order("id", desc=True)
                    .limit(8)
                    .execute()
                )
                target_heal = None
                for cand_r in (recent_opt.data or []):
                    if _row_contract_key(cand_r) == ck:
                        target_heal = cand_r
                        break

                if target_heal:
                    sb.table("opt_paper_trades").update({
                        "status": "open",
                        "qty": qty,
                        "expiry": exp_iso,
                        "entry_debit": entry_debit,
                        "entry_fills": leg_fill,
                        "entry_total_invested": total_invested,
                        "max_loss_total": total_invested,
                        "exit_time": None,
                        "exit_credit": None,
                        "exit_fills": [],
                        "exit_reason": None,
                        "realized_pnl": None,
                        "updated_at": now_iso,
                    }).eq("id", target_heal["id"]).execute()
                    log_info(MODULE, f"♻️ [BROKER SYNC] Opción {und_sym} {exp_iso} {strike_v}{right_v} reabierta desde TWS ({qty}x @ ${entry_debit:.2f})")
                else:
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
                        "unrealized_pnl": 0.0,
                        "last_mark_price": entry_debit,
                        "last_mark_at": now_iso,
                        "exit_plan": {"trailing_sl_type": "INITIAL", "highest_premium_seen": entry_debit},
                        "model_version": "v1.0-tws-sync",
                        "settings_version": 1,
                        "updated_at": now_iso,
                    }).execute()
                    log_info(MODULE, f"📥 [BROKER SYNC] Opción insertada desde TWS: {und_sym} {exp_iso} {strike_v}{right_v} ({qty}x @ ${entry_debit:.2f})")
                opt_synced += 1

        # Cerrar o eliminar en opt_paper_trades cualquier opción abierta que NO exista en TWS
        for ck, opt_t in sb_open_by_key.items():
            if ck not in active_broker_keys:
                sym = opt_t["symbol"]
                try:
                    et_str = opt_t.get("entry_time") or opt_t.get("updated_at")
                    if et_str:
                        et_dt = datetime.fromisoformat(str(et_str).replace("Z", "+00:00"))
                        if (now_dt - et_dt).total_seconds() < 45.0:
                            inflight_opt = (
                                sb.table("stocks_orders")
                                .select("id")
                                .eq("ticker", sym)
                                .eq("direction", "buy")
                                .in_("status", ["pending", "processing"])
                                .limit(1)
                                .execute()
                            )
                            if inflight_opt.data:
                                continue
                except Exception:
                    pass

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
                    e_deb = float(opt_t.get("entry_debit") or last_m)
                    t_qty = int(opt_t.get("qty") or 1)
                    t_rec = round(last_m * 100.0 * t_qty, 2)
                    r_pnl = round((last_m - e_deb) * 100.0 * t_qty, 2)
                    sb.table("opt_paper_trades").update({
                        "status": "closed",
                        "exit_reason": "manual_simulated",
                        "exit_credit": last_m,
                        "exit_total_recovered": t_rec,
                        "realized_pnl": r_pnl,
                        "unrealized_pnl": 0.0,
                        "exit_time": now_iso,
                        "updated_at": now_iso,
                    }).eq("id", opt_t["id"]).execute()
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

        for sym, b_data in broker_stocks.items():
            qty = int(round(float(b_data.get("shares") or 0)))
            if qty <= 0:
                continue
            avg_cost = float(b_data.get("avg_cost") or 0.0)
            if sym in sb_open_stocks:
                ex_p = sb_open_stocks[sym]
                if int(ex_p.get("shares") or 0) != qty or abs(float(ex_p.get("avg_price") or 0) - avg_cost) > 0.02:
                    sb.table("stocks_positions").update({
                        "status": "open",
                        "shares": qty,
                        "shares_remaining": qty,
                        "avg_price": round(avg_cost, 4),
                        "total_cost": round(qty * avg_cost, 2),
                        "updated_at": now_iso,
                    }).eq("id", ex_p["id"]).execute()
                    stk_synced += 1
            else:
                recent_closed = (
                    sb.table("stocks_positions")
                    .select("*")
                    .eq("ticker", sym)
                    .order("updated_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if recent_closed.data:
                    sb.table("stocks_positions").update({
                        "status": "open",
                        "shares": qty,
                        "shares_remaining": qty,
                        "avg_price": round(avg_cost, 4),
                        "total_cost": round(qty * avg_cost, 2),
                        "sl_close_reason": None,
                        "exit_triggered_by": None,
                        "updated_at": now_iso,
                    }).eq("id", recent_closed.data[0]["id"]).execute()
                else:
                    atr_fb = max(0.05, avg_cost * 0.02)
                    sl_calc = round(max(0.01, avg_cost - (atr_fb * 2.0)), 2)
                    tp_calc = round(avg_cost + (atr_fb * 5.0), 2)
                    sb.table("stocks_positions").insert({
                        "ticker": sym,
                        "direction": "long",
                        "shares": qty,
                        "shares_remaining": qty,
                        "avg_price": round(avg_cost, 4),
                        "total_cost": round(qty * avg_cost, 2),
                        "current_price": avg_cost,
                        "unrealized_pnl": 0.0,
                        "unrealized_pnl_pct": 0.0,
                        "stop_loss": sl_calc,
                        "trailing_sl_price": sl_calc,
                        "highest_price_reached": avg_cost,
                        "take_profit": tp_calc,
                        "group_name": "IB_PAPER",
                        "first_buy_at": now_iso,
                        "status": "open",
                        "updated_at": now_iso,
                    }).execute()
                stk_synced += 1

        for sym, p_data in sb_open_stocks.items():
            if sym not in broker_stocks:
                try:
                    fb_str = p_data.get("first_buy_at") or p_data.get("updated_at")
                    if fb_str:
                        fb_dt = datetime.fromisoformat(str(fb_str).replace("Z", "+00:00"))
                        if (now_dt - fb_dt).total_seconds() < 60.0:
                            continue
                except Exception:
                    pass
                entry_p = float(p_data.get("avg_price") or 0.0)
                cur_p = float(p_data.get("current_price") or entry_p)
                pos_sh = int(float(p_data.get("shares") or 0))
                sell_rule = "broker_sync"

                try:
                    sell_ord = sb.table("stocks_orders")\
                        .select("filled_at, filled_price, rule_code")\
                        .eq("ticker", sym)\
                        .eq("direction", "sell")\
                        .eq("status", "filled")\
                        .order("filled_at", desc=True)\
                        .limit(1)\
                        .execute()
                    if sell_ord.data and sell_ord.data[0].get("filled_at"):
                        if sell_ord.data[0].get("filled_price"):
                            cur_p = float(sell_ord.data[0]["filled_price"])
                        if sell_ord.data[0].get("rule_code"):
                            sell_rule = sell_ord.data[0]["rule_code"]
                except Exception:
                    pass

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

    return {"ok": True, "opt_synced": opt_synced, "opt_closed": opt_closed, "stk_synced": stk_synced}
