"""
Registro de parámetros de configuración para Cierre Proactivo en la tabla system_config.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def deploy_config():
    sb = get_supabase()
    print("Registrando configuración en system_config...")
    configs = [
        {"key": "proactive_exit_enabled", "value": "true"},
        {"key": "proactive_exit_min_profit_crypto", "value": "0.30"},
        {"key": "proactive_exit_min_profit_forex", "value": "0.05"},
        {"key": "proactive_exit_min_profit_stocks", "value": "0.20"},
        {"key": "proactive_exit_urgent_threshold", "value": "1.0"},
        {"key": "proactive_exit_candle_body_min", "value": "0.50"},
        {"key": "proactive_exit_require_all_3", "value": "true"}
    ]
    for c in configs:
        sb.table("system_config").delete().eq("key", c["key"]).execute()
        sb.table("system_config").insert(c).execute()

    print("Configuración en system_config completada.")

if __name__ == "__main__":
    deploy_config()
