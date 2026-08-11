import json
from collections import defaultdict

data = json.load(open("all_pos.json"))

def is_crypto(symbol):
    if not symbol: return False
    return symbol.endswith('USDT')

stats = defaultdict(lambda: {"count": 0, "pnl_fiat": 0.0, "total_invested": 0.0, "erep_count": 0})

for pos in data:
    if not is_crypto(pos.get("symbol")):
        continue
        
    if pos.get("status") != "closed":
        continue
        
    rule = pos.get("rule_code") or "Unknown"
    pnl_fiat = float(pos.get("realized_pnl") or 0.0)
    
    entry_price = float(pos.get("avg_entry_price") or pos.get("entry_price") or 0.0)
    size = float(pos.get("size") or 0.0)
    
    cost = entry_price * size

    erep_phase = int(pos.get("erep_phase") or 0)
    erep_active = pos.get("erep_active")

    stats[rule]["count"] += 1
    stats[rule]["pnl_fiat"] += pnl_fiat
    stats[rule]["total_invested"] += cost
    
    if erep_phase > 0 or erep_active:
        stats[rule]["erep_count"] += 1

# Calculate profitability based on total investment
for rule in stats:
    if stats[rule]["total_invested"] > 0:
        stats[rule]["roi_pct"] = (stats[rule]["pnl_fiat"] / stats[rule]["total_invested"]) * 100
    else:
        stats[rule]["roi_pct"] = 0.0

sorted_stats = sorted(stats.items(), key=lambda x: x[1]["pnl_fiat"], reverse=True)

print("| Estrategia | Operaciones | PNL ($) | Rentabilidad Global (%) | Ops en EREP |")
print("|:---:|:---:|:---:|:---:|:---:|")
for rule, s in sorted_stats:
    print(f"| **{rule}** | {s['count']} | ${s['pnl_fiat']:.2f} | {s['roi_pct']:.4f}% | {s['erep_count']} |")
