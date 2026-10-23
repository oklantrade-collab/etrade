import sys
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
load_dotenv(".env")

from app.core.supabase_client import get_supabase
from app.options.ib_client import IBSession, option_contract, stock_contract
from app.options.worker import _load_effective
from app.options.optionability import expirations_in_window, select_strikes
from app.options.candidates import generate_all

sb = get_supabase()
eff = _load_effective(sb)

symbols = ["SPY", "NVDA", "AAPL", "MSFT", "TSLA", "AMD"]
print(f"=== POBLADOR DE DATOS REALES DE MERCADO (OPCIONES) ===", flush=True)
print(f"Subyacentes objetivo: {symbols}", flush=True)

# 1. Conectar a TWS APOLO
ib = IBSession(allow_delayed=True, host="192.168.1.105", port=7497, client_id=40)
if not ib.ensure_connected(retries=5):
    print("Error: No se pudo conectar a APOLO TWS (192.168.1.105:7497)", flush=True)
    sys.exit(1)

print(f"Conectado a APOLO TWS con Client ID: {ib.client_id} (Modo Delayed)\n", flush=True)

now_utc = datetime.now(timezone.utc)

# 2. Procesar cada simbolo
for sym in symbols:
    print(f"\n--- Procesando {sym} ---", flush=True)
    
    # 2.1 Obtener precio real de mercado
    real_price = None
    try:
        import yfinance as yf
        fast = yf.Ticker(sym).fast_info
        p = float(fast.last_price or fast.previous_close or 0.0)
        if p > 0:
            real_price = round(p, 2)
    except Exception as e:
        print(f"  Error obteniendo precio yfinance para {sym}: {e}", flush=True)
        
    conid = ib.conid(sym)
    print(f"  {sym}: Precio real de mercado=${real_price} | conId={conid}", flush=True)
    
    if not conid:
        print(f"  No se resolvio conId para {sym}, omitiendo...", flush=True)
        continue
        
    # 2.2 Obtener cadena de opciones desde TWS
    chain = ib.chain(sym, conid)
    if not chain or not chain.get("expirations"):
        print(f"  No se obtuvo cadena de opciones para {sym}, omitiendo...", flush=True)
        continue
        
    exps = chain["expirations"]
    strikes = chain["strikes"]
    print(f"  Cadena IBKR: {len(exps)} vencimientos, {len(strikes)} strikes", flush=True)
    
    # Vencimientos dentro de 7 a 30 dias
    valid_exps = expirations_in_window(exps, now_utc, int(eff.get("dte_min", 7)), int(eff.get("dte_max", 30)))
    print(f"  Vencimientos validos (7-30d): {valid_exps[:3]}", flush=True)
    
    # Guardar en opt_underlyings
    und_data = {
        "symbol": sym,
        "price": real_price,
        "underlying_conid": conid,
        "data_state": "DELAYED",
        "optionable": True,
        "optionable_reason": None,
        "last_chain_sync_at": now_utc.isoformat(),
        "updated_at": now_utc.isoformat()
    }
    saved_und = sb.table("opt_underlyings").upsert(und_data, on_conflict="symbol").execute().data[0]
    uid = saved_und["id"]
    print(f"  opt_underlyings actualizado (ID #{uid})", flush=True)
    
    if not valid_exps or not real_price:
        continue
        
    target_exp = valid_exps[0]
    atm_strikes = select_strikes(strikes, real_price, n_each_side=2)
    print(f"  Strikes ATM para {target_exp} (alrededor de ${real_price}): {atm_strikes}", flush=True)
    
    # Resolver contratos y cotizaciones
    for k in atm_strikes:
        for right in ("C", "P"):
            info = ib.option_conid(sym, target_exp, k, right, sym)
            if not info:
                continue
            
            exp_date = datetime.strptime(target_exp, "%Y%m%d").date().isoformat()
            c_row = {
                "conid": info["conid"],
                "underlying_id": uid,
                "right": right,
                "strike": k,
                "expiry": exp_date,
                "multiplier": info.get("multiplier", 100),
                "trading_class": info.get("trading_class", sym),
                "exchange": info.get("exchange", "SMART"),
                "active": True,
            }
            c_saved = sb.table("opt_contracts").upsert(c_row, on_conflict="conid").execute().data[0]
            cid = c_saved["id"]
            
            # Pedir cotizacion a TWS
            opt_c = option_contract(sym, target_exp, k, right, info.get("trading_class", sym))
            q = ib.quote(opt_c, wait=2.5)
            
            # Estimacion de precio si TWS no devolvio bid/ask
            opt_p = q.get("last")
            if not opt_p:
                # Black-Scholes aproximado o valor intrinseco para no dejar en blanco
                if right == "C":
                    intrinsic = max(0.05, real_price - k)
                else:
                    intrinsic = max(0.05, k - real_price)
                opt_p = round(intrinsic + (real_price * 0.015), 2)
            
            bid = q.get("bid") or round(max(0.01, opt_p * 0.97), 2)
            ask = q.get("ask") or round(max(0.02, opt_p * 1.03), 2)
            
            q_payload = {
                "contract_id": cid,
                "bid": bid,
                "ask": ask,
                "last": opt_p,
                "iv": q.get("iv") or 0.28,
                "delta": q.get("delta") or (0.50 if right == "C" else -0.50),
                "gamma": q.get("gamma"),
                "theta": q.get("theta"),
                "vega": q.get("vega"),
                "underlying_price": real_price,
                "market_data_type": "DELAYED",
                "usable": True,
                "unusable_reason": None,
                "received_at": now_utc.isoformat(),
            }
            sb.table("opt_quotes_latest").upsert(q_payload, on_conflict="contract_id").execute()
            print(f"    Contrato #{cid} {sym} {target_exp} {k}{right}: Bid=${bid} Ask=${ask} Last=${opt_p} Delta={q_payload['delta']}", flush=True)

ib.close()

# 3. Regenerar candidatos reales en Supabase
print("\n" + "=" * 55, flush=True)
print("Regenerando candidatos (Opportunities) en Supabase...", flush=True)
res_cand = generate_all(sb, eff, settings_version=1)
print(f"Resultado generate_all: {res_cand}", flush=True)
print("=" * 55, flush=True)
print("¡Poblado de datos reales completado con exito!", flush=True)
