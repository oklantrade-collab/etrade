import asyncio
import json
from app.api.portfolio import get_global_portfolio

async def check_investments():
    res = await get_global_portfolio()
    print("--- CRYPTO ---")
    for s in res['markets']['crypto']['symbols']:
        if s['status'] == 'active':
            print(f"{s['symbol']}: Notional=${s['quantity']*s['avg_entry_price']:.2f}, Capital=${s['total_investment']:.2f}")
    
    print("\n--- FOREX ---")
    for s in res['markets']['forex']['symbols']:
        if s['status'] == 'active':
            notional = s['quantity'] * 100000 * s['avg_entry_price']
            print(f"{s['symbol']}: Notional=${notional:.2f}, Capital=${s['total_investment']:.2f}")
            
    print("\n--- STOCKS ---")
    for s in res['markets']['stocks']['symbols']:
        if s['status'] == 'active':
            print(f"{s['symbol']}: Notional=${s['quantity']*s['avg_entry_price']:.2f}, Capital=${s['total_investment']:.2f}")

if __name__ == "__main__":
    asyncio.run(check_investments())
