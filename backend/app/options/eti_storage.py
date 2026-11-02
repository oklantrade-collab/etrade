"""
eTrade — ETI Signal Storage & Persistence Manager
===================================================
Gestiona el almacenamiento atómico, memoria y persistencia de las señales
del Radar Cuántico ETI tanto en disco local (IPC zero-network fallback)
como en Supabase si está disponible.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.core.logger import log_info, log_warning, log_error
from app.options.eti_models import ETISignal

MODULE = "ETI_STORAGE"
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
FALLBACK_FILE = STORAGE_DIR / "etrade_signals_live.json"


def ensure_storage_dir() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_signals_from_disk() -> List[ETISignal]:
    """Carga las señales almacenadas en disco local."""
    ensure_storage_dir()
    if not FALLBACK_FILE.exists():
        return []
    try:
        with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            signals_data = data if isinstance(data, list) else data.get("signals", [])
            signals = []
            for item in signals_data:
                try:
                    signals.append(ETISignal.model_validate(item))
                except Exception as ex:
                    log_warning(MODULE, f"Error validando señal guardada: {ex}")
            return signals
    except Exception as e:
        log_error(MODULE, f"Error leyendo {FALLBACK_FILE}: {e}")
        return []


def save_signals_to_disk(signals: List[ETISignal]) -> bool:
    """Escribe de forma atómica la lista de señales activas en disco local."""
    ensure_storage_dir()
    temp_file = STORAGE_DIR / "etrade_signals_live.tmp"
    try:
        serialized = [s.model_dump() for s in signals]
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump({"signals": serialized, "updated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
        
        # Reemplazo atómico
        if temp_file.exists():
            temp_file.replace(FALLBACK_FILE)
        return True
    except Exception as e:
        log_error(MODULE, f"Error guardando señales en disco: {e}")
        return False


def save_eti_signal(signal: ETISignal) -> bool:
    """Registra o actualiza una señal de Radar Cuántico ETI."""
    signals = load_signals_from_disk()
    # Si ya existe, reemplazarla
    existing_idx = next((i for i, s in enumerate(signals) if s.signal_id == signal.signal_id), None)
    if existing_idx is not None:
        signals[existing_idx] = signal
    else:
        signals.append(signal)

    # Intentar guardar también en Supabase si está disponible
    try:
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        inst = signal.get_or_create_tactical_instruction()
        row_data = {
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "status": signal.status,
            "cadence": signal.cadence,
            "asset_class": signal.asset_class,
            "action": signal.action,
            "expires_at": signal.expires_at,
            "payload": signal.model_dump(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        sb.table("eti_signals").upsert(row_data, on_conflict="signal_id").execute()
    except Exception as e_sb:
        log_warning(MODULE, f"Aviso al persistir señal en Supabase (se mantiene copia local en disco): {e_sb}")

    return save_signals_to_disk(signals)


def get_active_eti_signals() -> List[ETISignal]:
    """Retorna las señales que están en estado ACTIVE y cuyo TTL no ha expirado."""
    signals = load_signals_from_disk()
    if not signals:
        # Sembrar señal de demostración si está vacía
        seed_default_sample_signal()
        signals = load_signals_from_disk()

    now_dt = datetime.now(timezone.utc)
    active: List[ETISignal] = []
    updated = False

    for s in signals:
        # Verificar si expiró
        try:
            exp_dt = datetime.fromisoformat(s.expires_at.replace("Z", "+00:00"))
            if now_dt > exp_dt and s.status == "ACTIVE":
                s.status = "EXPIRED"
                updated = True
        except Exception:
            pass

        if s.status == "ACTIVE":
            s.get_or_create_tactical_instruction()
            active.append(s)

    if updated:
        save_signals_to_disk(signals)

    return active


def get_eti_signal_by_id(signal_id: str) -> Optional[ETISignal]:
    signals = load_signals_from_disk()
    for s in signals:
        if s.signal_id == signal_id:
            s.get_or_create_tactical_instruction()
            return s
    return None


def update_eti_signal_status(signal_id: str, new_status: str, route_used: Optional[str] = None) -> bool:
    signals = load_signals_from_disk()
    found = False
    for s in signals:
        if s.signal_id == signal_id:
            s.status = new_status
            if route_used and s.tactical_instruction:
                s.tactical_instruction.recommended_route = route_used
            found = True
            break
    if found:
        return save_signals_to_disk(signals)
    return False


def seed_default_sample_signal() -> None:
    """Siembra el ejemplo canónico de META PUT 0DTE (Caso Yoel Sardiñas FCG Calibración #14)."""
    now = datetime.now(timezone.utc)
    # TTL de 24 horas para pruebas
    exp_iso = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()
    today_date = now.strftime("%Y-%m-%d")

    sample_dict = {
        "signal_id": "eti-sig-live-meta-put-001",
        "timestamp": now.isoformat(),
        "expires_at": exp_iso,
        "cadence": "PRE_MARKET",
        "status": "ACTIVE",
        "symbol": "META",
        "asset_class": "OPTION_0DTE",
        "action": "BUY_TO_OPEN",
        "options_contract": {
            "contract_symbol": f"META{now.strftime('%y%m%d')}P00590000",
            "option_type": "PUT",
            "strike": 590.0,
            "expiration_date": today_date,
            "dte": 0,
            "target_delta": -0.42,
            "max_bid_ask_spread_pct": 3.5,
            "estimated_contract_price": 2.75
        },
        "strategy": {
            "horizon": "SCALPING",
            "bias": "BEARISH",
            "playbook_rule": "META_GAMMA_CASCADE_PUT_0DTE",
            "expected_duration_minutes": 30
        },
        "causal_context": {
            "fde_regime": "DECELERATION",
            "fcg_confidence_pct": 91.5,
            "primary_source": "Yoel Sardiñas (FCG Calibración #14 - Short Gamma Cascade)",
            "catalyst_summary": "Subida de rendimientos de bonos a 10 años (4.93%) + Presiones regulatorias antimonopolio.",
            "catalyst_impact_score": -0.78,
            "greeks_thesis": "Gamma extrema en strikes $590-$595. Si el precio pierde $592.50, los market makers deben vender acciones para cubrir delta, acelerando la caída intradía."
        },
        "technical_gate": {
            "trigger_type": "VWAP_REJECTION",
            "underlying_trigger_price": 592.50,
            "trigger_operator": "LESS_THAN_OR_EQUAL",
            "indicator_requirements": {
                "vwap_condition": "PRICE_BELOW_VWAP",
                "ema_fast_vs_slow": "FAST_BELOW_SLOW",
                "min_relative_volume": 1.35,
                "timeframe_confirmation": "2m"
            }
        },
        "risk_management": {
            "invalidation_underlying": 596.20,
            "stop_loss_contract_pct": -20.0,
            "take_profit_1_pct": 40.0,
            "take_profit_2_pct": 90.0,
            "runner_trailing_stop_pct": 20.0,
            "max_account_risk_pct": 2.5
        },
        "safety_guardrails": {
            "execution_allowed": True,
            "max_slippage_pct": 1.5,
            "circuit_breaker_active": False
        }
    }
    try:
        sig = ETISignal.model_validate(sample_dict)
        sig.get_or_create_tactical_instruction()
        save_signals_to_disk([sig])
        log_info(MODULE, f"Señal canónica META PUT 0DTE sembrada en {FALLBACK_FILE}")
    except Exception as e:
        log_error(MODULE, f"Error sembrando señal de prueba: {e}")
