from app.core.supabase_client import get_supabase
import asyncio

async def debug_positions_for_paper_trades():
    sb = get_supabase()
    # Buscar una de las que sale en blanco (-)
    # Time: 2026-03-29T21:50:11 (local) -> 02:50 UTC? No.
    # 21:50 local = 21:50 local (screenshot).
    # En la DB: 2026-03-29T21:50:11.670036+00:00
    
    res = sb.table('positions').select('*').eq('symbol', 'ADAUSDT').eq('status', 'closed').order('closed_at', desc=True).limit(5).execute()
    for p in res.data:
        print(f"Pos ID: {p['id']}, Rule: {p.get('rule_code')}, Closed: {p['closed_at']}")

if __name__ == "__main__":
    asyncio.run(debug_positions_for_paper_trades())
