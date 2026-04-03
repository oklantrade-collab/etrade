import asyncio
from app.core.supabase_client import get_supabase

async def fix_historical_prices():
    sb = get_supabase()
    
    # Obtener todos los paper_trades para usarlos como fuente de verdad
    trades_res = sb.table('paper_trades').select('symbol, entry_price, exit_price, total_pnl_usd, closed_at').execute()
    trades = trades_res.data or []
    print(f"Encontrados {len(trades)} trades en paper_trades.")
    
    for t in trades:
        # Intentar encontrar la posición correspondiente en 'positions'
        # Usamos símbolo y closed_at (o similar) para matchear
        pos_res = sb.table('positions')\
            .select('id, symbol, realized_pnl')\
            .eq('symbol', t['symbol'])\
            .eq('status', 'closed')\
            .eq('realized_pnl', t['total_pnl_usd'])\
            .execute()
        
        if pos_res.data:
            for p in pos_res.data:
                sb.table('positions').update({
                    'current_price': t['exit_price']
                }).eq('id', p['id']).execute()
                print(f"Fixed position {p['id']} for {p['symbol']} -> Exit: {t['exit_price']}")

if __name__ == "__main__":
    asyncio.run(fix_historical_prices())
