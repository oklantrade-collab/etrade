import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
load_dotenv(".env")

from app.core.supabase_client import get_supabase
from app.options.worker import _load_effective
from app.options.candidates import generate_all
from app.options import settings_defaults as sd

sb = get_supabase()
eff = _load_effective(sb)

# Sincronizar nuevos limites efectivos
defaults = sd.default_settings()
eff.update({
    "capital_usd": defaults["capital_usd"],
    "max_risk_per_trade_usd": defaults["max_risk_per_trade_usd"],
    "max_open_risk_usd": defaults["max_open_risk_usd"],
    "spread_width_max": defaults["spread_width_max"],
    "max_underlyings": defaults["max_underlyings"],
})

print(f"Generando oportunidades con: max_risk=${eff['max_risk_per_trade_usd']} | spread_width_max={eff['spread_width_max']}...", flush=True)

res = generate_all(sb, eff, settings_version=1)
print(f"Resultado generate_all: {res}", flush=True)

# Verificar candidatas en BD
cands = sb.table("opt_candidates").select("id, strategy_type, direction, eligibility_status, opt_underlyings(symbol)").limit(20).execute().data
print(f"\nTotal candidatas encontradas en DB (primeras 20): {len(cands)}")
for c in cands:
    sym = (c.get("opt_underlyings") or {}).get("symbol")
    print(f"  #{c['id']} {sym} {c['strategy_type']} {c['direction']} [{c['eligibility_status']}]")
