import os
import dotenv
from supabase import create_client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

# Get the most recent closed ADAUSDT position
res = sb.table('positions').select('*').eq('symbol', 'ADAUSDT').eq('status', 'closed').order('closed_at', desc=True).limit(1).execute()
if res.data:
    pos = res.data[0]
    entry = float(pos.get('entry_price') or 0.1979)
    close_px = float(pos.get('current_price') or 0.1927)
    size = float(pos.get('size') or 378)
    pnl = round((entry - close_px) * size, 4)
    pnl_pct = round((pnl / (entry * size)) * 100, 2)
    
    update_data = {
        'realized_pnl': pnl,
        'realized_pnl_usd': pnl,
        'realized_pnl_pct': pnl_pct
    }
    sb.table('positions').update(update_data).eq('id', pos['id']).execute()
    print(f"Updated ADAUSDT position {pos['id']}: PnL=${pnl:.2f} ({pnl_pct:.2f}%)")
else:
    print("No ADAUSDT position found.")
