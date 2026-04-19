import asyncio
import logging
from datetime import datetime
from app.core.supabase_client import get_supabase as get_supabase_client
from app.stocks.universe_builder import UniverseBuilder

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

async def run_market_sweep(price_limit=200, volume_limit=1000000):
    """
    Realiza un barrido profundo del mercado usando UniverseBuilder (IB -> Yahoo -> Fallback).
    Configurado para correr justo después del cierre (16:01 ET).
    """
    logger.info("═══ INICIANDO MARKET SWEEP DINÁMICO (Capa 0) ═══")
    
    try:
        builder = UniverseBuilder()
        # Intentamos el escaneo dinámico (usa IB si está el PC prendido, si no Yahoo)
        candidates = await builder.build_daily_watchlist(
            max_price=price_limit,
            min_volume=volume_limit,
            max_results=50
        )
        
        if candidates and len(candidates) > 0:
            logger.info(f"✅ EXITO: {len(candidates)} candidatos dinámicos encontrados y guardados.")
            return

        logger.warning("⚠️ Scanner dinámico no devolvió resultados. Iniciando barrido de lista fija...")
        
    except Exception as e:
        logger.error(f"❌ Error en UniverseBuilder: {e}. Usando lista fija de respaldo.")

    # FALLBACK: Si todo lo anterior falla, usamos la lista de líderes históricos
    await run_fallback_sweep(price_limit, volume_limit)

async def run_fallback_sweep(price_limit, volume_limit):
    import yfinance as yf
    tickers = get_fallback_tickers()
    final_candidates = []
    today = datetime.now().date().isoformat()
    
    for ticker in tickers:
        try:
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
                    "catalyst_type": "Sweep_Fallback",
                    "market_regime": "bullish"
                })
        except Exception as e:
            logger.error(f"Error con {ticker}: {e}")

    if final_candidates:
        save_to_watchlist(final_candidates)
        logger.info(f"✅ EXITO: {len(final_candidates)} empresas de la lista fija cargadas.")

def save_to_watchlist(candidates):
    if not candidates: return
    supabase = get_supabase_client()
    today = datetime.now().date().isoformat()
    supabase.table("watchlist_daily").delete().eq("date", today).execute()
    for i in range(0, len(candidates), 100):
        batch = candidates[i:i+100]
        supabase.table("watchlist_daily").insert(batch).execute()

if __name__ == "__main__":
    asyncio.run(run_market_sweep())
