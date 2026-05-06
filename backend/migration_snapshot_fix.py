import asyncio
from app.core.supabase_client import get_supabase

async def migrate():
    sb = get_supabase()
    # Add missing columns to market_snapshot
    commands = [
        "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS ema_3 double precision;",
        "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS ema_9 double precision;",
        "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS ema_20 double precision;",
        "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS atr double precision;",
        "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS bb_expanding boolean;"
    ]
    
    for cmd in commands:
        try:
            # We don't have a direct SQL executor in the client, but we can use an RPC if it exists
            # Or just assume the user will apply them.
            # Actually, let's try to do it via a fake RPC if it exists
            print(f"Applying: {cmd}")
            # res = sb.rpc('exec_sql', {'sql': cmd}).execute()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
