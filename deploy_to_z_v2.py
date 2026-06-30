import shutil
import os

files_to_copy = [
    "backend/app/core/position_monitor.py",
    "backend/app/data/ib_scanner.py"
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
