import asyncio
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase
from dateutil.parser import parse as parse_dt

async def remediate():
    print("[INFO] Starting Stock Closed Positions Remediation...")
    sb = get_supabase()

    # 1. Fetch all closed stock positions
    pos_res = sb.table("stocks_positions").select("*").eq("status", "closed").execute()
    closed_positions = pos_res.data or []
    print(f"[INFO] Found {len(closed_positions)} closed positions in stocks_positions.")

    # 2. Fetch all journal entries to check for duplicates
    journal_res = sb.table("trades_journal").select("ticker, entry_date, exit_date, pnl_usd").execute()
    journal_entries = journal_res.data or []
    print(f"[INFO] Found {len(journal_entries)} existing journal entries in trades_journal.")

    # Build a lookup set of existing journal entries by ticker and exit_date
    existing_lookup = set()
    for entry in journal_entries:
        ticker = entry.get("ticker")
        exit_date = entry.get("exit_date")
        if ticker and exit_date:
            try:
                # Normalize exit_date string to allow matching
                parsed_exit = parse_dt(exit_date).replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M")
                existing_lookup.add((ticker, parsed_exit))
            except Exception:
                pass

    missing_count = 0
    remediated_count = 0

    # 3. Check and insert missing positions
    for pos in closed_positions:
        ticker = pos.get("ticker")
        exit_date_str = pos.get("updated_at") or pos.get("closed_at")
        
        if not ticker or not exit_date_str:
            continue

        try:
            parsed_exit = parse_dt(exit_date_str).replace(tzinfo=timezone.utc)
            exit_key = parsed_exit.strftime("%Y-%m-%d %H:%M")
        except Exception:
            continue

        # Check if this position is already in the journal
        if (ticker, exit_key) in existing_lookup:
            continue

        missing_count += 1
        print(f"[WARNING] Missing journal entry for {ticker} closed on {exit_date_str}.")

        # Reconstruct the journal entry
        avg_entry = float(pos.get("avg_price") or pos.get("entry_price") or 0.0)
        exit_price = float(pos.get("exit_price") or avg_entry)
        shares = float(pos.get("shares") or 0.0)
        pnl_usd = float(pos.get("unrealized_pnl") or pos.get("pnl_usd") or (exit_price - avg_entry) * shares)
        pnl_pct = float(pos.get("unrealized_pnl_pct") or pos.get("pnl_pct") or (((exit_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else 0.0))

        journal_entry = {
            "ticker": ticker,
            "shares": int(shares),
            "entry_price": round(avg_entry, 4),
            "exit_price": round(exit_price, 4),
            "entry_date": pos.get("first_buy_at") or pos.get("entry_date") or pos.get("created_at"),
            "exit_date": exit_date_str,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
            "result": "win" if pnl_usd > 0 else "loss",
            "exit_reason": pos.get("close_reason") or pos.get("exit_reason") or "REMEDIATED",
            "trade_type": pos.get("strategy") or pos.get("rule_code") or "V5_INDUSTRIAL"
        }

        try:
            # Insert into Supabase
            sb.table("trades_journal").insert(journal_entry).execute()
            remediated_count += 1
            print(f"[SUCCESS] Successfully remediated and inserted journal entry for {ticker} (PnL: ${pnl_usd:.2f})")
        except Exception as e:
            print(f"[ERROR] Failed to insert journal entry for {ticker}: {e}")

    print(f"[INFO] Remediation completed! Checked {len(closed_positions)} positions, found {missing_count} missing, successfully remediated {remediated_count}.")

if __name__ == "__main__":
    asyncio.run(remediate())
