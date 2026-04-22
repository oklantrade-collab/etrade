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


def get_system_config() -> dict:
    """Load all system_config rows from Supabase into a flat dict."""
    sb = get_supabase()
    result = sb.table("system_config").select("key, value").execute()
    config = {}
    for row in result.data:
        # value is stored as JSONB (could be string, number, etc.)
        val = row["value"]
        # Try to cast numeric strings
        if isinstance(val, str):
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except (ValueError, TypeError):
                pass
        config[row["key"]] = val
    return config


def get_risk_config() -> dict:
    """Load the single risk_config row."""
    sb = get_supabase()
    result = sb.table("risk_config").select("*").limit(1).execute()
    if result.data:
        return result.data[0]
    return {}
