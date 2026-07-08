import sys
import os
import json
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.core.supabase_client import get_supabase

def insert_dip_rules():
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Check if they exist first
    res = sb.table('stocks_rules').select('*').in_('rule_code', ['HOT_DIP_BUY', 'PRO_DIP_BUY']).execute()
    existing = [r['rule_code'] for r in (res.data or [])]
    
    rules_to_insert = []
    
    if 'HOT_DIP_BUY' not in existing:
        rules_to_insert.append({
            "rule_code": "HOT_DIP_BUY",
            "name": "HOT DIP: Retroceso EMA20, SAR o Pine (15m)",
            "group_name": "hot_by_volume",
            "direction": "buy",
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "rvol_min": 1.0,
            "ia_min": 0,
            "tech_score_min": 0,
            "notes": "Compra si EMA9>EMA20>EMA50 y ocurre uno de: LOW<=EMA20, SAR alcista inicia, o PineBuy inicia.",
            "created_at": now_iso,
            "updated_at": now_iso
        })
        
    if 'PRO_DIP_BUY' not in existing:
        rules_to_insert.append({
            "rule_code": "PRO_DIP_BUY",
            "name": "PRO DIP: Retroceso EMA20, SAR o Pine (15m)",
            "group_name": "inversiones_pro",
            "direction": "buy",
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "rvol_min": 1.0,
            "ia_min": 0,
            "tech_score_min": 0,
            "notes": "Compra si EMA9>EMA20>EMA50 y ocurre uno de: LOW<=EMA20, SAR alcista inicia, o PineBuy inicia.",
            "created_at": now_iso,
            "updated_at": now_iso
        })
        
    if rules_to_insert:
        print(f"Inserting rules: {[r['rule_code'] for r in rules_to_insert]}")
        res = sb.table('stocks_rules').insert(rules_to_insert).execute()
        print("Insert successful.")
    else:
        print("Rules already exist.")
        
    # Mark task as completed
    with open("C:/Users/jyups/.gemini/antigravity/brain/d7742b01-19b1-4c79-bca2-b77ea1235c50/task.md", "r") as f:
        content = f.read()
    content = content.replace("- [ ] Insert `HOT_DIP_BUY`", "- [x] Insert `HOT_DIP_BUY`")
    content = content.replace("- [ ] Update `app/stocks/stocks_rule_engine.py`", "- [x] Update `app/stocks/stocks_rule_engine.py`")
    content = content.replace("- [ ] Update `app/workers/stocks_scheduler.py`", "- [x] Update `app/workers/stocks_scheduler.py`")
    
    with open("C:/Users/jyups/.gemini/antigravity/brain/d7742b01-19b1-4c79-bca2-b77ea1235c50/task.md", "w") as f:
        f.write(content)

if __name__ == "__main__":
    insert_dip_rules()
