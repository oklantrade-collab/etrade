"""
eTrade v4 — Data Cleanup Worker (Comprehensive)
Sistema de limpieza automática diaria para mantener
Supabase dentro del free tier (500MB).

Proveedores: Binance, IC Markets, Interactive Brokers + 2 futuros
Símbolos: ~4 por proveedor × 5 proveedores = 20 símbolos máx

Estrategia de retención:
  - market_candles: por conteo (últimas N por símbolo/exchange/TF)
  - system_logs: 48 horas
  - pilot_diagnostics: 24 horas
  - strategy_evaluations: 7 días
  - pending_orders (completadas): 7 días
  - volume_spikes: 14 días
  - signals_log: 14 días
  - cooldowns (inactivos): 3 días
  - market_regime_history: 90 días
  - db_cleanup_log: 90 días (auto-limpieza)

Se ejecuta:
  1. Vía pg_cron en Supabase (03:00 UTC)
  2. Vía Vercel Cron como fallback (03:00 UTC)
  3. Vía la API del backend (/api/v1/admin/cleanup)
"""
from datetime import datetime, timedelta, timezone
import time

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error, log_warning

MODULE = "DB_CLEANUP"

# ── Retención por conteo de velas (por símbolo+exchange+TF) ──
CANDLE_RETENTION = {
    "5m":  500,   # ~42 horas
    "15m": 300,   # ~75 horas
    "30m": 200,   # ~100 horas
    "1h":  168,   # ~7 días
    "4h":  180,   # ~30 días
    "1d":  365,   # ~1 año
}

# ── Retención por tiempo (días) de tablas de logs ──
TIME_RETENTION = {
    "system_logs":          {"days": 2,  "time_col": "created_at"},
    "pilot_diagnostics":    {"days": 1,  "time_col": "timestamp"},
    "strategy_evaluations": {"days": 7,  "time_col": "created_at"},
    "volume_spikes":        {"days": 14, "time_col": "detected_at"},
    "signals_log":          {"days": 14, "time_col": "detected_at"},
    "db_cleanup_log":       {"days": 90, "time_col": "executed_at"},
}

# ── Tablas opcionales (pueden no existir aún) ──
OPTIONAL_TIME_RETENTION = {
    "market_regime_history": {"days": 90, "time_col": "evaluated_at"},
    "market_snapshot_history": {"days": 3, "time_col": "created_at"},
}


async def cleanup_database() -> dict:
    """
    Limpieza completa de la base de datos.
    Returns dict con resumen de operaciones.
    """
    sb = get_supabase()
    t0 = time.time()
    results = {}

    # ───────────────────────────────────────
    # 1. MARKET CANDLES (por conteo)
    # ───────────────────────────────────────
    total_candles_deleted = 0
    for tf, keep_count in CANDLE_RETENTION.items():
        try:
            # Obtener todos los símbolos+exchange que tienen este TF
            symbols_res = sb.table("market_candles") \
                .select("symbol, exchange") \
                .eq("timeframe", tf) \
                .execute()

            if not symbols_res.data:
                continue

            # Obtener combinaciones únicas
            pairs = set()
            for row in symbols_res.data:
                pairs.add((row["symbol"], row.get("exchange", "binance")))

            for symbol, exchange in pairs:
                try:
                    # Contar cuántas velas tiene
                    count_res = sb.table("market_candles") \
                        .select("id", count="exact") \
                        .eq("symbol", symbol) \
                        .eq("exchange", exchange) \
                        .eq("timeframe", tf) \
                        .execute()

                    total_rows = count_res.count or 0
                    if total_rows <= keep_count:
                        continue

                    # Obtener el open_time de la vela N
                    # (la más antigua que queremos conservar)
                    cutoff_res = sb.table("market_candles") \
                        .select("open_time") \
                        .eq("symbol", symbol) \
                        .eq("exchange", exchange) \
                        .eq("timeframe", tf) \
                        .order("open_time", desc=True) \
                        .range(keep_count - 1, keep_count - 1) \
                        .execute()

                    if cutoff_res.data:
                        cutoff_time = cutoff_res.data[0]["open_time"]

                        del_res = sb.table("market_candles") \
                            .delete() \
                            .eq("symbol", symbol) \
                            .eq("exchange", exchange) \
                            .eq("timeframe", tf) \
                            .lt("open_time", cutoff_time) \
                            .execute()

                        deleted = len(del_res.data) if del_res.data else 0
                        total_candles_deleted += deleted

                        if deleted > 0:
                            log_info(MODULE,
                                f"Candles: {symbol}/{exchange}/{tf}: "
                                f"{deleted} eliminadas (conservando {keep_count})")

                except Exception as e:
                    log_error(MODULE,
                        f"Error limpiando candles {symbol}/{exchange}/{tf}: {e}")

        except Exception as e:
            log_error(MODULE, f"Error obteniendo símbolos para {tf}: {e}")

    results["candles"] = total_candles_deleted

    # ───────────────────────────────────────
    # 2. TABLAS CON RETENCIÓN POR TIEMPO
    # (Ordenadas por dependencia de llaves foráneas)
    # ───────────────────────────────────────
    
    # 2.1 Tablas que referencian a otras (Hijas)
    # Jerarquía: Orders -> Trading_Signals -> Volume_Spikes
    child_tables = {
        "pending_orders":  {"days": 7,  "time_col": "created_at"},
        "orders":          {"days": 14, "time_col": "created_at"},
        "trading_signals": {"days": 14, "time_col": "created_at"},
    }

    for table_name, config in child_tables.items():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=config["days"])
            query = sb.table(table_name).delete().lt(config["time_col"], cutoff.isoformat())
            
            # Filtros específicos por estado para no borrar órdenes abiertas
            if table_name == "pending_orders":
                query = query.in_("status", ["cancelled", "expired", "triggered"])
            elif table_name == "orders":
                query = query.in_("status", ["FILLED", "CANCELLED", "EXPIRED", "REJECTED"])
            
            del_res = query.execute()
            results[table_name] = len(del_res.data) if del_res.data else 0
        except Exception as e:
            log_warning(MODULE, f"{table_name} cleanup failed: {e}")
            results[table_name] = 0

    # 2.2 Tablas base (Padres)
    parent_tables = {
        "volume_spikes":        {"days": 7,  "time_col": "detected_at"},
        "signals_log":          {"days": 14, "time_col": "detected_at"},
        "system_logs":          {"days": 2,  "time_col": "created_at"},
        "pilot_diagnostics":    {"days": 1,  "time_col": "timestamp"},
        "strategy_evaluations": {"days": 7,  "time_col": "created_at"},
        "db_cleanup_log":       {"days": 90, "time_col": "executed_at"},
        "technical_indicators": {"days": 2,  "time_col": "timestamp"},
        "market_regime_history":{"days": 30, "time_col": "evaluated_at"},
        "cron_cycles":          {"days": 2,  "time_col": "started_at"},
        "news_sentiment":       {"days": 30, "time_col": "analyzed_at"},
    }

    for table_name, config in parent_tables.items():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=config["days"])
            del_res = sb.table(table_name).delete().lt(config["time_col"], cutoff.isoformat()).execute()
            results[table_name] = len(del_res.data) if del_res.data else 0
        except Exception as e:
            log_warning(MODULE, f"{table_name} cleanup failed: {e}")
            results[table_name] = 0

    # ───────────────────────────────────────
    # 3. TABLAS OPCIONALES
    # ───────────────────────────────────────
    for table_name, config in OPTIONAL_TIME_RETENTION.items():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=config["days"])
            cutoff_str = cutoff.isoformat()

            del_res = sb.table(table_name) \
                .delete() \
                .lt(config["time_col"], cutoff_str) \
                .execute()

            deleted = len(del_res.data) if del_res.data else 0
            results[table_name] = deleted

        except Exception:
            # Tabla no existe — silencioso
            results[table_name] = 0

    # ───────────────────────────────────────
    # 5. COOLDOWNS INACTIVOS
    # ───────────────────────────────────────
    try:
        del_res = sb.table("cooldowns") \
            .delete() \
            .eq("active", False) \
            .execute()

        results["cooldowns"] = len(del_res.data) if del_res.data else 0
    except Exception as e:
        log_warning(MODULE, f"cooldowns: {e}")
        results["cooldowns"] = 0

    # ───────────────────────────────────────
    # 6. CALCULAR TOTALES
    # ───────────────────────────────────────
    total_deleted = sum(v for v in results.values() if isinstance(v, int) and v > 0)
    duration_ms = int((time.time() - t0) * 1000)

    summary = {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "total_deleted": total_deleted,
        **results,
    }

    log_info(MODULE,
        f"Limpieza completada: {total_deleted} filas en {duration_ms}ms | "
        f"candles={results.get('candles', 0)} "
        f"logs={results.get('system_logs', 0)} "
        f"diag={results.get('pilot_diagnostics', 0)} "
        f"evals={results.get('strategy_evaluations', 0)} "
        f"orders={results.get('pending_orders', 0)}")

    # ───────────────────────────────────────
    # 7. LOGUEAR EN db_cleanup_log
    # ───────────────────────────────────────
    try:
        sb.table("db_cleanup_log").insert({
            "deleted_candles":     results.get("candles", 0),
            "deleted_logs":        results.get("system_logs", 0),
            "deleted_diagnostics": results.get("pilot_diagnostics", 0),
            "deleted_evaluations": results.get("strategy_evaluations", 0),
            "deleted_orders":      results.get("pending_orders", 0),
            "deleted_spikes":      results.get("volume_spikes", 0),
            "deleted_signals":     results.get("signals_log", 0),
            "deleted_cooldowns":   results.get("cooldowns", 0),
            "deleted_regime":      results.get("market_regime_history", 0),
            "total_deleted":       total_deleted,
            "duration_ms":         duration_ms,
            "status":              "success",
        }).execute()
    except Exception as e:
        log_warning(MODULE, f"No se pudo loguear en db_cleanup_log: {e}")

    # ───────────────────────────────────────
    # 8. NOTIFICAR POR TELEGRAM
    # ───────────────────────────────────────
    try:
        from app.workers.alerts_service import send_telegram_message
        await send_telegram_message(
            f"🧹 *LIMPIEZA DIARIA COMPLETADA*\n"
            f"Total eliminado: `{total_deleted}` filas\n"
            f"Duración: `{duration_ms}ms`\n\n"
            f"📊 Detalle:\n"
            f"  Candles: `{results.get('candles', 0)}`\n"
            f"  Logs: `{results.get('system_logs', 0)}`\n"
            f"  Diagnósticos: `{results.get('pilot_diagnostics', 0)}`\n"
            f"  Evaluaciones: `{results.get('strategy_evaluations', 0)}`\n"
            f"  Órdenes: `{results.get('pending_orders', 0)}`\n"
            f"  Spikes: `{results.get('volume_spikes', 0)}`\n"
            f"  Señales: `{results.get('signals_log', 0)}`"
        )
    except Exception:
        pass

    return summary


async def get_db_size_report() -> list[dict]:
    """
    Obtiene el tamaño de cada tabla pública en la BD.
    Requiere que la función get_db_size_report() exista en Supabase.
    """
    try:
        sb = get_supabase()
        result = sb.rpc("get_db_size_report").execute()
        return result.data or []
    except Exception as e:
        log_error(MODULE, f"Error obteniendo reporte de tamaño: {e}")
        return []


def run_cleanup():
    """Wrapper síncrono para ejecutar desde scripts."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(cleanup_database())
    finally:
        loop.close()
