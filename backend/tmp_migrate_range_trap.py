import asyncio
from app.core.supabase_client import get_supabase

async def migrate():
    sb = get_supabase()

    # 1. Condition for SHORT extreme
    c_short_extreme = {
        "id": 60,
        "name": "Precio en zona extrema HIGH",
        "variable_id": 23, # fibonacci_zone
        "operator": ">=",
        "value_literal": 5,
        "value_type": "literal",
        "enabled": True
    }
    sb.table('strategy_conditions').upsert(c_short_extreme).execute()

    # 2. Cleanup old Dd61 if exists
    sb.table('strategy_rules_v2').delete().eq('rule_code', 'Dd61').execute()

    # 3. Rules
    rules = [
        # --- LONG TRAP (15m/4h) ---
        {
            "rule_code": "Dd61_15m",
            "name": "SWING LONG 15m Dd61: Range Trap",
            "notes": "Caza en rango lateral (15m). TP en Basis.",
            "strategy_type": "swing",
            "direction": "long",
            "cycle": "15m",
            "enabled": True,
            "priority": 10,
            "min_score": 0.5,
            "condition_logic": "AND",
            "condition_ids": [58, 59],
            "condition_weights": {"58": 0.6, "59": 0.4},
            "applicable_cycles": ["15m"]
        },
        {
            "rule_code": "Dd61_4h",
            "name": "SWING LONG 4h Dd61: Range Trap",
            "notes": "Caza en rango lateral (4h). TP en Basis.",
            "strategy_type": "swing",
            "direction": "long",
            "cycle": "4h",
            "enabled": True,
            "priority": 10,
            "min_score": 0.5,
            "condition_logic": "AND",
            "condition_ids": [58, 59],
            "condition_weights": {"58": 0.6, "59": 0.4},
            "applicable_cycles": ["4h"]
        },
        # --- SHORT TRAP (15m/4h) ---
        {
            "rule_code": "Dd51_15m",
            "name": "SWING SHORT 15m Dd51: Range Trap",
            "notes": "Caza en rango lateral (15m). TP en Basis.",
            "strategy_type": "swing",
            "direction": "short",
            "cycle": "15m",
            "enabled": True,
            "priority": 10,
            "min_score": 0.5,
            "condition_logic": "AND",
            "condition_ids": [58, 60],
            "condition_weights": {"58": 0.6, "60": 0.4},
            "applicable_cycles": ["15m"]
        },
        {
            "rule_code": "Dd51_4h",
            "name": "SWING SHORT 4h Dd51: Range Trap",
            "notes": "Caza en rango lateral (4h). TP en Basis.",
            "strategy_type": "swing",
            "direction": "short",
            "cycle": "4h",
            "enabled": True,
            "priority": 10,
            "min_score": 0.5,
            "condition_logic": "AND",
            "condition_ids": [58, 60],
            "condition_weights": {"58": 0.6, "60": 0.4},
            "applicable_cycles": ["4h"]
        }
    ]

    for rule in rules:
        sb.table('strategy_rules_v2').upsert(rule, on_conflict="rule_code").execute()

    # Reload engine
    from app.strategy.strategy_engine import StrategyEngine
    engine = StrategyEngine.get_instance(sb)
    await engine.reload()

    print("Migration completed: Dd61 and Dd51 added for 15m and 4h.")

if __name__ == "__main__":
    asyncio.run(migrate())
