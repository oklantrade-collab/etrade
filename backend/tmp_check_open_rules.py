from app.core.supabase_client import get_supabase
import asyncio

async def check_open_positions_rules():
    sb = get_supabase()
    res = sb.table('positions').select('id, symbol, rule_code, rule_entry').eq('status', 'open').execute()
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, RuleCode: {p['rule_code']}, RuleEntry: {p['rule_entry']}")

if __name__ == "__main__":
    asyncio.run(check_open_positions_rules())
