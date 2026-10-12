"""
eTrader v2 — Supabase Client
Provides a singleton Supabase client for all modules.
"""
from supabase import create_client, Client, ClientOptions
from app.core.config import settings


_client: Client | None = None


def get_supabase() -> Client:
    """Return a singleton Supabase client using the service key."""
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set"
            )
        # Aumentar timeout por inestabilidad de red en entorno Windows
        # Nota: http_client se ha removido por incompatibilidad con algunas versiones de SyncClientOptions
        options = ClientOptions(
            postgrest_client_timeout=60,
            storage_client_timeout=60
        )

        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_key,
            options=options
        )
    return _client


def reset_supabase():
    """Reset the singleton client to force recreation on next use."""
    global _client
    _client = None


import time

_system_config_cache: dict | None = None
_system_config_ts: float = 0.0

_risk_config_cache: dict | None = None
_risk_config_ts: float = 0.0

CONFIG_CACHE_TTL = 300.0  # 5 minutos de caché en memoria para proteger cuota de Egress


def get_system_config(force_reload: bool = False) -> dict:
    """Load all system_config rows from Supabase into a flat dict with in-memory TTL cache."""
    global _system_config_cache, _system_config_ts
    now = time.time()
    if not force_reload and _system_config_cache is not None and (now - _system_config_ts) < CONFIG_CACHE_TTL:
        return _system_config_cache

    try:
        sb = get_supabase()
        result = sb.table("system_config").select("key, value").execute()
        config = {}
        for row in result.data:
            val = row["value"]
            if isinstance(val, str):
                try:
                    val = float(val)
                    if val == int(val):
                        val = int(val)
                except (ValueError, TypeError):
                    pass
            config[row["key"]] = val
        _system_config_cache = config
        _system_config_ts = now
        return _system_config_cache
    except Exception:
        if _system_config_cache is not None:
            return _system_config_cache
        raise


def get_risk_config(force_reload: bool = False) -> dict:
    """Load the single risk_config row with in-memory TTL cache."""
    global _risk_config_cache, _risk_config_ts
    now = time.time()
    if not force_reload and _risk_config_cache is not None and (now - _risk_config_ts) < CONFIG_CACHE_TTL:
        return _risk_config_cache

    try:
        sb = get_supabase()
        result = sb.table("risk_config").select("*").limit(1).execute()
        if result.data:
            _risk_config_cache = result.data[0]
            _risk_config_ts = now
            return _risk_config_cache
        return {}
    except Exception:
        if _risk_config_cache is not None:
            return _risk_config_cache
        raise


def invalidate_config_cache():
    """Invalidate memory cache when a config change occurs."""
    global _system_config_cache, _system_config_ts, _risk_config_cache, _risk_config_ts
    _system_config_cache = None
    _system_config_ts = 0.0
    _risk_config_cache = None
    _risk_config_ts = 0.0

