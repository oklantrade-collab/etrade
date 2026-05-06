import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_risk_config

async def check_risk_config():
    cfg = get_risk_config()
    print(f"Risk Config: {cfg}")

if __name__ == "__main__":
    asyncio.run(check_risk_config())
