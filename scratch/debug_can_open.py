import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
from app.strategy.position_guards import can_open_position

sb = get_supabase()

res = sb.table("forex_positions").select("*").eq("status", "open").execute()
open_positions = res.data or []

print(f"TOTAL OPEN POSITIONS IN DB ({len(open_positions)}):")
for p in open_positions:
    print(f" - ID: {p['id']}, Symbol: {p['symbol']}, Side: {p['side']}, OpenedAt: {p['opened_at']}, Rule: {p.get('rule_code')}")

active_symbols = set(p['symbol'] for p in open_positions)
print(f"ACTIVE UNIQUE SYMBOLS SET: {active_symbols}")

check_eurusd = can_open_position(
    symbol='EURUSD',
    direction='long',
    market_type='forex_futures',
    open_positions=open_positions
)
print(f"\nTEST can_open_position('EURUSD'): {check_eurusd}")

tc_res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
tc_data = tc_res.data if tc_res and tc_res.data else {}
reg_params = tc_data.get('regime_params', {}) or {}
print(f"\nTRADING_CONFIG regime_params: {reg_params}")
