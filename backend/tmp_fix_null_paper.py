from app.core.supabase_client import get_supabase
import asyncio

async def fix_null_paper_trades():
    sb = get_supabase()
    # Buscar paper_trades con rule_code NULL
    res = sb.table('paper_trades').select('id, symbol, closed_at').is_('rule_code', 'null').execute()
    print(f"Found {len(res.data)} paper trades with NULL rule_code")
    
    for pt in res.data:
        # Buscar en positions por symbol y closed_at (o similar temporalmente)
        pos_res = sb.table('positions').select('rule_code, rule_entry')\
            .eq('symbol', pt['symbol'])\
            .gte('closed_at', pt['closed_at'])\
            .order('closed_at', desc=False).limit(1).execute()
        
        if pos_res.data:
            p = pos_res.data[0]
            rule = p.get('rule_code') or p.get('rule_entry') or 'Dd61'
            sb.table('paper_trades').update({'rule_code': rule}).eq('id', pt['id']).execute()
            print(f"Fixed PaperTrade {pt['id']} with rule {rule}")

if __name__ == "__main__":
    asyncio.run(fix_null_paper_trades())
