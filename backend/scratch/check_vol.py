import asyncio
from app.core.supabase_client import get_supabase
import json

async def run():
    sb = get_supabase()
    res = sb.table('technical_scores').select('ticker, timestamp, signals_json').in_('ticker', ['NWG', 'MRNA']).order('timestamp', desc=True).limit(4).execute()
    for r in res.data:
        sigs = json.loads(r['signals_json']) if isinstance(r['signals_json'], str) else r['signals_json']
        print(f"{r['ticker']} ({r['timestamp']}): vol={sigs.get('volume', 'MISSING')} price={sigs.get('price')} raw={sigs.get('raw_vol')}")

if __name__ == "__main__":
    asyncio.run(run())
