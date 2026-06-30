import asyncio
import sys
from app.core.supabase_client import get_supabase
from app.stocks.stocks_orchestrator import _get_df, evaluate_5m_breakout, check_active_rules
from app.stocks.stocks_rule_engine import StocksRuleEngine

async def main():
    sb = get_supabase()
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'BRBR'
    
    snap_res = sb.table('market_snapshot').select('*').eq('symbol', ticker).limit(1).execute()
    snap = snap_res.data[0] if snap_res.data else {}
    
    df_5m = await _get_df(ticker, '5m')
    df_1d = await _get_df(ticker, '1d')
    
    # Check Breakout
    b_out = evaluate_5m_breakout(ticker, df_5m, df_1d, snap)
    print(f"Breakout 5m result for {ticker}: {b_out['reason']}")
    
    # Check Rule Engine directly to get failures
    engine = StocksRuleEngine.get_instance()
    if not engine.rules:
        engine.load_rules()
        
    context = engine.build_context(
        ticker     = ticker,
        snap       = snap,
        ia_score   = float(snap.get('meta_score', 0) or 0) / 10,
        tech_score = float(snap.get('technical_score', 0) or 0),
        rvol       = float(snap.get('rvol', 1.0) or 1.0),
        pine_signal = str(snap.get('pinescript_signal', '') or ''),
    )
    
    results = engine.evaluate_all(context=context, direction='buy')
    
    print("\n--- Rule Failures ---")
    for r in results:
        if not r['triggered']:
            print(f"Rule: {r['rule_code']}")
            for f in r['failures']:
                print(f"  - {f}")

if __name__ == '__main__':
    asyncio.run(main())
