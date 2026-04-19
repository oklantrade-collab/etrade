"""
Clonación exacta de metadatos para Aa41 y Bb41 (Basado en Aa11).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

def mirror_ui_fix():
    sb = get_supabase()
    
    # ─── 1. OBTENER METADATOS DE Aa11 PARA COPIARLOS ───
    res = sb.table("trading_rules").select("*").eq("rule_code", "Aa11").execute()
    if not res.data:
        print("No se pudo encontrar Aa11 para clonar.")
        return
    
    template = res.data[0]
    print(f"Usando Aa11 como plantilla (v{template['version']}, priority {template['priority']})")

    # ─── 2. RE-REGISTRAR Aa41 ───
    sb.table("trading_rules").delete().eq("rule_code", "Aa41").execute()
    rule_a = template.copy()
    rule_a["id"] = 1141
    rule_a["rule_code"] = "Aa41"
    rule_a["name"] = "LONG AA41: ANTIGRAVITY CANDLE BUY"
    rule_a["description"] = "Detección de patrones de velas 4H/1D + Filtro Fib Zone."
    rule_a["direction"] = "long"
    # Mantenemos market_type original de Aa11 por si acaso
    rule_a["market_type"] = ["crypto_spot", "crypto_futures"] 
    rule_a["enabled"] = True
    
    sb.table("trading_rules").insert(rule_a).execute()
    print("  [OK] Aa41 clonada de Aa11.")

    # ─── 3. RE-REGISTRAR Bb41 (Basado en una de Short si existe) ───
    sb.table("trading_rules").delete().eq("rule_code", "Bb41").execute()
    # Buscamos una short activa para clonar
    res_s = sb.table("trading_rules").select("*").eq("direction", "short").limit(1).execute()
    if res_s.data:
        rule_b = res_s.data[0].copy()
        print(f"Usando {rule_b['rule_code']} como plantilla para Bb41")
    else:
        rule_b = rule_a.copy() # fall back to long template but change side
    
    rule_b["id"] = 1142
    rule_b["rule_code"] = "Bb41"
    rule_b["name"] = "SHORT BB41: ANTIGRAVITY CANDLE SELL"
    rule_b["description"] = "Detección de patrones de velas 4H/1D + Filtro Fib Zone."
    rule_b["direction"] = "short"
    rule_b["enabled"] = True
    
    sb.table("trading_rules").insert(rule_b).execute()
    print("  [OK] Bb41 clonada.")

if __name__ == "__main__":
    mirror_ui_fix()
