from app.core.supabase_client import get_supabase

def recover_positions():
    sb = get_supabase()
    # 1. Recover Stocks Positions
    res = sb.table('stocks_positions').select('id, ticker').eq('status', 'error').gt('avg_price', 0).execute()
    count = 0
    for pos in res.data:
        sb.table('stocks_positions').update({
            'status': 'open',
            'sl_close_reason': None
        }).eq('id', pos['id']).execute()
        count += 1
    print(f"RECOVERED {count} STOCKS POSITIONS.")

    # 2. Sync state machine for recovered positions
    from app.core.symbol_state import SymbolStateMachine, SymbolState
    sm = SymbolStateMachine.get_instance()
    for pos in res.data:
        ticker = pos['ticker']
        ctx = sm.get(ticker)
        if ctx.state == SymbolState.NEUTRAL:
            ctx.state = SymbolState.LONG
            sm.save_to_db(ticker)
            print(f"Synced state machine for {ticker} -> LONG")

if __name__ == "__main__":
    recover_positions()
