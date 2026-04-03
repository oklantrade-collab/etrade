import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env")
    exit(1)

sb = create_client(url, key)

# Insertar 10 trades perdedores para Aa22 para forzar la alerta
trades = []
for i in range(10):
    trades.append({
        'symbol':        'BTCUSDT',
        'side':          'long',
        'rule_code':     'Aa22',
        'regime':        'riesgo_medio',
        'total_pnl_usd': -1.50,
        'total_pnl_pct': -0.80,
        'close_reason':  'sl',
        'mode':          'paper',
        'opened_at':     datetime.now(timezone.utc).isoformat(),
        'closed_at':     datetime.now(timezone.utc).isoformat(),
    })

try:
    sb.table('paper_trades').insert(trades).execute()
    print("Trades insertados. Esperar siguiente ciclo de 15m para alerta.")
except Exception as e:
    print(f"Error insertando trades: {e}")
