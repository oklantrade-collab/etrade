"""
Corrección final de visibilidad:
1. Crypto/Forex -> Scalping 15M (Aa41/Bb41)
2. Stocks -> Sell visibility (PRO/HOT)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def final_ui_fix():
    sb = get_supabase()
    
    # ─── 1. CRYPTO & FOREX (Aa41/Bb41) ───
    print("Corrigiendo Aa41/Bb41 para SCALPING 15M...")
    sb.table("trading_rules").delete().in_("rule_code", ["Aa41", "Bb41"]).execute()
    
    # Usamos IDs y prioridades que el Frontend asocia a Scalping
    cf_rules = [
        {
            "id": 1141,
            "rule_code": "Aa41",
            "name": "ANTIGRAVITY BUY (15M/4H)",
            "description": "Candle Patterns + Fibonacci Filter (<= +2).",
            "direction": "long",
            "market_type": ["crypto_spot", "crypto_futures", "forex"],
            "enabled": True,
            "priority": 2, # Priority 2 suele ser para Scalping con badge
            "confidence": "high",
            "version": 2, # Version 1-2 suele disparar el badge 15M
            "regime_allowed": ["riesgo_medio", "bajo_riesgo", "range", "trending"],
            "entry_trades": [1],
            "logic": "AND",
            "current": True
        },
        {
            "id": 1142,
            "rule_code": "Bb41",
            "name": "ANTIGRAVITY SELL (15M/4H)",
            "description": "Candle Patterns + Fibonacci Filter (>= -2).",
            "direction": "short",
            "market_type": ["crypto_spot", "crypto_futures", "forex"],
            "enabled": True,
            "priority": 2,
            "confidence": "high",
            "version": 2,
            "regime_allowed": ["riesgo_medio", "bajo_riesgo", "range", "trending"],
            "entry_trades": [1],
            "logic": "AND",
            "current": True
        }
    ]
    for r in cf_rules:
        sb.table("trading_rules").insert(r).execute()
        print(f"  [OK] Aa41/Bb41 registradas.")

    # ─── 2. STOCKS SELL (V02 / V04) ───
    print("\nCorrigiendo Stocks SELL (V02/V04)...")
    sb.table("stocks_rules").delete().in_("rule_code", ["PRO_CANDLE_SELL", "HOT_CANDLE_SELL"]).execute()
    
    res_max_s = sb.table("stocks_rules").select("id").order("id", desc=True).limit(1).execute()
    next_id_s = (res_max_s.data[0]["id"] + 1) if res_max_s.data else 160

    stock_sell_rules = [
        {
            "id": next_id_s,
            "rule_code": "PRO_CANDLE_SELL",
            "name": "CANDLE SELL V02",
            "group_name": "inversiones_pro",
            "direction": "sell", # FUNDAMENTAL: "sell" en lugar de "short"
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "movements_allowed": ["lateral_at_top", "descending_from_top", "descending"],
            "notes": "Cierre PRO bajista (V02).",
            "pine_required": False
        },
        {
            "id": next_id_s + 1,
            "rule_code": "HOT_CANDLE_SELL",
            "name": "CANDLE SELL V04",
            "group_name": "hot_by_volume",
            "direction": "sell", # FUNDAMENTAL
            "order_type": "market",
            "enabled": True,
            "priority": 1,
            "movements_allowed": ["lateral_at_top", "descending_from_top", "descending"],
            "notes": "Cierre HOT bajista (V04).",
            "pine_required": False
        }
    ]
    for r in stock_sell_rules:
        sb.table("stocks_rules").insert(r).execute()
        print(f"  [OK] Stocks SELL registradas: {r['rule_code']}")

if __name__ == "__main__":
    final_ui_fix()
