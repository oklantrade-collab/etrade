import os
import sys
import json
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

strategies = ['Aa30', 'AaHot', 'Bb30']

print("\n=== CRYPTO PERFORMANCE ===")
for strat in strategies:
    pos = sb.table('positions').select('pnl_pct, status').eq('rule_code', strat).execute()
    trades = pos.data
    closed = [t for t in trades if t['status'] == 'closed']
    if not closed:
        print(f"{strat}: No closed trades")
        continue
    wins = len([t for t in closed if (t.get('pnl_pct') or 0) > 0])
    win_rate = (wins / len(closed)) * 100
    total_pnl = sum((t.get('pnl_pct') or 0) for t in closed)
    print(f"{strat}: {len(closed)} trades, Win Rate: {win_rate:.1f}%, Total PnL Pct: {total_pnl:.2f}%")

print("\n=== FOREX PERFORMANCE ===")
for strat in strategies:
    pos = sb.table('forex_positions').select('pnl_usd, status, pips_pnl').eq('rule_code', strat).execute()
    trades = pos.data
    closed = [t for t in trades if t['status'] == 'closed']
    if not closed:
        print(f"{strat}: No closed trades")
        continue
    wins = len([t for t in closed if (t.get('pnl_usd') or 0) > 0])
    win_rate = (wins / len(closed)) * 100
    total_pnl = sum((t.get('pnl_usd') or 0) for t in closed)
    total_pips = sum((t.get('pips_pnl') or 0) for t in closed)
    print(f"{strat}: {len(closed)} trades, Win Rate: {win_rate:.1f}%, Total PnL: ${total_pnl:.2f}, Total Pips: {total_pips:.1f}")
