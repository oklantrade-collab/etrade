"""
Pruebas Unitarias para los 4 Escenarios de Rebote:
1. Clímax Extremo (AaReb_Climax / BbReb_Climax)
2. Escenario 2-A: Agotamiento 3 Velas + Curvatura + EMA Stack (AaReb_Floor_A / BbReb_Ceiling_A)
3. Escenario 2-B: Absorción SIPV + Vela Previa L5/U5 + EMA Stack (AaReb_Floor_B / BbReb_Ceiling_B)
4. Escenario 3: Pullback Menor + 5M Stack + (1H EMA o SAR 15M) + PineScript (AaReb_Pullback / BbReb_Pullback)
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from app.strategy.rule_engine import build_market_data_dict, DEFAULT_RULES, evaluate_rule_conditions

def make_test_df(
    ema1=90, ema2=92, ema3=94, ema4=96, ema5=100,
    close=91, open_p=90.5, low=89, high=92,
    lower_band=90, upper_band=110,
    lower_2=91.0, upper_2=109.0,
    lower_5=89.5, upper_5=110.5,
    lower_6=88.5, upper_6=111.5,
    adx=25, rsi=28, pinescript="Buy",
    sar_trend=1, ema3_1h_above_ema9=True,
    sipv_buy=True, sipv_sell=False,
    n=10
):
    df = pd.DataFrame(index=range(n))
    df['ema1'] = [ema1 - (n - i)*0.2 for i in range(n)]
    df['ema2'] = [ema2 - (n - i)*0.2 for i in range(n)]
    df['ema3'] = [ema3 - (n - i)*0.2 for i in range(n)]
    df['ema4'] = [ema4 - (n - i)*0.2 for i in range(n)]
    df['ema5'] = [ema5 - (n - i)*0.2 for i in range(n)]
    
    df['close'] = [close + i*0.1 for i in range(n)]
    df['open'] = [open_p + i*0.1 for i in range(n)]
    df['low'] = [low + i*0.1 for i in range(n)]
    df['high'] = [high + i*0.1 for i in range(n)]
    
    # BB Lower ascendente en las últimas velas
    df['lower_band'] = [lower_band + i*0.05 for i in range(n)]
    df['bb_lower'] = df['lower_band']
    df['upper_band'] = [upper_band - i*0.05 for i in range(n)]
    df['bb_upper'] = df['upper_band']
    
    df['lower_2'] = lower_2
    df['upper_2'] = upper_2
    df['lower_5'] = lower_5
    df['upper_5'] = upper_5
    df['lower_6'] = lower_6
    df['upper_6'] = upper_6
    
    df['adx'] = adx
    df['rsi'] = rsi
    df['rsi_14'] = rsi
    df['pinescript_signal'] = pinescript
    df['sar_trend'] = sar_trend
    df['ema3_above_ema9_1h'] = ema3_1h_above_ema9
    df['ema3_below_ema9_1h'] = not ema3_1h_above_ema9
    df['ema3_above_ema9_5m'] = True
    df['ema9_above_ema20_5m'] = True
    df['ema3_below_ema9_5m'] = False
    df['ema9_below_ema20_5m'] = False
    df['sipv_buy'] = sipv_buy
    df['sipv_sell'] = sipv_sell
    df['is_hammer'] = sipv_buy
    df['bb_expanding'] = False
    
    return df

def test_scenario_1_climax():
    # Long Climax en LOWER_6 con RSI <= 25
    df = make_test_df(low=88.0, lower_6=88.5, rsi=22.0)
    fib_levels = {'zone': -5}
    regime = {}
    market_data = build_market_data_dict(df, fib_levels, regime)
    
    assert market_data['aareb_climax_ok'] is True
    
    rule = next(r for r in DEFAULT_RULES if r['rule_code'] == 'AaReb_Climax')
    assert evaluate_rule_conditions(rule, market_data) is True

def test_scenario_2a_floor():
    # Long Floor 2-A: 3 velas de piso + BB inferior asc + EMA3 asc + EMA Stack bajista
    df = make_test_df(
        ema1=90, ema2=92, ema3=94, ema4=96, ema5=100, # EMA Stack bajista
        close=92, low=91, lower_band=90, # close y low sobre banda inferior
        rsi=32.0
    )
    fib_levels = {'zone': -3}
    regime = {}
    market_data = build_market_data_dict(df, fib_levels, regime)
    
    assert market_data['aareb_floor_a_ok'] is True
    
    rule = next(r for r in DEFAULT_RULES if r['rule_code'] == 'AaReb_Floor_A')
    assert evaluate_rule_conditions(rule, market_data) is True

def test_scenario_2b_sipv():
    # Long Floor 2-B: SIPV Buy + Vela anterior perforando L5 + EMA Stack bajista
    df = make_test_df(
        ema1=90, ema2=92, ema3=94, ema4=96, ema5=100,
        sipv_buy=True
    )
    # Hacer que la vela anterior (-2) haya caído bajo Lower_5
    df.loc[len(df)-2, 'close'] = 88.0
    df.loc[len(df)-2, 'low'] = 87.0
    df.loc[len(df)-2, 'lower_band'] = 89.0
    df.loc[len(df)-2, 'lower_5'] = 88.0
    
    fib_levels = {'zone': -4}
    regime = {}
    market_data = build_market_data_dict(df, fib_levels, regime)
    
    assert market_data['aareb_floor_b_ok'] is True
    
    rule = next(r for r in DEFAULT_RULES if r['rule_code'] == 'AaReb_Floor_B')
    assert evaluate_rule_conditions(rule, market_data) is True

def test_scenario_3_pullback():
    # Long Pullback: Zona intermedia + 5M stack + 1H EMA + PineScript
    df = make_test_df(
        ema1=95, ema2=94, # 15M EMA3 > EMA9
        low=90.0, lower_2=91.0, # En zona intermedia
        pinescript="Buy",
        ema3_1h_above_ema9=True
    )
    fib_levels = {'zone': -2}
    regime = {}
    market_data = build_market_data_dict(df, fib_levels, regime)
    
    assert market_data['aareb_pullback_ok'] is True
    
    rule = next(r for r in DEFAULT_RULES if r['rule_code'] == 'AaReb_Pullback')
    assert evaluate_rule_conditions(rule, market_data) is True

if __name__ == '__main__':
    print("Ejecutando tests de los 4 Escenarios de Rebote...")
    test_scenario_1_climax()
    print("[PASS] Escenario 1: AaReb_Climax (LOWER_6)")
    test_scenario_2a_floor()
    print("[PASS] Escenario 2-A: AaReb_Floor_A (3 Velas + Curvatura + EMA Stack)")
    test_scenario_2b_sipv()
    print("[PASS] Escenario 2-B: AaReb_Floor_B (SIPV + Vela Previa L5 + EMA Stack)")
    test_scenario_3_pullback()
    print("[PASS] Escenario 3: AaReb_Pullback (Zona Intermedia + 5M + 1H/SAR + PineScript)")
    print("\n>>> TODOS LOS TESTS DE LOS 4 ESCENARIOS DE REBOTE PASARON EXITOSAMENTE! <<<")
