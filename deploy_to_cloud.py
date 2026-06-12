import subprocess
import os

# Configuración DigitalOcean
SERVER_IP = "165.22.87.171"
SSH_KEY = "C:/Users/jyups/.ssh/etrade_cloud_key"
REMOTE_PATH = "/home/etrade/etrade/backend"

# Archivos críticos para sincronizar
files_to_sync = [
    "app/strategy/smart_loss_guard.py",
    "app/strategy/dca_manager.py",
    "app/strategy/profit_capture.py",
    "app/strategy/profit_ladder.py",
    "app/strategy/erep_manager.py",
    "app/strategy/macro_filter.py",
    "app/workers/scheduler.py",
    "app/analysis/indicators_v2.py",
    "app/analysis/swing_detector.py",
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
    "app/core/logger.py",
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
    "app/api/portfolio.py",
    "app/api/positions.py",
    "app/analysis/fundamental_scorer.py",
    "app/stocks/universe_builder.py",
    "app/workers/performance_monitor.py",
    "app/core/symbol_state.py",
    "app/execution/data_provider.py",
    "app/data/yfinance_provider.py",
    "app/data/ib_scanner.py",
    "app/core/startup.py",
    "app/candle_signals/candle_execution.py",
    "app/ws/ws_manager.py",
    "app/core/market_hours.py",
    "app/execution/providers/ctrader_provider.py"
]

def check_syntax():
    import py_compile
    print("=" * 60)
    print("Ejecutando analisis sintactico preventivo pre-despliegue...")
    print("=" * 60)
    all_ok = True
    for f in files_to_sync:
        local_file = os.path.join("c:/Fuentes/eTrade/backend", f)
        try:
            py_compile.compile(local_file, doraise=True)
        except py_compile.PyCompileError as e:
            print(f"[FAIL] ERROR SINTACTICO DETECTADO EN: {f}")
            print(str(e))
            all_ok = False
        except FileNotFoundError:
            print(f"[WARN] Archivo no encontrado: {f}")
            
    if not all_ok:
        print("\n[CRITICAL] ERROR: El analisis estatico de codigo ha fallado.")
        print("El despliegue ha sido CANCELADO por medidas de seguridad preventiva.")
        print("=" * 60)
        return False
    
    print("\n[SUCCESS] Todos los archivos pasaron la validacion sintactica.")
    print("=" * 60)
    return True

def deploy():
    if not check_syntax():
        return
        
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
        import time
        time.sleep(1)

    print("\nReiniciando servicios en el servidor...")
    restart_cmd = [
        "ssh", "-i", SSH_KEY, 
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        "systemctl restart etrade-crypto etrade-forex etrade-forex-scheduler etrade-api etrade-stocks"
    ]
    subprocess.run(restart_cmd, check=True)
    print("¡Despliegue y reinicio completado!")

if __name__ == "__main__":
    deploy()
