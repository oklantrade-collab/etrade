import asyncio
from app.core.supabase_client import get_supabase

async def migrate():
    sb = get_supabase()

    # 1. Variables
    variables = [
        {"id": 49, "name": "basis_slope", "category": "basis", "source_field": "basis_slope", "enabled": True},
        {"id": 50, "name": "is_flat", "category": "basis", "source_field": "is_flat", "enabled": True}
    ]
    for v in variables:
        sb.table('strategy_variables').upsert(v).execute()

    # 2. Conditions
    conditions = [
        {
            "id": 58,
            "name": "Mercado Lateral (Range)",
            "variable_id": 50,
            "operator": "==",
            "value_literal": 1, 
            "value_type": "literal",
            "enabled": True
        },
        {
            "id": 59,
            "name": "Precio en zona extrema LOW",
            "variable_id": 23, # fibonacci_zone
            "operator": "<=",
            "value_literal": -5,
            "value_type": "literal",
            "enabled": True
        }
    ]
    for c in conditions:
        sb.table('strategy_conditions').upsert(c).execute()

    # 3. Rule Dd61
    rule_dd61 = {
        "rule_code": "Dd61",
        "name": "SWING LONG Dd61: Range Trap",
        "notes": "Caza en rango lateral al tocar banda externa (lower_6). TP en Basis.",
        "strategy_type": "swing",
        "direction": "long",
        "cycle": "all",
        "enabled": True,
        "priority": 10,
        "min_score": 0.5,
        "condition_logic": "AND",
        "condition_ids": [58, 59],
        "condition_weights": {"58": 0.6, "59": 0.4},
        "applicable_cycles": ["15m", "4h"]
    }
    sb.table('strategy_rules_v2').upsert(rule_dd61, on_conflict="rule_code").execute()

    # Trigger reload on engine
    from app.strategy.strategy_engine import StrategyEngine
    engine = StrategyEngine.get_instance(sb)
    await engine.reload()

    print("Migration completed: Rule Dd61 added and engine reloaded.")

if __name__ == "__main__":
    asyncio.run(migrate())
