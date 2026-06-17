"""
Script para insertar las 3 reglas BLUE en stocks_rules de Supabase.
"""
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

sb = get_supabase()

rules = [
    {
        "rule_code": "BLUE_DEEP_PULLBACK_BUY",
        "name": "BLUE Deep Pullback (LOW toca EMA20 5m)",
        "direction": "buy",
        "order_type": "market",
        "enabled": True,
        "priority": 1,
        "group_name": "hot",
        "notes": "APEX AZUL: Compra cuando LOW toca EMA20 en 5m y rebota. Solo acciones STRONG_BUY_BLUE."
    },
    {
        "rule_code": "BLUE_MOMENTUM_RESUME_BUY",
        "name": "BLUE Momentum Resume (EMA3 cruza EMA9 5m)",
        "direction": "buy",
        "order_type": "market",
        "enabled": True,
        "priority": 2,
        "group_name": "hot",
        "notes": "APEX AZUL: Compra en primer cruce EMA3 > EMA9 fresco en 5m. Solo acciones STRONG_BUY_BLUE."
    },
    {
        "rule_code": "BLUE_MICRO_PULLBACK_BUY",
        "name": "BLUE Micro Pullback (CLOSE < EMA3 con tendencia intacta)",
        "direction": "buy",
        "order_type": "market",
        "enabled": True,
        "priority": 3,
        "group_name": "hot",
        "notes": "APEX AZUL: Compra micro-descanso bajo EMA3 mientras EMA3>EMA9>EMA20. Solo acciones STRONG_BUY_BLUE."
    },
]

for r in rules:
    # Check if exists
    existing = sb.table("stocks_rules").select("id").eq("rule_code", r["rule_code"]).execute()
    if existing.data:
        sb.table("stocks_rules").update(r).eq("rule_code", r["rule_code"]).execute()
        print(f"  UPDATED: {r['rule_code']}")
    else:
        sb.table("stocks_rules").insert(r).execute()
        print(f"  INSERTED: {r['rule_code']}")

print("\n✅ 3 reglas BLUE insertadas correctamente en stocks_rules.")
