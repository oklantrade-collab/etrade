"""
Diagnóstico: por qué Aa23 no genera trades a pesar de 881 activaciones.
Cuenta cuántas veces cada pre-filtro bloquea la entrada.
"""
import asyncio
import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb  = create_client(url, key)

# Importar los módulos del pipeline
try:
    from app.analysis.indicators_v2 import calculate_all_indicators
    from app.execution.data_provider import BinanceCryptoProvider
    from app.analysis.fibonacci_bb import fibonacci_bollinger
except ImportError as e:
    print(f"Error importando módulos: {e}")
    # Ajuste de rutas si es necesario
    import sys
    sys.path.append(os.getcwd())
    from app.analysis.indicators_v2 import calculate_all_indicators
    from app.execution.data_provider import BinanceCryptoProvider
    from app.analysis.fibonacci_bb import fibonacci_bollinger

async def debug_aa23():
    # Usamos el provider real para obtener data fresca
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_SECRET')
    provider = BinanceCryptoProvider(api_key, api_secret, market='futures')
    print("Descargando data de BTCUSDT...")
    df = await provider.get_ohlcv('BTCUSDT', '15m', limit=500)

    print("Calculando indicadores...")
    df = fibonacci_bollinger(df)
    df = calculate_all_indicators(df, {}) # Config vacía para este test

    total = len(df)
    
    # Condición base de Aa23 (según especificación v3)
    # Aa23: Tendencia Fuerte (EMA9 > EMA21 > EMA50) + Angulos positivos
    # En el excel/docs dice: ema9_angle >= 0 AND ema50_angle >= 0
    # Verificamos si existen las columnas de ángulos
    if 'ema9_angle' not in df.columns or 'ema50_angle' not in df.columns:
        print("Columnas de ángulos NO encontradas. Calculándolas...")
        # Simulación rápida de ángulos si faltan
        df['ema9_angle'] = df['ema9'].diff(3)
        df['ema50_angle'] = df['ema50'].diff(3)

    aa23_base = (df['ema9_angle'] >= 0) & (df['ema50_angle'] >= 0)
    count_base = aa23_base.sum()

    # Pre-filtros que podrían bloquearla
    # 1. Precio cerca del basis (close <= basis × 1.02)
    cerca_basis = df['close'] <= df['basis'] * 1.02
    
    # 2. Volumen suficiente (vol_entry_ok)
    vol_ok = df['vol_entry_ok'] if 'vol_entry_ok' in df.columns else (df['volume'] >= df['vol_ema'] * 0.7)
    
    # 3. ADX mínimo (adx >= adx_min del régimen — default 20)
    adx_ok = df['adx'] >= 20
    
    # 4. Señal PineScript activa (Este es el sospechoso habitual)
    pinescript_ok = df['pinescript_signal'].notna() if 'pinescript_signal' in df.columns else None

    print(f"\n{'='*55}")
    print(f"DIAGNÓSTICO Aa23 — BTCUSDT 15m ({total} barras)")
    print(f"{'='*55}")
    print(f"Condición base (ema9_angle>=0 AND ema50_angle>=0): {count_base}")
    print(f"  + Precio cerca del basis (<=1.02x):              {(aa23_base & cerca_basis).sum()}")
    print(f"  + Volumen suficiente (vol_entry_ok):              {(aa23_base & vol_ok).sum()}")
    print(f"  + ADX >= 20:                                      {(aa23_base & adx_ok).sum()}")
    print(f"  + TODOS los pre-filtros juntos:                   {(aa23_base & cerca_basis & vol_ok & adx_ok).sum()}")
    if pinescript_ok is not None:
        print(f"  + Señal PineScript activa:                        {(aa23_base & pinescript_ok).sum()}")
    else:
        print(f"  + Señal PineScript: columna NO encontrada en df <- POSIBLE BUG")
    print(f"{'='*55}\n")
    
    # --- DIAGNÓSTICO ADICIONAL (solicitud de Jhon) ---
    print("\nMUESTRA DE pinescript_signal (ultimas 20 barras):")
    cols = ['close', 'macd_buy', 'macd_sell', 'pinescript_signal', 'signal_age']
    available_cols = [c for c in cols if c in df.columns]
    print(df[available_cols].tail(20).to_string())

    print(f"\nDistribucion de pinescript_signal:")
    print(df['pinescript_signal'].value_counts(dropna=False))

    total_buy  = (df['pinescript_signal'] == 'Buy').sum()
    total_sell = (df['pinescript_signal'] == 'Sell').sum()
    total_none = df['pinescript_signal'].isna().sum()
    print(f"\nTotal barras con 'Buy':  {total_buy}")
    print(f"Total barras con 'Sell': {total_sell}")
    print(f"Total barras con None:   {total_none}")
    
    # Verificar que Buy == macd_buy exactamente
    if 'macd_buy' in df.columns:
        macd_buy_count = df['macd_buy'].sum()
        match = total_buy == macd_buy_count
        print(f"\nmacd_buy True count:     {macd_buy_count}")
        print(f"pinescript_signal='Buy': {total_buy}")
        print(f"Son identicos:           {'SI' if match else 'NO'}")
    
    if 'macd_sell' in df.columns:
        macd_sell_count = df['macd_sell'].sum()
        match = total_sell == macd_sell_count
        print(f"\nmacd_sell True count:    {macd_sell_count}")
        print(f"pinescript_signal='Sell':{total_sell}")
        print(f"Son identicos:           {'SI' if match else 'NO'}")
    
    await provider.close()

if __name__ == "__main__":
    asyncio.run(debug_aa23())
