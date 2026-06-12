import sys
import os
import asyncio
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.supabase_client import get_supabase
from app.core.market_hours import get_nyc_now

async def check_tech_scores():
    sb = get_supabase()
    today_str = get_nyc_now().date().isoformat()
    res = sb.table("technical_scores").select("*").gte("timestamp", today_str).order('timestamp', desc=True).limit(200).execute()
    print(f"Tech scores today ({today_str}): {len(res.data)} items")
    if not res.data:
        res = sb.table("technical_scores").select("*").order('timestamp', desc=True).limit(200).execute()
        print(f"Fallback tech scores: {len(res.data)} items")
    
    if res.data:
        # Check what fields are in the first item
        item = res.data[0]
        # print keys
        print("Keys:", item.keys())
        # print signals_json keys
        sigs = item.get("signals_json")
        if isinstance(sigs, str):
            try: sigs = json.loads(sigs)
            except: sigs = {}
        if sigs:
            print("Signals keys:", sigs.keys())
        
        # Check how many have trade_type
        types = [i.get("trade_type") or (json.loads(i.get("signals_json") or "{}")).get("trade_type") for i in res.data]
        valid = [t for t in types if t]
        print(f"Items with trade_type: {len(valid)}")

if __name__ == "__main__":
    asyncio.run(check_tech_scores())
