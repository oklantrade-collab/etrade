import asyncio
from app.core.supabase_client import get_supabase
import json

async def check_missing_ids():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('*').in_('id', [63, 64]).execute()
    print(f"RES: {json.dumps(res.data, indent=2)}")

if __name__ == "__main__":
    asyncio.run(check_missing_ids())
