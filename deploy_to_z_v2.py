import shutil
import os

files_to_copy = [
    "backend/app/analysis/stocks_indicators.py",
    "backend/app/stocks/position_monitor.py",
    "backend/app/strategy/proactive_exit.py",
    "backend/app/workers/forex_execution_service.py",
    "backend/app/core/position_monitor.py",
    "backend/app/strategy/swing_orders.py",
    "backend/app/workers/scheduler.py",
    "backend/app/workers/stocks_scheduler.py",
    "backend/app/stocks/apex_score.py",
    "backend/app/stocks/apex_scheduler.py",
    "backend/app/stocks/migrations/005_apex_scores_table.sql",
    "backend/app/api/stocks.py",
    "backend/app/execution/providers/ctrader_provider.py"
]

source_base = "C:/Fuentes/eTrade"
target_base = "Z:/etrade"

print(f"--- Iniciando despliegue al Servidor Z ({target_base}) ---")

for f in files_to_copy:
    src = os.path.join(source_base, f)
    dst = os.path.join(target_base, f)
    
    if os.path.exists(src):
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"SUCCESS: {f}")
        except Exception as e:
            print(f"ERROR copying {f}: {e}")
    else:
        print(f"NOT FOUND: {f}")

print("--- Despliegue completado ---")
