import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def update_rules():
    sb = get_supabase()
    
    # 1. Ajustar HOT_SENTMARKET_BUY (Relajar IA de 4.0 a 2.5 para capturar momentum puro)
    sb.table("stocks_rules").update({
        "ia_min": 2.5,
        "notes": "Relajado a 2.5 por solicitud usuario para capturar momentum fuerte aunque fundamentals sean bajos."
    }).eq("rule_code", "HOT_SENTMARKET_BUY").execute()
    
    # 2. Ajustar HOT_CANDLE_BUY (Relajar IA de 4.0 a 2.5)
    sb.table("stocks_rules").update({
        "ia_min": 2.5,
    }).eq("rule_code", "HOT_CANDLE_BUY").execute()
    
    # 3. Activar SM_MIN como filtro de seguridad en lugar de IA (Priorizar Momentum Score)
    # Si la regla soporta sm_min (visto en stocks_rule_engine.py), lo usamos.
    sb.table("stocks_rules").update({
        "notes": '{"sm_min": 6.5}', # Usando el sistema de notas JSON para parámetros extendidos
    }).eq("rule_code", "HOT_SENTMARKET_BUY").execute()

    print("✅ Reglas HOT actualizadas en Supabase (IA Min: 2.5 | SM Min: 6.5)")

if __name__ == "__main__":
    asyncio.run(update_rules())
