"""Fix zombie positions where SL should have triggered."""
import sys
sys.path.insert(0, r'c:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

sb = get_supabase()
res = sb.table('positions').select('*').eq('status', 'open').execute()
closed = 0

for pos in res.data:
    side = (pos.get('side') or '').lower()
    sl = float(pos.get('sl_price') or 0)
    price = float(pos.get('current_price') or 0)
    entry = float(pos.get('entry_price') or 0)
    
    should_close = (side == 'short' and price >= sl and sl > 0)
    
    if should_close:
        qty = float(pos.get('size') or 0)
        pnl_usd = (entry - price) * qty
        pnl_pct = (entry - price) / entry * 100 if entry > 0 else 0
        now_iso = datetime.now(timezone.utc).isoformat()
        
        sb.table('positions').update({
            'status': 'closed',
            'close_reason': 'sl',
            'current_price': price,
            'closed_at': now_iso,
            'realized_pnl': round(pnl_usd, 4)
        }).eq('id', pos['id']).execute()
        
        sb.table('paper_trades').insert({
            'symbol': pos['symbol'],
            'side': pos['side'],
            'entry_price': entry,
            'exit_price': price,
            'total_pnl_usd': round(pnl_usd, 4),
            'total_pnl_pct': round(pnl_pct, 4),
            'close_reason': 'sl',
            'closed_at': now_iso,
            'mode': 'paper',
            'rule_code': pos.get('rule_code', 'N/A')
        }).execute()
        
        closed += 1
        sym = pos['symbol']
        print(f"CLOSED: {sym} entry={entry} sl={sl} price={price} pnl=${pnl_usd:.2f}")

print(f"\nTotal cerradas: {closed}")
rem = sb.table('positions').select('symbol, side, entry_price, sl_price, current_price').eq('status', 'open').execute()
print(f"Posiciones abiertas restantes: {len(rem.data)}")
for r in rem.data:
    print(f"  {r['symbol']} {r['side']} entry={r['entry_price']} sl={r['sl_price']} price={r['current_price']}")
