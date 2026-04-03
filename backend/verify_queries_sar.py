from app.core.supabase_client import get_supabase
import asyncio

async def verify_queries():
    sb = get_supabase()
    
    # QUERY 1: market_snapshot
    res1 = sb.table('market_snapshot').select('symbol, price, sar_4h, sar_trend_4h, sar_phase, updated_at').neq('symbol', 'TEST').order('symbol').execute()
    print("--- OUTPUT QUERY 1 — market_snapshot ---")
    if res1.data:
        for row in res1.data:
            print(f"Symbol: {row['symbol']}, Price: {row['price']}, SAR 4h: {row['sar_4h']}, Trend: {row['sar_trend_4h']}, Phase: {row['sar_phase']}, Updated: {row['updated_at']}")
    else:
        print("No data found in market_snapshot.")
    
    print("\n" + "="*40 + "\n")
    
    # QUERY 2: pilot_diagnostics
    res2 = sb.table('pilot_diagnostics').select('symbol, direction_evaluated, mtf_score_logged, timestamp').eq('cycle_type', '15m').order('timestamp', desc=True).limit(8).execute()
    print("--- OUTPUT QUERY 2 — pilot_diagnostics (15m cycles) ---")
    if res2.data:
        for row in res2.data:
            print(f"Symbol: {row['symbol']}, Direction Evaluated: {row['direction_evaluated']}, MTF Score: {row['mtf_score_logged']}, Timestamp: {row['timestamp']}")
    else:
        print("No diagnostics found.")

if __name__ == "__main__":
    asyncio.run(verify_queries())
