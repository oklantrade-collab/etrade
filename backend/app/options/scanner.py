"""Scanner de universo y datos de opciones (Sprint 2). SOLO LECTURA hacia IBKR; escribe en Supabase.

Flujo: universo APEX -> filtro de opcionabilidad -> contratos de los optionables -> cotizaciones
-> opt_quotes_latest + opt_snapshots (grabador). Se ejecuta dentro del Options Worker.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.core.logger import log_info, log_warning
from app.options.ib_client import IBSession, option_contract, stock_contract
from app.options.optionability import (
    OptionabilityInput, classify_quote, evaluate_optionability, expirations_in_window,
    select_strikes, strike_gap_pct,
)

MODULE = "OPTIONS_SCAN"
QUOTE_FIELDS = ("bid", "ask", "last", "volume", "iv", "delta", "gamma", "theta", "vega", "underlying_price")


def load_universe(sb, eff: dict[str, Any]) -> list[dict[str, Any]]:
    """Carga universo combinando catalizadores activos (CALL/PUT hasta max_candidates_per_direction)
    y fallback de APEX scores."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_per_dir = int(eff.get("max_candidates_per_direction") or 25)

    # 1. Cargar desde universe_catalyst_state si hay candidatos disponibles
    try:
        cat_rows = (sb.table("universe_catalyst_state").select("*")
                    .in_("decision", ["ENTER_CALL", "ENTER_PUT"])
                    .order("catalyst_score", desc=True).limit(100).execute().data or [])
        calls = [r for r in cat_rows if r.get("direction") in ("CALL", "bullish")][:max_per_dir]
        puts = [r for r in cat_rows if r.get("direction") in ("PUT", "bearish")][:max_per_dir]
        for r in calls + puts:
            sym = r["symbol"].upper()
            if sym not in seen:
                seen.add(sym)
                out.append({
                    "symbol": sym,
                    "direction": r.get("direction"),
                    "direction_source": "catalyst",
                    "catalyst_score": r.get("catalyst_score"),
                    "catalyst_state": {
                        "c1_gap": r.get("c1_gap"),
                        "c2_basis_1h": r.get("c2_basis_1h"),
                        "c3_adx": r.get("c3_adx"),
                        "c4_rebote": r.get("c4_rebote"),
                        "sipv_state": r.get("sipv_state"),
                    },
                })
    except Exception as e:
        log_warning(MODULE, f"No se pudo cargar de universe_catalyst_state: {e}")

    # 2. Complementar o fallback con APEX scores
    try:
        rows = (sb.table("apex_scores").select("ticker,apex_score_1d,apex_score_4h,calculated_at")
                .order("calculated_at", desc=True).limit(500).execute().data or [])
        seen_apex: dict[str, dict] = {}
        for r in rows:
            seen_apex.setdefault(r["ticker"], r)
        ranked = sorted(seen_apex.values(), key=lambda r: (r.get("apex_score_1d") or r.get("apex_score_4h") or 0), reverse=True)
        max_und = int(eff.get("max_underlyings") or 50)
        for r in ranked:
            if len(out) >= max_und:
                break
            t = r["ticker"].upper()
            if t not in seen:
                seen.add(t)
                out.append({"symbol": t, "apex_score": r.get("apex_score_1d") or r.get("apex_score_4h")})
    except Exception as e:
        log_warning(MODULE, f"Error cargando apex_scores: {e}")

    # 3. Lista complementaria D-1
    if eff.get("supplementary_list_enabled") and eff.get("supplementary_tickers"):
        for t in str(eff["supplementary_tickers"]).replace(" ", "").upper().split(","):
            if t and t not in seen:
                seen.add(t)
                out.append({"symbol": t, "apex_score": None, "supplementary": True})

    return out


def _pct_spread(bid: float | None, ask: float | None) -> float | None:
    if bid and ask and ask > 0:
        return round((ask - bid) / ask * 100, 3)
    return None


def evaluate_underlying(ib: IBSession, sym: str, eff: dict[str, Any], today: datetime) -> tuple[dict, dict | None, dict | None]:
    """Devuelve (fila para opt_underlyings, cadena, quote del subyacente)."""
    row: dict[str, Any] = {"symbol": sym}
    px = ib.quote(stock_contract(sym))
    price = px.get("last") or px.get("close") or px.get("ask")
    inp = OptionabilityInput(symbol=sym, price=price, data_states=[px["market_data_type"]])
    row.update(price=price, data_state=px["market_data_type"])
    conid = ib.conid(sym)
    row["underlying_conid"] = conid
    chain = ib.chain(sym, conid) if conid else None
    inp.has_options = bool(chain)
    exps: list[str] = []
    if chain and price:
        exps = expirations_in_window(chain["expirations"], today, int(eff["dte_min"]), int(eff["dte_max"]))
        inp.expirations_in_window = len(exps)
        inp.strike_gap_pct = strike_gap_pct(chain["strikes"], price)
        if exps:
            atm = min(chain["strikes"], key=lambda k: abs(k - price))
            q = ib.quote(option_contract(sym, exps[0], atm, "C", sym), wait=3.0)
            inp.data_states.append(q["market_data_type"])
            inp.atm_spread_pct = _pct_spread(q.get("bid"), q.get("ask"))
            inp.atm_volume = q.get("volume")
            inp.atm_oi = q.get("oi_call")
    ok, reasons, warns = evaluate_optionability(inp, eff)
    row.update(optionable=ok, optionable_reason="; ".join(reasons) or None, warnings=warns,
               strike_gap_pct=inp.strike_gap_pct, atm_spread_pct=inp.atm_spread_pct,
               atm_oi=inp.atm_oi, atm_volume=inp.atm_volume, iv_hv_ratio=None,
               event_flags=[], updated_at=datetime.now(timezone.utc).isoformat())
    row["_exps"] = exps
    return row, chain, px


def sync_contracts_and_quotes(ib: IBSession, sb, underlying_id: int, sym: str, price: float, chain: dict,
                              exps: list[str], eff: dict[str, Any], limit_contracts: int) -> dict[str, int]:
    """Resuelve conIds de strikes cercanos (calls y puts) del primer vencimiento y guarda cotizaciones + snapshots."""
    stats = {"contracts": 0, "quotes_usable": 0, "quotes_unusable": 0}
    now = datetime.now(timezone.utc)
    strikes = select_strikes(chain["strikes"], price, n_each_side=3)
    expiry = exps[0]
    for k in strikes:
        for right in ("C", "P"):
            if stats["contracts"] >= limit_contracts:
                return stats
            info = ib.option_conid(sym, expiry, k, right, sym)
            if not info:
                continue
            c = sb.table("opt_contracts").upsert({
                "conid": info["conid"], "underlying_id": underlying_id, "right": right, "strike": k,
                "expiry": datetime.strptime(expiry, "%Y%m%d").date().isoformat(),
                "multiplier": info["multiplier"], "trading_class": info["trading_class"],
                "exchange": info["exchange"], "active": True,
            }, on_conflict="conid").execute().data[0]
            stats["contracts"] += 1
            q = ib.quote(option_contract(sym, expiry, k, right, info["trading_class"]), wait=3.0)
            state, usable, why = classify_quote(q, now=None, max_age_sec=float(eff["max_quote_age_sec"]),
                                                allow_delayed=bool(eff["allow_delayed_data"]))
            oi = q.get("oi_call") if right == "C" else q.get("oi_put")
            vals = {f: q.get(f) for f in QUOTE_FIELDS}
            vals["open_interest"] = oi
            sb.table("opt_quotes_latest").upsert({
                "contract_id": c["id"], **vals, "market_data_type": state, "usable": usable,
                "unusable_reason": why, "received_at": q["received_at"],
            }, on_conflict="contract_id").execute()
            sb.table("opt_snapshots").insert({
                "contract_id": c["id"], **vals, "market_data_type": state, "captured_at": q["received_at"],
            }).execute()
            stats["quotes_usable" if usable else "quotes_unusable"] += 1
    return stats


def run_scan(ib: IBSession, sb, eff: dict[str, Any], symbols: list[str] | None = None,
             contracts_per_underlying: int = 12) -> dict[str, Any]:
    today = datetime.now(timezone.utc)
    universe = ([{"symbol": s, "apex_score": None} for s in symbols] if symbols else load_universe(sb, eff))
    summary = {"evaluated": 0, "optionable": 0, "rejected": 0, "errors": 0, "contracts": 0, "quotes_usable": 0,
               "quotes_unusable": 0, "details": []}
    for u in universe:
        sym = u["symbol"]
        try:
            if not ib.ensure_connected():
                raise RuntimeError("TWS no disponible")
            row, chain, px = evaluate_underlying(ib, sym, eff, today)
            exps = row.pop("_exps")
            row["apex_score"] = u.get("apex_score")
            if u.get("direction"):
                row["direction"] = u.get("direction")
                row["direction_source"] = u.get("direction_source") or "catalyst"
                row["catalyst_score"] = u.get("catalyst_score")
                row["catalysts_active"] = u.get("catalysts_active")
                row["catalyst_state"] = u.get("catalyst_state")
            saved = sb.table("opt_underlyings").upsert(row, on_conflict="symbol").execute().data[0]
            summary["evaluated"] += 1
            if row["optionable"]:
                summary["optionable"] += 1
                st = sync_contracts_and_quotes(ib, sb, saved["id"], sym, row["price"], chain, exps, eff, contracts_per_underlying)
                sb.table("opt_underlyings").update({"last_chain_sync_at": datetime.now(timezone.utc).isoformat()}).eq("id", saved["id"]).execute()
                for k in ("contracts", "quotes_usable", "quotes_unusable"):
                    summary[k] += st[k]
            else:
                summary["rejected"] += 1
            summary["details"].append({"symbol": sym, "optionable": row["optionable"], "reason": row["optionable_reason"]})
        except Exception as e:
            summary["errors"] += 1
            summary["details"].append({"symbol": sym, "error": str(e)[:200]})
            log_warning(MODULE, f"{sym}: {e}")
    log_info(MODULE, f"Scan: {summary['optionable']}/{summary['evaluated']} optionables, {summary['contracts']} contratos")
    return summary


def record_snapshots(ib: IBSession, sb, eff: dict[str, Any], max_contracts: int | None = None) -> dict[str, int]:
    """Grabador: refresca cotizaciones de los contratos activos de subyacentes optionables (respeta max_concurrent_quotes)."""
    cap = int(max_contracts or eff["max_concurrent_quotes"])
    rows = (sb.table("opt_contracts").select("id,conid,right,strike,expiry,trading_class,underlying_id,opt_underlyings(symbol,optionable)")
            .eq("active", True).limit(cap * 2).execute().data or [])
    rows = [r for r in rows if (r.get("opt_underlyings") or {}).get("optionable")][:cap]
    n_ok = n_bad = 0
    today = date.today()
    for r in rows:
        if datetime.strptime(r["expiry"], "%Y-%m-%d").date() < today:
            sb.table("opt_contracts").update({"active": False}).eq("id", r["id"]).execute()
            continue
        if not ib.ensure_connected():
            break
        sym = r["opt_underlyings"]["symbol"]
        q = ib.quote(option_contract(sym, r["expiry"].replace("-", ""), float(r["strike"]), r["right"], r.get("trading_class") or sym), wait=2.5)
        state, usable, why = classify_quote(q, None, float(eff["max_quote_age_sec"]), bool(eff["allow_delayed_data"]))
        vals = {f: q.get(f) for f in QUOTE_FIELDS}
        vals["open_interest"] = q.get("oi_call") if r["right"] == "C" else q.get("oi_put")
        sb.table("opt_quotes_latest").upsert({"contract_id": r["id"], **vals, "market_data_type": state, "usable": usable,
                                              "unusable_reason": why, "received_at": q["received_at"]}, on_conflict="contract_id").execute()
        sb.table("opt_snapshots").insert({"contract_id": r["id"], **vals, "market_data_type": state, "captured_at": q["received_at"]}).execute()
        n_ok += usable
        n_bad += (not usable)
    return {"snapshots_usable": n_ok, "snapshots_unusable": n_bad}
