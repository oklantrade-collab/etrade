"""
eTrade v7.0 — DAILY CIRCUIT BREAKER & TICKER COOLDOWN
=====================================================
Disyuntor institucional de riesgo diario:
1. Pausa automática de NUEVAS ENTRADAS si:
   - Se registran 3 pérdidas consecutivas en el día.
   - La pérdida acumulada del día supera el -0.5% del capital total.
2. Cooldown por Ticker:
   - 60 minutos de bloqueo para cualquier ticker que acaba de cerrar en pérdida.
   - Máximo 2 reentradas por ticker en la misma jornada (evita reincidencias tipo KSS/BDN).
3. Estado persistente en Supabase (tabla `stocks_config`, clave `circuit_breaker_state`).
"""

from __future__ import annotations
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase

MODULE = "CIRCUIT_BREAKER"


def get_circuit_breaker_state() -> Dict[str, Any]:
    """Lee el estado del disyuntor desde stocks_config o memoria."""
    sb = get_supabase()
    default_state = {
        "tripped": False,
        "trip_reason": None,
        "trip_time": None,
        "consecutive_losses": 0,
        "daily_realized_pnl": 0.0,
        "last_reset_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ticker_cooldowns": {},  # { TICKER: {"cooldown_until": ts, "losses_count": n, "entries_today": m} }
    }
    try:
        res = sb.table("stocks_config").select("value").eq("key", "circuit_breaker_state").execute()
        if res.data and res.data[0].get("value"):
            val = res.data[0]["value"]
            state = json.loads(val) if isinstance(val, str) else val
            # Reset diario automático a las 00:00 UTC
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if state.get("last_reset_date") != today_str:
                state["tripped"] = False
                state["trip_reason"] = None
                state["consecutive_losses"] = 0
                state["daily_realized_pnl"] = 0.0
                state["last_reset_date"] = today_str
                state["ticker_cooldowns"] = {}
                save_circuit_breaker_state(state)
            return state
    except Exception as e:
        log_warning(MODULE, f"Aviso leyendo circuit_breaker_state: {e}")

    return default_state


def save_circuit_breaker_state(state: Dict[str, Any]) -> None:
    """Persiste el estado del disyuntor en stocks_config."""
    sb = get_supabase()
    try:
        sb.table("stocks_config").upsert({
            "key": "circuit_breaker_state",
            "value": json.dumps(state) if not isinstance(state, str) else state,
            "description": "Estado del disyuntor diario y cooldowns por ticker",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        log_warning(MODULE, f"Error guardando circuit_breaker_state: {e}")


def can_open_new_trade(ticker: str, capital_total: float = 100000.0) -> Tuple[bool, str]:
    """
    Verifica si el sistema o el ticker tienen autorización para abrir una nueva operación.
    Returns: (can_open: bool, reason: str)
    """
    state = get_circuit_breaker_state()
    ticker_u = ticker.upper().strip()
    now_ts = time.time()

    # 1. ¿Disyuntor general disparado?
    if state.get("tripped"):
        return False, f"⛔ DISYUNTOR DIARIO ACTIVO: {state.get('trip_reason')}"

    # 2. ¿Ticker en cooldown o exceso de reentradas?
    t_info = (state.get("ticker_cooldowns") or {}).get(ticker_u, {})
    cooldown_until = t_info.get("cooldown_until", 0)
    if now_ts < cooldown_until:
        rem_min = int((cooldown_until - now_ts) / 60) + 1
        return False, f"⏳ Ticker {ticker_u} en cooldown defensivo tras pérdida (restan {rem_min} min)"

    entries_today = t_info.get("entries_today", 0)
    if entries_today >= 2:
        return False, f"⛔ Límite alcanzado para {ticker_u}: Máximo 2 reentradas diarias permitidas"

    return True, "OK"


def record_trade_completion(
    ticker: str,
    realized_pnl_usd: float,
    capital_total: float = 100000.0,
    cooldown_duration_minutes: int = 60
) -> None:
    """
    Actualiza el estado del disyuntor tras cerrarse una operación.
    """
    state = get_circuit_breaker_state()
    ticker_u = ticker.upper().strip()
    now_ts = time.time()
    pnl = float(realized_pnl_usd or 0.0)

    # Actualizar PnL acumulado diario
    state["daily_realized_pnl"] = round(state.get("daily_realized_pnl", 0.0) + pnl, 2)

    # Cooldown del ticker
    t_cds = state.setdefault("ticker_cooldowns", {})
    t_info = t_cds.setdefault(ticker_u, {"cooldown_until": 0, "losses_count": 0, "entries_today": 0})
    t_info["entries_today"] = t_info.get("entries_today", 0) + 1

    if pnl < 0:
        # Pérdida
        state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
        t_info["losses_count"] = t_info.get("losses_count", 0) + 1
        t_info["cooldown_until"] = now_ts + (cooldown_duration_minutes * 60)
        log_warning(
            MODULE,
            f"⚠️ Pérdida registrada en {ticker_u} (${pnl:.2f}). "
            f"Cooldown activado por {cooldown_duration_minutes}m. Consecutivas: {state['consecutive_losses']}"
        )
    else:
        # Ganancia: resetea racha de pérdidas consecutivas
        state["consecutive_losses"] = 0
        log_info(MODULE, f"✅ Ganancia en {ticker_u} (+${pnl:.2f}). Racha de pérdidas reseteada.")

    # Evaluación de Disparo de Disyuntor
    max_daily_loss_usd = -abs(capital_total * 0.005)  # -0.5% del capital total
    if state["consecutive_losses"] >= 3:
        state["tripped"] = True
        state["trip_reason"] = f"3 pérdidas consecutivas alcanzadas hoy (${state['daily_realized_pnl']:.2f} PnL)"
        state["trip_time"] = datetime.now(timezone.utc).isoformat()
        log_warning(MODULE, f"🚨 {state['trip_reason']}. NUEVAS COMPRAS BLOQUEADAS.")
    elif state["daily_realized_pnl"] <= max_daily_loss_usd:
        state["tripped"] = True
        state["trip_reason"] = f"Pérdida diaria acumulada ({state['daily_realized_pnl']:.2f}) superó -0.5% del capital"
        state["trip_time"] = datetime.now(timezone.utc).isoformat()
        log_warning(MODULE, f"🚨 {state['trip_reason']}. NUEVAS COMPRAS BLOQUEADAS.")

    save_circuit_breaker_state(state)
