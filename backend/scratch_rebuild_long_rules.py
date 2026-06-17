import json

def flip_operator(op, val):
    if op == '<=': return '>='
    if op == '>=': return '<='
    if op == '<': return '>'
    if op == '>': return '<'
    return op

with open("bb_rules.json", "r") as f:
    all_rules = json.load(f)

# Keep only short rules
short_rules = [r for r in all_rules if r['direction'] == 'short']

new_rules = []
for sr in short_rules:
    new_rules.append(sr) # keep original
    
    # create long version
    lr = dict(sr)
    lr['id'] = lr.get('id', 0) + 1000
    lr['direction'] = 'long'
    lr['rule_code'] = lr['rule_code'].replace('_Short', '').replace('_Long', '') + '_Long'
    lr['name'] = lr['name'].replace('SHORT', 'LONG').replace('Short', 'Long').replace('short', 'long')
    
    conds_str = json.dumps(sr.get('conditions', []))
    
    # String replacements
    conds_str = conds_str.replace('short', 'long')
    conds_str = conds_str.replace('_below_', '_above_')
    conds_str = conds_str.replace('upper', 'TEMP_UPPER')
    conds_str = conds_str.replace('lower', 'upper')
    conds_str = conds_str.replace('TEMP_UPPER', 'lower')
    conds_str = conds_str.replace('bearish', 'bullish')
    conds_str = conds_str.replace('macd_sell', 'macd_buy')
    conds_str = conds_str.replace('not_in_floor', 'not_in_ceiling')
    conds_str = conds_str.replace('adx_floor', 'adx_ceiling') # wait, adx floor ok might be the same? adx has no floor/ceiling direction in terms of trend.
    conds_str = conds_str.replace('adx_ceiling', 'adx_floor') # revert adx_floor
    conds_str = conds_str.replace('bottom', 'TEMP_BOTTOM')
    conds_str = conds_str.replace('top', 'bottom')
    conds_str = conds_str.replace('TEMP_BOTTOM', 'top')
    
    lr['conditions'] = json.loads(conds_str)
    
    # Logic operator flips
    for c in lr['conditions']:
        ind = c.get('indicator', '')
        # Only flip operators for certain numeric indicators like angles, ADX, RSI?
        # ADX > 40 should remain > 40!
        if 'angle' in ind:
            if c.get('operator') == '<=' and c.get('value') == 0:
                c['operator'] = '>='
            elif c.get('operator') == '<' and c.get('value') == 0:
                c['operator'] = '>'
            elif c.get('operator') == '>=' and c.get('value') == 0:
                c['operator'] = '<='
            elif c.get('operator') == '>' and c.get('value') == 0:
                c['operator'] = '<'
        
        # Di margin is abs diff? Actually di_margin is minus_di - plus_di.
        # So for long we want plus_di - minus_di? 
        # In rule_engine we have "di_margin": minus_di - plus_di. 
        # So if di_margin > 10 (short), for long we want di_margin < -10!
        if ind == 'di_margin':
            if c.get('operator') == '>':
                c['operator'] = '<'
                c['value'] = -c['value']
                
        # RSI
        if ind == 'rsi_14':
            if c.get('operator') == '>':
                c['operator'] = '<'
                c['value'] = 100 - c.get('value', 50)
                
    new_rules.append(lr)

with open("bb_rules.json", "w") as f:
    json.dump(new_rules, f, indent=4)
print("Re-generated LONG rules correctly.")
