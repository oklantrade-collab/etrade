from app.core.supabase_client import get_supabase
from datetime import datetime

def debug_data():
    sb = get_supabase()
    today = datetime.now().date().isoformat()
    print(f"Checking data for {today}...")
    
    # 1. Watchlist
    wl = sb.table("watchlist_daily").select("ticker").eq("date", today).execute()
    print(f"Watchlist today: {len(wl.data)} tickers")
    
    # 2. Opportunities
    opps = sb.table("trade_opportunities").select("ticker").eq("status", "active").execute()
    print(f"Active Opportunities: {len(opps.data)}")
    
    # 3. Technical Scores
    scores = sb.table("technical_scores").select("ticker").order("timestamp", desc=True).limit(5).execute()
    print(f"Latest scores: {[s['ticker'] for s in scores.data]}")

if __name__ == "__main__":
    try:
        debug_data()
    except Exception as e:
        print(f"Error: {e}")
