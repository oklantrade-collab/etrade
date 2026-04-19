import asyncio
from app.analysis.fundamental_scorer import FundamentalScorer
from app.core.supabase_client import get_supabase
from datetime import date

async def refresh_current_fundamentals():
    sb = get_supabase()
    scorer = FundamentalScorer()
    today = date.today().isoformat()
    
    print("Iniciando actualización de Consensus para los tickers actuales...")
    
    # Obtener tickers de hoy
    res = sb.table("watchlist_daily").select("ticker").eq("date", today).execute()
    tickers = [r["ticker"] for r in res.data]
    
    if not tickers:
        print("No hay tickers hoy para actualizar.")
        return
        
    spy_perf = await scorer.get_spy_performance_6m()
    
    for ticker in tickers:
        print(f"Refrescando {ticker}...")
        try:
            data = await scorer.calculate_score(ticker, spy_perf)
            if data:
                # Actualizar la fila de hoy con el nuevo score y el rating
                sb.table("watchlist_daily").update({
                    "fundamental_score": data["fundamental_score"],
                    "analyst_rating": data["analyst_rating"]
                }).eq("ticker", ticker).eq("date", today).execute()
        except Exception as e:
            print(f"Error en {ticker}: {e}")

    print("✅ Actualización completada.")

if __name__ == "__main__":
    asyncio.run(refresh_current_fundamentals())
