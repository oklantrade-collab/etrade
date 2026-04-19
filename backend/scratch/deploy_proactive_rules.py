"""
Migración para implementar reglas de cierre proactivo Aa51/Bb51 y Aa52/Bb52.
Se utilizan IDs 70-73 para evitar conflictos.
Direcciones acortadas a 'exit_l' y 'exit_s' para cumplir con VARCHAR(10).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def deploy_db_rules():
    sb = get_supabase()
    
    # 1. Insertar Condiciones (IDs 70-73)
    print("Registrando condiciones 70-73...")
    conditions = [
        {"id": 70, "name": "Vela 4H bajista confirmada (>0.5%)", "operator": "==", "value_type": "literal", "value_literal": 1, "timeframe": "4h", "description": "Vela 4H roja con cuerpo >= 0.5%"},
        {"id": 71, "name": "Ganancia posición > umbral mínimo", "operator": "==", "value_type": "literal", "value_literal": 1, "timeframe": "5m", "description": "P&L de posición abierta > umbral config"},
        {"id": 72, "name": "Vela 4H alcista confirmada (>0.5%)", "operator": "==", "value_type": "literal", "value_literal": 1, "timeframe": "4h", "description": "Vela 4H verde con cuerpo >= 0.5%"},
        {"id": 73, "name": "Ganancia posición > 1%", "operator": "==", "value_type": "literal", "value_literal": 1, "timeframe": "5m", "description": "P&L de posición abierta > 1%"}
    ]
    for c in conditions:
        sb.table("strategy_conditions").delete().eq("id", c["id"]).execute()
        sb.table("strategy_conditions").insert(c).execute()

    # 2. Insertar Reglas de Cierre
    print("Registrando reglas Aa51, Bb51, Aa52, Bb52...")
    rules = [
        {
            "rule_code": "Aa51", "name": "CIERRE LONG proactivo — reversión triple confirmada", "strategy_type": "exit_long", "direction": "exit_l", "cycle": "5m",
            "condition_ids": [36, 25, 70, 71], "condition_logic": "AND", "min_score": 0.75, "condition_weights": {"36": 0.30, "25": 0.30, "70": 0.25, "71": 0.15},
            "market_types": ["crypto_futures", "forex_futures", "stocks_spot", "crypto_spot"], "applicable_cycles": ["5m", "15m"], "enabled": True, "priority": 0,
            "notes": "Cierre LONG con ganancia antes del SL. Triple confirmación: Pine=S + SAR- + Vela4H bajista"
        },
        {
            "rule_code": "Bb51", "name": "CIERRE SHORT proactivo — reversión triple confirmada", "strategy_type": "exit_short", "direction": "exit_s", "cycle": "5m",
            "condition_ids": [37, 24, 72, 71], "condition_logic": "AND", "min_score": 0.75, "condition_weights": {"37": 0.30, "24": 0.30, "72": 0.25, "71": 0.15},
            "market_types": ["crypto_futures", "forex_futures", "stocks_spot", "crypto_spot"], "applicable_cycles": ["5m", "15m"], "enabled": True, "priority": 0,
            "notes": "Cierre SHORT con ganancia antes del SL. Triple confirmación: Pine=B + SAR+ + Vela4H alcista"
        },
        {
            "rule_code": "Aa52", "name": "CIERRE LONG urgente — 2/3 condiciones + ganancia alta", "strategy_type": "exit_long", "direction": "exit_l", "cycle": "5m",
            "condition_ids": [36, 25, 73], "condition_logic": "AND", "min_score": 0.65, "condition_weights": {"36": 0.35, "25": 0.35, "73": 0.30},
            "market_types": ["crypto_futures", "forex_futures", "stocks_spot"], "applicable_cycles": ["5m", "15m"], "enabled": True, "priority": 0,
            "notes": "Cierre LONG urgente con ganancia >1%. Solo requiere Pine=S + SAR-"
        },
        {
            "rule_code": "Bb52", "name": "CIERRE SHORT urgente — 2/3 condiciones + ganancia alta", "strategy_type": "exit_short", "direction": "exit_s", "cycle": "5m",
            "condition_ids": [37, 24, 73], "condition_logic": "AND", "min_score": 0.65, "condition_weights": {"37": 0.35, "24": 0.35, "73": 0.30},
            "market_types": ["crypto_futures", "forex_futures", "stocks_spot"], "applicable_cycles": ["5m", "15m"], "enabled": True, "priority": 0,
            "notes": "Cierre SHORT urgente con ganancia >1%. Solo requiere Pine=B + SAR+"
        }
    ]
    for r in rules:
        sb.table("strategy_rules_v2").delete().eq("rule_code", r["rule_code"]).execute()
        sb.table("strategy_rules_v2").insert(r).execute()

    # 3. Configuración en trading_config
    print("Registrando configuración en trading_config...")
    configs = [
        {"key": "proactive_exit_enabled", "value": "true", "description": "Activar cierre proactivo Aa51/Bb51"},
        {"key": "proactive_exit_min_profit_crypto", "value": "0.30", "description": "Ganancia mínima % para cerrar en Crypto"},
        {"key": "proactive_exit_min_profit_forex", "value": "0.05", "description": "Ganancia mínima % para cerrar en Forex"},
        {"key": "proactive_exit_min_profit_stocks", "value": "0.20", "description": "Ganancia mínima % para cerrar en Stocks"},
        {"key": "proactive_exit_urgent_threshold", "value": "1.0", "description": "Ganancia % para activar Aa52/Bb52 urgente"},
        {"key": "proactive_exit_candle_body_min", "value": "0.50", "description": "Tamaño mínimo cuerpo vela 4H (%)"},
        {"key": "proactive_exit_require_all_3", "value": "true", "description": "Requerir las 3 condiciones (false=2 de 3)"}
    ]
    for c in configs:
        sb.table("trading_config").delete().eq("key", c["key"]).execute()
        sb.table("trading_config").insert(c).execute()

    print("Despliegue de reglas en DB completado.")

if __name__ == "__main__":
    deploy_db_rules()
