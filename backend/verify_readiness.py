import asyncio, os
from dotenv import load_dotenv
from supabase import create_client
from app.core.readiness import check_real_mode_readiness

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env")
    exit(1)

sb = create_client(url, key)

async def main():
    result = await check_real_mode_readiness(sb)
    print(f"all_criteria_met: {result['all_criteria_met']}")
    print(f"pending: {result['pending']}")
    for k, v in result['criteria'].items():
        status = "OK" if v['met'] else "PENDIENTE"
        print(f"  [{status}] {k}: valor={v['value']} requerido={v['required']}")

if __name__ == "__main__":
    asyncio.run(main())
