"""
eTrade v3 — Dynamic Market Regime Classification
Classifies market conditions every 15 minutes into risk categories
that control all trading parameters.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.core.logger import log_info
from app.core.supabase_client import get_supabase
from app.core.parameter_guard import get_active_params

MODULE = "market_regime"

CONFIG_BY_RISK = {
    "alto_riesgo": {
        "mtf_threshold": 0.80,
        "max_trades": 1,
        "atr_mult": 2.5,
        "rr_min": 3.0,
        "adx_min": 30,
        "min_nivel_entrada": 2,
        "di_cross_required": True,
        "flat_pct": 25.0,
        "peak_pct": 75.0,
        "label": "🔴 Alto Riesgo",
    },
    "riesgo_medio": {
        "mtf_threshold": 0.65,
        "max_trades": 3,
        "atr_mult": 2.0,
        "rr_min": 2.5,
        "adx_min": 20,
        "min_nivel_entrada": 1,
        "di_cross_required": True,
        "flat_pct": 20.0,
        "peak_pct": 80.0,
        "label": "🟡 Riesgo Medio",
    },
    "bajo_riesgo": {
        "mtf_threshold": 0.50,
        "max_trades": 5,
        "atr_mult": 1.5,
        "rr_min": 2.0,
        "adx_min": 15,
        "min_nivel_entrada": 1,
        "di_cross_required": False,
        "flat_pct": 15.0,
        "peak_pct": 85.0,
        "label": "🟢 Bajo Riesgo",
    },
}


def classify_market_risk(
    df: pd.DataFrame,
    custom_config: dict | None = None,
) -> dict:
    """
    Classify current market conditions into a risk category.

    Risk score 0-100 (low = favorable market, high = hostile market).

    Weights:
      ATR percentile  35% → high relative volatility = more risk
      ADX score       35% → weak trend = more risk
      Volume ratio    20% → low volume = more risk
      Macro trend     10% → EMA50 < EMA200 = more risk

    Parameters
    ----------
    df : DataFrame with atr, adx, volume, ema4, ema5 columns
    custom_config : optional override for CONFIG_BY_RISK values

    Returns
    -------
    dict with category, risk_score, label, active_params, features
    """
    last = df.iloc[-1]

    # ATR percentile (how volatile vs recent history)
    atr_pct = float((df["atr"].tail(50) < last["atr"]).mean() * 100)

    # ADX score (inverted — low ADX = high risk)
    adx_val = float(last["adx"]) if pd.notna(last["adx"]) else 0.0
    adx_score = max(0, 100 - adx_val * 2.5)

    # Volume ratio vs 20-bar average
    vol_avg = float(df["volume"].tail(20).mean())
    vol_ratio = float(last["volume"]) / vol_avg if vol_avg > 0 else 1.0
    vol_score = max(0, min(100, (1.5 - vol_ratio) * 67))

    # Macro trend
    ema50 = float(last["ema4"]) if pd.notna(last.get("ema4")) else 0.0
    ema200 = float(last["ema5"]) if pd.notna(last.get("ema5")) else 0.0
    macro = 80 if ema50 < ema200 else 20

    # Weights
    weights = {'atr': 0.35, 'adx': 0.35, 'vol': 0.20, 'macro': 0.10}
    
    # Rounded components for transparency
    risk_components = {
        "atr_contribution": round(atr_pct * weights['atr'], 2),
        "adx_contribution": round(adx_score * weights['adx'], 2),
        "vol_contribution": round(vol_score * weights['vol'], 2),
        "macro_contribution": round(macro * weights['macro'], 2)
    }

    # Weighted score
    risk_score = (
        atr_pct * weights['atr'] + 
        adx_score * weights['adx'] + 
        vol_score * weights['vol'] + 
        macro * weights['macro']
    )

    # Classify
    if risk_score >= 65:
        category = "alto_riesgo"
    elif risk_score >= 35:
        category = "riesgo_medio"
    else:
        category = "bajo_riesgo"

    # --- SPRINT 2: DYNAMIC PARAMS VIA GUARDRAILS (CACHED) ---
    global _PARAMS_CACHE
    if '_PARAMS_CACHE' not in globals():
        _PARAMS_CACHE = {}

    try:
        from datetime import timedelta
        now = datetime.now()
        
        # Cache por 1 minuto para no saturar Supabase
        if category not in _PARAMS_CACHE or (now - _PARAMS_CACHE[category]['time']) > timedelta(minutes=1):
            sb = get_supabase()
            _PARAMS_CACHE[category] = {
                'data': get_active_params(category, sb),
                'time': now
            }
        cfg = _PARAMS_CACHE[category]['data']
    except Exception:
        # Fallback to local dict if DB fails
        cfg = CONFIG_BY_RISK.get(category, CONFIG_BY_RISK["riesgo_medio"])
    
    # Label mapping (guards might not have this readable label)
    labels = {
        "alto_riesgo": "🔴 Alto Riesgo",
        "riesgo_medio": "🟡 Riesgo Medio",
        "bajo_riesgo": "🟢 Bajo Riesgo"
    }

    return {
        "category": category,
        "risk_score": round(risk_score, 1),
        "label": labels.get(category, "⚪ Desconocido"),
        "active_params": cfg,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "features": {
            "atr_percentile": round(atr_pct, 1),
            "adx_value": round(adx_val, 1),
            "volume_ratio": round(vol_ratio, 2),
            "macro_trend": "bearish" if macro == 80 else "bullish",
            "score_breakdown": risk_components
        },
    }


# ─── Emergency ATR Spike Monitor ───

EMERGENCY_CONFIG = {
    "enabled": True,
    "atr_multiplier": 2.0,
    "action": "pause",  # 'pause' | 'close_all' | 'alert_only'
}


def check_emergency(
    current_atr: float,
    avg_atr: float,
    config: dict | None = None,
) -> dict:
    """
    Check for emergency ATR spike condition.
    Executed by the WebSocket monitor or 5m cycle.

    Parameters
    ----------
    current_atr : current ATR value
    avg_atr : average ATR over recent history
    config : emergency config dict (optional, uses defaults)

    Returns
    -------
    dict with emergency_active, atr_ratio, action
    """
    cfg = config or EMERGENCY_CONFIG
    if not cfg.get("enabled", True):
        return {"emergency_active": False, "atr_ratio": 0.0, "action": None}

    ratio = current_atr / avg_atr if avg_atr > 0 else 0.0
    is_emergency = current_atr > avg_atr * cfg["atr_multiplier"]

    return {
        "emergency_active": is_emergency,
        "atr_ratio": round(ratio, 2),
        "action": cfg["action"] if is_emergency else None,
    }


from app.core.memory_store import BOT_STATE

async def update_regime_if_changed(symbol: str, new_regime: dict, supabase_client):
    """
    DB write SOLO si la categora cambi respecto a la ltima registrada.
    Un mercado en riesgo_medio puede mantenerse as durante horas
    sin generar ninguna escritura.
    """
    prev_regime = BOT_STATE.regime_cache.get(symbol)
    prev_category = prev_regime.get('category') if prev_regime else None
    
    if prev_category == new_regime['category']:
        # Update memory cache with latest data (score, features) but don't hit DB
        BOT_STATE.regime_cache[symbol] = new_regime
        return

    # Category changed -> Escribir en Supabase y actualizar historial
    BOT_STATE.regime_cache[symbol] = new_regime
    try:
        # Update current state (WARM) - Using columns available in bot_state
        # Note: bot_state table in migration_008 doesn't have last_regime_category
        # We'll skip writing regime to bot_state for now to avoid errors, 
        # as it's primarily tracked in pilot_diagnostics anyway.
        
        # Log to history (COLD)
        supabase_client.table('market_regime_history').insert({
            'symbol': symbol,
            'category': new_regime['category'],
            'risk_score': new_regime['risk_score'],
            'features': new_regime['features'],
            'evaluated_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        
        log_info(MODULE, f"Regime changed for {symbol}: {prev_category} -> {new_regime['category']}")
    except Exception as e:
        log_info(MODULE, f"Failed to record regime change for {symbol}: {e}")
