import os
import sys
import asyncio
from dotenv import load_dotenv
from supabase import create_client

# Force utf-8 output
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def check():
    print("=== ALL TRADING RULES ===")
    res = sb.table('trading_rules').select('id, rule_code, name, enabled, current').execute()
    for row in sorted(res.data, key=lambda x: x['id']):
        print(f"ID: {row['id']} | Code: {row['rule_code']} | Name: {row['name']} | Enabled: {row['enabled']} | Current: {row['current']}")

if __name__ == '__main__':
    asyncio.run(check())
