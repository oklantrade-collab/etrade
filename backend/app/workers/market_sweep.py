import yfinance as yf
from app.core.supabase_client import get_supabase as get_supabase_client
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MarketSweep")

def get_fallback_tickers():
    return [
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "PYPL", 
        "INTC", "CSCO", "PEP", "AVGO", "COST", "TMUS", "QCOM", "TXN", "AMAT", "SBUX",
        "TQQQ", "SQQQ", "SOXL", "SOXS", "LABU", "LABD", "MARA", "RIOT", "COIN", "AIXI",
        "NOK", "TSLL", "TZA", "SQ", "PLTR", "SOFI", "UBER", "LYFT", "HOOD", "AFRM",
        "OPEN", "UPST", "VALE", "PBR", "NIO", "XPEV", "LI", "JD", "BABA", "PDD"
    ]

def run_market_sweep(price_limit=200, volume_limit=1000000):
    tickers = get_fallback_tickers()
    logger.info(f"Escaneando {len(tickers)} líderes de volumen.")
    
    final_candidates = []
    today = datetime.now().date().isoformat()
    
    # Descarga directa sin parámetros conflictivos
    for ticker in tickers:
        try:
            logger.info(f"Analizando: {ticker}")
            t = yf.Ticker(ticker)
            df = t.history(period="1d")
            if df.empty: continue
            
            price = float(df['Close'].iloc[-1])
            volume = int(df['Volume'].iloc[-1])
            
            if 0.5 <= price <= price_limit and volume >= volume_limit:
                final_candidates.append({
                    "ticker": ticker,
                    "date": today,
                    "hard_filter_pass": True,
                    "catalyst_type": "Sweep",
                    "market_regime": "bullish"
                })
        except Exception as e:
            logger.error(f"Error con {ticker}: {e}")

    logger.info(f"Candidatos encontrados: {len(final_candidates)}")
    save_to_watchlist(final_candidates)

def save_to_watchlist(candidates):
    if not candidates: return
    supabase = get_supabase_client()
    today = datetime.now().date().isoformat()
    supabase.table("watchlist_daily").delete().eq("date", today).execute()
    for i in range(0, len(candidates), 100):
        batch = candidates[i:i+100]
        supabase.table("watchlist_daily").insert(batch).execute()
    logger.info(f"EXITO: {len(candidates)} empresas cargadas.")

if __name__ == "__main__":
    run_market_sweep()
