from app.core.supabase_client import get_supabase
import pandas as pd
import yfinance as yf

def find_candidates():
    sb = get_supabase()
    # 1. Buscar activos en Zona 5 o superior
    res = sb.table('market_snapshot').select('symbol, price, fibonacci_zone, basis, upper_5, upper_6').gte('fibonacci_zone', 5).execute()
    
    candidates = res.data or []
    if not candidates:
        print("No hay activos en Zona 5+ en este momento.")
        return

    print(f"Encontrados {len(candidates)} activos en zonas extremas (5+). Analizando velas 15m...")
    
    for c in candidates:
        ticker = c['symbol']
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1d", interval="15m")
            if len(hist) < 2: continue
            
            last = hist.iloc[-1]
            prev = hist.iloc[-2]
            
            is_red = last['Close'] < last['Open']
            was_green = prev['Close'] > prev['Open']
            
            status = "🔴 REVERSIÓN DETECTADA" if (is_red and was_green) else "🟢 SIGUE ALCISTA"
            
            print(f"Ticker: {ticker} | Zona: {c['fibonacci_zone']} | Precio: {c['price']} | {status}")
            print(f"  Vela Actual: {'Roja' if is_red else 'Verde'} | Vela Anterior: {'Roja' if not was_green else 'Verde'}")
            
        except Exception as e:
            print(f"Error analizando {ticker}: {e}")

if __name__ == "__main__":
    find_candidates()
