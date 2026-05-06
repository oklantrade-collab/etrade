import shutil
import os

files_to_copy = [
    "backend/app/workers/forex_worker_standalone.py",
    "backend/app/execution/providers/ctrader_provider.py",
    "frontend/components/TradeMarkerChart.tsx",
    "frontend/app/dashboard/page.tsx",
    "frontend/app/portfolio/page.tsx",
    "backend/cleanup_forex_ficticio.py",
    "backend/migration_snapshot_fix.py"
]

source_base = "C:/Fuentes/eTrade"
target_base = "Z:/etrade"

for f in files_to_copy:
    src = os.path.join(source_base, f)
    dst = os.path.join(target_base, f)
    
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Copiado: {f}")
