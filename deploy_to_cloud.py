import subprocess
import os
import sys

# Configuración DigitalOcean
SERVER_IP = "165.22.87.171"
SSH_KEY = "C:/Users/jyups/.ssh/etrade_cloud_key"
REMOTE_PATH = "/home/etrade/etrade/backend"
ROOT_REMOTE_PATH = "/home/etrade/etrade"

# Archivos críticos para sincronizar (relativos a backend)
files_to_sync = [
    # RADAR
    "app/radar/__init__.py",
    "app/radar/config.py",
    "app/radar/slope_classifier.py",
    "app/radar/crossover_detector.py",
    "app/radar/event_bus.py",
    "app/radar/radar_service.py",
    "app/radar/logger.py",

    # CASCADA
    "app/cascada/__init__.py",
    "app/cascada/config.py",
    "app/cascada/giveback_monitor.py",
    "app/cascada/level_evaluator.py",
    "app/cascada/cascada_engine.py",
    "app/cascada/cascada_manager.py",
    "app/cascada/logger.py",

    # API
    "app/api/radar_cascada.py",
    "app/api/halcon.py",
    "app/main.py",

    # Migraciones & Tests
    "migration_035_radar_cascada.sql",
    "migration_034_rebote_aduana.sql",
    "tests/test_radar_service.py",
    "tests/test_cascada_engine.py",

    # REBOTE / ADUANA
    "app/rebote_aduana/__init__.py",
    "app/rebote_aduana/config.py",
    "app/rebote_aduana/rebote_engine.py",
    "app/rebote_aduana/aduana_validator.py",
    "app/rebote_aduana/rebote_monitor.py",
    "app/rebote_aduana/logger.py",
    "app/rebote_aduana/scoring/__init__.py",
    "app/rebote_aduana/scoring/signal_fib_extreme.py",
    "app/rebote_aduana/scoring/signal_double_bottom.py",
    "app/rebote_aduana/scoring/signal_ema_squeeze.py",
    "app/rebote_aduana/scoring/signal_rsi_extreme.py",
    "app/rebote_aduana/scoring/signal_zone_confluence.py",
    "app/rebote_aduana/scoring/regime_local.py",
    "app/core/breakpoint_detector.py",
    "tests/test_rebote_engine.py",
    "tests/test_aduana_validator.py",
    "tests/test_breakpoint_detector.py",

    # HALCÓN CENTINELA
    "app/halcon_centinela/__init__.py",
    "app/halcon_centinela/config.py",
    "app/halcon_centinela/halcon_engine.py",
    "app/halcon_centinela/state_machine.py",
    "app/halcon_centinela/arbitrage.py",
    "app/halcon_centinela/centinela_monitor.py",
    "app/halcon_centinela/logger.py",
    "app/halcon_centinela/scoring/__init__.py",
    "app/halcon_centinela/scoring/score_1d.py",
    "app/halcon_centinela/scoring/score_4h.py",
    "app/halcon_centinela/scoring/score_15m.py",
    "app/halcon_centinela/scoring/score_5m.py",
    "app/halcon_centinela/scoring/score_1m.py",
    "app/halcon_centinela/scoring/rsi_component.py",
    "app/halcon_centinela/scoring/regime_filter.py",
    "app/halcon_centinela/scoring/compression_index.py",
    "app/halcon_centinela/scoring/volume_confirmation.py",
    "app/halcon_centinela/oraculo/__init__.py",
    "app/halcon_centinela/oraculo/calendar_service.py",
    "app/halcon_centinela/oraculo/pause_manager.py",
    "app/halcon_centinela/oraculo/bracket_manager.py",
    
    # API
    "app/api/halcon.py",
    "app/main.py",
    
    # Migraciones & Tests
    "migration_033_halcon_centinela.sql",
    "apply_migration_033.py",
    "tests/test_halcon_engine.py",
    "tests/test_centinela_state_machine.py",
    "tests/test_oraculo.py",

    # Core & Workers modificados
    "app/workers/forex_execution_service.py",
    "app/core/position_monitor.py",
    "app/core/symbol_state.py",
    "app/core/memory_store.py",
    "app/core/logger.py",

    # Otros módulos de la plataforma
    "app/strategy/quantum_squeeze_hedge.py",
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
    "app/core/pnl_calculator.py",
    "app/strategy/rule_engine.py",
    "app/workers/unified_trading_worker.py",
    "app/execution/oco_builder.py",
    "app/execution/order_manager.py",
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
    "app/analysis/capa3_fundamentals.py",
    "app/stocks/fundamental_analyzer.py",
    "app/workers/performance_monitor.py",
    "app/execution/data_provider.py",
    "app/data/yfinance_provider.py",
    "app/data/ib_scanner.py",
    "app/core/startup.py",
    "app/candle_signals/candle_execution.py",
    "app/candle_signals/candle_worker.py",
    "app/strategy/bollinger_exhaustion.py",
    "app/ws/ws_manager.py",
    "app/core/market_hours.py",
    "app/execution/providers/ctrader_provider.py",
    "app/analysis/fibonacci_bb.py",
    "app/strategy/emergency_guards.py",
    "app/api/strategies.py",
    "config_btc_pilot.json",
    "requirements.txt",
    ".env"
]

# Archivos frontend para sincronizar (relativos a root)
frontend_files = [
    ("frontend/app/halcon/page.tsx", "frontend/app/halcon/page.tsx"),
    ("frontend/components/HalconConfigModal.tsx", "frontend/components/HalconConfigModal.tsx"),
    ("frontend/components/widgets/CascadaWidget.tsx", "frontend/components/widgets/CascadaWidget.tsx"),
    ("frontend/components/widgets/RadarWidget.tsx", "frontend/components/widgets/RadarWidget.tsx"),
    ("frontend/components/widgets/HalconCentinelaWidget.tsx", "frontend/components/widgets/HalconCentinelaWidget.tsx"),
    ("frontend/app/forex/dashboard/page.tsx", "frontend/app/forex/dashboard/page.tsx"),
    ("frontend/app/dashboard/page.tsx", "frontend/app/dashboard/page.tsx")
]

def check_syntax():
    import py_compile
    print("=" * 60)
    print("Ejecutando analisis sintactico preventivo pre-despliegue...")
    print("=" * 60)
    all_ok = True
    for f in files_to_sync:
        if not f.endswith('.py'):
            continue
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

def ensure_remote_directories():
    print("Creando estructura de directorios remota...")
    dirs = [
        f"{REMOTE_PATH}/app/radar",
        f"{REMOTE_PATH}/app/cascada",
        f"{REMOTE_PATH}/app/rebote_aduana/scoring",
        f"{REMOTE_PATH}/app/halcon_centinela/scoring",
        f"{REMOTE_PATH}/app/halcon_centinela/oraculo",
        f"{REMOTE_PATH}/data",
        f"{REMOTE_PATH}/tests",
        f"{ROOT_REMOTE_PATH}/frontend/app/halcon",
        f"{ROOT_REMOTE_PATH}/frontend/components/widgets"
    ]
    mkdir_cmd = f"mkdir -p {' '.join(dirs)}"
    cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        mkdir_cmd
    ]
    subprocess.run(cmd, check=True)
    print("[OK] Directorios remotos listos.")

def deploy():
    if not check_syntax():
        return
    
    ensure_remote_directories()
        
    print("\nSincronizando archivos backend...")
    for f in files_to_sync:
        local_file = os.path.join("c:/Fuentes/eTrade/backend", f)
        if not os.path.exists(local_file):
            print(f"[SKIP] No existe localmente: {f}")
            continue
            
        remote_file = f"root@{SERVER_IP}:{REMOTE_PATH}/{f}"
        
        print(f"  -> {f}")
        cmd = [
            "scp", "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            local_file, remote_file
        ]
        subprocess.run(cmd, check=True)

    print("\nSincronizando archivos frontend...")
    for local_rel, remote_rel in frontend_files:
        local_file = os.path.join("c:/Fuentes/eTrade", local_rel)
        if os.path.exists(local_file):
            remote_file = f"root@{SERVER_IP}:{ROOT_REMOTE_PATH}/{remote_rel}"
            print(f"  -> {local_rel}")
            cmd = [
                "scp", "-i", SSH_KEY,
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                local_file, remote_file
            ]
            subprocess.run(cmd, check=True)

    print("\nAjustando permisos...")
    chown_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        f"chown -R etrade:etrade {ROOT_REMOTE_PATH}"
    ]
    subprocess.run(chown_cmd, check=True)

    print("\nReiniciando servicios en el servidor...")
    restart_cmd = [
        "ssh", "-i", SSH_KEY, 
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        "systemctl restart etrade-api etrade-forex etrade-forex-scheduler etrade-crypto etrade-stocks"
    ]
    subprocess.run(restart_cmd, check=True)
    print("¡Despliegue y reinicio completado!")

if __name__ == "__main__":
    deploy()
