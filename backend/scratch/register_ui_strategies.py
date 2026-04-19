"""
Actualiza las estrategias con metadatos exactos de visibilidad (Aa11/S01 style).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def update_ui_strategies():
    sb = get_supabase()
    
    # ─── 1. CRYPTO & FOREX ───
    print("Actualizando visibilidad Crypto/Forex...")
    # Borrar IDs viejos del test anterior para recrear limpios
    sb.table("trading_rules").delete().in_("rule_code", ["Aa41", "Bb41"]).execute()
    
    res_max = sb.table("trading_rules").select("id").order("id", desc=True).limit(1).execute()
    next_id = (res_max.data[0]["id"] + 1) if res_max.data else 1050
    
    cf_rules = [
        {
            "id": next_id,
            "rule_code": "Aa41",
            "name": "CANDLE SIGNAL BUY (4H/1D)",
            "description": "Patrones de velas japonesas alcistas + Filtro Fibonacci (<= +2).",
            "direction": "long", # lowercase
            "market_type": ["crypto_spot", "crypto_futures", "forex"], # Array format
            "enabled": True,
            "priority": 1,
            "confidence": "high",
            "regime_allowed": ["riesgo_medio", "bajo_riesgo", "range", "trending"],
            "entry_trades": [1],
            "logic": "AND",
            "current": True
        },
        {
            "id": next_id + 1,
            "rule_code": "Bb41",
            "name": "CANDLE SIGNAL SELL (4H/1D)",
            "description": "Patrones de velas japonesas bajistas + Filtro Fibonacci (>= -2).",
            "direction": "short", # lowercase
            "market_type": ["crypto_spot", "crypto_futures", "forex"],
            "enabled": True,
            "priority": 1,
            "confidence": "high",
            "regime_allowed": ["riesgo_medio", "bajo_riesgo", "range", "trending"],
            "entry_trades": [1],
            "logic": "AND",
            "current": True
        }
    ]
    
    for r in cf_rules:
        sb.table("trading_rules").insert(r).execute()
        print(f"  [OK] Re-registrada Crypto/Forex: {r['rule_code']}")

    # ─── 2. STOCKS ───
    print("\nActualizando visibilidad Stocks...")
    sb.table("stocks_rules").delete().in_("rule_code", ["PRO_CANDLE_BUY", "PRO_CANDLE_SELL", "HOT_CANDLE_BUY", "HOT_CANDLE_SELL"]).execute()
    
    res_max_s = sb.table("stocks_rules").select("id").order("id", desc=True).limit(1).execute()
    next_id_s = (res_max_s.data[0]["id"] + 1) if res_max_s.data else 150
    
    s_rules = [
        {
            "id": next_id_s,
            "rule_code": "PRO_CANDLE_BUY",
            "name": "CANDLE BUY V01",
            "group_name": "inversiones_pro", # snake_case lowercase
            "direction": "buy",
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "ia_min": 2,
            "tech_score_min": 40,
            "movements_allowed": ["ascending", "sideways", "lateral_ascending", "asc_from_low"],
            "notes": "Estrategia PRO (4H/1D).",
            "pine_required": False
        },
        {
            "id": next_id_s + 1,
            "rule_code": "PRO_CANDLE_SELL",
            "name": "CANDLE SELL V02",
            "group_name": "inversiones_pro",
            "direction": "short",
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "notes": "Cierre PRO bajista.",
            "pine_required": False
        },
        {
            "id": next_id_s + 2,
            "rule_code": "HOT_CANDLE_BUY",
            "name": "CANDLE BUY V03",
            "group_name": "hot_by_volume", 
            "direction": "buy",
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "ia_min": 4,
            "tech_score_min": 30,
            "movements_allowed": ["ascending", "lateral_ascending"],
            "notes": "Estrategia HOT (4H/1D).",
            "pine_required": False
        },
        {
            "id": next_id_s + 3,
            "rule_code": "HOT_CANDLE_SELL",
            "name": "CANDLE SELL V04",
            "group_name": "hot_by_volume",
            "direction": "short",
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "notes": "Cierre HOT bajista.",
            "pine_required": False
        }
    ]
    
    for r in s_rules:
        sb.table("stocks_rules").insert(r).execute()
        print(f"  [OK] Re-registrada Stock: {r['rule_code']}")

if __name__ == "__main__":
    update_ui_strategies()
