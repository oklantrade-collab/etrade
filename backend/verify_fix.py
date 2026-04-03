import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

# Check Positions
res_pos = sb.table('positions').select('symbol, side, avg_entry_price').eq('status', 'open').execute()
res_snap = sb.table('market_snapshot').select('symbol, price').execute()
prices = {r['symbol']: r['price'] for r in res_snap.data}

print("CHECK A — Signos de P&L %")
print("-" * 50)
for r in res_pos.data:
    sym = r['symbol']
    side = r['side']
    entry = r['avg_entry_price']
    actual = prices.get(sym, 0)
    side_mult = 1 if side.lower() == 'long' else -1
    pnl_pct = (actual - entry) / entry * 100 * side_mult
    print(f"{sym:9} | {side:5} | Ent: {entry:8} | Act: {actual:8} | PnL: {pnl_pct:>6.2f}%")

# Check Metrics
res_metrics = sb.table('paper_trades').select('id, symbol, total_pnl_usd, mode, closed_at').eq('mode', 'paper').gte('closed_at', '2026-03-16').execute()
print("\nCHECK B — Métricas en Paper (Desde 16 MAR)")
print("-" * 50)
total_pnl = 0
for t in res_metrics.data:
    val = float(t['total_pnl_usd'] or 0)
    total_pnl += val
    print(f"{t['symbol']:9} | {t['closed_at'][:10]} | PnL: ${val:>6.2f} | Mode: {t['mode']}")

print("-" * 50)
print(f"TOTAL TRADES: {len(res_metrics.data)}")
print(f"SUMA P&L USD: ${total_pnl:.2f}")
