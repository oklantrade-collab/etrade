import asyncio
import json
from app.core.supabase_client import get_supabase
from app.data.yfinance_provider import YFinanceProvider
from app.analysis.stocks_indicators import calculate_stock_indicators
from app.stocks.apex_score import calculate_apex_score

async def run():
    sb = get_supabase()
    provider = YFinanceProvider()
    ticker = "ASPI"
    
    # Download data
    df_5m  = await provider.get_ohlcv(ticker, interval="5m",  period="5d")
    df_15m = await provider.get_ohlcv(ticker, interval="15m", period="60d")
    df_4h  = await provider.get_ohlcv(ticker, interval="4h",  period="120d")
    df_1d  = await provider.get_ohlcv(ticker, interval="1d",  period="365d")
    
    # Indicators
    ind_5m  = calculate_stock_indicators(df_5m,  "5m",  ticker)
    ind_15m = calculate_stock_indicators(df_15m, "15m", ticker)
    ind_4h  = calculate_stock_indicators(df_4h,  "4h",  ticker)
    ind_1d  = calculate_stock_indicators(df_1d,  "1d",  ticker)
    
    snap = {**ind_15m["_df"].iloc[-1].to_dict(), **ind_15m}
    snap['price'] = float(df_15m['close'].iloc[-1])
    
    fund_res = sb.table("fundamental_cache").select("*").eq("ticker", ticker).execute()
    fund = fund_res.data[0] if fund_res.data else {}
    
    res = calculate_apex_score(
        ticker=ticker,
        snap=snap,
        fundamental_cache=fund,
        macro={'score': 0, 'sentiment': 'neutral', 'flags': []},
        df_5m=ind_5m["_df"],
        df_15m=ind_15m["_df"],
        df_4h=ind_4h["_df"],
        df_daily=ind_1d["_df"],
        ia_score=5.0
    )
    
    print(json.dumps(res['detail'], indent=2))
    print(f"APEX 1D: {res['apex_score_1d']}")

if __name__ == "__main__":
    asyncio.run(run())
