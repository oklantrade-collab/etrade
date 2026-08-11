import os
import sys
import dotenv
import json
from datetime import datetime, timezone

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table('market_snapshot').select('*').in_('symbol', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']).execute()
print("CRYPTO AND FOREX SNAPSHOT STATUS:")
now = datetime.now(timezone.utc)
for r in res.data or []:
    ts_str = r.get('updated_at')
    print(f"Symbol: {r.get('symbol')}, Price: {r.get('price')}, UpdatedAt: {ts_str}")
