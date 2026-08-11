import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def calc_pnl():
    sb = get_supabase()
    positions = sb.table('positions').select('*').ilike('rule_code', '%Aa30C%').order('id', desc=True).limit(100).execute()
    
    total_pnl = 0.0
    closed_count = 0
    erep_count = 0
    total_loss_erep = 0.0
    
    for p in positions.data:
        pnl = float(p.get('realized_pnl') or p.get('pnl') or 0.0)
        status = p.get('status')
        if status in ('CLOSED', 'CLOSED_EREP', 'closed', 'closed_erep'):
            closed_count += 1
            total_pnl += pnl
            if p.get('erep_active') or p.get('close_reason') == 'EREP':
                erep_count += 1
                total_loss_erep += pnl
                
    print(f"Total Closed: {closed_count}")
    print(f"Total EREP Closed: {erep_count}")
    print(f"Total PNL of Closed: {total_pnl}")
    print(f"Total PNL of EREP: {total_loss_erep}")

if __name__ == '__main__':
    calc_pnl()
