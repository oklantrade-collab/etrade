"""
eTrade v6.0 — Saneamiento de Reglas HOT en stocks_rules
======================================================
1. Erradica 'lateral' y 'lateral_at_top' de las reglas HOT para evitar
   entradas en consolidaciones horizontales muertas.
2. Eleva rvol_min de 0.5 a 1.2+ en HOT_BB_PULLBACK_5M y HOT_DIP_BUY
   para garantizar combustible institucional.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

def update_rules():
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    updates = [
        {
            "rule_code": "HOT_BB_PULLBACK_5M",
            "movements_allowed": ["ascending", "lateral_ascending", "asc_from_low"],
            "rvol_min": 1.2,
            "notes": "Compra pullback a EMA9 en 5m con tendencia alcista activa en 15m (RVOL >= 1.2x, prohibido lateral muerto)."
        },
        {
            "rule_code": "HOT_DIP_BUY",
            "movements_allowed": ["ascending", "lateral_ascending", "asc_from_low"],
            "rvol_min": 1.2,
            "notes": "Compra DIP a EMA20 Diaria solo con inercia alcista confirmada (RVOL >= 1.2x, prohibido lateral plano)."
        },
        {
            "rule_code": "HOT_BB_BREAKOUT_5M",
            "movements_allowed": ["ascending", "lateral_ascending", "asc_from_low"],
            "rvol_min": 1.3,
            "notes": "Ruptura de Bollinger con expansión en 5m (RVOL >= 1.3x, prohibido lateral)."
        },
        {
            "rule_code": "S05",
            "movements_allowed": ["ascending", "lateral_ascending", "asc_from_low"],
            "rvol_min": 1.2,
            "notes": "HOT Compra Market: Solo con inercia alcista comprobada (RVOL >= 1.2x)."
        },
        {
            "rule_code": "S06",
            "movements_allowed": ["ascending", "lateral_ascending", "asc_from_low", "descending"],
            "rvol_min": 1.2,
            "notes": "HOT Compra Limit: Solo en rebote con volumen activo (RVOL >= 1.2x)."
        },
        {
            "rule_code": "HOT_CANDLE_BUY",
            "movements_allowed": ["ascending", "lateral_ascending", "asc_from_low", "lateral_at_bottom"],
            "rvol_min": 1.2,
            "notes": "CANDLE BUY V03: Solo con volumen institucional (RVOL >= 1.2x)."
        }
    ]

    print("Actualizando reglas HOT en Supabase...")
    for u in updates:
        code = u["rule_code"]
        res = sb.table("stocks_rules").update({
            "movements_allowed": u["movements_allowed"],
            "rvol_min": u["rvol_min"],
            "notes": u["notes"],
            "updated_at": now_iso
        }).eq("rule_code", code).execute()
        print(f"[{code}] Actualizado: movements={u['movements_allowed']}, rvol_min={u['rvol_min']}")

    print("\nVerificando reglas actualizadas en Supabase:")
    res_all = sb.table("stocks_rules").select("rule_code, movements_allowed, rvol_min").in_(
        "rule_code", [u["rule_code"] for u in updates]
    ).execute()
    for row in (res_all.data or []):
        print(row)

if __name__ == "__main__":
    update_rules()
