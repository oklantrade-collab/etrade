import asyncio
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error

async def sync_orphaned_positions():
    sb = get_supabase()
    today = "2026-05-07"
    
    # 1. Obtener posiciones cerradas hoy
    res = sb.table("stocks_positions").select("*").eq("status", "closed").gte("updated_at", today).execute()
    closed_positions = res.data or []
    
    if not closed_positions:
        print("No se encontraron posiciones cerradas hoy para sincronizar.")
        return

    print(f"Encontradas {len(closed_positions)} posiciones cerradas hoy. Verificando journal...")
    
    # 2. Obtener tickers ya en el journal hoy para evitar duplicados
    journal_res = sb.table("trades_journal").select("ticker, exit_date").gte("exit_date", today).execute()
    journal_tickers = {r["ticker"] for r in (journal_res.data or [])}
    
    synced_count = 0
    for pos in closed_positions:
        ticker = pos["ticker"]
        
        # Evitar duplicar si ya se registró (por si acaso se registró hace unos segundos)
        if ticker in journal_tickers:
            print(f"Skipping {ticker}: ya existe en el journal hoy.")
            continue
            
        try:
            # Preparar entrada para el journal
            avg_price = float(pos.get("avg_price") or pos.get("entry_price") or 0)
            exit_price = float(pos.get("exit_price") or pos.get("current_price") or avg_price)
            shares = int(float(pos.get("shares") or 0))
            pnl_usd = float(pos.get("unrealized_pnl") or 0)
            pnl_pct = float(pos.get("unrealized_pnl_pct") or 0)
            
            journal_entry = {
                "ticker": ticker,
                "shares": shares,
                "entry_price": avg_price,
                "exit_price": exit_price,
                "entry_date": pos.get("first_buy_at") or pos.get("entry_date"),
                "exit_date": pos.get("updated_at"),
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "result": "win" if pnl_usd > 0 else "loss",
                "exit_reason": pos.get("close_reason") or "MANUAL_SYNC",
                "trade_type": pos.get("strategy") or pos.get("rule_code") or "V5_INDUSTRIAL"
            }
            
            sb.table("trades_journal").insert(journal_entry).execute()
            print(f"SUCCESS: {ticker} sincronizado al historial.")
            synced_count += 1
        except Exception as e:
            print(f"ERROR sincronizando {ticker}: {e}")

    print(f"Proceso finalizado. {synced_count} posiciones sincronizadas.")

if __name__ == "__main__":
    asyncio.run(sync_orphaned_positions())
