
import asyncio
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.supabase_client import get_supabase

async def verify_system():
    print("--- System Verification ---")
    sb = get_supabase()
    
    # 1. Check Global State
    print("\n1. Checking bot_global_state...")
    gs = sb.table("bot_global_state").select("*").eq("id", 1).maybe_single().execute()
    if gs.data:
        print(f"Global State Data: {gs.data}")
    else:
        print("No global state found.")

    # 2. Check Open Positions
    print("\n2. Checking active positions in memory (via DB sync)...")
    pos = sb.table("positions").select("symbol, side, entry_price, sl_price, status, opened_at").eq("status", "open").execute()
    print(f"Active positions in DB: {len(pos.data)}")
    for p in pos.data:
        print(f" - {p['symbol']} ({p['side']}): Entry {p['entry_price']} | SL {p['sl_price']} | Opened: {p['opened_at']}")

    # 3. Check Recent Signals
    print("\n3. Checking recent signals (last 30m)...")
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    signals = sb.table("trading_signals").select("symbol, signal_type, score_final, created_at").gte("created_at", cutoff).execute()
    print(f"Recent signals: {len(signals.data)}")

    # 4. Check Pilot Diagnostics
    print("\n4. Checking pilot diagnostics (last 5m)...")
    cutoff_diag = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    diags = sb.table("pilot_diagnostics").select("symbol, rule_triggered, entry_blocked_by, timestamp").gte("timestamp", cutoff_diag).limit(5).execute()
    for d in diags.data:
        print(f" - {d['symbol']}: Triggered={d['rule_triggered']} | BlockedBy={d['entry_blocked_by']} | Time={d['timestamp']}")

if __name__ == "__main__":
    asyncio.run(verify_system())
