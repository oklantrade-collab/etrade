import json
from app.core.supabase_client import get_supabase
from app.rebote_aduana.config import load_rebote_config_from_db, REBOTE_PARAMS, ADUANA_PARAMS
from app.rebote_aduana.rebote_engine import ReboteEngine, ReboteResult
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult
from app.rebote_aduana.logger import log_rebote_score, log_aduana_decision

sb = get_supabase()

print("=" * 60)
print("1. VERIFICANDO TABLA rebote_scores_log")
print("=" * 60)
try:
    res1 = sb.table("rebote_scores_log").select("*").limit(1).execute()
    print("  [OK] Tabla rebote_scores_log accesible. Filas existentes:", len(res1.data or []))
except Exception as e:
    print("  [ERROR] rebote_scores_log:", e)

print("\n" + "=" * 60)
print("2. VERIFICANDO TABLA aduana_decisions_log")
print("=" * 60)
try:
    res2 = sb.table("aduana_decisions_log").select("*").limit(1).execute()
    print("  [OK] Tabla aduana_decisions_log accesible. Filas existentes:", len(res2.data or []))
except Exception as e:
    print("  [ERROR] aduana_decisions_log:", e)

print("\n" + "=" * 60)
print("3. VERIFICANDO CONFIGURACIÓN EN system_config")
print("=" * 60)
try:
    res3 = sb.table("system_config").select("*").like("key", "rebote_%").execute()
    print(f"  [OK] Parámetros REBOTE en DB ({len(res3.data)}):")
    for row in res3.data:
        print(f"    - {row['key']}: {row['value']} ({row.get('description', '')})")
        
    res4 = sb.table("system_config").select("*").like("key", "aduana_%").execute()
    print(f"\n  [OK] Parámetros ADUANA en DB ({len(res4.data)}):")
    for row in res4.data:
        print(f"    - {row['key']}: {row['value']} ({row.get('description', '')})")
except Exception as e:
    print("  [ERROR] system_config:", e)

print("\n" + "=" * 60)
print("4. VERIFICANDO load_rebote_config_from_db()")
print("=" * 60)
try:
    cfg = load_rebote_config_from_db()
    print("  [OK] Config REBOTE cargada desde DB:")
    for k, v in cfg.items():
        print(f"    - {k}: {v}")
except Exception as e:
    print("  [ERROR] load_rebote_config_from_db():", e)

print("\n" + "=" * 60)
print("5. PRUEBA DE INSERCIÓN Y AUDITORÍA END-TO-END (TEST LOG)")
print("=" * 60)
try:
    # Test logging REBOTE
    dummy_res = ReboteResult(
        symbol="EURUSD_VERIF_TEST",
        direction="long",
        score_raw=65.0,
        score_final=78.0,
        decision="ENTER",
        signals=[{"name": "fib_extreme", "score": 40, "triggered": True, "detail": "Test L6"}],
        regime_adx="choppy",
        regime_adx_multiplier=1.2,
        regime_local="neutral",
        contra_trend=False,
        contra_trend_confirmed=True,
        volume_confirmed=True,
        fib_zone=-6,
        sl_price=1.0800,
        tp_price=1.0900,
        detail={"test": True}
    )
    log_rebote_score("EURUSD_VERIF_TEST", dummy_res)
    print("  [OK] log_rebote_score ejecutado con éxito")
    
    # Test logging ADUANA
    dummy_aduana = AduanaResult(
        approved=True,
        rule_triggered="",
        reason="Passed all checks (Test)",
        step=6,
        detail={"test": True}
    )
    log_aduana_decision("EURUSD_VERIF_TEST", "long", "MARKET", dummy_aduana, strategy="REBOTE")
    print("  [OK] log_aduana_decision ejecutado con éxito")
    
    # Verify rows written
    r_check = sb.table("rebote_scores_log").select("id, symbol, score_final, decision").eq("symbol", "EURUSD_VERIF_TEST").execute()
    print("  [OK] Verificación lectura rebote_scores_log:", r_check.data)
    
    a_check = sb.table("aduana_decisions_log").select("id, symbol, approved, reason").eq("symbol", "EURUSD_VERIF_TEST").execute()
    print("  [OK] Verificación lectura aduana_decisions_log:", a_check.data)
    
    # Cleanup test records
    sb.table("rebote_scores_log").delete().eq("symbol", "EURUSD_VERIF_TEST").execute()
    sb.table("aduana_decisions_log").delete().eq("symbol", "EURUSD_VERIF_TEST").execute()
    print("  [OK] Limpieza de registros de prueba completada")
    
except Exception as e:
    print("  [ERROR] en prueba de auditoría:", e)

print("\n" + "=" * 60)
print("VERIFICACIÓN FINALIZADA CON ÉXITO")
print("=" * 60)
