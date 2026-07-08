import sys
import os
import pytz
from datetime import datetime, timezone, timedelta
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.core.supabase_client import get_supabase
import asyncio

async def test_summary():
    supabase = get_supabase()
    
    # Fetch
    res_crypto = supabase.table('positions').select('id, realized_pnl, closed_at, rule_code').eq('status', 'closed').execute()
    res_forex  = supabase.table('forex_positions').select('id, pnl_usd, closed_at, rule_code').eq('status', 'closed').execute()
    res_stocks = supabase.table('stocks_positions').select('id, ticker, unrealized_pnl, updated_at').eq('status', 'closed').execute()
    
    print(f"res_crypto length: {len(res_crypto.data or [])}")
    print(f"res_forex length: {len(res_forex.data or [])}")
    print(f"res_stocks length: {len(res_stocks.data or [])}")
    if res_stocks.data:
        print("First stock trade sample:", res_stocks.data[0])

    raw_combined = []
    for t in (res_crypto.data or []):
        raw_combined.append({**t, 'pnl': t.get('realized_pnl') or 0, 'time': t['closed_at'], 'market': 'crypto'})
    for t in (res_forex.data or []):
        raw_combined.append({**t, 'pnl': t['pnl_usd'], 'time': t['closed_at'], 'market': 'forex'})
    for t in (res_stocks.data or []):
        raw_combined.append({**t, 'pnl': t['unrealized_pnl'], 'time': t['updated_at'], 'market': 'stocks'})

    def is_real_trade(t):
        pnl = t.get('pnl')
        if pnl is None: return False
        try:
            if abs(float(pnl)) < 0.0001: return False
        except: return False
        return True

    all_closed = []
    for t in raw_combined:
        if is_real_trade(t):
            try:
                ts = t['time'].replace('Z', '+00:00')
                if '.' in ts:
                    prefix, rest = ts.split('.', 1)
                    sep = '+' if '+' in rest else ('-' if '-' in rest else None)
                    if sep:
                        micro_part, tz_part = rest.split(sep, 1)
                        micro_part = micro_part.ljust(6, '0')[:6]
                        ts = f"{prefix}.{micro_part}{sep}{tz_part}"
                    else:
                        micro_part = rest.ljust(6, '0')[:6]
                        ts = f"{prefix}.{micro_part}"
                
                t['dt_object'] = datetime.fromisoformat(ts)
                t['total_pnl_usd'] = t['pnl']
                all_closed.append(t)
            except Exception as e:
                print(f"Error parsing date for {t}: {e}")

    lima_tz = pytz.timezone('America/Lima')
    now_lima = datetime.now(lima_tz)
    
    today_start_lima = now_lima.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_lima.astimezone(timezone.utc)

    monday_lima = (now_lima - timedelta(days=now_lima.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    monday_start_utc = monday_lima.astimezone(timezone.utc)

    month_lima = now_lima.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = month_lima.astimezone(timezone.utc)
    
    # Filter
    today_trades = [t for t in all_closed if t['dt_object'] >= today_start_utc]
    week_trades  = [t for t in all_closed if t['dt_object'] >= monday_start_utc]
    month_trades = [t for t in all_closed if t['dt_object'] >= month_start_utc]
    
    print(f"Month closed trades: {len(month_trades)}")
    
    stocks_in_month = [t for t in month_trades if t['market'] == 'stocks']
    print(f"Stocks in month: {len(stocks_in_month)}")
    for t in stocks_in_month:
         print(t)

if __name__ == "__main__":
    asyncio.run(test_summary())
