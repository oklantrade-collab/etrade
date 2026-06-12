"""
eTrader v2 — Logger Module
Structured logging to both console and Supabase system_logs table.
"""
import logging
import json
import time
import asyncio
import sys
from datetime import datetime, timezone
from app.core.market_hours import is_forex_market_open

# Reconfigure system streams to use UTF-8 on Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Standard Python logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("eTrader")

def _safe_log_call(log_func, text: str):
    """Safely calls a logger function, encoding/decoding if a UnicodeEncodeError occurs."""
    try:
        log_func(text)
    except UnicodeEncodeError:
        try:
            # Fallback to ascii representation of the string
            clean_text = text.encode('ascii', errors='replace').decode('ascii')
            log_func(clean_text)
        except Exception:
            pass
    except Exception:
        pass



def log_to_db(
    module: str,
    level: str,
    message: str,
    context: dict | None = None,
    cycle_id: str | None = None,
):
    """
    Insert a log entry into system_logs in Supabase.
    Fails silently to never block the pipeline.
    """
    # OPTIMIZACIÓN DISK IO: Solo guardar en DB los ERRORES graves.
    if level.upper() not in ['ERROR', 'CRITICAL']:
        return

    try:
        from app.core.supabase_client import get_supabase

        sb = get_supabase()
        row = {
            "module": module,
            "level": level,
            "message": message,
            "context": json.dumps(context) if context else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if cycle_id:
            row["cycle_id"] = cycle_id
        sb.table("system_logs").insert(row).execute()
    except Exception as e:
        _safe_log_call(logger.warning, f"Failed to write log to DB: {e}")


def log_info(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    _safe_log_call(logger.info, f"[{module}] {message}")


def log_warning(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    _safe_log_call(logger.warning, f"[{module}] {message}")
    log_to_db(module, "WARNING", message, context, cycle_id)


# In-memory throttle for telegram errors: {(module, msg_prefix): timestamp}
ERROR_THROTTLE = {} # (module, fingerprint) -> last_sent_time
THROTTLE_SECONDS = 300 # 5 minutes

def _should_notify(module: str, message: str) -> bool:
    """Verifica si debemos enviar alerta a Telegram (throttling)."""
    if module == "alerts_service":
        return False
    
    now = time.time()
    
    # Generic fingerprint for Binance ban or rate-limiting errors to prevent Telegram spam
    if "BinanceAPIException" in message or "APIError(code=-1003)" in message or "IP banned" in message or "IP is banned" in message or "418 I'm a teapot" in message or "baneada" in message.lower():
        return False
        
    if module == "CTRADER" and not is_forex_market_open():
        if "Sin precio" in message or "No autenticado" in message or "Desconectado" in message:
            return False

    # Fingerprint: módulo + primeros 40 caracteres del mensaje
    fingerprint = (module, message[:40])
    
    if now - ERROR_THROTTLE.get(fingerprint, 0) > THROTTLE_SECONDS:
        ERROR_THROTTLE[fingerprint] = now
        return True
    return False

async def _async_notify(module: str, level: str, message: str):
    """Llama a send_telegram_message de forma segura."""
    try:
        from app.workers.alerts_service import send_telegram_message
        emoji = "❌" if level == "ERROR" else "🚨"
        msg = f"{emoji} *{level} EN SISTEMA* [{module}]\n`{message}`"
        await send_telegram_message(msg)
    except Exception:
        pass

def _trigger_notification(module: str, level: str, message: str):
    """Dispara la notificación asíncrona si aplica."""
    if _should_notify(module, message):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(_async_notify(module, level, message))
        except RuntimeError:
            # Sin loop activo (startup o scripts)
            pass

def log_error(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    _safe_log_call(logger.error, f"[{module}] {message}")
    log_to_db(module, "ERROR", message, context, cycle_id)
    _trigger_notification(module, "ERROR", message)


def log_critical(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    _safe_log_call(logger.critical, f"[{module}] {message}")
    log_to_db(module, "CRITICAL", message, context, cycle_id)
    _trigger_notification(module, "CRITICAL", message)


def log_debug(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    _safe_log_call(logger.debug, f"[{module}] {message}")
    # Debug logs not persisted to DB to save space

