import asyncio
from app.core.supabase_client import get_supabase

async def check_confidence():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('rule_code, confidence').limit(5).execute()
    for r in res.data:
        print(f"Code: {r['rule_code']} | Confidence: {r['confidence']} ({type(r['confidence'])})")

if __name__ == "__main__":
    asyncio.run(check_confidence())
