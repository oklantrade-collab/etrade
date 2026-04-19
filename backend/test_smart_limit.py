import asyncio
import pandas as pd
import numpy as np
from app.analysis.movement_classifier import classify_movement
from app.analysis.smart_limit import calculate_smart_limit_price

async def test_smart_limit_logic():
    print("INICIANDO TEST DE SMART LIMIT...")
    
    # 1. Crear data ficticia (Tendencia Alcista)
    data = {
        'close': [100 + i*0.1 for i in range(100)],
        'high':  [100.5 + i*0.1 for i in range(100)],
        'low':   [99.5 + i*0.1 for i in range(100)],
        'basis': [100 + i*0.08 for i in range(100)],
        'ema200': [90 + i*0.05 for i in range(100)],
        'upper_1': [102 + i*0.08 for i in range(100)],
        'upper_2': [103 + i*0.08 for i in range(100)],
        'upper_3': [104 + i*0.08 for i in range(100)],
        'upper_4': [105 + i*0.08 for i in range(100)],
        'upper_5': [106 + i*0.08 for i in range(100)],
        'upper_6': [107 + i*0.08 for i in range(100)],
        'lower_1': [98 + i*0.08 for i in range(100)],
        'lower_2': [97 + i*0.08 for i in range(100)],
        'lower_3': [96 + i*0.08 for i in range(100)],
        'lower_4': [95 + i*0.08 for i in range(100)],
        'lower_5': [94 + i*0.08 for i in range(100)],
        'lower_6': [93 + i*0.08 for i in range(100)],
    }
    df = pd.DataFrame(data)
    
    print("\n--- CASO 1: TENDENCIA ALCISTA ---")
    movement = classify_movement(df)
    print(f"Tipo detectado: {movement['movement_type']}")
    print(f"Confidencial: {movement['confidence']:.2f}")
    
    limit_long = calculate_smart_limit_price(df, 'long', movement['movement_type'])
    print(f"Smart Limit LONG: {limit_long['limit_price']}")
    print(f"Banda objetivo: {limit_long['band_target']}")
    print(f"Sizing Sugerido: {limit_long['sizing_pct']*100}%")

    # 2. Reversión
    data_rev = {
        'close': [100 - i*0.2 for i in range(100)],
        'high':  [100.2 - i*0.2 for i in range(100)],
        'low':   [99.8 - i*0.2 for i in range(100)],
        'basis': [100 - i*0.15 for i in range(100)],
        'ema200': [110 - i*0.01 for i in range(100)],
        'upper_1': [102 - i*0.15 for i in range(100)],
        'upper_2': [104 - i*0.15 for i in range(100)],
        'upper_3': [106 - i*0.15 for i in range(100)],
        'upper_4': [108 - i*0.15 for i in range(100)],
        'upper_5': [110 - i*0.15 for i in range(100)],
        'upper_6': [112 - i*0.15 for i in range(100)],
        'lower_1': [98 - i*0.15 for i in range(100)],
        'lower_2': [96 - i*0.15 for i in range(100)],
        'lower_3': [94 - i*0.15 for i in range(100)],
        'lower_4': [92 - i*0.15 for i in range(100)],
        'lower_5': [90 - i*0.15 for i in range(100)],
        'lower_6': [88 - i*0.15 for i in range(100)],
    }
    df_rev = pd.DataFrame(data_rev)
    
    print("\n--- CASO 2: TENDENCIA BAJISTA ---")
    movement_rev = classify_movement(df_rev)
    print(f"Tipo detectado: {movement_rev['movement_type']}")
    
    limit_short = calculate_smart_limit_price(df_rev, 'short', movement_rev['movement_type'])
    print(f"Smart Limit SHORT: {limit_short['limit_price']}")
    print(f"Banda objetivo: {limit_short['band_target']}")
    print(f"Razón: {limit_short['rationale']}")

if __name__ == "__main__":
    asyncio.run(test_smart_limit_logic())
