
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def update_config_and_rules():
    sb = get_supabase()
    
    # 1. Update technical_score_threshold to 30
    print("Updating technical_score_threshold to 30...")
    res_cfg = sb.table("stocks_config").update({"value": "30"}).eq("key", "technical_score_threshold").execute()
    print("Config updated.")

    # 2. Add 'lateral' to movements_allowed for all active buy rules
    print("Updating rules to allow 'lateral' movement...")
    res_rules = sb.table("stocks_rules").select("*").eq("enabled", True).eq("direction", "buy").execute()
    
    if res_rules.data:
        for rule in res_rules.data:
            movements = rule.get("movements_allowed") or []
            if "lateral" not in movements:
                movements.append("lateral")
                sb.table("stocks_rules").update({"movements_allowed": movements}).eq("id", rule["id"]).execute()
                print(f"Updated rule {rule['rule_code']}: movements_allowed={movements}")
            else:
                print(f"Rule {rule['rule_code']} already allows 'lateral'.")
    else:
        print("No active buy rules found.")

if __name__ == "__main__":
    update_config_and_rules()
