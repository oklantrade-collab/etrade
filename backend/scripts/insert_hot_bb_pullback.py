import asyncio
import os
import sys

# Add backend to path so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

async def insert_rule():
    sb = get_supabase()
    
    # Check if already exists
    res = sb.table("stocks_rules").select("*").eq("rule_code", "HOT_BB_PULLBACK_5M").execute()
    if res.data:
        print("Rule already exists!")
        return

    rule = {
        "rule_code": "HOT_BB_PULLBACK_5M",
        "name": "HOT — BB Pullback a EMA9 5m",
        "group_name": "inversiones_hot",
        "direction": "buy",
        "order_type": "market",
        "enabled": True,
        "priority": 5,
        "ia_min": 0,
        "tech_score_min": 0,
        "movements_allowed": ["lateral", "ascending"],
        "pine_signal": "",
        "pine_required": False,
        "rvol_min": 0.5,
        "notes": "Compra de retroceso a la EMA9 en 5m inmediatamente después de una ruptura de Bollinger. Requiere tendencia alcista en 15m y soporte confirmado en EMA9.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    sb.table("stocks_rules").insert(rule).execute()
    print("Rule HOT_BB_PULLBACK_5M inserted successfully!")

if __name__ == "__main__":
    asyncio.run(insert_rule())
