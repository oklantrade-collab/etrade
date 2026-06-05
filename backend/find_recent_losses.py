import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def find_losses():
    sb = get_supabase()
    
    print("=== Crypto Closed Losses (positions) ===")
    try:
        res = sb.table('positions').select('*').eq('status', 'closed').order('closed_at', desc=True).limit(50).execute()
        losses = [p for p in res.data if float(p.get('realized_pnl') or 0) < 0]
        for p in losses[:5]:
            print(f"ID: {p['id']} | Ticker: {p['symbol']} | Side: {p['side']} | Entry: {p['entry_price']} | Exit: {p['exit_price']} | PnL: {p['realized_pnl']} | Closed At: {p['closed_at']}")
        if not losses:
            print("No closed losses found in 'positions'.")
    except Exception as e:
        print(f"Error querying positions: {e}")

    print("\n=== Forex Closed Losses (forex_positions) ===")
    try:
        res = sb.table('forex_positions').select('*').eq('status', 'closed').order('updated_at', desc=True).limit(50).execute()
        # Let's see what columns represent pnl or if there are any closed positions
        for p in res.data[:5]:
            print(f"ID: {p['id']} | Ticker: {p['symbol']} | Lots: {p['lots']} | Entry: {p['entry_price']} | Exit: {p['exit_price']} | Status: {p['status']} | Updated: {p['updated_at']}")
    except Exception as e:
        print(f"Error querying forex_positions: {e}")

    print("\n=== Stocks Closed Losses (trades_journal) ===")
    try:
        res = sb.table('trades_journal').select('*').eq('result', 'loss').order('exit_date', desc=True).limit(5).execute()
        for p in res.data:
            print(f"ID: {p.get('id')} | Ticker: {p['ticker']} | Shares: {p['shares']} | Entry: {p['entry_price']} | Exit: {p['exit_price']} | PnL USD: {p['pnl_usd']} | Exit Date: {p['exit_date']}")
        if not res.data:
            print("No losses found in 'trades_journal'.")
    except Exception as e:
        print(f"Error querying trades_journal: {e}")

if __name__ == "__main__":
    find_losses()
