"""
eTrader DB & Egress Audit Tool
Audita el estado actual de la base de datos Supabase:
- Conteo exacto de filas por tabla (sin transferir datos, usando count='exact', head=True)
- Estado de logs de limpieza (db_cleanup_log)
- Deteccion de acumulacion de datos de alta frecuencia (velas, snapshots, logs)
- Analisis de Egress y consumo de disco para el Plan Free de Supabase (500 MB disco, 5 GB Egress)
"""
import sys
import os

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

# Lista exhaustiva de tablas conocidas en eTrader (Crypto, Forex, Stocks, Options, Sistema)
TABLES = [
    # Sistema y Diagnósticos
    "system_logs",
    "db_cleanup_log",
    "pilot_diagnostics",
    "cron_cycles",
    "system_config",
    "risk_config",
    "user_profiles",
    # Crypto / Forex Trading
    "market_candles",
    "technical_indicators",
    "volume_spikes",
    "trading_signals",
    "pending_orders",
    "orders",
    "trades",
    "positions",
    "strategy_evaluations",
    "market_regime_history",
    "news_sentiment",
    # Stocks
    "stocks_universe",
    "stocks_watchlists",
    "stocks_candidates",
    "stocks_positions",
    "stocks_closed_positions",
    "stocks_price_history",
    "stocks_orders",
    "apex_scores",
    "priority_queue",
    "fundamental_cache",
    "adr_volatility_cache",
    # Options
    "opt_underlyings",
    "opt_contracts",
    "opt_snapshots",
    "opt_candidates",
    "opt_paper_trades",
    "opt_paper_positions",
    "opt_paper_exits",
    "opt_daily_risk",
    "opt_event_calendar",
    "opt_control_events",
    "opt_replay_runs",
]

def run_audit():
    print("=" * 70)
    print("[*] AUDITORIA DE BASE DE DATOS Y CONSUMO (SUPABASE FREE PLAN)")
    print("=" * 70)
    
    sb = get_supabase()
    results = []
    
    print("\n1. CONSULTANDO CONTEO DE FILAS POR TABLA (HEAD requests sin transferir payload)...")
    for tbl in TABLES:
        try:
            res = sb.table(tbl).select("*", count="exact", head=True).execute()
            count = res.count if res.count is not None else 0
            results.append((tbl, count, "OK"))
        except Exception as e:
            err = str(e)
            if "404" in err or "PGRST205" in err or "does not exist" in err:
                results.append((tbl, 0, "No existe en schema"))
            else:
                results.append((tbl, -1, f"Error: {err[:60]}"))

    # Ordenar por conteo descendente
    existing = [r for r in results if r[2] == "OK"]
    missing = [r for r in results if r[2] != "OK"]
    
    existing.sort(key=lambda x: x[1], reverse=True)
    
    total_rows = sum(r[1] for r in existing if r[1] > 0)
    
    print(f"\n{'TABLA':<30} | {'FILAS':<12} | {'ESTADO':<15}")
    print("-" * 65)
    for tbl, count, status in existing:
        flag = " [!] ALTO" if count > 50_000 else " [!] ATENCION" if count > 10_000 else ""
        print(f"{tbl:<30} | {count:<12,}{flag}")
        
    print("-" * 65)
    print(f"TOTAL FILAS IDENTIFICADAS: {total_rows:,}")
    
    print("\n2. TABLAS NO INSTALADAS O PENDIENTES DE MIGRACION:")
    for tbl, _, status in missing:
        print(f"  - {tbl}: {status}")
        
    print("\n3. HISTORIAL DE LIMPIEZA AUTOMATICA (db_cleanup_log):")
    try:
        cleanup_res = sb.table("db_cleanup_log").select("*").order("executed_at", desc=True).limit(5).execute()
        if cleanup_res.data:
            for c in cleanup_res.data:
                print(f"  - Fecha: {c.get('executed_at')} | Total borrado: {c.get('total_deleted')} | Velas: {c.get('deleted_candles')} | Logs: {c.get('deleted_logs')} | Estado: {c.get('status')}")
        else:
            print("  [!] No hay registros en db_cleanup_log (pg_cron podria no estar ejecutandose automaticamente).")
    except Exception as e:
        print(f"  [!] Error consultando db_cleanup_log: {e}")

if __name__ == "__main__":
    run_audit()
