"""
eTrader v2 — Configuration Module
Loads environment variables and provides typed configuration access.
"""
import os
import time
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
_backend_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)


class Settings(BaseModel):
    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")

    # Binance
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_secret: str = os.getenv("BINANCE_SECRET") or os.getenv("BINANCE_API_SECRET", "")
    binance_testnet: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Qwen (Alibaba) 
    qwen_api_key: str = os.getenv("QWEN_API_KEY", "")

    # OpenAI (ChatGPT)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Alpha Vantage
    alphavantage_api_key: str = os.getenv("ALPHAVANTAGE_API_KEY", "")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # SendGrid
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    sendgrid_from_email: str = os.getenv("SENDGRID_FROM_EMAIL", "")
    sendgrid_to_email: str = os.getenv("SENDGRID_TO_EMAIL", "")

    # Frontend
    next_public_url: str = os.getenv("NEXT_PUBLIC_URL", "http://localhost:3000")

    # Worker
    max_pipeline_workers: int = int(os.getenv("MAX_PIPELINE_WORKERS", "2"))
    pipeline_timeout_seconds: int = int(os.getenv("PIPELINE_TIMEOUT_SECONDS", "480"))


settings = Settings()


# Default strategy parameters (overridden by system_config in Supabase)
DEFAULT_CONFIG = {
    "spike_multiplier": 2.5,
    "mtf_signal_threshold": 0.65,
    "sl_multiplier": 2.0,
    "rr_ratio": 2.5,
    "max_risk_per_trade": 0.01,
    "top_symbols": 20,
    "candle_history_days": 90,
    "allowed_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
}

# ── SYMBOL_MAP: Binance → Internal format ──
SYMBOL_MAP = {
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "SOLUSDT": "SOLUSDT",
    "BNBUSDT": "BNBUSDT",
    "XRPUSDT": "XRPUSDT",
    "DOGEUSDT": "DOGEUSDT",
    "ADAUSDT": "ADAUSDT",
    "AVAXUSDT": "AVAXUSDT",
    "DOTUSDT": "DOTUSDT",
    "MATICUSDT": "MATICUSDT",
    "LINKUSDT": "LINKUSDT",
    "LTCUSDT": "LTCUSDT",
    "TRXUSDT": "TRXUSDT",
    "NEARUSDT": "NEARUSDT",
    "UNIUSDT": "UNIUSDT",
    "APTUSDT": "APTUSDT",
    "ARBUSDT": "ARBUSDT",
    "OPUSDT": "OPUSDT",
    "SUIUSDT": "SUIUSDT",
    "PEPEUSDT": "PEPEUSDT",
}


# ── Excluded stablecoin symbols ──
EXCLUDED_SYMBOLS = [
    "FDUSDUSDT",
    "USDCUSDT",
    "BUSDUSDT",
    "TUSDUSDT",
    "USDPUSDT",
    "DAIUSDT",
    "USDDUSDT",
    "EURCUSDT",
    "PAXGUSDT",
    "USD1USDT",
]


# ── Timeframe configuration ──
# Updated: 15m/30m/1h/4h → 200 candles for indicators + spike detection
# NOTE: 45m was replaced by 1h because Binance API does not support 45m interval
TIMEFRAMES = {
    "15m": {"limit": 200, "weight": 0.35},
    "30m": {"limit": 200, "weight": 0.20},
    "1h":  {"limit": 200, "weight": 0.15},
    "4h":  {"limit": 200, "weight": 0.15},
    "1d":  {"limit": 60,  "weight": 0.10},
    "1w":  {"limit": 30,  "weight": 0.05},
}

MTF_WEIGHTS = {tf: cfg["weight"] for tf, cfg in TIMEFRAMES.items()}


# ── Market Structure Confirmation Config ──
# Filtro de confirmación de estructura que afecta a TODOS los ciclos
STRUCTURE_CONFIG = {
    # Umbral mínimo para considerar un Lower Low / Higher High significativo
    'umbral_lower_low':       0.003,  # 0.3%
    'umbral_higher_high':     0.003,  # 0.3%

    # Velas consecutivas para confirmar estructura
    # 2 = dos Lower Lows o Higher Highs seguidos
    'velas_confirmacion':     2,

    # No revertir posición si está en pérdida
    'require_profit_to_reverse': True,

    # Timeframe de referencia por ciclo
    # Ciclo 5m mira SAR y estructura de 15m
    # Ciclo 15m mira SAR y estructura de 4h
    'structure_ref': {
        '5m':  '15m',
        '15m': '4h'
    }
}


# ── Market Toggles (Crypto / Forex) ──
_MARKET_TOGGLE_CACHE: dict[str, tuple[float, bool]] = {}
_MARKET_TOGGLE_TTL = 30.0


def clear_market_toggle_cache() -> None:
    """Limpia la caché en memoria de toggles de mercado."""
    _MARKET_TOGGLE_CACHE.clear()


def is_market_enabled(
    config_key: str,
    sb=None,
    default: bool = True,
    use_cache: bool = True,
) -> bool:
    """Consulta system_config para saber si un mercado (crypto_enabled / forex_enabled) está activo."""
    now = time.time()
    cached = _MARKET_TOGGLE_CACHE.get(config_key)
    if use_cache and cached and (now - cached[0]) < _MARKET_TOGGLE_TTL:
        return cached[1]

    try:
        if sb is None:
            from app.core.supabase_client import get_supabase
            sb = get_supabase()
        res = sb.table("system_config").select("value").eq("key", config_key).maybe_single().execute()
        if res and getattr(res, "data", None) and "value" in res.data:
            val = res.data["value"]
            enabled = not (
                val is False or str(val).strip().lower() in ("false", "0", "no", "off", "none", "")
            )
            _MARKET_TOGGLE_CACHE[config_key] = (now, enabled)
            return enabled
        _MARKET_TOGGLE_CACHE[config_key] = (now, default)
        return default
    except Exception:
        if cached is not None:
            return cached[1]
        return default


def is_crypto_enabled(sb=None, use_cache: bool = True) -> bool:
    """Retorna True si el mercado Crypto / Binance Futures está habilitado en system_config."""
    return is_market_enabled("crypto_enabled", sb=sb, default=True, use_cache=use_cache)


def is_forex_enabled(sb=None, use_cache: bool = True) -> bool:
    """Retorna True si el mercado Forex / cTrader está habilitado en system_config."""
    return is_market_enabled("forex_enabled", sb=sb, default=True, use_cache=use_cache)
