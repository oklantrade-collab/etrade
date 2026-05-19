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
    "app/workers/forex_scheduler.py",
    "app/workers/forex_execution_service.py",
    "app/strategy/virtual_sl_recovery.py",
    "app/workers/stocks_scheduler.py",
    "app/analysis/stocks_indicators.py",
    "app/stocks/apex_score.py",
    "app/stocks/apex_scheduler.py",
    "app/stocks/stocks_rule_engine.py",
    "app/stocks/stocks_orchestrator.py",
    "app/core/safety_manager.py",
    "app/strategy/swing_orders.py",
    "app/strategy/capital_protection.py",
    "app/strategy/proactive_exit.py",
    "app/strategy/position_guards.py",
    "app/core/position_monitor.py",
    "app/strategy/rule_engine.py",
    "app/workers/unified_trading_worker.py",
    "app/execution/oco_builder.py",
    "app/core/position_sizing.py",
    "app/strategy/dynamic_sl_manager.py",
    "app/stocks/stocks_adaptive_tp.py",
    "app/stocks/stocks_adaptive_tp_v2.py",
    "app/stocks/stocks_tp_manager.py",
    "app/stocks/position_monitor.py",
    "app/strategy/risk_manager.py",
    "app/strategy/signal_generator.py",
    "app/api/stocks.py",
    "app/api/market.py",
    "app/api/forex.py",
    "app/api/crypto.py",
    "app/analysis/fundamental_scorer.py",
    "app/stocks/universe_builder.py",
    "app/workers/performance_monitor.py",
    "app/core/symbol_state.py"
]

def deploy():
    for f in files_to_sync:
        local_file = os.path.join("c:/Fuentes/eTrade/backend", f)
        remote_file = f"root@{SERVER_IP}:{REMOTE_PATH}/{f}"
        
        print(f"Desplegando {f}...")
        cmd = [
            "scp", "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            local_file, remote_file
        ]
        subprocess.run(cmd, check=True)

    print("\nReiniciando servicios en el servidor...")
    restart_cmd = [
        "ssh", "-i", SSH_KEY, 
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        "systemctl restart etrade-crypto etrade-forex etrade-api etrade-stocks"
    ]
    subprocess.run(restart_cmd, check=True)
    print("¡Despliegue y reinicio completado!")

if __name__ == "__main__":
    deploy()
