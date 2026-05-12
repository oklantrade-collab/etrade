import subprocess
import os

# Configuración DigitalOcean
SERVER_IP = "207.154.224.71"
SSH_KEY = "C:/Users/jyups/.ssh/etrade_cloud_key"
REMOTE_PATH = "/home/etrade/etrade/backend"

# Archivos críticos para sincronizar
files_to_sync = [
    "app/workers/scheduler.py",
    "app/analysis/indicators_v2.py",
    "app/strategy/strategy_engine.py",
    "app/workers/forex_worker_standalone.py",
    "app/workers/forex_execution_service.py",
    "app/workers/stocks_scheduler.py",
    "app/stocks/apex_score.py",
    "app/stocks/stocks_rule_engine.py",
    "app/stocks/stocks_orchestrator.py"
]

def deploy():
    for f in files_to_sync:
        local_file = os.path.join("c:/Fuentes/eTrade/backend", f)
        remote_file = f"root@{SERVER_IP}:{REMOTE_PATH}/{f}"
        
        print(f"Desplegando {f}...")
        cmd = [
            "scp", "-i", SSH_KEY,
            local_file, remote_file
        ]
        subprocess.run(cmd, check=True)

    print("\nReiniciando servicios en el servidor...")
    restart_cmd = [
        "ssh", "-i", SSH_KEY, f"root@{SERVER_IP}",
        "systemctl restart etrade-crypto etrade-forex etrade-api etrade-stocks"
    ]
    subprocess.run(restart_cmd, check=True)
    print("¡Despliegue y reinicio completado!")

if __name__ == "__main__":
    deploy()
