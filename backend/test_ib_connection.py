import os
from app.data.ib_provider import get_ib_connection

def test_ib_connectivity():
    print("--- Probando Conexión a Interactive Brokers (TWS) ---")
    ib = get_ib_connection()
    if not ib:
        print("❌ Error: No se pudo instanciar la conexión. Verifica que 'ibapi' esté instalado.")
        return

    # Intentamos conectar
    connected = ib.connect_tws(host="127.0.0.1", port=7497, client_id=10)
    
    if connected:
        print("✅ ¡ÉXITO! eTrade se conectó correctamente a tu TWS.")
        status = ib.get_status()
        print(f"Estado de la conexión: {status}")
        ib.disconnect_tws()
    else:
        print("❌ Fallo de conexión. Verifica que TWS esté abierta y la API habilitada en el puerto 7497.")

if __name__ == "__main__":
    test_ib_connectivity()
