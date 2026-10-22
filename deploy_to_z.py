import shutil
import os

files_to_copy = [
    # Módulos Core & Filtros Macro / Riesgo (Propuestas #1, #2, #3, #7)
    "backend/app/core/macro_sentiment_engine.py",
    "backend/app/core/relative_strength.py",
    "backend/app/core/cost_guard.py",
    "backend/app/core/circuit_breaker.py",
    "backend/app/core/structural_regime_engine.py",

    # Opciones & Pre-Trade Validator
    "backend/app/options/pre_trade_validator.py",
    "backend/app/options/score.py",
    "backend/app/api/options.py",

    # Stocks Orchestration & Cost Basis Buffer Exits
    "backend/app/stocks/stocks_orchestrator.py",
    "backend/app/stocks/stocks_order_executor.py",
    "backend/app/stocks/stocks_adaptive_tp_v2.py",
    "backend/app/stocks/aduana_stocks_exit_engine.py",

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
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"Copiado a Z: {f}")
        else:
            print(f"No existe: {src}")
    print("Sincronización a APOLO (Z:) finalizada.")
