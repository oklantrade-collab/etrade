"""
Simulación Aa30: ¿En qué momento exacto se habría activado la compra LONG en velas de 5 minutos?
Descarga velas reales de ADAUSDT de Binance y evalúa las condiciones.
"""
import requests
import pandas as pd
from datetime import datetime, timezone

# 1. Descargar velas 5m de ADAUSDT (últimas 288 = 24 horas)
url = "https://fapi.binance.com/fapi/v1/klines"
params = {
    "symbol": "ADAUSDT",
    "interval": "5m",
    "limit": 288,
}
resp = requests.get(url, params=params)
data = resp.json()

df = pd.DataFrame(data, columns=[
    'open_time','open','high','low','close','volume',
    'close_time','quote_vol','trades','taker_buy_vol','taker_buy_quote','ignore'
])
for col in ['open','high','low','close','volume']:
    df[col] = df[col].astype(float)

df['time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)

# 2. Calcular EMAs
df['ema3']  = df['close'].ewm(span=3,  adjust=False).mean()
df['ema9']  = df['close'].ewm(span=9,  adjust=False).mean()
df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

# 3. Calcular ángulos de EMAs (cambio porcentual respecto a la vela anterior)
df['ema9_angle']  = df['ema9'].pct_change()  * 100
df['ema20_angle'] = df['ema20'].pct_change() * 100

# 4. Calcular SAR 5m simplificado (usando Parabolic SAR)
def parabolic_sar(df, af_start=0.02, af_step=0.02, af_max=0.2):
    high = df['high'].values
    low  = df['low'].values
    close = df['close'].values
    n = len(df)
    
    sar = [0.0] * n
    trend = [0] * n  # +1 = alcista, -1 = bajista
    
    # Inicializar
    trend[0] = 1 if close[0] > close[0] else 1
    sar[0] = low[0]
    ep = high[0]
    af = af_start
    
    for i in range(1, n):
        if trend[i-1] == 1:  # Tendencia alcista
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[i-2] if i >= 2 else low[i-1])
            
            if low[i] < sar[i]:  # Flip a bajista
                trend[i] = -1
                sar[i] = ep
                ep = low[i]
                af = af_start
            else:
                trend[i] = 1
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_step, af_max)
        else:  # Tendencia bajista
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[i-2] if i >= 2 else high[i-1])
            
            if high[i] > sar[i]:  # Flip a alcista
                trend[i] = 1
                sar[i] = ep
                ep = high[i]
                af = af_start
            else:
                trend[i] = -1
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_step, af_max)
    
    df['sar'] = sar
    df['sar_trend'] = trend
    return df

df = parabolic_sar(df)

# Mostrar solo las ultimas 120 velas (10 horas)
start_idx = max(0, len(df) - 120)

print("=" * 100)
print("SIMULACION Aa30 — ADAUSDT 5m")
print("Condiciones: EMA3>EMA9, EMA9>EMA20, EMA20 angulo+, EMA9 angulo+, SAR 5m alcista")
print("=" * 100)
print()

# Encontrar la primera señal
first_signal = None
for i in range(start_idx, len(df)):
    row = df.iloc[i]
    c1 = row['ema3'] > row['ema9']
    c2 = row['ema9'] > row['ema20']
    c3 = row['ema20_angle'] >= 0
    c4 = row['ema9_angle'] >= 0
    c5 = row['sar_trend'] == 1
    if c1 and c2 and c3 and c4 and c5 and first_signal is None:
        first_signal = row
        break

if first_signal is not None:
    t = first_signal['time'].strftime('%Y-%m-%d %H:%M UTC')
    print(f"\nPRIMERA SENAL EN 5m:")
    print(f"  Momento:  {t}")
    print(f"  Precio:   {first_signal['close']:.4f}")
    print(f"  EMA3:     {first_signal['ema3']:.4f}")
    print(f"  EMA9:     {first_signal['ema9']:.4f}")
    print(f"  EMA20:    {first_signal['ema20']:.4f}")
    
    # Calcular ganancia potencial hasta el maximo posterior
    idx = df.index.get_loc(first_signal.name)
    if idx < len(df) - 1:
        remaining = df.iloc[idx:]
        max_price = remaining['high'].max()
        gain_pct = (max_price - first_signal['close']) / first_signal['close'] * 100
        print(f"  Max posterior: {max_price:.4f}")
        print(f"  Ganancia potencial: +{gain_pct:.2f}%")
else:
    print("\nNo se encontro senal en 5m en las ultimas 10 horas.")

# Mostrar algunas velas alrededor de la senal
if first_signal is not None:
    print("\nDetalle de velas alrededor de la senal:")
    idx = df.index.get_loc(first_signal.name)
    start_view = max(start_idx, idx - 5)
    end_view = min(len(df), idx + 10)
    for i in range(start_view, end_view):
        row = df.iloc[i]
        t = row['time'].strftime('%Y-%m-%d %H:%M UTC')
        c1 = row['ema3'] > row['ema9']
        c2 = row['ema9'] > row['ema20']
        c3 = row['ema20_angle'] >= 0
        c4 = row['ema9_angle'] >= 0
        c5 = row['sar_trend'] == 1
        all_ok = c1 and c2 and c3 and c4 and c5
        status = ">>> COMPRA <<<" if all_ok else ""
        marker = "***" if all_ok else "   "
        checks = f"EMA3>9:{'OK' if c1 else 'NO'} | EMA9>20:{'OK' if c2 else 'NO'} | EMA20ang:{'OK' if c3 else 'NO'} | EMA9ang:{'OK' if c4 else 'NO'} | SAR:{'OK' if c5 else 'NO'}"
        print(f"{marker} {t} | Close={row['close']:.4f} | {checks} {status}")
