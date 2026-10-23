import sys
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
load_dotenv(".env")

from app.core.supabase_client import get_supabase
from app.options.ib_client import IBSession, option_contract
from app.options.worker import _load_effective
from app.options.optionability import expirations_in_window, select_strikes

sb = get_supabase()
eff = _load_effective(sb)

symbols = ["SPY", "NVDA", "AAPL", "MSFT", "TSLA"]
print(f"Iniciando sesion con APOLO para poblar datos de opciones: {symbols}...", flush=True)

ib = IBSession(allow_delayed=True, host="192.168.1.105", port=7497, client_id=28)
if not ib.ensure_connected(retries=5):
    print("Error: no se pudo conectar a APOLO TWS (192.168.1.105:7497)", flush=True)
    sys.exit(1)

print(f"Conectado exitosamente con client_id={ib.client_id}!", flush=True)

now_utc = datetime.now(timezone.utc)
stats = {"underlyings": 0, "contracts": 0, "errors": 0}

for sym in symbols:
    try:
        print(f"\n[Procesando {sym}]", flush=True)
        conid = ib.conid(sym)
        if not conid:
            print(f"  No se encontro conId para {sym}", flush=True)
            continue
        
        chain = ib.chain(sym, conid)
        if not chain or not chain.get("expirations"):
            print(f"  No se obtuvo cadena de opciones para {sym}", flush=True)
            continue
        
        exps = chain["expirations"]
        strikes = chain["strikes"]
        print(f"  {sym} conId={conid}: {len(exps)} vencimientos, {len(strikes)} strikes disponibles.", flush=True)
        
        # Filtro de vencimientos dentro de ventana DTE (7 a 30 dias)
        valid_exps = expirations_in_window(exps, now_utc, int(eff.get("dte_min", 7)), int(eff.get("dte_max", 30)))
        print(f"  Vencimientos en ventana DTE (7-30 dias): {valid_exps[:3]}", flush=True)
        
        # Guardar / actualizar en opt_underlyings
        und_row = {
            "symbol": sym,
            "underlying_conid": conid,
            "data_state": "DELAYED",
            "optionable": True,
            "last_chain_sync_at": now_utc.isoformat(),
            "updated_at": now_utc.isoformat(),
        }
        saved_und = sb.table("opt_underlyings").upsert(und_row, on_conflict="symbol").execute().data[0]
        stats["underlyings"] += 1
        print(f"  Guardado en opt_underlyings con ID #{saved_und['id']}", flush=True)
        
        if not valid_exps:
            continue
            
        target_exp = valid_exps[0]
        
        # Obtener referencia de precio del subyacente
        # Usamos strikes centrales o precio existente
        cur_p = float(saved_und.get("price") or 0.0)
        if cur_p <= 0:
            # Buscar strike intermedio como aproximacion inicial
            cur_p = strikes[len(strikes) // 2]
            
        chosen_strikes = select_strikes(strikes, cur_p, n_each_side=2)
        print(f"  Strikes seleccionados para exp {target_exp}: {chosen_strikes}", flush=True)
        
        for k in chosen_strikes:
            for right in ("C", "P"):
                info = ib.option_conid(sym, target_exp, k, right, sym)
                if not info:
                    continue
                
                exp_date = datetime.strptime(target_exp, "%Y%m%d").date().isoformat()
                c_row = {
                    "conid": info["conid"],
                    "underlying_id": saved_und["id"],
                    "right": right,
                    "strike": k,
                    "expiry": exp_date,
                    "multiplier": info.get("multiplier", 100),
                    "trading_class": info.get("trading_class", sym),
                    "exchange": info.get("exchange", "SMART"),
                    "active": True,
                }
                c_saved = sb.table("opt_contracts").upsert(c_row, on_conflict="conid").execute().data[0]
                stats["contracts"] += 1
                
                # Solicitar cotizacion para el contrato
                opt_c = option_contract(sym, target_exp, k, right, info.get("trading_class", sym))
                q = ib.quote(opt_c, wait=2.5)
                
                q_vals = {
                    "contract_id": c_saved["id"],
                    "bid": q.get("bid"),
                    "ask": q.get("ask"),
                    "last": q.get("last"),
                    "iv": q.get("iv"),
                    "delta": q.get("delta"),
                    "gamma": q.get("gamma"),
                    "theta": q.get("theta"),
                    "vega": q.get("vega"),
                    "underlying_price": q.get("underlying_price"),
                    "market_data_type": q.get("market_data_type", "DELAYED"),
                    "usable": True if (q.get("last") or q.get("iv")) else False,
                    "received_at": q.get("received_at", now_utc.isoformat()),
                }
                sb.table("opt_quotes_latest").upsert(q_vals, on_conflict="contract_id").execute()
                print(f"    Contrato #{c_saved['id']} {sym} {target_exp} {k}{right}: conId={info['conid']} Last={q.get('last')} IV={q.get('iv')}", flush=True)

    except Exception as e:
        print(f"  Error en {sym}: {e}", flush=True)
        stats["errors"] += 1

ib.close()
print("\n" + "=" * 50, flush=True)
print(f"Resumen de ejecucion:", flush=True)
print(f"  Subyacentes procesados: {stats['underlyings']}")
print(f"  Contratos de opciones guardados: {stats['contracts']}")
print(f"  Errores: {stats['errors']}")
print("=" * 50, flush=True)
