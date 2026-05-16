import asyncio
import json
from app.core.supabase_client import get_supabase

async def setup_rules():
    sb = get_supabase()
    
    notes_data = {
        "bb_expanding_required": True,
        "ema_alignment_required": True,
        "ia_min": 0,
        "tech_score_min": 0,
        "fundamental_score_min": 0,
        "rvol_min": 2.0
    }
    
    rule = {
        "rule_code": "BOLLINGER_EXPLOSION",
        "name": "Bollinger Explosion Breakout",
        "direction": "buy",
        "order_type": "market",
        "enabled": True,
        "priority": 1,
        "group_name": "hot",
        "notes": json.dumps(notes_data)
    }
    
    # Try to upsert
    try:
        res = sb.table("stocks_rules").upsert(rule, on_conflict="rule_code").execute()
        print(f"Rule BOLLINGER_EXPLOSION configured: {res.data}")
    except Exception as e:
        print(f"Error setting up rule: {e}")

if __name__ == "__main__":
    asyncio.run(setup_rules())
