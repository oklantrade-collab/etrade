import shutil
import os

files_to_copy = [
    # Módulos Core & Filtros Macro / Riesgo (Propuestas #1, #2, #3, #7)
    "backend/app/core/macro_sentiment_engine.py",
    "backend/app/core/relative_strength.py",
    "backend/app/core/cost_guard.py",
    "backend/app/core/circuit_breaker.py",
    "backend/app/core/structural_regime_engine.py",
    "backend/app/core/market_hours.py",

    # Opciones & Pre-Trade Validator
    "backend/app/options/pre_trade_validator.py",
    "backend/app/options/score.py",
    "backend/app/options/autonomous_options_dispatcher.py",
    "backend/app/options/opt_contract_picker.py",
    "backend/app/options/aduana_gap_runner_options.py",
    "backend/app/options/options_aduana.py",
    "backend/app/options/settings_defaults.py",
    "backend/app/options/stock_driven_options_scanner.py",
    "backend/app/api/options.py",

    # Stocks Orchestration & Cost Basis Buffer Exits
    "backend/app/stocks/stocks_orchestrator.py",
    "backend/app/stocks/stocks_order_executor.py",
    "backend/app/stocks/stocks_adaptive_tp_v2.py",
    "backend/app/stocks/aduana_stocks_exit_engine.py",
    "backend/app/stocks/aduana_gap_runner_engine.py",
    "backend/app/stocks/alpha_runner_scanner.py",
    "backend/app/stocks/bull_expansion_scanner.py",
    "backend/app/stocks/bear_rollover_scanner.py",
    "backend/app/stocks/catalyst_classifier.py",
    "backend/app/stocks/live_1h_candle_service.py",
    "backend/app/stocks/trap_shield.py",
    "backend/app/workers/stocks_scheduler.py",
    "backend/app/data/ib_scanner.py",
    "backend/tests/test_bull_expansion_scanner.py",
    "backend/tests/test_bear_rollover_scanner.py",
    "backend/tests/test_autonomous_options_dispatcher.py",

    # IBKR Bridge Worker (APOLO TWS Bridge + LMT Shield + Slippage Reconciliation)
    "backend/app/workers/ib_bridge_worker.py",

    # Otros módulos
    "backend/app/workers/forex_worker_standalone.py",
    "backend/app/workers/forex_execution_service.py",
    "backend/app/execution/providers/ctrader_provider.py",
]

source_base = "C:/Fuentes/eTrade"
target_base = "Z:/etrade"

if not os.path.exists(target_base):
    print(f"AVISO: {target_base} no está accesible en este momento. Conecte APOLO o monte la unidad Z: para sincronizar.")
else:
    for f in files_to_copy:
        src = os.path.join(source_base, f.replace("/", os.sep))
        dst = os.path.join(target_base, f.replace("/", os.sep))
        
        if os.path.exists(src):
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                print(f"Copiado a Z: {f}")
            except Exception as e:
                print(f"No se pudo copiar {f}: {e}")
        else:
            print(f"No existe: {src}")
    print("Sincronización a APOLO (Z:) finalizada.")
