import sys
import os
import asyncio
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.supabase_client import get_supabase
from app.core.market_hours import get_nyc_now

async def check_filters():
    sb = get_supabase()
    today_str = get_nyc_now().date().isoformat()
    res = sb.table("technical_scores").select("*").gte("timestamp", today_str).order('timestamp', desc=True).limit(200).execute()
    
    items = res.data or []
    print(f"Total items today: {len(items)}")
    
    passed_hot = 0
    passed_pro = 0
    for item in items:
        sigs = item.get("signals_json")
        if isinstance(sigs, str):
            try: sigs = json.loads(sigs)
            except: sigs = {}
        if not sigs: sigs = {}
        
        merged = {**item, **sigs}
        
        price = float(merged.get("price") or 0)
        rvol = float(merged.get("rvol") or 0)
        volume = float(merged.get("volume") or 0)
        
        is_pro = merged.get("fundamental_score", 0) >= 80  # simplistic check
        
        if price <= 50 and rvol >= 0.1 and volume >= 200000:
            passed_hot += 1
        
        if is_pro:
            passed_pro += 1
            
        if passed_hot == 0 and passed_pro == 0 and len(items) > 0 and item == items[0]:
            print(f"Sample item - Price: {price}, Rvol: {rvol}, Volume: {volume}, is_pro: {is_pro}")
            
    print(f"Passed HOT: {passed_hot}")
    print(f"Passed PRO: {passed_pro}")

if __name__ == "__main__":
    asyncio.run(check_filters())
