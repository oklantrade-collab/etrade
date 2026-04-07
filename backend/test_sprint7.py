"""
eTrader v4.5 — Sprint 7 Integration Test
Tests the full Execution Layer: Order Executor + Position Monitor.
"""
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.stocks.order_executor import OrderExecutor
from app.stocks.position_monitor import PositionMonitor
from app.core.supabase_client import get_supabase

async def test_sprint7():
    print("=" * 60)
    print("  eTrader v4.5 — SPRINT 7 EXECUTION LAYER TEST")
    print("=" * 60)
    print()

    sb = get_supabase()

    # 1. Test Order Executor
    try:
        executor = OrderExecutor()
        await executor.load_config()
        print(f"✅ OrderExecutor initialized")
        print(f"   Paper Mode: {executor.paper_mode}")
        print(f"   Capital: ${executor.total_capital}")
        print(f"   Max Risk/Trade: {executor.max_risk_pct}%")
        print(f"   Max Positions: {executor.max_positions}")
        print(f"   Max Daily Loss: ${executor.max_daily_loss}")
    except Exception as e:
        print(f"❌ OrderExecutor init failed: {e}")
        return

    # 2. Check pending opportunities
    try:
        pending = sb.table("trade_opportunities")\
            .select("id, ticker, meta_score, status")\
            .eq("status", "pending")\
            .order("meta_score", desc=True)\
            .limit(5)\
            .execute()
        print(f"\n📋 Pending Opportunities: {len(pending.data or [])}")
        for opp in (pending.data or []):
            print(f"   • {opp['ticker']} | MetaScore: {opp['meta_score']} | Status: {opp['status']}")
    except Exception as e:
        print(f"❌ Opportunities query failed: {e}")

    # 3. Execute pending opportunities (Paper Mode)
    try:
        print("\n🚀 Executing pending opportunities (PAPER MODE)...")
        results = await executor.execute_pending_opportunities()
        print(f"✅ Execution completed: {len(results)} trade(s)")
        for r in results:
            print(f"   • {r.get('ticker', '?')} → {r.get('status', '?')} "
                  f"| Shares: {r.get('shares', '?')} | Entry: ${r.get('entry', 0):.2f}")
    except Exception as e:
        print(f"❌ Execution failed: {e}")

    # 4. Test Position Monitor
    try:
        monitor = PositionMonitor()
        print("\n👁️ Checking active positions...")
        await monitor.check_all_positions()
        
        active = sb.table("trades_active")\
            .select("ticker, shares, entry_price, stop_loss, unrealized_pnl, status")\
            .eq("status", "active")\
            .execute()
        print(f"✅ Active Positions: {len(active.data or [])}")
        for pos in (active.data or []):
            pnl = float(pos.get("unrealized_pnl") or 0)
            print(f"   • {pos['ticker']} | {pos['shares']}x @ ${pos['entry_price']:.2f} "
                  f"| SL=${pos['stop_loss']:.2f} | P&L: ${pnl:+.2f}")
    except Exception as e:
        print(f"❌ Monitor failed: {e}")

    # 5. Check trades_journal
    try:
        journal = sb.table("trades_journal")\
            .select("ticker, result, pnl_usd, exit_reason")\
            .order("exit_date", desc=True)\
            .limit(5)\
            .execute()
        print(f"\n📒 Recent Journal Entries: {len(journal.data or [])}")
        for j in (journal.data or []):
            pnl = float(j.get("pnl_usd") or 0)
            print(f"   • {j['ticker']} | {j['result']} | ${pnl:+.2f} | {j['exit_reason']}")
    except Exception as e:
        print(f"❌ Journal query failed: {e}")

    # 6. IB Status
    try:
        from app.data.ib_provider import IB_AVAILABLE, get_ib_connection
        print(f"\n🔌 IB TWS API Available: {IB_AVAILABLE}")
        if IB_AVAILABLE:
            ib = get_ib_connection()
            if ib:
                status = ib.get_status()
                print(f"   Connected: {status['connected']}")
                print(f"   Next Order ID: {status['next_order_id']}")
        else:
            print("   ⚠️ ibapi not installed — Paper Mode only")
    except Exception as e:
        print(f"   IB Status check: {e}")

    print()
    print("=" * 60)
    print("  Sprint 7 — Execution Layer Test Completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_sprint7())
