import os, sys
from dotenv import load_dotenv
load_dotenv('.env')
from app.core.supabase_client import get_supabase
from app.options.worker import _load_effective
from app.options.candidates import generate_all

sb = get_supabase()
eff = _load_effective(sb)

print(f"Running generate_all with min_score={eff.get('min_score')}, spread_width_min={eff.get('spread_width_min')}, allow_delayed={eff.get('allow_delayed_data')}...")
res = generate_all(sb, eff, settings_version=2)
print("Candidates generated:", res["candidates"])
print("Portfolio selection:", res["portfolio_selection"])

cands = sb.table("opt_candidates").select("id, underlying_id, strategy_type, eligibility_status, score, rank_global, entry_debit, qty, max_loss_total, ev_view_net, opt_underlyings(symbol)").execute().data or []
statuses = {}
for c in cands:
    st_val = c.get("eligibility_status")
    statuses[st_val] = statuses.get(st_val, 0) + 1
print("DB status breakdown:", statuses)

eligible = [c for c in cands if c.get("eligibility_status") in ("eligible", "selected")]
print("Eligible/Selected count:", len(eligible))
for e in eligible:
    sym = (e.get("opt_underlyings") or {}).get("symbol")
    print(f"  #{e.get('rank_global')} {sym} {e['strategy_type']} debit={e['entry_debit']} qty={e['qty']} max_loss={e['max_loss_total']} ev={e['ev_view_net']} score={e['score']} [{e['eligibility_status']}]")
