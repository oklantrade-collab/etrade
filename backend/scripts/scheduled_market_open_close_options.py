"""
eTrade — Scheduled Market Open Options Liquidation Runner
=========================================================
Script autónomo para ejecutar la liquidación de todas las opciones abiertas
exactamente a la apertura del mercado (09:30:05 ET / 08:30:05 Lima).

Uso:
    python backend/scripts/scheduled_market_open_close_options.py
    python backend/scripts/scheduled_market_open_close_options.py --now
    python backend/scripts/scheduled_market_open_close_options.py --force
"""
from __future__ import annotations
import sys
import os
import time
from datetime import datetime, timezone, timedelta
import zoneinfo

# Asegurar path de backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.core.market_hours import is_market_open
from app.options.close_all import close_all_open_options


def get_target_open_time() -> datetime:
    """Calcula la próxima apertura regular de mercado (09:30:05 ET)."""
    tz_et = zoneinfo.ZoneInfo("US/Eastern")
    now_et = datetime.now(tz_et)
    
    # 09:30:05 ET de hoy
    target_today = now_et.replace(hour=9, minute=30, second=5, microsecond=0)
    
    if now_et < target_today and now_et.weekday() < 5:
        return target_today
    
    # Próximo día hábil a las 09:30:05 ET
    target = target_today + timedelta(days=1)
    while target.weekday() >= 5:  # Saltar fin de semana
        target += timedelta(days=1)
    return target


def main():
    force = "--force" in sys.argv
    run_now = "--now" in sys.argv

    log_info("OPEN_LIQUIDATION_RUNNER", "🚀 Iniciando Scheduled Market Open Options Liquidation Runner...")
    sb = get_supabase()

    if not run_now:
        target_et = get_target_open_time()
        tz_et = zoneinfo.ZoneInfo("US/Eastern")
        now_et = datetime.now(tz_et)
        wait_seconds = (target_et - now_et).total_seconds()

        log_info(
            "OPEN_LIQUIDATION_RUNNER",
            f"⏰ Próxima apertura del mercado programada: {target_et.strftime('%Y-%m-%d %H:%M:%S %Z')}. "
            f"Esperando {wait_seconds:.0f} segundos ({wait_seconds/3600:.2f} horas)..."
        )

        while True:
            now_et = datetime.now(tz_et)
            rem = (target_et - now_et).total_seconds()
            if rem <= 0:
                log_info("OPEN_LIQUIDATION_RUNNER", "🔔 ¡Hora de apertura alcanzada (09:30:05 ET)! Verificando estado...")
                break
            
            # Loguear cada 30 minutos de progreso mientras espera
            sleep_step = min(rem, 30.0)
            time.sleep(sleep_step)

    # Verificar si el flag está activo o si se pasó --force
    cfg_res = sb.table("bot_config").select("value").eq("key", "close_all_options_at_market_open").limit(1).execute()
    flag_active = bool(cfg_res.data[0].get("value")) if cfg_res.data else False

    if not flag_active and not force:
        log_info("OPEN_LIQUIDATION_RUNNER", "ℹ️ El flag 'close_all_options_at_market_open' no está activo. Abortando sin ejecutar.")
        return

    log_info("OPEN_LIQUIDATION_RUNNER", "🚨 Disparando liquidación de opciones a la apertura del mercado...")

    # Desarmar flag
    try:
        sb.table("bot_config").update({
            "value": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("key", "close_all_options_at_market_open").execute()
    except Exception as e_flag:
        log_warning("OPEN_LIQUIDATION_RUNNER", f"Aviso al desarmar flag en bot_config: {e_flag}")

    # Ejecutar liquidación
    res = close_all_open_options(sb=sb, reason="market_open_liquidation")
    log_info("OPEN_LIQUIDATION_RUNNER", f"🏁 Liquidación completada. Resultado: {res}")


if __name__ == "__main__":
    main()
