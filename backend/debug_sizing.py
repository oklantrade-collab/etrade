import asyncio
from app.core.supabase_client import get_supabase
from app.core.position_sizing import calculate_position_size

async def check():
    sb = get_supabase()
    
    # We will simulate for BTC, ETH, SOL, ADA with some dummy entry/sl prices.
    # The prices in the screenshot:
    # BTC entry: 75468.80
    # ETH entry: 2056.81
    # SOL entry: 84.19
    # ADA entry: 0.2415
    
    # Let's see what calculate_position_size returns for Forex
    res = calculate_position_size(
        symbol='EURUSD',
        entry_price=1.1610,
        sl_price=1.1550,
        market_type='forex_futures',
        trade_number=1,
        regime='riesgo_medio',
        supabase=sb
    )
    print("Simulated forex position sizing:")
    if res:
        for k, v in res.items():
            print(f"  {k}: {v}")
    else:
        print("Result is None (sizing failed!)")

    # Let's fetch the actual open positions to see their notional and margin
    pos = sb.table('positions').select('*').eq('status', 'OPEN').execute()
    print("\nActual OPEN positions from DB:")
    for p in pos.data:
        print(f"Symbol: {p['symbol']}, entry: {p['entry_price']}, sl: {p.get('sl_price')}, size: {p['position_size']}, margin: {p.get('margin_used')}, notional: {float(p['entry_price']) * float(p['position_size'])}")

if __name__ == "__main__":
    asyncio.run(check())
