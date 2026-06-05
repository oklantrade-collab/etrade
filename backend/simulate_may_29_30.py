import asyncio
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import yfinance as yf

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.analysis.indicators_v2 import calculate_emas, calculate_macd_4c, classify_ema20_phase, calculate_ema_angles, detect_ema_crosses
from app.analysis.parabolic_sar import calculate_parabolic_sar
from app.analysis.fibonacci_bb import fibonacci_bollinger, extract_fib_levels
from app.analysis.adx_di import calculate_adx
from app.analysis.volume_candles import detect_volume_signals, detect_reversal_candles
from app.strategy.market_regime import classify_market_risk

def build_market_data_dict_custom(df, last_idx, fib_levels, regime, config_type="new"):
    row_data = df.iloc[:last_idx + 1]
    last = row_data.iloc[-1]
    adx_min = regime.get("active_params", {}).get("adx_min", 20)
    
    adx_val = float(last.get("adx", 0)) if pd.notna(last.get("adx")) else 0.0
    rsi_14_val = float(last.get("rsi_14", 50.0))
    
    # 1. ADX Filter Comparison
    if config_type == "old":
        adx_floor_ok = adx_val > 22
        rsi_ok_long = rsi_14_val < 60
        rsi_ok_short = rsi_14_val > 40
    else:
        adx_floor_ok = adx_val >= 15
        rsi_ok_long = rsi_14_val <= 65
        rsi_ok_short = rsi_14_val >= 35

    data = {
        "ema9_angle": float(last.get("ema9_angle", 0)) if pd.notna(last.get("ema9_angle")) else 0.0,
        "ema20_angle": float(last.get("ema20_angle", 0)) if pd.notna(last.get("ema20_angle")) else 0.0,
        "ema50_angle": float(last.get("ema50_angle", 0)) if pd.notna(last.get("ema50_angle")) else 0.0,
        "adx": adx_val,
        "adx_above_regime_min": adx_val >= adx_min,
        "plus_di": float(last.get("plus_di", 0)) if pd.notna(last.get("plus_di")) else 0.0,
        "minus_di": float(last.get("minus_di", 0)) if pd.notna(last.get("minus_di")) else 0.0,
        "di_cross_bullish": bool(last.get("di_cross_bullish", False)),
        "di_cross_bearish": bool(last.get("di_cross_bearish", False)),
        "di_margin": float(last.get("minus_di", 0)) - float(last.get("plus_di", 0)),
        "ema20_phase": str(last.get("ema20_phase", "flat")),
        "ema4_cross_above_basis": bool(last.get("ema4_cross_above_basis", False)),
        "ema4_cross_below_basis": bool(last.get("ema4_cross_below_basis", False)),
        "ema4_above_basis": float(last.get("ema4", 0)) > float(last.get("basis", 0)) if pd.notna(last.get("ema4")) and pd.notna(last.get("basis")) else False,
        "ema4_below_basis": float(last.get("ema4", 0)) < float(last.get("basis", 0)) if pd.notna(last.get("ema4")) and pd.notna(last.get("basis")) else False,
        "fib_zone": fib_levels.get("zone", 0),
        "fib_zone_abs": abs(fib_levels.get("zone", 0)),
        "price_touched_lower_5_6": bool(last.get("price_touched_lower_5_6", False)),
        "price_touched_upper_6": bool(last.get("price_touched_upper_6", False)),
        "reversal_confirmation_long": bool(last.get("is_dragonfly", False) or last.get("low_higher_than_prev", False) or last.get("is_hammer", False) or last.get("is_bullish_engulfing", False) or last.get("is_doji", False)),
        "reversal_confirmation_short": bool(last.get("is_gravestone", False) or (last.get("is_red_candle", False) and fib_levels.get("zone", 0) >= 5) or last.get("high_lower_than_prev", False) or last.get("is_bearish_engulfing", False) or last.get("is_doji", False)),
        "adx_floor_ok": adx_floor_ok,
        "sar_15m_ok_long": int(last.get("sar_trend", 0)) > 0 if pd.notna(last.get("sar_trend")) else False,
        "sar_15m_ok_short": int(last.get("sar_trend", 0)) < 0 if pd.notna(last.get("sar_trend")) else False,
        "bb_expanding": bool(last.get("bb_expanding", False)),
    }

    ema3 = float(last.get("ema1", last.get("ema_3", 0)))
    ema9 = float(last.get("ema2", last.get("ema_9", 0)))
    ema20 = float(last.get("ema3", last.get("ema_20", 0)))
    
    # 2. Crossover Comparison (1 vs 3 bars lookback)
    ema3_cruce_up = False
    ema_col1 = "ema1" if "ema1" in df.columns else "ema_3"
    ema_col2 = "ema2" if "ema2" in df.columns else "ema_9"
    
    if ema_col1 in df.columns and ema_col2 in df.columns and len(row_data) >= 5:
        ema3_s = pd.to_numeric(row_data[ema_col1], errors="coerce")
        ema9_s = pd.to_numeric(row_data[ema_col2], errors="coerce")
        
        lookback = 1 if config_type == "old" else 3
        for i in range(1, lookback + 1):
            idx = -i
            if pd.notna(ema3_s.iloc[idx]) and pd.notna(ema9_s.iloc[idx]) and pd.notna(ema3_s.iloc[idx-1]) and pd.notna(ema9_s.iloc[idx-1]):
                curr_above = ema3_s.iloc[idx] > ema9_s.iloc[idx]
                prev_above = ema3_s.iloc[idx-1] > ema9_s.iloc[idx-1]
                if curr_above and not prev_above:
                    ema3_cruce_up = True
                    break

    bb_exp = bool(last.get("bb_expanding", False))
    mtf_score = float(last.get("mtf_score", 0)) if pd.notna(last.get("mtf_score")) else 0.0
    upper_2 = float(last.get("upper_2", 99999))
    lower_2 = float(last.get("lower_2", 0))

    data.update({
        "ema_cross_short": (ema3 < ema9) or (abs(ema3 - ema9) / ema9 * 100 <= 0.05),
        "ema_cross_long": (ema3 > ema9) or (abs(ema3 - ema9) / ema9 * 100 <= 0.05),
        "ema_cross_short_hot": (ema3 < ema9) or (abs(ema3 - ema9) / ema9 * 100 <= 0.03),
        "ema_cross_long_hot": (ema3 > ema9) or (abs(ema3 - ema9) / ema9 * 100 <= 0.03),
        "fresh_cross_long": ema3_cruce_up,
        "fresh_cross_short": (ema3 < ema9),
        "ema3_slope_positive": True,
        "sipv_buy": data["reversal_confirmation_long"],
        "sipv_sell": data["reversal_confirmation_short"],
        "bb_expanding_or_mtf_long": bb_exp or mtf_score >= 0.5,
        "bb_expanding_or_mtf_short": bb_exp or mtf_score <= -0.5,
        "bb_expanding_or_mtf_long_or_bottom": bb_exp or mtf_score >= 0.5 or (fib_levels.get("zone", 0) <= -4),
        "bb_expanding_or_mtf_short_or_top": bb_exp or mtf_score <= -0.5 or (fib_levels.get("zone", 0) >= 4),
        "mtf_score": mtf_score,
        "hot_mtf_ok_long": (mtf_score > -0.4) if (fib_levels.get("zone", 0) <= -4) else (mtf_score > 0),
        "hot_mtf_ok_short": (mtf_score < 0.4) if (fib_levels.get("zone", 0) >= 4) else (mtf_score < 0),
        "hot_sar_ok_long": True if (fib_levels.get("zone", 0) <= -4) else (int(last.get("sar_trend", 0)) > 0 if pd.notna(last.get("sar_trend")) else False),
        "hot_sar_ok_short": True if (fib_levels.get("zone", 0) >= 4) else (int(last.get("sar_trend", 0)) < 0 if pd.notna(last.get("sar_trend")) else False),
        "strong_contratrend_long": float(last.get("adx", 0)) > 35 and mtf_score <= -0.5,
        "strong_contratrend_short": float(last.get("adx", 0)) > 35 and mtf_score >= 0.5,
        "rsi_ok_long": rsi_ok_long,
        "rsi_ok_short": rsi_ok_short,
        "not_in_ceiling": float(last.get("close", 0)) <= upper_2 if upper_2 > 0 else True,
        "not_in_floor": float(last.get("close", 0)) >= lower_2 if lower_2 > 0 else True,
        "close_below_upper": float(last["close"]) < upper_2 if upper_2 > 0 else True,
        "close_above_lower": float(last["close"]) > lower_2 if lower_2 > 0 else True,
        "ema_exhaustion": False,
        "ema3_cross_ema9_up": ema3_cruce_up,
        "ema3_ema9_trend_ok": (ema9 > ema20) or (ema3 > ema20),
    })

    return data

def evaluate_rule_conditions_local(rule, market_data):
    conditions = rule.get("conditions", [])
    logic = rule.get("logic", "AND")
    if not conditions:
        return False
    results = []
    for cond in conditions:
        indicator = cond["indicator"]
        operator = cond["operator"]
        expected = cond["value"]
        actual = market_data.get(indicator)
        if actual is None:
            results.append(False)
            continue
        try:
            if operator == "==":
                res = actual == expected
            elif operator == "!=":
                res = actual != expected
            elif operator == ">":
                res = float(actual) > float(expected)
            elif operator == ">=":
                res = float(actual) >= float(expected)
            elif operator == "<":
                res = float(actual) < float(expected)
            elif operator == "<=":
                res = float(actual) <= float(expected)
            elif operator == "in":
                res = actual in expected
            elif operator == "not_in":
                res = actual not in expected
            else:
                res = False
            results.append(res)
        except:
            results.append(False)
    if logic == "AND":
        return all(results)
    elif logic == "OR":
        return any(results)
    return False

async def run_simulation():
    symbols = {'BTCUSDT': 'BTC-USD', 'ETHUSDT': 'ETH-USD', 'ADAUSDT': 'ADA-USD'}
    print("=" * 70)
    print("SIMULACIÓN DE TRADES: 29 y 30 de Mayo del 2026 (15m Interval)")
    print("=" * 70, flush=True)

    for sym, ticker in symbols.items():
        print(f"Descargando datos históricos para {sym} ({ticker})...", flush=True)
        df_raw = yf.download(ticker, start='2026-05-26', end='2026-05-31', interval='15m')
        if df_raw.empty:
            print(f"No hay datos para {sym}")
            continue
            
        # Limpiar columnas
        df = df_raw.copy()
        df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]
        
        # Calcular todos los indicadores de eTrader
        df = fibonacci_bollinger(df, length=200, mult=3.0)
        df = calculate_emas(df)
        df = calculate_macd_4c(df)
        df = calculate_adx(df)
        df = detect_volume_signals(df, vol_ema_period=20)
        df = detect_reversal_candles(df)
        df = classify_ema20_phase(df, flat_pct=20.0, peak_pct=80.0)
        df = calculate_ema_angles(df)
        df = detect_ema_crosses(df)
        df = calculate_parabolic_sar(df)
        
        # RSI 14
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi_14'] = 100 - (100 / (1 + (gain/loss)))
        df['bb_width'] = (df['upper_6'] - df['lower_6']) / df['basis']
        df['bb_width_avg'] = df['bb_width'].rolling(20).mean()
        df['bb_expanding'] = df['bb_width'] > (df['bb_width_avg'] * 1.15)
        
        # Filtrar exactamente para el 29 y 30 de Mayo de 2026
        df_filtered = df[(df.index >= '2026-05-29 00:00:00') & (df.index < '2026-05-31 00:00:00')]
        
        # Reglas definidas localmente
        # 1. AaHot
        AaHot_rule = {
            "rule_code": "AaHot",
            "direction": "long",
            "conditions": [
                {"indicator": "fresh_cross_long", "operator": "==", "value": True},
                {"indicator": "adx_floor_ok", "operator": "==", "value": True},
                {"indicator": "rsi_ok_long", "operator": "==", "value": True},
            ]
        }
        BbHot_rule = {
            "rule_code": "BbHot",
            "direction": "short",
            "conditions": [
                {"indicator": "fresh_cross_short", "operator": "==", "value": True},
                {"indicator": "adx_floor_ok", "operator": "==", "value": True},
                {"indicator": "rsi_ok_short", "operator": "==", "value": True},
            ]
        }
        # 2. Aa25
        Aa25_rule = {
            "rule_code": "Aa25",
            "direction": "long",
            "conditions": [
                {"indicator": "ema3_cross_ema9_up", "operator": "==", "value": True},
                {"indicator": "ema3_ema9_trend_ok", "operator": "==", "value": True},
            ]
        }
        # 3. Aa21
        Aa21_rule = {
            "rule_code": "Aa21",
            "direction": "long",
            "conditions": [
                {"indicator": "ema20_angle", "operator": ">=", "value": 0},
                {"indicator": "fib_zone_abs", "operator": "<=", "value": 2},
                {"indicator": "close_below_upper", "operator": "==", "value": True},
            ]
        }
        Bb21_rule = {
            "rule_code": "Bb21",
            "direction": "short",
            "conditions": [
                {"indicator": "ema20_angle", "operator": "<=", "value": 0},
                {"indicator": "close_above_lower", "operator": "==", "value": True},
            ]
        }

        # Simular Ambos Esquemas
        for cfg_name, cfg_type in [("Esquema Anterior (Strict)", "old"), ("Nuevo Esquema (Flex)", "new")]:
            long_trades = 0
            short_trades = 0
            rule_counts = {'AaHot': 0, 'BbHot': 0, 'Aa25': 0, 'Aa21': 0, 'Bb21': 0}
            
            # Loop por los índices de la serie temporal filtrada
            for idx_dt in df_filtered.index:
                # Obtener el índice absoluto en el df original
                abs_idx = df.index.get_loc(idx_dt)
                if abs_idx < 100: continue
                
                bar_window = df.iloc[:abs_idx+1]
                fib_levels = extract_fib_levels(bar_window)
                regime = classify_market_risk(bar_window)
                
                # Check macro trend and regime allowed filters
                ema50 = float(bar_window.iloc[-1]['ema4'])
                ema200 = float(bar_window.iloc[-1]['ema5'])
                macro = "above" if ema50 > ema200 else "below"
                regime_cat = regime["category"] # bajo_riesgo, riesgo_medio, alto_riesgo
                
                # Regime evaluation comparison
                if cfg_type == "old":
                    # Aa21/Bb21 restricted only to bajo_riesgo
                    aa21_regime_ok = regime_cat == "bajo_riesgo"
                else:
                    # Aa21/Bb21 unlocked (allowed in all regimes)
                    aa21_regime_ok = True
                
                # Build Custom Market Data Dictionary
                market_data = build_market_data_dict_custom(df, abs_idx, fib_levels, regime, config_type=cfg_type)
                
                # Evaluate LONG
                # AaHot
                if evaluate_rule_conditions_local(AaHot_rule, market_data):
                    long_trades += 1
                    rule_counts['AaHot'] += 1
                # Aa25
                elif evaluate_rule_conditions_local(Aa25_rule, market_data) and macro == "above":
                    long_trades += 1
                    rule_counts['Aa25'] += 1
                # Aa21
                elif aa21_regime_ok and evaluate_rule_conditions_local(Aa21_rule, market_data) and macro == "above":
                    long_trades += 1
                    rule_counts['Aa21'] += 1
                    
                # Evaluate SHORT
                # BbHot
                if evaluate_rule_conditions_local(BbHot_rule, market_data):
                    short_trades += 1
                    rule_counts['BbHot'] += 1
                # Bb21
                elif aa21_regime_ok and evaluate_rule_conditions_local(Bb21_rule, market_data) and macro == "below":
                    short_trades += 1
                    rule_counts['Bb21'] += 1

            print(f"\n📈 Ticker: {sym} | Configuración: {cfg_name}")
            print(f"  Total LONG trades:  {long_trades}")
            print(f"  Total SHORT trades: {short_trades}")
            print(f"  Detalle por Regla:")
            for k, v in rule_counts.items():
                print(f"    - {k}: {v} entradas")
            
        print("-" * 70, flush=True)

if __name__ == '__main__':
    asyncio.run(run_simulation())
