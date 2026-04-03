from app.core.supabase_client import get_supabase
import asyncio

async def check_null_strategy():
    sb = get_supabase()
    # Buscar posiciones cerradas recientemente con rule_code nulo
    res = sb.table('positions').select('id, symbol, rule_code, rule_entry, status, closed_at')\
        .eq('status', 'closed')\
        .eq('symbol', 'ADAUSDT')\
        .order('closed_at', desc=True)\
        .limit(10).execute()
    
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, RuleCode: {p['rule_code']}, RuleEntry: {p['rule_entry']}, Closed: {p['closed_at']}")

if __name__ == "__main__":
    asyncio.run(check_null_strategy())
