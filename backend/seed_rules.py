import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client
from app.strategy.rule_engine import seed_default_rules

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def main():
    await seed_default_rules(sb)
    print("Reglas sembradas correctamente.")

if __name__ == "__main__":
    asyncio.run(main())
