import os
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase

async def execute_verifications():
    sb = get_supabase()
    
    # --- VERIFICACIÓN 1: market_candles ---
    print("\n--- VERIFICACIÓN 1: Cobertura completa de velas ---")
    res1 = sb.table('market_candles').select('symbol, timeframe, open_time').execute()
    df1 = pd.DataFrame(res1.data)
    if not df1.empty:
        symbols = ['BTC/USDT','ETH/USDT','SOL/USDT','ADA/USDT']
        df_filtered = df1[df1['symbol'].isin(symbols)]
        out1 = df_filtered.groupby(['symbol', 'timeframe']).agg(
            total_velas=('open_time', 'count'),
            primera_vela=('open_time', 'min'),
            ultima_vela=('open_time', 'max')
        ).sort_index()
        print(out1.to_string())
    else:
        print("No hay velas en market_candles.")

    # --- VERIFICACIÓN 2: bot_global_state ---
    print("\n--- VERIFICACIÓN 2: Contador de ciclos activo ---")
    res2 = sb.table('bot_global_state').select('*').eq('id', 1).execute()
    print(res2.data)

    # --- VERIFICACIÓN 3: pilot_diagnostics ---
    print("\n--- VERIFICACIÓN 3: Frankfurt con nueva lógica ---")
    res3 = sb.table('pilot_diagnostics').select('symbol, cycle_type, timestamp').execute()
    df3 = pd.DataFrame(res3.data)
    if not df3.empty:
        df3['timestamp'] = pd.to_datetime(df3['timestamp'])
        # Filter recent 20 mins
        now = datetime.now(timezone.utc)
        mask = df3['timestamp'] >= (now - timedelta(minutes=20))
        out3 = df3[mask].groupby(['symbol', 'cycle_type']).agg(
            ciclos=('timestamp', 'count'),
            ultimo=('timestamp', 'max')
        )
        print(out3.to_string())
    else:
        print("No hay registros recientes en pilot_diagnostics.")

    # --- VERIFICACIÓN 4: Estado actual ---
    print("\n--- VERIFICACIÓN 4: Estado actual (BTC y Trades) ---")
    res4_p = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').execute()
    res4_m = sb.table('market_snapshot').select('*').eq('symbol', 'BTCUSDT').execute()
    
    print("\nBTC POSITION:")
    if res4_p.data:
        p = res4_p.data[0]
        m = res4_m.data[0] if res4_m.data else {}
        pnl_pct = round(((m.get('price', 0) - p['avg_entry_price']) / p['avg_entry_price'] * 100), 2) if m and p['avg_entry_price'] else 0
        print(f"SYMBOL: {p['symbol']} | STATUS: {p['status']} | ENTRADA: {p['avg_entry_price']} | ACTUAL: {m.get('price')} | SL: {p['sl_price']} | MTF: {m.get('mtf_score')} | PNL%: {pnl_pct}%")
    else:
        print("BTCUSDT position not found.")

    res4_t = sb.table('paper_trades').select('symbol, close_reason, total_pnl_usd, total_pnl_pct, closed_at').order('closed_at', desc=True).limit(5).execute()
    print("\nRECIENTES (paper_trades):")
    print(pd.DataFrame(res4_t.data).to_string() if res4_t.data else "No trades closed today.")

if __name__ == "__main__":
    asyncio.run(execute_verifications())
