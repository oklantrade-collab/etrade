from app.core.supabase_client import get_supabase
from app.core.symbol_state import SymbolStateMachine, SymbolState
import time

def robust_recovery():
    sb = get_supabase()
    sm = SymbolStateMachine.get_instance()
    
    # 1. Get all error positions with avg_price > 0
    res = sb.table('stocks_positions').select('*').eq('status', 'error').gt('avg_price', 0).execute()
    
    recovered = 0
    skipped = 0
    
    print(f"Starting recovery for {len(res.data)} positions...")
    
    for pos in res.data:
        ticker = pos['ticker']
        
        # Check if there's already an open position for this ticker
        existing = sb.table('stocks_positions').select('id').eq('ticker', ticker).eq('status', 'open').execute()
        
        if existing.data:
            print(f"Skipping {ticker}: Already has an open position (ID: {existing.data[0]['id']})")
            skipped += 1
            continue
            
        # Recover position
        try:
            sb.table('stocks_positions').update({
                'status': 'open',
                'sl_close_reason': None
            }).eq('id', pos['id']).execute()
            
            # Sync State Machine
            ctx = sm.get(ticker)
            ctx.state = SymbolState.LONG
            sm.save_to_db(ticker)
            
            print(f"Recovered {ticker} (Position ID: {pos['id']})")
            recovered += 1
        except Exception as e:
            print(f"Error recovering {ticker}: {e}")

    print(f"RECOVERY COMPLETE: {recovered} recovered, {skipped} skipped.")

if __name__ == "__main__":
    robust_recovery()
