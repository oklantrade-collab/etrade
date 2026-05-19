import asyncio
from app.core.supabase_client import get_supabase

async def register_strategy_61():
    sb = get_supabase()
    
    print("Registering Squeeze Breakout Strategy rules in strategy_rules_v2...")
    
    rules = [
        {
            "rule_code": "Aa61",
            "name": "LONG Aa61: SQUEEZE BREAKOUT (BOLLINGER EXPLOSION)",
            "notes": "Estrategia alcista de ruptura de volatilidad (15m): Bollinger Band Expansion (15%), cruce EMA3 > EMA9 > EMA20, precio > basis, ADX > 20, alineacion de tendencia (SAR 15m).",
            "direction": "long",
            "strategy_type": "scalping",
            "cycle": "15m",
            "applicable_cycles": ["15m"],
            "condition_ids": [],
            "condition_logic": "AND",
            "condition_weights": {},
            "min_score": 0.98,
            "priority": 0,
            "enabled": True,
            "confidence": 0.98,
            "market_types": ["forex_futures", "crypto_futures"]
        },
        {
            "rule_code": "Bb61",
            "name": "SHORT Bb61: SALIDA PREVENTIVA SQUEEZE",
            "notes": "Cierre preventivo ultra-rapido (5m/15m): cruce contrario EMA3 < EMA9 en 5m para LONG, o perdida de impulso (cercania extrema de EMAs < 0.02% en 15m).",
            "direction": "short", # SHORT direction to show up in the SHORT tab
            "strategy_type": "scalping",
            "cycle": "5m",
            "applicable_cycles": ["5m", "15m"],
            "condition_ids": [],
            "condition_logic": "OR",
            "condition_weights": {},
            "min_score": 0.98,
            "priority": 0,
            "enabled": True,
            "confidence": 0.98,
            "market_types": ["forex_futures", "crypto_futures"]
        }
    ]
    
    for rule in rules:
        # Check if already exists to decide between insert or update
        res = sb.table('strategy_rules_v2').select('id').eq('rule_code', rule['rule_code']).execute()
        if res.data:
            print(f"Rule {rule['rule_code']} already exists. Updating...")
            sb.table('strategy_rules_v2').update(rule).eq('rule_code', rule['rule_code']).execute()
        else:
            print(f"Rule {rule['rule_code']} not found. Inserting...")
            sb.table('strategy_rules_v2').insert(rule).execute()
            
    print("Strategy registration completed successfully!")

if __name__ == "__main__":
    asyncio.run(register_strategy_61())
