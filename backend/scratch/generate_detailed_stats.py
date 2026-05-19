import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_detailed_stats():
    sb = get_supabase()
    
    forex_res = sb.table('forex_positions').select('*').eq('status', 'closed').execute()
    crypto_res = sb.table('paper_trades').select('*').not_.is_('closed_at', 'null').execute()
    stocks_res = sb.table('stocks_positions').select('*').eq('status', 'closed').execute()
    
    start_date = datetime(2026, 5, 9, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    
    def parse_dt(dt_str):
        if not dt_str:
            return None
        ts = dt_str.replace('Z', '+00:00')
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
        return datetime.fromisoformat(ts)

    # Filter
    w_forex = [t for t in (forex_res.data or []) if parse_dt(t.get('closed_at')) and start_date <= parse_dt(t.get('closed_at')) < end_date]
    w_crypto = [t for t in (crypto_res.data or []) if parse_dt(t.get('closed_at')) and start_date <= parse_dt(t.get('closed_at')) < end_date]
    w_stocks = [t for t in (stocks_res.data or []) if parse_dt(t.get('updated_at') or t.get('exit_date')) and start_date <= parse_dt(t.get('updated_at') or t.get('exit_date')) < end_date]
    
    def analyze(trades, key_pnl):
        total = len(trades)
        if total == 0:
            return 0, 0, 0, 0.0, 0.0, 0.0
        
        pnls = [float(t.get(key_pnl) or 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        win_rate = (len(wins) / total) * 100
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        total_pnl = sum(pnls)
        
        return total, len(wins), len(losses), win_rate, avg_win, avg_loss, total_pnl

    fx_stats = analyze(w_forex, 'pnl_usd')
    cr_stats = analyze(w_crypto, 'total_pnl_usd')
    st_stats = analyze(w_stocks, 'unrealized_pnl')
    
    print("FX_STATS:", fx_stats)
    print("CR_STATS:", cr_stats)
    print("ST_STATS:", st_stats)

if __name__ == "__main__":
    asyncio.run(check_detailed_stats())
