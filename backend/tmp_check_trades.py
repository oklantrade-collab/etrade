import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_trades():
    sb = get_supabase()
    # Check paper_trades or orders
    trades = sb.table('paper_trades').select('*').in_('symbol', ['BTCUSDT', 'BTC/USDT']).order('created_at', desc=True).limit(10).execute().data
    for t in trades:
        print(f"Time: {t['created_at']} | Side: {t['side']} | Rule: {t.get('rule_code')} | PnL: {t.get('pnl_pct')}%")
        print(f"  Entry: {t['entry_price']} | SL: {t['sl_price']} | TP: {t['tp_price']}")
        # print(f"  Metadata: {json.dumps(t.get('metadata', {}), indent=2)}")

if __name__ == "__main__":
    asyncio.run(check_trades())
