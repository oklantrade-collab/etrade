import os
import asyncio
from dotenv import load_dotenv
from app.api.dashboard import get_dashboard_summary

load_dotenv('.env')

async def check_dash():
    res = await get_dashboard_summary()
    btc = res['symbols']['BTCUSDT']['position']
    eth = res['symbols']['ETHUSDT']['position']
    print(f"BTC: P&L ${btc['unrealized_pnl_usd']} ({btc['unrealized_pnl_pct']}%)")
    print(f"ETH: P&L ${eth['unrealized_pnl_usd']} ({eth['unrealized_pnl_pct']}%)")

if __name__ == "__main__":
    asyncio.run(check_dash())
