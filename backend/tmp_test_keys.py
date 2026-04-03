from app.core.supabase_client import get_supabase
import asyncio

async def test_pos_keys():
    sb = get_supabase()
    res = sb.table('positions').select('*').eq('status', 'open').execute()
    if res.data:
        pos = res.data[0]
        print(f"Keys: {pos.keys()}")
        print(f"rule_code: {pos.get('rule_code')}")
        print(f"rule_entry: {pos.get('rule_entry')}")

if __name__ == "__main__":
    asyncio.run(test_pos_keys())
