import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.execution.binance_connector import get_client, get_account_balance, get_symbol_info

client = get_client()
balance = get_account_balance(client, 'USDT')
print(f'✅ Conexión OK | Balance USDT Testnet: ${balance:,.2f}')

btc_info = get_symbol_info(client, 'BTCUSDT')
print(f'✅ BTCUSDT info: step_size={btc_info["step_size"]}')
