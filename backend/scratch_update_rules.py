import json
import os

with open("bb_rules.json", "r") as f:
    rules = json.load(f)

new_rules = []

for r in rules:
    # Modify the short rule
    short_rule = dict(r)
    if short_rule['direction'] == 'short':
        # Ensure conditions exist
        if 'conditions' not in short_rule:
            short_rule['conditions'] = []
            
        # Check if MTF conditions already exist
        has_mtf_4h = any(c.get('indicator') == 'mtf_4h_trend' for c in short_rule['conditions'])
        if not has_mtf_4h:
            short_rule['conditions'].append({
                "indicator": "mtf_4h_trend",
                "operator": "==",
                "value": "short"
            })
            
        has_mtf_1d = any(c.get('indicator') == 'mtf_1d_trend' for c in short_rule['conditions'])
        if not has_mtf_1d:
            short_rule['conditions'].append({
                "indicator": "mtf_1d_trend",
                "operator": "==",
                "value": "short"
            })
        
        new_rules.append(short_rule)

        # Create the LONG counterpart
        long_rule = dict(r)
        # Modify ID to avoid collision (e.g. add 1000)
        long_rule['id'] = long_rule.get('id', 0) + 1000
        long_rule['rule_code'] = long_rule['rule_code'] + "_Long"
        long_rule['direction'] = "long"
        long_rule['name'] = long_rule['name'].replace("SHORT", "LONG").replace("Short", "Long")
        
        # Deep copy conditions
        import copy
        new_conds = copy.deepcopy(r.get('conditions', []))
        
        # Flip specific conditions for LONG
        for c in new_conds:
            ind = c.get('indicator', '')
            val = c.get('value')
            op = c.get('operator')
            
            # Flip Bollinger touches
            if ind == "price_touched_upper_6":
                c['indicator'] = "price_touched_lower_5_6"
            elif ind == "price_touched_lower_5_6":
                c['indicator'] = "price_touched_upper_6"
                
            # Flip reversal confirmations
            if ind == "reversal_confirmation_short":
                c['indicator'] = "reversal_confirmation_long"
            elif ind == "reversal_confirmation_long":
                c['indicator'] = "reversal_confirmation_short"
                
            # Flip SAR
            if ind == "sar_15m_ok_short":
                c['indicator'] = "sar_15m_ok_long"
                
            # Flip pullback checks
            if ind == "pullback_short":
                c['indicator'] = "pullback_long"
                
            if ind == "strong_contratrend_short":
                c['indicator'] = "strong_contratrend_long"

            if ind == "di_cross_bearish":
                c['indicator'] = "di_cross_bullish"
                
            if ind == "ema9_below_ema20":
                c['indicator'] = "ema9_above_ema20"
                
            if ind == "ema3_below_ema9":
                c['indicator'] = "ema3_above_ema9"
                
            if ind == "ema20_phase" and val == "nivel_1_short":
                c['value'] = "nivel_1_long"

            if ind == "ema20_angle" and op == "<" and val == 0:
                c['operator'] = ">"
                c['value'] = 0

            if ind == "ema20_angle" and op == "<=":
                c['operator'] = ">="

            if ind == "macd_sell_signal":
                c['indicator'] = "macd_buy_signal"

            if ind == "rsi_14" and op == ">":
                c['operator'] = "<"
                if isinstance(val, (int, float)) and val > 50:
                    c['value'] = 100 - val
                    
        # Add LONG MTF trends
        new_conds.append({
            "indicator": "mtf_4h_trend",
            "operator": "==",
            "value": "long"
        })
        new_conds.append({
            "indicator": "mtf_1d_trend",
            "operator": "==",
            "value": "long"
        })
        
        long_rule['conditions'] = new_conds
        new_rules.append(long_rule)
        
    else:
        new_rules.append(r)

with open("bb_rules.json", "w") as f:
    json.dump(new_rules, f, indent=4)

print("Added MTF filters and LONG rule variants!")
