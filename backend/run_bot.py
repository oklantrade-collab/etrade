import time
import subprocess
import sys

def run_worker():
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando ciclo de trading...")
    try:
        # Ejecuta tu worker de eTrader
        subprocess.run([sys.executable, "-m", "app.workers.unified_trading_worker"], check=True)
        print("Ciclo completado con éxito.")
    except Exception as e:
        print(f"Error durante la ejecución: {e}")

if __name__ == "__main__":
    print("Bot de eTrader iniciado (Local). Presiona Ctrl+C para detener.")
    while True:
        run_worker()
        print("Esperando 15 minutos para el próximo ciclo...")
        time.sleep(900)  # 900 segundos = 15 minutos