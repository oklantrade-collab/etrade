"""
Actualización de visibilidad para Aa51/Bb51/Aa52/Bb52.
Configura strategy_type='scalping' para que aparezcan en el Dashboard.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def update_visibility():
    sb = get_supabase()
    
    # ── market_types compatibles con el UI (basado en Aa41) ──
    markets = ['crypto', 'forex', 'forex_futures', 'crypto_futures', 'stocks_spot']
    
    rules = [
        {
            "rule_code": "Aa51", "strategy_type": "scalping", "direction": "long", 
            "market_types": markets, "notes": "CIERRE PROACTIVO LONG (Triple Confirmación)"
        },
        {
            "rule_code": "Bb51", "strategy_type": "scalping", "direction": "short", 
            "market_types": markets, "notes": "CIERRE PROACTIVO SHORT (Triple Confirmación)"
        },
        {
            "rule_code": "Aa52", "strategy_type": "scalping", "direction": "long", 
            "market_types": markets, "notes": "CIERRE URGENTE LONG (P&L > 1%)"
        },
        {
            "rule_code": "Bb52", "strategy_type": "scalping", "direction": "short", 
            "market_types": markets, "notes": "CIERRE URGENTE SHORT (P&L > 1%)"
        }
    ]

    print("Actualizando tipos y mercados para visibilidad...")
    for r in rules:
        sb.table("strategy_rules_v2").update({
            "strategy_type": r["strategy_type"],
            "direction":     r["direction"],
            "market_types":  r["market_types"],
            "notes":         r["notes"]
        }).eq("rule_code", r["rule_code"]).execute()

    print("Visibilidad actualizada. Por favor, refresca el navegador.")

if __name__ == "__main__":
    update_visibility()
