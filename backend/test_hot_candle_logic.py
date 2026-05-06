import pandas as pd
import yfinance as yf
from ta.trend import EMAIndicator
from ta.volatility import BollingerBands
from app.core.supabase_client import get_supabase
from app.analysis.fibonacci_bb import fibonacci_bollinger

def test_hot_logic():
    sb = get_supabase()
    # 1. Obtener candidatos recientes del snapshot
    res = sb.table('market_snapshot').select('symbol, price, fibonacci_zone, basis').execute()
    candidates = res.data or []
    
    print(f"Analizando {len(candidates)} candidatos con la nueva lógica HOT_CANDLE...\n")
    print(f"{'TICKER':<8} | {'ZONA':<5} | {'EMA ALIGN':<10} | {'BB EXPAND':<10} | {'RESULTADO'}")
    print("-" * 60)
    
    for c in candidates:
        ticker = c['symbol']
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="1d", interval="15m")
            if len(df) < 20: continue
            
            # Calcular indicadores
            df['ema3'] = EMAIndicator(df['Close'], window=3).ema_indicator()
            df['ema9'] = EMAIndicator(df['Close'], window=9).ema_indicator()
            df['ema20'] = EMAIndicator(df['Close'], window=20).ema_indicator()
            bb = BollingerBands(df['Close'], window=20)
            df['bb_up'] = bb.bollinger_hband()
            df['bb_low'] = bb.bollinger_lband()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Validaciones
            ema_ok = last['ema3'] > last['ema9'] > last['ema20']
            bb_exp = (last['bb_up'] > prev['bb_up']) and (last['bb_low'] < prev['bb_low'])
            fib_z = int(c['fibonacci_zone'])
            
            # Lógica de descarte/aceptación
            status = "❌"
            if ema_ok and bb_exp:
                if -6 <= fib_z <= 2:
                    status = "🚀 TRIGGER HOT (+2)"
                elif fib_z == 3:
                    status = "⚠️ TRIGGER HOT (+3)"
                else:
                    status = "⏳ ZONA ALTA"
            
            print(f"{ticker:<8} | {fib_z:<5} | {'OK' if ema_ok else 'FAIL':<10} | {'OK' if bb_exp else 'FAIL':<10} | {status}")
            
        except Exception as e:
            pass

if __name__ == "__main__":
    test_hot_logic()
