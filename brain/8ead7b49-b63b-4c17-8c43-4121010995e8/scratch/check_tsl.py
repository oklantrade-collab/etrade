import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv('c:/Fuentes/eTrade/backend/.env')

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

if "--closed" in sys.argv:
    ticker = sys.argv[sys.argv.index("--closed") + 1]
    print(f"Checking journal for {ticker}...")
    res = sb.table('trades_journal').select('*').eq('ticker', ticker).order('closed_at', desc=True).limit(5).execute()
    if res.data:
        for j in res.data:
            print(f"{j.get('closed_at')} | {j.get('ticker')} | P&L: {j.get('pnl_usd')} | Reason: {j.get('exit_reason')}")
    else:
        print(f"No journal entries found for {ticker}.")
    sys.exit(0)

if "--logs" in sys.argv or "--logs_module" in sys.argv:
    module = 'position_monitor'
    limit = 20
    if "--logs_module" in sys.argv:
        idx = sys.argv.index("--logs_module")
        if idx + 1 < len(sys.argv):
            module = sys.argv[idx+1]
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx+1])
            
    print(f"Fetching last {limit} logs for {module}...")
    query = sb.table('system_logs').select('*').order('created_at', desc=True).limit(limit)
    if module != 'ALL':
        query = query.eq('module', module)
    
    res = query.execute()
    if res.data:
        for l in res.data:
            try:
                print(f"{l.get('created_at')} | {l.get('module'):<15} | {l.get('level'):<7} | {l.get('message')}")
            except:
                print(f"{l.get('created_at')} | {l.get('module'):<15} | {l.get('level'):<7} | [Message with non-ascii chars]")
    else:
        print(f"No logs found for {module}.")
    sys.exit(0)

tickers = ['DSGN', 'ONEG', 'FCEL', 'HYPR']

res = sb.table('stocks_positions').select('*').in_('ticker', tickers).eq('status', 'open').execute()

if res.data:
    print(f"{'TICKER':<6} | {'GROUP':<15} | {'AVG':<8} | {'CURRENT':<8} | {'STOP_LOSS':<10} | {'TRAILING':<10} | {'MAX_REACHED':<12}")
    print("-" * 95)
    for p in res.data:
        ticker = str(p.get('ticker') or '')
        group = str(p.get('group_name') or 'N/A')
        avg = f"{p.get('avg_price'):.2f}" if p.get('avg_price') is not None else 'N/A'
        curr = f"{p.get('current_price'):.2f}" if p.get('current_price') is not None else 'N/A'
        sl = f"{p.get('stop_loss'):.2f}" if p.get('stop_loss') is not None else 'N/A'
        tsl = f"{p.get('trailing_sl_price'):.2f}" if p.get('trailing_sl_price') is not None else 'N/A'
        mprice = f"{p.get('highest_price_reached'):.2f}" if p.get('highest_price_reached') is not None else 'N/A'
        print(f"{ticker:<6} | {group:<15} | {avg:<8} | {curr:<8} | {sl:<10} | {tsl:<10} | {mprice:<12}")
else:
    print("No open positions found for these tickers.")
