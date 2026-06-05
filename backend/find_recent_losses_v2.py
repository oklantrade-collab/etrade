import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def find_losses():
    sb = get_supabase()
    
    print("=== Crypto Losses ===")
    try:
        res = sb.table('positions').select('*').eq('status', 'closed').order('opened_at', desc=True).limit(200).execute()
        losses = [p for p in res.data if float(p.get('realized_pnl') or 0) < 0]
        for p in losses[:5]:
            print(f"Symbol: {p['symbol']} | Side: {p['side']} | Size: {p['size']} | Entry: {p['entry_price']} | Exit PnL: {p['realized_pnl']} | Date: {p['opened_at']}")
        if not losses:
            # Fallback to general closed if no losses in database
            print("No negative realized_pnl, printing general closed:")
            for p in res.data[:5]:
                print(f"Symbol: {p['symbol']} | Side: {p['side']} | Size: {p['size']} | Entry: {p['entry_price']} | Date: {p['opened_at']}")
    except Exception as e:
        print(f"Error Crypto: {e}")
        
    print("\n=== Forex Losses ===")
    try:
        res = sb.table('forex_positions').select('*').eq('status', 'closed').order('opened_at', desc=True).limit(200).execute()
        losses = [p for p in res.data if float(p.get('pnl_usd') or 0) < 0]
        for p in losses[:5]:
            print(f"Symbol: {p['symbol']} | Side: {p['side']} | Lots: {p['lots']} | Entry: {p['entry_price']} | Exit: {p['current_price']} | PnL USD: {p['pnl_usd']} | Date: {p['opened_at']}")
        if not losses:
            print("No negative pnl_usd, printing general closed:")
            for p in res.data[:5]:
                print(f"Symbol: {p['symbol']} | Side: {p['side']} | Lots: {p['lots']} | Entry: {p['entry_price']} | Exit: {p['current_price']} | Date: {p['opened_at']}")
    except Exception as e:
        print(f"Error Forex: {e}")

    print("\n=== Stocks Losses ===")
    try:
        res = sb.table('trades_journal').select('*').eq('result', 'loss').order('exit_date', desc=True).limit(5).execute()
        for p in res.data:
            print(f"Symbol: {p['ticker']} | Shares: {p['shares']} | Entry: {p['entry_price']} | Exit: {p['exit_price']} | PnL USD: {p['pnl_usd']} | Date: {p['exit_date']}")
    except Exception as e:
        print(f"Error Stocks: {e}")

if __name__ == "__main__":
    find_losses()
