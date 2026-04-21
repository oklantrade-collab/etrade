import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def dump_all():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').execute()
    with open('all_forex_positions.json', 'w') as f:
        json.dump(res.data, f, indent=2)
    print(f"Dumped {len(res.data)} positions to all_forex_positions.json")

if __name__ == "__main__":
    asyncio.run(dump_all())
