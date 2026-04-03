"""
eTrader v2 — Logger Module
Structured logging to both console and Supabase system_logs table.
"""
import logging
import json
from datetime import datetime, timezone


# Standard Python logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("eTrader")


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
        logger.warning(f"Failed to write log to DB: {e}")


def log_info(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    logger.info(f"[{module}] {message}")
    log_to_db(module, "INFO", message, context, cycle_id)


def log_warning(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    logger.warning(f"[{module}] {message}")
    log_to_db(module, "WARNING", message, context, cycle_id)


def log_error(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    logger.error(f"[{module}] {message}")
    log_to_db(module, "ERROR", message, context, cycle_id)


def log_critical(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    logger.critical(f"[{module}] {message}")
    log_to_db(module, "CRITICAL", message, context, cycle_id)


def log_debug(module: str, message: str, context: dict | None = None, cycle_id: str | None = None):
    logger.debug(f"[{module}] {message}")
    # Debug logs not persisted to DB to save space
