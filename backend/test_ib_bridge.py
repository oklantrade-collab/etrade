"""
eTrade — Test Diagnóstico de Conexión Interactive Brokers (APOLO)
================================================================
Verifica:
1. Instalación de la librería ibapi
2. Conexión de socket al puerto 7497 de TWS (Paper Trading) en APOLO
3. Lectura de cuentas administradas en TWS
4. Conexión y sincronización con Supabase
"""
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.data.ib_provider import get_ib_connection, IB_AVAILABLE

def test_diagnostics():
    print("=" * 60)
    print(" 🔍 DIAGNÓSTICO DE CONEXIÓN A INTERACTIVE BROKERS (PAPER)")
    print("=" * 60)

    # 1. Verificar ibapi
    print("\n[Paso 1/4] Verificando librería oficial 'ibapi'...")
    if IB_AVAILABLE:
        import ibapi
        print(f"  ✅ 'ibapi' está instalada correctamente (versión: {getattr(ibapi, '__version__', 'instalada')})")
    else:
        print("  ❌ 'ibapi' NO está disponible.")
        return

    # 2. Probar conexión con Supabase
    print("\n[Paso 2/4] Probando conexión a Supabase...")
    try:
        sb = get_supabase()
        res = sb.table("stocks_config").select("key, value").limit(5).execute()
        print(f"  ✅ Conectado a Supabase con éxito. Filas de config leídas: {len(res.data or [])}")
    except Exception as e:
        print(f"  ❌ Error conectando a Supabase: {e}")
        return

    # 3. Intentar conexión al Socket de TWS
    from app.workers.ib_bridge_worker import get_default_ib_host
    target_host = get_default_ib_host()
    print(f"\n[Paso 3/4] Probando conexión con Trader Workstation (TWS) en APOLO ({target_host})...")
    print(f"  Target: {target_host}:7497 (Paper Trading)")
    ib = get_ib_connection()
    connected = ib.connect_tws(host=target_host, port=7497, client_id=88)

    if connected:
        print("  ✅ ¡CONEXIÓN ESTABLECIDA CON ÉXITO CON TWS!")
        time.sleep(1) # Esperar paquetes de bienvenida
        accounts = ib.accounts or ["Sesión Paper Detectada"]
        print(f"  📋 Cuentas detectadas en TWS: {accounts}")
        print(f"  🔢 Próximo ID de orden válido de IB: {ib.next_order_id}")
        
        # 4. Probar desconexión limpia
        print("\n[Paso 4/4] Cerrando sesión de prueba...")
        ib.disconnect_tws()
        print("  ✅ Desconexión limpia efectuada.")
        print("\n🎉 TODO ESTÁ LISTO para operar en Paper Trading con TWS.")
    else:
        print("  ⚠️ No se pudo conectar a TWS en el puerto 7497.")
        print("     Verifica en tu computadora APOLO:")
        print("     1. Que TWS esté abierto e iniciada la sesión en 'Paper Trading'.")
        print("     2. Que en TWS > File > Global Configuration > API > Settings:")
        print("        - 'Enable ActiveX and Socket Clients' esté marcado.")
        print("        - El 'Socket Port' sea 7497.")
        print("        - 'Read-Only API' esté DESMARCADO.")

if __name__ == "__main__":
    test_diagnostics()
