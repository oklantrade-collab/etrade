import asyncio
from app.core.supabase_client import get_supabase

async def update_bb22_db():
    sb = get_supabase()
    
    # ── 1. Update Variables ──
    # Var 59: is_range_or_fall_15m
    # Var 60: sar_or_pine_sell_5m
    print("Updating strategy_variables...")
    sb.table('strategy_variables').upsert({"id": 59, "name": "is_range_or_fall_15m", "source_field": "is_range_or_fall_15m", "category": "combined", "enabled": True}).execute()
    sb.table('strategy_variables').upsert({"id": 60, "name": "sar_or_pine_sell_5m", "source_field": "sar_or_pine_sell_5m", "category": "combined", "enabled": True}).execute()

    print("Adding strategy_conditions...")
    # Cond 73: Range o Basis FALL (OR) (15m)
    # Cond 74: Precio toca upper_5 (5m)
    # Cond 75: (Inicio SARS- o Pine Sell) (5m)
    # Cond 76: Precio toca upper_6 (5m)
    conditions = [
        {"id": 73, "name": "Range o Basis FALL (OR) (15m)", "variable_id": 59, "operator": "==", "value_type": "literal", "value_literal": 1, "enabled": True},
        {"id": 74, "name": "Precio toca upper_5 (5m)", "variable_id": 1, "operator": ">=", "value_type": "variable", "value_variable": "upper_5", "enabled": True},
        {"id": 75, "name": "(Inicio SARS- o Pine Sell) (5m)", "variable_id": 60, "operator": "==", "value_type": "literal", "value_literal": 1, "enabled": True},
        {"id": 76, "name": "Precio toca upper_6 (5m)", "variable_id": 1, "operator": ">=", "value_type": "variable", "value_variable": "upper_6", "enabled": True}
    ]
    for c in conditions:
        sb.table('strategy_conditions').upsert(c).execute()

    print("Updating Rule Bb22...")
    rule_data = {
        "rule_code": "Bb22",
        "name": "SHORT Bb22: MTF Strategy",
        "notes": "Estrategia bajista (5m-15m): 15m Range/Fall (40%), 5m upper_5 (20%), 5m SAR-/Pine Sell (20%), 5m upper_6 (20%). Score min 80%",
        "direction": "short",
        "strategy_type": "scalping",
        "cycle": "15m", # For dashboard consistency
        "applicable_cycles": ["15m", "5m"],
        "condition_ids": [73, 74, 75, 76],
        "condition_weights": {"73": 0.40, "74": 0.20, "75": 0.20, "76": 0.20},
        "min_score": 0.80,
        "priority": 0,
        "enabled": True,
        "confidence": 0.80
    }
    sb.table('strategy_rules_v2').update(rule_data).eq('rule_code', 'Bb22').execute()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(update_bb22_db())
