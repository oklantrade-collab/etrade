"""
eTrader v2 — Alerts Worker
Sends trade alerts via Telegram and Email (SendGrid).
"""
import httpx
from datetime import datetime, timezone

from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error, log_warning

MODULE = "alerts"


def send_trade_alert(
    order: dict,
    signal: dict,
    cycle_id: str | None = None,
) -> None:
    """
    Send a trade execution alert via Telegram + Email.

    Parameters
    ----------
    order : dict with symbol, side, entry_price, sl_price, tp_price, quantity
    signal : dict with score_final, mtf_score
    """
    side = order.get("side", "?")
    symbol = order.get("symbol", "?")
    entry = order.get("entry_price", 0)
    sl = order.get("sl_price", 0)
    tp = order.get("tp_price", 0)
    rr = signal.get("risk_reward_ratio", 0)
    score = signal.get("score_final", 0)

    emoji = "🟢" if side == "BUY" else "🔴"

    message = (
        f"{emoji} *{side} {symbol}*\n"
        f"Entry: ${entry:,.2f}\n"
        f"SL: ${sl:,.2f}\n"
        f"TP: ${tp:,.2f}\n"
        f"R/R: {rr:.1f}x\n"
        f"MTF Score: {score:+.4f}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    telegram_sent = _send_telegram(message, cycle_id)
    email_sent = False  # Email is for daily summary only

    # Save alert event
    _save_alert_event(
        event_type="trade_executed",
        symbol=symbol,
        message=message.replace("*", ""),
        data={"order": order, "signal": signal},
        severity="info",
        telegram_sent=telegram_sent,
        email_sent=email_sent,
    )


def send_kill_switch_alert(reason: str, cycle_id: str | None = None) -> None:
    """Send CRITICAL alert when kill switch activates."""
    message = (
        "🚨 *KILL SWITCH ACTIVATED* 🚨\n\n"
        f"Reason: {reason}\n"
        f"Bot has been DEACTIVATED.\n"
        f"Manual intervention required to reactivate.\n"
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    _send_telegram(message, cycle_id)

    _save_alert_event(
        event_type="kill_switch",
        symbol=None,
        message=message.replace("*", ""),
        data={"reason": reason},
        severity="critical",
        telegram_sent=True,
        email_sent=False,
    )


def send_cycle_summary(cycle: dict, cycle_id: str | None = None) -> None:
    """
    Send cycle summary — only if orders were executed.
    """
    orders_executed = cycle.get("orders_executed", 0)
    if orders_executed == 0:
        return

    message = (
        f"📊 *Cycle Summary*\n"
        f"Symbols analyzed: {cycle.get('symbols_analyzed', 0)}\n"
        f"Spikes detected: {cycle.get('spikes_detected', 0)}\n"
        f"Signals generated: {cycle.get('signals_generated', 0)}\n"
        f"Orders executed: {orders_executed}\n"
        f"Duration: {cycle.get('duration_seconds', 0):.1f}s\n"
        f"Status: {cycle.get('status', '?')}"
    )

    _send_telegram(message, cycle_id)


def send_error_alert(error_message: str, context: dict | None = None, cycle_id: str | None = None) -> None:
    """Send error alert."""
    message = f"⚠️ *eTrader Error*\n{error_message}"
    _send_telegram(message, cycle_id)

    _save_alert_event(
        event_type="error",
        symbol=None,
        message=error_message,
        data=context,
        severity="warning",
        telegram_sent=True,
        email_sent=False,
    )


def _send_telegram(message: str, cycle_id: str | None = None) -> bool:
    """Send message via Telegram Bot API."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log_warning(MODULE, "Telegram not configured — skipping alert", cycle_id=cycle_id)
        return False

    try:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": settings.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload)
            if response.status_code == 200:
                log_info(MODULE, "Telegram alert sent successfully", cycle_id=cycle_id)
                return True
            else:
                log_error(MODULE, f"Telegram API error: {response.status_code} {response.text}", cycle_id=cycle_id)
                return False

    except Exception as e:
        log_error(MODULE, f"Telegram send failed: {e}", cycle_id=cycle_id)
        return False


def _save_alert_event(
    event_type: str,
    symbol: str | None,
    message: str,
    data: dict | None,
    severity: str,
    telegram_sent: bool,
    email_sent: bool,
) -> None:
    """Persist alert event to Supabase."""
    try:
        import json
        sb = get_supabase()
        row = {
            "event_type": event_type,
            "symbol": symbol,
            "message": message,
            "data": json.dumps(data) if data else None,
            "severity": severity,
            "telegram_sent": telegram_sent,
            "email_sent": email_sent,
        }
        sb.table("alert_events").insert(row).execute()
    except Exception:
        pass  # Non-critical — don't block pipeline
