import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table("positions").select("*").eq("status", "open").execute()
print("OPEN POSITIONS IN 'positions' DB TABLE (CRYPTO):")
for p in res.data or []:
    print(f"ID: {p['id']}, Symbol: {p['symbol']}, Side: {p['side']}, Entry: {p['entry_price']}, Size: {p['size']}, Mode: {p.get('mode')}, Rule: {p.get('rule_code')}, OpenedAt: {p['opened_at']}")

cfg_res = sb.table("trading_config").select("*").eq("id", 1).maybe_single().execute()
print("\nTRADING CONFIG ID 1:")
if cfg_res and cfg_res.data:
    print(f"paper_trading: {cfg_res.data.get('paper_trading')}")
    print(f"mode: {cfg_res.data.get('mode')}")
    print(f"regime_params: {cfg_res.data.get('regime_params')}")
