import asyncio
from app.core.supabase_client import get_supabase
import json

async def main():
    sb = get_supabase()
    res = sb.table("trading_rules").select("rule_code, name, direction, market_type, enabled, conditions, priority, regime_allowed").ilike("rule_code", "Bb%").execute()
    with open("bb_rules.json", "w", encoding="utf-8") as f:
        json.dump(res.data, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
