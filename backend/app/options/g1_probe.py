"""Sprint 0.5 - Sonda de factibilidad G1 y verificacion de suscripcion de opciones.

SOLO LECTURA (IBSession -> OptionsReadOnlyAdapter con whitelist). No envia ordenes.

Uso (con TWS/IB Gateway paper abierto, idealmente en horario de mercado):
  python -m app.options.g1_probe --check-subscription            # tengo datos de opciones? LIVE o DELAYED?
  python -m app.options.g1_probe --symbols AAPL,AMD,PLTR --save   # mide una sesion G1 y guarda en opt_g1_sessions
  python -m app.options.g1_probe --from-apex --save               # usa tickers de apex_scores

Variables: IB_HOST, IB_PORT (7497 paper), OPT_IB_CLIENT_ID (defecto 31),
           OPT_ALLOW_DELAYED (defecto true: fase de prueba con datos gratuitos).
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timezone
from typing import Any

from app.options import settings_defaults as sd
from app.options.ib_client import SUBSCRIPTION_ERRORS, IBSession, option_contract, stock_contract
from app.options.optionability import expirations_in_window, select_strikes

ALLOW_DELAYED = os.getenv("OPT_ALLOW_DELAYED", "true").strip().lower() in ("1", "true", "yes")


def _session() -> IBSession:
    ib = IBSession(allow_delayed=ALLOW_DELAYED)
    if not ib.ensure_connected(retries=2):
        raise SystemExit(f"No se pudo conectar a TWS {ib.host}:{ib.port} (clientId {ib.client_id}). "
                         "Abra TWS/Gateway paper y habilite la API (Configuration > API > Settings).")
    return ib


def check_subscription(price_fallback: float | None = None) -> int:
    ib = _session()
    print("== Verificacion de suscripcion de datos (solo lectura) ==")
    s = ib.quote(stock_contract("SPY"), wait=4.0)
    print(f"Acciones SPY -> estado: {s['market_data_type']} bid={s.get('bid')} ask={s.get('ask')} last={s.get('last')} close={s.get('close')} errores={s['errors']}")
    px = s.get("last") or s.get("close") or s.get("ask") or price_fallback
    conid = ib.conid("SPY")
    chain = ib.chain("SPY", conid) if conid else None
    if not chain:
        print(f"No se pudo obtener la cadena de opciones de SPY (conid={conid}). Verifique conexion con TWS.")
        return 2
    if not px:
        # En fin de semana / fuera de mercado TWS no emite ticks: usar precio de referencia para sondear opciones
        px = 580.0
        print(f"Mercado cerrado (fin de semana): usando precio de referencia SPY=${px:.2f} para sondear contratos.")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    exp = next((e for e in chain["expirations"] if e > today), None)
    strike = min(chain["strikes"], key=lambda k: abs(k - px))
    o = ib.quote(option_contract("SPY", exp, strike, "C", "SPY"), wait=4.0)
    print(f"Opcion SPY {exp} C {strike} -> estado: {o['market_data_type']} bid={o.get('bid')} ask={o.get('ask')} last={o.get('last')} close={o.get('close')} errores={o['errors']}")
    for _, code, _msg in ib.app.errors:
        if code in SUBSCRIPTION_ERRORS:
            print(f"  [{code}] {SUBSCRIPTION_ERRORS[code]}")
    has_live_spread = bool(o.get("bid") and o.get("ask"))
    has_delayed = (o["market_data_type"] in ("DELAYED", "FROZEN") or
                   any(c in (10167, 10090) for r, c, m in ib.app.errors) or
                   bool(o.get("last") or o.get("close")))
    if o["market_data_type"] == "LIVE" and has_live_spread:
        print("RESULTADO: OK - datos LIVE de opciones")
        return 0
    if has_delayed and ALLOW_DELAYED:
        print("RESULTADO: OK PARA PRUEBAS - datos DELAYED gratuitos (~15 min / fin de semana). Validos para desarrollo y paper trading.")
        return 0
    print("RESULTADO: sin cotizaciones de opciones utilizables (mercado cerrado, permisos o API sin habilitar).")
    return 1


def _candidate_viable(calls: list[dict], cap_usd: float, max_spread_pct: float, widths: tuple[float, float]) -> bool:
    """Bull call spread de debito: compra K1 (ask), vende K2 (bid). Riesgo = (debito + costes) * 100."""
    for i, lo in enumerate(calls):
        for hi in calls[i + 1:]:
            w = hi["strike"] - lo["strike"]
            if w < widths[0] or w > widths[1]:
                continue
            if None in (lo.get("ask"), lo.get("bid"), hi.get("ask"), hi.get("bid")):
                continue
            debit = lo["ask"] - hi["bid"]
            if debit <= 0 or debit >= w:
                continue
            sp_lo = (lo["ask"] - lo["bid"]) / lo["ask"] * 100 if lo["ask"] else 999
            sp_hi = (hi["ask"] - hi["bid"]) / hi["ask"] * 100 if hi["ask"] else 999
            if max(sp_lo, sp_hi) > max_spread_pct:
                continue
            risk = (debit + 2 * 0.70 / 100) * 100
            if risk <= cap_usd:
                return True
    return False


def measure_symbol(ib: IBSession, sym: str, eff: dict[str, Any]) -> dict[str, Any]:
    res: dict[str, Any] = {"symbol": sym, "optionable": False, "reason": None, "viable": False}
    px = ib.quote(stock_contract(sym))
    price = px.get("last") or px.get("close") or px.get("ask")
    if not price:
        res["reason"] = "sin precio del subyacente"
        return res
    if price < eff["min_underlying_price"]:
        res["reason"] = f"precio {price} < minimo"
        return res
    conid = ib.conid(sym)
    if not conid:
        res["reason"] = "contrato del subyacente no resuelto"
        return res
    chain = ib.chain(sym, conid)
    if not chain:
        res["reason"] = "sin opciones listadas"
        return res
    exps = expirations_in_window(chain["expirations"], datetime.now(timezone.utc), int(eff["dte_min"]), int(eff["dte_max"]))
    if not exps:
        res["reason"] = "sin vencimientos en ventana DTE"
        return res
    calls = []
    for k in select_strikes(chain["strikes"], price, n_each_side=3):
        q = ib.quote(option_contract(sym, exps[0], k, "C", sym), wait=2.5)
        calls.append({"strike": k, "bid": q.get("bid"), "ask": q.get("ask"), "volume": q.get("volume"),
                      "oi_call": q.get("oi_call"), "state": q["market_data_type"]})
    liquid = [c for c in calls if c.get("bid") and c.get("ask")]
    if not liquid:
        res["reason"] = "sin cotizaciones bid/ask de opciones (permisos o iliquidez)"
        res["states"] = sorted({c["state"] for c in calls})
        return res
    atm = min(liquid, key=lambda c: abs(c["strike"] - price))
    spread_pct = (atm["ask"] - atm["bid"]) / atm["ask"] * 100
    res.update({"price": price, "expiry": exps[0], "atm_spread_pct": round(spread_pct, 2), "atm_oi": atm.get("oi_call"),
                "states": sorted({c["state"] for c in calls})})
    if spread_pct > eff["max_atm_spread_pct"]:
        res["reason"] = f"spread ATM {spread_pct:.1f}% > {eff['max_atm_spread_pct']}%"
        return res
    res["optionable"] = True
    res["viable"] = _candidate_viable(liquid, eff["g1_max_risk_usd"], eff["g1_max_spread_pct"],
                                      (eff["spread_width_min"], eff["spread_width_max"]))
    return res


def load_apex_symbols(limit: int) -> list[str]:
    from app.core.supabase_client import get_supabase
    rows = get_supabase().table("apex_scores").select("ticker,calculated_at").order("calculated_at", desc=True).limit(500).execute().data or []
    seen: list[str] = []
    for r in rows:
        if r["ticker"] not in seen:
            seen.append(r["ticker"])
        if len(seen) >= limit:
            break
    return seen


def run_session(symbols: list[str], save: bool) -> int:
    eff = sd.effective_settings(None)
    ib = _session()
    results = []
    for s in symbols:
        r = measure_symbol(ib, s, eff)
        results.append(r)
        print(f"{s:6} optionable={r['optionable']!s:5} viable={r['viable']!s:5} {r.get('reason') or ''}")
    n_opt = sum(1 for r in results if r["optionable"])
    n_via = sum(1 for r in results if r["viable"])
    states = sorted({st for r in results for st in r.get("states", [])})
    allowed_states = {"LIVE", "DELAYED"} if ALLOW_DELAYED else {"LIVE"}
    passed = n_opt >= eff["g1_min_optionable"] and n_via >= 1 and bool(states) and set(states) <= allowed_states
    test_only = "DELAYED" in states
    print(f"\nSesion {date.today()}: optionable={n_opt}/{len(results)} viables={n_via} datos={states} -> {'PASA' if passed else 'NO PASA'}"
          + (" (SOLO PRUEBA: datos retrasados, no valido para decision G1 definitiva)" if test_only else ""))
    if save:
        from app.core.supabase_client import get_supabase
        get_supabase().table("opt_g1_sessions").upsert({
            "session_date": date.today().isoformat(), "symbols_evaluated": len(results),
            "optionable_count": n_opt, "viable_candidates": n_via,
            "market_data_type": ",".join(states) or "UNKNOWN", "details": results, "session_pass": passed,
        }, on_conflict="session_date").execute()
        print("Guardado en opt_g1_sessions.")
    ib.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-subscription", action="store_true")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--from-apex", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--price", type=float, default=None, help="Precio de referencia para pruebas fuera de mercado")
    a = ap.parse_args()
    if a.check_subscription:
        raise SystemExit(check_subscription(price_fallback=a.price))
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    if a.from_apex:
        syms = load_apex_symbols(a.limit)
    if not syms:
        raise SystemExit("Indique --symbols o --from-apex")
    raise SystemExit(run_session(syms, a.save))
