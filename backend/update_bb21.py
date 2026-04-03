
import os
import asyncio
from app.core.supabase_client import get_supabase

async def update_rule_bb21():
    sb = get_supabase()
    
    print("Iniciando actualización de Regla Bb21...")

    # 1. Insertar Variables si no existen
    # IDs 47, 48, 49
    new_vars = [
        {
            "id": 47,
            "name": "basis_slope",
            "category": "fibonacci",
            "timeframes": ["15m", "4h"],
            "data_type": "float",
            "description": "Pendiente del BASIS (%)",
            "source_field": "basis_slope"
        },
        {
            "id": 48,
            "name": "is_flat",
            "category": "fibonacci",
            "timeframes": ["15m", "4h"],
            "data_type": "boolean",
            "description": "Mercado Lateral (Range)",
            "source_field": "is_flat"
        },
        {
            "id": 49,
            "name": "signal_age",
            "category": "system",
            "timeframes": ["5m", "15m"],
            "data_type": "integer",
            "description": "Edad última señal Pine",
            "source_field": "pinescript_signal_age"
        }
    ]
    
    for v in new_vars:
        try:
            sb.table("strategy_variables").upsert(v).execute()
            print(f"Variable {v['id']} ({v['name']}) OK")
        except Exception as e:
            print(f"Error insertando variable {v['id']}: {e}")

    # 2. Insertar Condiciones
    # IDs 46, 47, 48
    new_conds = [
        {
            "id": 46,
            "name": "Mercado Lateral (Range)",
            "variable_id": 48,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1, # True
            "timeframe": "15m",
            "description": "Basis está plano (rango)"
        },
        {
            "id": 47,
            "name": "Basis cayendo (retratamiento)",
            "variable_id": 47,
            "operator": "<",
            "value_type": "literal",
            "value_literal": 0.0,
            "timeframe": "15m",
            "description": "La pendiente del basis es negativa"
        },
        {
            "id": 48,
            "name": "PineScript Sell Reciente (<=3 velas)",
            "variable_id": 49,
            "operator": "<=",
            "value_type": "literal",
            "value_literal": 3,
            "timeframe": "15m",
            "description": "Señal Sell ocurrió hace 3 velas o menos"
        }
    ]
    
    for c in new_conds:
        try:
            sb.table("strategy_conditions").upsert(c).execute()
            print(f"Condición {c['id']} ({c['name']}) OK")
        except Exception as e:
            print(f"Error insertando condición {c['id']}: {e}")

    # 3. Actualizar la Regla Bb21 (ID 1013)
    # Condiciones originales: {9,14,17,27,34,41}
    # Remover: 9 (EMA20 fase short), 14 (EMA9 ángulo negativo), 34 (MTF fuerte-)
    # Mantener: 17 (Zona negativa), 27 (SAR 4h bajista), 41 (Estructura 4h SHORT ok)
    # Agregar: 46 (Lateral), 47 (Basis cayendo), 37 (PineScript Sell), 48 (Sell Reciente)
    
    new_condition_ids = [17, 27, 41, 46, 47, 37, 48]
    new_weights = {
        "17": 0.10,
        "27": 0.20,
        "41": 0.10,
        "46": 0.20,
        "47": 0.20,
        "37": 0.10,
        "48": 0.10
    }
    
    try:
        sb.table("strategy_rules_v2").update({
            "condition_ids": new_condition_ids,
            "condition_weights": new_weights,
            "name": "SHORT Bb21: Range + Basis Fall + Pine Sell",
            "notes": "Actualizada: Eliminadas EMAs y MTF; agregados Range, Basis Fall y PineScript Sell Reciente"
        }).eq("rule_code", "Bb21").execute()
        print("Regla Bb21 actualizada con éxito.")
    except Exception as e:
        print(f"Error actualizando regla Bb21: {e}")

if __name__ == "__main__":
    asyncio.run(update_rule_bb21())
