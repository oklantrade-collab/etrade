import asyncio
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    # 1. Ordenes recientes o errores
    res_orders = sb.table('system_logs').select('*').order('created_at', desc=True).limit(10).execute()
    print("--- ULTIMOS LOGS DEL BOT ---")
    for row in res_orders.data:
        print(f"[{row['level']}] {row.get('module', 'sys')}: {row.get('message', '')}")
        
    # 2. Señales
    res_sig = sb.table('trade_signals').select('*').order('created_at', desc=True).limit(2).execute()
    print("--- ULTIMAS SEÑALES ---")
    for row in res_sig.data:
        print(f"[{row['symbol']}] {row['rule_code']} - Executed: {row.get('executed')}")

asyncio.run(check())
