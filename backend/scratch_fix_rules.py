import json
import os

with open("bb_rules.json", "r") as f:
    rules = json.load(f)

for r in rules:
    if r.get('direction') == 'long':
        new_conds = []
        for c in r.get('conditions', []):
            if c.get('indicator') in ['mtf_4h_trend', 'mtf_1d_trend'] and c.get('value') == 'short':
                continue # remove the contradictory short condition
            new_conds.append(c)
        r['conditions'] = new_conds

with open("bb_rules.json", "w") as f:
    json.dump(rules, f, indent=4)

print("Fixed conflicting MTF conditions in Long rules.")
