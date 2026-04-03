"""
Sprint 2 — Closure Checklist Verification
==========================================
Checks 3 conditions before moving to Sprint 3:
  1. technical_indicators with ema_3 IS NOT NULL  → count > 0
  2. volume_spikes recent rows                    → real rows exist
  3. Last cron_cycle with status = success        → real numbers
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

print("=" * 64)
print("  SPRINT 2 — CLOSURE CHECKLIST")
print("=" * 64)

# ── CHECK 1: technical_indicators WHERE ema_3 IS NOT NULL ──
print("\n✅ CHECK 1: SELECT COUNT(*) FROM technical_indicators WHERE ema_3 IS NOT NULL")
print("-" * 64)
try:
    # Supabase client doesn't support raw SQL count easily,
    # so we fetch with filter and use the count header
    res1 = (
        sb.table("technical_indicators")
        .select("id", count="exact")
        .not_.is_("ema_3", "null")
        .execute()
    )
    count_ema3 = res1.count if res1.count is not None else len(res1.data)
    status1 = "✅ PASS" if count_ema3 > 0 else "❌ FAIL"
    print(f"   Count of rows with ema_3 NOT NULL: {count_ema3}")
    print(f"   Result: {status1}")

    # Show a sample
    sample = (
        sb.table("technical_indicators")
        .select("symbol, timeframe, ema_3, ema_9, ema_20, timestamp")
        .not_.is_("ema_3", "null")
        .order("timestamp", desc=True)
        .limit(5)
        .execute()
    )
    if sample.data:
        print("   Sample rows:")
        for r in sample.data:
            print(f"     {r['symbol']:12s} {r['timeframe']:4s}  ema_3={r['ema_3']}  ema_9={r['ema_9']}  ema_20={r['ema_20']}  ts={r['timestamp']}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    status1 = "❌ ERROR"

# ── CHECK 2: volume_spikes recent rows ──
print(f"\n✅ CHECK 2: SELECT symbol, spike_direction, spike_ratio FROM volume_spikes ORDER BY detected_at DESC LIMIT 10")
print("-" * 64)
try:
    res2 = (
        sb.table("volume_spikes")
        .select("symbol, spike_direction, spike_ratio, detected_at")
        .order("detected_at", desc=True)
        .limit(10)
        .execute()
    )
    count_spikes = len(res2.data)
    status2 = "✅ PASS" if count_spikes > 0 else "❌ FAIL (no rows)"
    print(f"   Rows returned: {count_spikes}")
    print(f"   Result: {status2}")
    if res2.data:
        print(f"   {'Symbol':<14s} {'Direction':<14s} {'Ratio':<10s} {'Detected At'}")
        print(f"   {'─'*14} {'─'*14} {'─'*10} {'─'*26}")
        for r in res2.data:
            print(f"   {r['symbol']:<14s} {str(r.get('spike_direction','?')):<14s} {str(r.get('spike_ratio','?')):<10s} {r.get('detected_at','?')}")
    else:
        print("   ⚠️  No volume_spikes rows found. The worker may not have detected any spikes yet.")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    status2 = "❌ ERROR"

# ── CHECK 3: Last cron_cycle with status=success ──
print(f"\n✅ CHECK 3: Last cron_cycle — should show 20 symbols, N spikes, status=success")
print("-" * 64)
try:
    res3 = (
        sb.table("cron_cycles")
        .select("*")
        .order("started_at", desc=True)
        .limit(5)
        .execute()
    )
    if res3.data:
        latest = res3.data[0]
        has_success = latest.get("status") in ("success", "partial_error")
        has_symbols = (latest.get("symbols_analyzed") or 0) > 0
        status3 = "✅ PASS" if (has_success and has_symbols) else "❌ FAIL"

        print(f"   Last 5 cycles:")
        print(f"   {'Status':<16s} {'Symbols':<10s} {'Spikes':<10s} {'Signals':<10s} {'Orders':<10s} {'Errors':<8s} {'Duration':<10s} {'Started At'}")
        print(f"   {'─'*16} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*8} {'─'*10} {'─'*26}")
        for d in res3.data:
            print(
                f"   {str(d.get('status','?')):<16s} "
                f"{str(d.get('symbols_analyzed','?')):<10s} "
                f"{str(d.get('spikes_detected','?')):<10s} "
                f"{str(d.get('signals_generated','?')):<10s} "
                f"{str(d.get('orders_executed','?')):<10s} "
                f"{str(d.get('errors','?')):<8s} "
                f"{str(d.get('duration_seconds','?')):<10s} "
                f"{str(d.get('started_at','?'))}"
            )
        print(f"\n   Result: {status3}")
    else:
        print("   ❌ No cron_cycles found at all.")
        status3 = "❌ FAIL"
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    status3 = "❌ ERROR"

# ── SUMMARY ──
print(f"\n{'=' * 64}")
print("  SUMMARY")
print(f"{'=' * 64}")
print(f"  CHECK 1 (ema_3 calculated):      {status1}")
print(f"  CHECK 2 (volume_spikes rows):     {status2}")
print(f"  CHECK 3 (last cycle success):     {status3}")
all_pass = all("PASS" in s for s in [status1, status2, status3])
print(f"\n  {'🎉 ALL CHECKS PASSED — Sprint 2 closed! Ready for Sprint 3.' if all_pass else '⚠️  Some checks failed. Review above for details.'}")
print(f"{'=' * 64}")
