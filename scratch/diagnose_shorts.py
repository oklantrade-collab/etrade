import asyncio, sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

async def diagnose():
    sb = get_supabase()
    
    # 1. Check crypto positions
    print("=== POSICIONES CRYPTO ABIERTAS ===")
    try:
        res = sb.table('paper_trades').select('*').limit(5).execute()
        if res.data:
            cols = list(res.data[0].keys())
            print(f"  Columnas: {cols[:15]}")
            for p in res.data:
                print(f"  {p.get('symbol')} | {p.get('side')} | {p.get('rule_code')} | closed={p.get('closed_at')}")
        else:
            print("  (tabla vacía)")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 2. Check bot_state for SAR and MTF
    print("\n=== BOT STATE (SAR/MTF por simbolo crypto) ===")
    bs = sb.table('bot_state').select('*').execute()
    for row in (bs.data or []):
        sym = row.get('symbol', '')
        if any(c in sym for c in ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA']):
            print(f"  {sym}: SAR={row.get('sar_phase')} | MTF={row.get('mtf_score')} | short_15m={row.get('allow_short_15m')} | short_4h={row.get('allow_short_4h')}")
    
    # 3. Check trading_config market_type
    print("\n=== TRADING CONFIG ===")
    tc = sb.table('trading_config').select('market_type, paper_trading').eq('id', 1).maybe_single().execute()
    if tc.data:
        print(f"  market_type: {tc.data.get('market_type')}")
        print(f"  paper_trading: {tc.data.get('paper_trading')}")
    
    # 4. Check recent strategy evaluations for SHORT
    print("\n=== ULTIMAS EVALUACIONES SHORT (strategy_evaluations) ===")
    try:
        evals = sb.table('strategy_evaluations').select('symbol, rule_code, direction, score, triggered, created_at').eq('direction', 'short').order('created_at', desc=True).limit(10).execute()
        for e in (evals.data or []):
            print(f"  {e['symbol']} | {e['rule_code']} | score={e['score']} | triggered={e['triggered']} | {e['created_at']}")
        if not evals.data:
            print("  (ninguna evaluación SHORT reciente)")
    except Exception as e:
        print(f"  Error: {e}")

    # 5. Check if there are any open positions in crypto
    print("\n=== POSITIONS TABLE (crypto open) ===")
    try:
        pos = sb.table('positions').select('symbol, side, status, entry_price, rule_code, opened_at').eq('status', 'open').execute()
        for p in (pos.data or []):
            print(f"  {p['symbol']} | {p['side']} | {p['rule_code']} | entry={p['entry_price']} | {p['opened_at']}")
        if not pos.data:
            print("  (ninguna posicion abierta)")
    except Exception as e:
        print(f"  Error: {e}")

asyncio.run(diagnose())
