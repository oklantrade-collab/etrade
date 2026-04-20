"""
eTrade v3 — Risk Controls
Circuit breaker, cooldowns, correlation filter, liquidation price,
funding rate, health checks, and max holding time.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase

MODULE = "risk_controls"

# ─── Correlation Config (MEJORA 4) ───

CORRELATION_CONFIG = {
    'bajo_riesgo': {
        'window_bars':     20,      # 5 horas de datos
        'max_correlation': 0.80,    # umbral estándar
        'enabled':         True,
    },
    'riesgo_medio': {
        'window_bars':     20,
        'max_correlation': 0.85,    # más permisivo
        'enabled':         True,
    },
    'alto_riesgo': {
        'window_bars':     20,
        'max_correlation': 1.01,    # efectivamente desactivado
        'enabled':         False,   # max_trades=1 ya protege
        'reason':          'En alto_riesgo, max_trades=1 '
                           'elimina el riesgo de posiciones '
                           'correlacionadas simultáneas'
    }
}

# ─── Circuit Breaker ───

CIRCUIT_BREAKER_DEFAULTS = {
    "max_daily_loss_pct": 5.0,
    "max_trade_loss_pct": 2.0,
}


def check_circuit_breaker(
    daily_pnl_usd: float,
    capital_total: float,
    config: Optional[dict] = None,
) -> dict:
    """
    Check if the daily loss limit has been reached.
    """
    cfg = config or CIRCUIT_BREAKER_DEFAULTS
    max_pct = float(cfg.get("max_daily_loss_pct", 5.0))

    daily_loss_pct = abs(min(daily_pnl_usd, 0)) / capital_total * 100 if capital_total > 0 else 0.0
    triggered = daily_loss_pct >= max_pct

    return {
        "triggered": triggered,
        "daily_loss_pct": round(daily_loss_pct, 2),
        "daily_loss_usd": round(abs(min(daily_pnl_usd, 0)), 2),
        "reset_at": "00:00 UTC del día siguiente" if triggered else None,
    }


# ─── Cooldown ───

COOLDOWN_DEFAULTS = {
    "post_sl_bars": 3,
    "post_tp_bars": 1,
}


def check_cooldown(
    symbol: str,
    supabase_client=None,
) -> dict:
    """
    Check if a symbol is in cooldown (post-SL or post-TP).
    """
    if supabase_client is None:
        supabase_client = get_supabase()

    try:
        result = (
            supabase_client.table("cooldowns")
            .select("*")
            .eq("symbol", symbol)
            .eq("active", True)
            .execute()
        )
        if result.data:
            cooldown = result.data[0]
            expires_at = cooldown.get("expires_at")
            if expires_at:
                # Check if still active
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < exp_dt:
                    return {
                        "in_cooldown": True,
                        "type": cooldown.get("cooldown_type"),
                        "expires_at": expires_at,
                    }
                else:
                    # Expired — deactivate
                    supabase_client.table("cooldowns").update(
                        {"active": False}
                    ).eq("id", cooldown["id"]).execute()
    except Exception as e:
        log_warning(MODULE, f"Cooldown check failed for {symbol}: {e}")

    return {"in_cooldown": False, "type": None, "expires_at": None}


def activate_cooldown(
    symbol: str,
    cooldown_type: str,
    bars: int,
    timeframe: str = "15m",
    supabase_client=None,
) -> None:
    """
    Activate a cooldown for a symbol after SL or TP.
    """
    if supabase_client is None:
        supabase_client = get_supabase()

    bar_minutes = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}.get(
        timeframe, 15
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=bar_minutes * bars)

    try:
        supabase_client.table("cooldowns").upsert(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "cooldown_type": cooldown_type,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat(),
                "active": True,
            },
            on_conflict="symbol,timeframe",
        ).execute()
    except Exception as e:
        log_warning(MODULE, f"Failed to activate cooldown for {symbol}: {e}")


# ─── Max Holding Time ───

MAX_HOLDING_BARS = {
    "15m": 48,   # 12 hours
    "30m": 48,   # 24 hours
    "1h": 32,    # ~32 hours
    "4h": 30,    # 5 days
    "1d": 14,    # 2 weeks
    "1w": 8,     # 2 months
}


def check_max_holding(
    position_side: str,
    avg_entry_price: float,
    current_bar: int,
    entry_bar: int,
    timeframe: str,
    current_price: float,
) -> dict:
    """
    Check if a position has exceeded maximum holding time.
    """
    bars_held = current_bar - entry_bar
    max_bars = MAX_HOLDING_BARS.get(timeframe, 48)

    if bars_held >= max_bars:
        in_profit = (
            (position_side == "long" and current_price > avg_entry_price)
            or (position_side == "short" and current_price < avg_entry_price)
        )
        return {
            "expired": True,
            "action": "partial_close_and_breakeven" if in_profit else "alert_manual",
            "bars_held": bars_held,
        }
    return {"expired": False, "bars_held": bars_held}


# ─── Correlation Filter (MEJORA 4) ───

def check_correlation_filter(
    symbol_new:      str,
    direction_new:   str,
    open_positions:  list,
    df_dict:         dict,   # {symbol: DataFrame con precios}
    regime:          str     # 'bajo_riesgo'|'riesgo_medio'|'alto_riesgo'
) -> dict:
    """
    Filtra entradas por correlación según el régimen activo.

    En alto_riesgo: siempre permite (max_trades=1 ya protege).
    En riesgo_medio: umbral 0.85.
    En bajo_riesgo: umbral 0.80.

    Solo bloquea si hay posición abierta en la MISMA dirección
    con correlación superior al umbral del régimen.
    """
    cfg = CORRELATION_CONFIG.get(regime, CORRELATION_CONFIG['riesgo_medio'])

    # En alto_riesgo la correlación está desactivada
    if not cfg['enabled']:
        return {
            'blocked':     False,
            'reason':      cfg.get('reason', 'Correlación desactivada'),
            'regime':      regime,
            'checked':     False
        }

    max_corr = cfg['max_correlation']
    window   = cfg['window_bars']

    # Verificar correlación solo con posiciones en la misma dirección
    for pos in open_positions:
        # Check if pos is a dict or object
        pos_side = getattr(pos, 'side', pos.get('side', '')) if hasattr(pos, 'side') or isinstance(pos, dict) else ''
        pos_symbol = getattr(pos, 'symbol', pos.get('symbol', '')) if hasattr(pos, 'symbol') or isinstance(pos, dict) else ''
        
        if pos_side != direction_new:
            continue  # dirección diferente → no hay riesgo de duplicar

        if pos_symbol not in df_dict or symbol_new not in df_dict:
            continue  # sin datos → no bloquear por precaución

        try:
            returns_new = (df_dict[symbol_new]['close']
                           .pct_change()
                           .tail(window))
            returns_pos = (df_dict[pos_symbol]['close']
                           .pct_change()
                           .tail(window))

            corr = returns_new.corr(returns_pos)

            if pd.notna(corr) and corr > max_corr:
                return {
                    'blocked':     True,
                    'reason':      (
                        f'Correlación {corr:.2f} entre {symbol_new} '
                        f'y {pos_symbol} supera umbral '
                        f'{max_corr} ({regime})'
                    ),
                    'correlation': round(float(corr), 3),
                    'regime':      regime,
                    'checked':     True
                }

        except Exception as e:
            from app.core.logger import log_warning
            log_warning('CORRELATION', 
                f'Error calculando correlación {symbol_new}'
                f'/{pos_symbol}: {e}')
            continue

    return {
        'blocked':  False,
        'regime':   regime,
        'checked':  True
    }


# ─── Liquidation Price (Futures) ───


def calculate_liquidation_price(
    entry_price: float,
    leverage: int,
    side: str,
    maintenance_margin: float = 0.005,
) -> dict:
    """
    Calculate the liquidation price for a futures position.
    """
    if side == "long":
        liq = entry_price * (1 - (1 / leverage) + maintenance_margin)
    else:
        liq = entry_price * (1 + (1 / leverage) - maintenance_margin)

    distance_pct = abs(entry_price - liq) / entry_price * 100

    return {
        "liquidation_price": round(liq, 4),
        "distance_pct": round(distance_pct, 2),
        "leverage": leverage,
    }


def validate_sl_vs_liquidation(
    sl_price: float,
    liquidation_price: float,
    side: str,
) -> dict:
    """
    Validate that the stop loss is more conservative than liquidation.
    """
    if side == "long":
        valid = sl_price > liquidation_price
    else:
        valid = sl_price < liquidation_price

    return {
        "valid": valid,
        "reason": ""
        if valid
        else f"SL ({sl_price:.4f}) is beyond liquidation ({liquidation_price:.4f})",
    }


# ─── Symbol Health Check ───


def check_symbol_health(
    volume_24h: float,
    spread_pct: float,
    min_volume_24h: float = 1_000_000,
    max_spread_pct: float = 0.15,
) -> dict:
    """
    Validate symbol health before opening any position.
    """
    volume_ok = volume_24h > min_volume_24h
    spread_ok = spread_pct < max_spread_pct

    return {
        "healthy": volume_ok and spread_ok,
        "volume_24h": round(volume_24h, 0),
        "spread_pct": round(spread_pct, 4),
        "volume_ok": volume_ok,
        "spread_ok": spread_ok,
    }


# ─── Rate Limiter ───


class RateLimiter:
    """Token bucket rate limiter: use only 50% of Binance limit (600/min)."""

    def __init__(self, max_calls_per_minute: int = 300):
        self.max_calls = max_calls_per_minute
        self.tokens = float(max_calls_per_minute)
        self.last_refill = time.time()

    def can_proceed(self) -> bool:
        self._refill()
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    def wait_for_token(self) -> None:
        """Block until a token is available."""
        while not self.can_proceed():
            time.sleep(0.1)

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        refill = elapsed * (self.max_calls / 60)
        self.tokens = min(self.max_calls, self.tokens + refill)
        self.last_refill = now


# Global rate limiter instance
rate_limiter = RateLimiter()


# ─── Pre-filters ───

def check_pre_filters(
    regime: dict,
    market_data: dict,
    direction: str,
    symbol: str,
    current_price: float,
    basis_price: float,
    open_trades_count: int,
    symbol_positions_count: int,
    capital_sufficient: bool,
    warmup_complete: bool,
    max_per_symbol: int = 4,
    rule_code: str = "",
) -> dict:
    """
    Evaluate all universal pre-filters before any rule condition.
    """
    reasons = []
    cfg = regime.get("active_params", {})

    # Volume entry check (CORRECCIÓN 2: Hacerlo opcional para ciertas reglas)
    if not market_data.get("vol_entry_ok", False):
        if rule_code not in ("Aa21", "Aa22", "Aa23", "Bb22", "Cc11", "Cc21"):
            reasons.append("Volume too low for entry (< 70% vol_ema)")

    # Max trades check (GLOBAL)
    max_trades = cfg.get("max_trades", 15) # Default large, the per-symbol one is more restrictive usually
    if open_trades_count >= max_trades:
        reasons.append(f"Global max trades reached ({open_trades_count}/{max_trades})")

    # Max trades check (PER SYMBOL - Compliance with Cant. Operación x Cripto)
    if symbol_positions_count >= max_per_symbol:
        reasons.append(f"Max positions for {symbol} reached ({symbol_positions_count}/{max_per_symbol})")

    # Capital check
    if not capital_sufficient:
        reasons.append("Insufficient operating capital")

    # Warmup check
    if not warmup_complete:
        reasons.append("Warm-up period not complete (need 200+ bars)")

    # Basis proximity filter (except Aa12 and Bb22)
    if rule_code not in ("Aa12", "Bb22"):
        if direction == "long" and basis_price > 0:
            if current_price > basis_price * 1.02:
                reasons.append("Price too far above basis for LONG entry")
        elif direction == "short" and basis_price > 0:
            if current_price < basis_price * 0.98:
                reasons.append("Price too far below basis for SHORT entry")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }


def check_total_market_risk(
    market: str, # 'crypto' or 'forex'
    capital_total: float,
    sb_client=None
) -> dict:
    """
    Check if the total investment in a specific market exceeds the allowed limit.
    """
    if sb_client is None:
        sb_client = get_supabase()
    
    # 1. Get limit from trading_config
    try:
        cfg_res = sb_client.table('trading_config').select('regime_params').eq('id', 1).single().execute()
        params = cfg_res.data.get('regime_params', {})
        
        limit_key = f"max_total_risk_{market}_pct"
        limit_pct = float(params.get(limit_key, 30)) / 100.0
        
        max_allowed_usd = capital_total * limit_pct
        
        # 2. Calculate current investment
        current_invested_usd = 0.0
        if market == 'crypto':
            # Crypto positions (Binance) - usually tracked in positions table
            res = sb_client.table('paper_trades').select('entry_price, quantity').is_('closed_at', 'null').execute()
            for p in (res.data or []):
                current_invested_usd += float(p.get('entry_price', 0)) * float(p.get('quantity', 0))
        else:
            # Forex positions
            res = sb_client.table('forex_positions').select('lots, entry_price').eq('status', 'open').execute()
            # Approximation: Lots * 100,000 * Price (for currencies) or Lots * 100 * Price (for Gold)
            for p in (res.data or []):
                mul = 100.0 if "XAU" in p.get('symbol', '').upper() else 100000.0
                current_invested_usd += float(p.get('lots', 0)) * mul * float(p.get('entry_price', 0))

        passed = current_invested_usd < max_allowed_usd
        
        return {
            "passed": passed,
            "current_usd": round(current_invested_usd, 2),
            "limit_usd": round(max_allowed_usd, 2),
            "reason": None if passed else f"Límite {market.upper()} alcanzado (${current_invested_usd:.0f}/${max_allowed_usd:.0f})"
        }
    except Exception as e:
        log_warning("RISK", f"Error checking total risk for {market}: {e}")
        return {"passed": True, "current_usd": 0, "limit_usd": 0}
