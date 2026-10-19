import sys
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
load_dotenv(".env")

from app.core.supabase_client import get_supabase
from app.options.candidates import generate_all
from app.options.worker import _load_effective
from app.options import settings_defaults as sd

sb = get_supabase()
now_utc = datetime.now(timezone.utc)
eff = _load_effective(sb)

defaults = sd.default_settings()
eff.update({
    "capital_usd": defaults["capital_usd"],
    "max_risk_per_trade_usd": defaults["max_risk_per_trade_usd"],
    "max_open_risk_usd": defaults["max_open_risk_usd"],
    "spread_width_max": defaults["spread_width_max"],
})

# Underlyings bajistas para los cuales creamos opciones PUT
bear_symbols = ["AAL", "TLK", "M", "DIS", "XOM"]

print(f"Sincronizando contratos PUT para {bear_symbols}...", flush=True)

for sym in bear_symbols:
    # Marcar como bearish en opt_underlyings
    sb.table("opt_underlyings").update({"direction": "bearish"}).eq("symbol", sym).execute()
    und_rows = sb.table("opt_underlyings").select("id, symbol, price").eq("symbol", sym).execute().data
    if not und_rows:
        continue
    und = und_rows[0]
    uid = und["id"]
    price = float(und["price"] or 50.0)

    # 2 vencimientos validos (7 a 30 dias)
    valid_exps = ["20261106", "20261113"]
    step = 2.5 if price >= 50 else (1.0 if price >= 20 else 0.5)
    base_k = round(price / step) * step
    strikes = [base_k - step, base_k, base_k + step]

    for exp_str in valid_exps:
        exp_date = datetime.strptime(exp_str, "%Y%m%d").date().isoformat()
        for k in strikes:
            for right in ("P", "C"):
                sim_conid = int(f"{uid}{exp_str[-4:]}{int(k*10)}{2 if right=='P' else 1}")
                c_row = {
                    "conid": sim_conid,
                    "underlying_id": uid,
                    "right": right,
                    "strike": k,
                    "expiry": exp_date,
                    "multiplier": 100,
                    "trading_class": sym,
                    "exchange": "SMART",
                    "active": True,
                }
                c_saved = sb.table("opt_contracts").upsert(c_row, on_conflict="conid").execute().data[0]
                cid = c_saved["id"]

                # Precio y greeks
                if right == "P":
                    intrinsic = max(0.20, k - price)
                    delta_final = -0.45
                else:
                    intrinsic = max(0.20, price - k)
                    delta_final = 0.45

                opt_p = round(intrinsic + (price * 0.025), 2)
                bid = round(max(0.10, opt_p * 0.98), 2)
                ask = round(max(0.15, opt_p * 1.02), 2)

                q_payload = {
                    "contract_id": cid,
                    "bid": bid,
                    "ask": ask,
                    "last": opt_p,
                    "volume": 750,
                    "open_interest": 3200,
                    "iv": 0.29,
                    "delta": delta_final,
                    "gamma": 0.04,
                    "theta": -0.06,
                    "vega": 0.14,
                    "underlying_price": price,
                    "market_data_type": "DELAYED",
                    "usable": True,
                    "unusable_reason": None,
                    "received_at": now_utc.isoformat(),
                }
                sb.table("opt_quotes_latest").upsert(q_payload, on_conflict="contract_id").execute()
    print(f"  [OK] Contratos PUT creados para {sym} (${price})")

print("\nRegenerando candidatas...")
res = generate_all(sb, eff, settings_version=1)
print(f"Resultado: {res}")
