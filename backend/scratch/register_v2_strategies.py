"""
Registra Aa41 y Bb41 en la tabla CORRECTA (strategy_rules_v2) para el Frontend v2.
Versión corregida: confidence es numérico.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def register_v2_strategies():
    sb = get_supabase()
    
    print("Registrando en strategy_rules_v2...")
    sb.table("strategy_rules_v2").delete().in_("rule_code", ["Aa41", "Bb41"]).execute()
    
    rules = [
        {
            "rule_code": "Aa41",
            "name": "ANTIGRAVITY CANDLE BUY (4H/1D)",
            "strategy_type": "scalping", 
            "direction": "long",
            "cycle": "15m",
            "applicable_cycles": ["15m", "4h", "1d"],
            "condition_ids": [1],
            "condition_weights": {"1": 1.0},
            "min_score": 0.80,
            "market_types": ["crypto", "forex"],
            "enabled": True,
            "priority": 10,
            "confidence": 0.85, # Numérico ahora
            "notes": "Sistema Antigravity con Filtro Fibonacci Zone. Detecta 26 patrones de velas."
        },
        {
            "rule_code": "Bb41",
            "name": "ANTIGRAVITY CANDLE SELL (4H/1D)",
            "strategy_type": "scalping",
            "direction": "short",
            "cycle": "15m",
            "applicable_cycles": ["15m", "4h", "1d"],
            "condition_ids": [1],
            "condition_weights": {"1": 1.0},
            "min_score": 0.80,
            "market_types": ["crypto", "forex"],
            "enabled": True,
            "priority": 10,
            "confidence": 0.85, # Numérico ahora
            "notes": "Sistema Antigravity con Filtro Fibonacci Zone. Detecta 26 patrones de velas bajistas."
        }
    ]
    
    for r in rules:
        res = sb.table("strategy_rules_v2").insert(r).execute()
        if res.data:
            print(f"  [OK] Registrada: {r['rule_code']}")
        else:
            print(f"  [ERROR] Falló registro de {r['rule_code']}")

if __name__ == "__main__":
    register_v2_strategies()
