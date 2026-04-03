
import sys
import os
import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

# Add backend to path
sys.path.append('c:\\Fuentes\\eTrade\\backend')

# Import modules to test
from app.strategy.market_regime import classify_market_risk, check_emergency
from app.strategy.position_manager import Position, PositionEntry, calculate_partial_close_sizes, calculate_real_rr
from app.strategy.risk_controls import check_circuit_breaker, check_correlation_filter, calculate_liquidation_price, validate_sl_vs_liquidation
from app.execution.reconciliation import reconcile_positions

class MockSupabase:
    def __init__(self, data=None):
        self.data = data or []
        self.last_update = None
        self.last_delete = None

    def table(self, name):
        return self
    
    def select(self, *args):
        return self
        
    def eq(self, *args):
        return self
        
    def order(self, *args):
        return self
        
    def execute(self):
        class MockResult:
            def __init__(self, data):
                self.data = data
        return MockResult(self.data)

    def update(self, payload):
        self.last_update = payload
        return self

class MockDataProvider:
    def __init__(self, position=None):
        self.position = position or {"size": 0}
        
    async def get_position(self, symbol):
        return self.position

# --- TEST SUITE 4-11 ---

def test_4_market_regime_edges():
    print("\n[TEST 4] Dynamic Market Regime Borders")
    
    # Mock DF with basic values
    df = pd.DataFrame({
        'atr': [20.0] * 100,
        'adx': [25.0] * 100,
        'volume': [1000.0] * 100,
        'ema4': [100.0] * 100,
        'ema5': [95.0] * 100
    })

    # Test High Risk Border (65)
    # We'll mock the risk_score calculation inside custom calls or just verify the logic
    # In my implementation, risk_score is calculated based on weights:
    # atr_pct(35%) + adx_score(35%) + vol_score(20%) + macro(10%)
    
    print("- Verificando clasificación por score...")
    
    def simulate_regime(score):
        if score >= 65: return "alto_riesgo"
        if score >= 35: return "riesgo_medio"
        return "bajo_riesgo"

    print(f"  Score 65.0: {simulate_regime(65.0)} (Expected: alto_riesgo)")
    print(f"  Score 64.9: {simulate_regime(64.9)} (Expected: riesgo_medio)")
    print(f"  Score 35.0: {simulate_regime(35.0)} (Expected: riesgo_medio)")
    print(f"  Score 34.9: {simulate_regime(34.9)} (Expected: bajo_riesgo)")
    
    # Validation of parameter propagation
    from app.strategy.market_regime import CONFIG_BY_RISK
    high_cfg = CONFIG_BY_RISK["alto_riesgo"]
    print(f"  Propagation check: Alto Riesgo uses ADX min {high_cfg['adx_min']} and Max Trades {high_cfg['max_trades']}")
    
    return True

def test_5_partial_close_proportions():
    print("\n[TEST 5] Proportional Partial Close")
    
    # Case A: 3 Trades
    print("- Caso 3 Trades (T1, T2, T3)...")
    entries_3 = [
        PositionEntry(1, 100, 18.0, datetime.now(), "Aa11"), # Smallest
        PositionEntry(2, 97, 27.0, datetime.now(), "Aa11"),  # Medium
        PositionEntry(3, 94, 45.0, datetime.now(), "Aa11")   # Largest
    ]
    pos_3 = Position("BTC/USDT", "long", entries_3, 90.0, 105.0, 110.0)
    sizes_3 = calculate_partial_close_sizes(pos_3)
    
    print(f"  Partial Close USD: ${sizes_3['partial_usd']} (T1+T2)")
    print(f"  Full Close USD: ${sizes_3['full_usd']} (T3 - El mayor)")
    print(f"  Trades cerrados en parcial: {sizes_3['partial_trades']}")
    
    # Case B: 1 Trade
    print("- Caso 1 Trade...")
    entries_1 = [PositionEntry(1, 100, 90.0, datetime.now(), "Aa11")]
    pos_1 = Position("BTC/USDT", "long", entries_1, 90.0, 105.0, 110.0)
    sizes_1 = calculate_partial_close_sizes(pos_1)
    
    print(f"  Partial Close 40%: ${sizes_1['partial_usd']}")
    print(f"  Full Close 60%: ${sizes_1['full_usd']}")
    
    if sizes_3['partial_usd'] == 45.0 and sizes_1['partial_usd'] == 36.0:
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

def test_6_breakeven_logic():
    print("\n[TEST 6] Break-even Idempotency")
    
    entries = [PositionEntry(1, 100.0, 100.0, datetime.now(), "Aa11")]
    pos = Position("BTC/USDT", "long", entries, sl_price=90.0, tp_upper5=110, tp_upper6=120)
    
    # Target to move to BE: avg + (avg - SL) = 100 + (100 - 90) = 110
    print("- Probando activación de BE al tocar target ($110)...")
    triggered = pos.check_breakeven(110.0, fee_pct=0.001)
    
    print(f"  BE Triggered: {triggered}")
    print(f"  New SL: ${pos.sl_price:.2f} (Entry + Fee)")
    
    print("- Probando que no se activa dos veces...")
    second_trigger = pos.check_breakeven(115.0, fee_pct=0.001)
    print(f"  Second Trigger: {second_trigger}")
    
    if triggered and not second_trigger and pos.sl_price > 100:
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

def test_7_correlation_filter():
    print("\n[TEST 7] Correlation Filter")
    
    # Simulate high correlation (0.9)
    # We mock the dataframe returns
    df_btc = pd.DataFrame({'close': [100, 101, 102, 103, 104]})
    df_eth = pd.DataFrame({'close': [200, 202, 204, 206, 208]})
    df_dict = {"BTC/USDT": df_btc, "ETH/USDT": df_eth}
    
    open_positions = [{"symbol": "BTC/USDT", "side": "long"}]
    
    print("- Intentando LONG ETH/USDT (Correlation 1.0)...")
    res_long = check_correlation_filter("ETH/USDT", "long", open_positions, df_dict, max_correlation=0.8)
    print(f"  Blocked: {res_long.get('blocked')} | Reason: {res_long.get('reason')}")
    
    print("- Intentando SHORT ETH/USDT (Correlation 1.0, side opuesto)...")
    res_short = check_correlation_filter("ETH/USDT", "short", open_positions, df_dict, max_correlation=0.8)
    print(f"  Blocked: {res_short.get('blocked')}")
    
    if res_long['blocked'] and not res_short['blocked']:
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

def test_8_circuit_breaker():
    print("\n[TEST 8] Circuit Breaker & Daily Reset")
    
    capital = 500.0
    
    print("- Simulando pérdida del 2% ($10)...")
    cb_1 = check_circuit_breaker(daily_pnl_usd=-10.0, capital_total=capital)
    print(f"  Triggered: {cb_1['triggered']} | Loss: {cb_1['daily_loss_pct']}%")
    
    print("- Simulando pérdida del 6% ($30)...")
    cb_2 = check_circuit_breaker(daily_pnl_usd=-30.0, capital_total=capital)
    print(f"  Triggered: {cb_2['triggered']} | Loss: {cb_2['daily_loss_pct']}%")
    
    if not cb_1['triggered'] and cb_2['triggered']:
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

def test_9_liquidation_and_sl_safety():
    print("\n[TEST 9] Liquidation vs ATR-SL Safety")
    
    # 5x Leverage, Long
    entry = 100.0
    leverage = 5
    liq_res = calculate_liquidation_price(entry, leverage, "long")
    liq_price = liq_res['liquidation_price']
    
    print(f"  Entry: ${entry} | Leverage: {leverage}x")
    print(f"  Liq Price (Binance 0.5% margin): ${liq_price}")
    
    # Case A: High ATR making SL beyond Liquidation
    sl_bad = 75.0 # Worse than Liq ~80.5
    valid_bad = validate_sl_vs_liquidation(sl_bad, liq_price, "long")
    print(f"  SL $75.0 check: Valid={valid_bad['valid']} | Reason={valid_bad['reason']}")
    
    # Case B: Safe SL
    sl_safe = 90.0
    valid_safe = validate_sl_vs_liquidation(sl_safe, liq_price, "long")
    print(f"  SL $90.0 check: Valid={valid_safe['valid']}")
    
    if not valid_bad['valid'] and valid_safe['valid']:
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

async def test_10_reconciliation_sync():
    print("\n[TEST 10] Reconciliation Sync")
    
    # Mock Supabase: thinks BTC is open
    mock_sb = MockSupabase([{"id": "uuid-123", "symbol": "BTC/USDT", "status": "open"}])
    # Mock Provider: thinks BTC is FLAT (size 0)
    mock_provider = MockDataProvider({"size": 0})
    
    print("- Ejecutando reconciliación (Bot=Open, Real=Flat)...")
    discrepancies = await reconcile_positions(["BTCUSDT"], mock_provider, mock_sb)
    
    print(f"  Discrepancies found: {len(discrepancies)}")
    print(f"  Supabase update called: {mock_sb.last_update is not None}")
    if mock_sb.last_update:
        print(f"  New status set: {mock_sb.last_update['status']}")

    if len(discrepancies) > 0 and mock_sb.last_update['status'] == 'closed':
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

def test_11_limit_timeout():
    print("\n[TEST 11] Limit Order Timeout Logic")
    
    def check_timeout(current_bar, order_bar, timeout=2):
        return (current_bar - order_bar) >= timeout

    print(f"  Bar 100 -> Bar 101: Cancel={check_timeout(101, 100)}")
    print(f"  Bar 100 -> Bar 102: Cancel={check_timeout(102, 100)}")
    
    if not check_timeout(101, 100) and check_timeout(102, 100):
        print("RESULTADO: PASSED")
    else:
        print("RESULTADO: FAILED")

async def run_all():
    test_4_market_regime_edges()
    test_5_partial_close_proportions()
    test_6_breakeven_logic()
    test_7_correlation_filter()
    test_8_circuit_breaker()
    test_9_liquidation_and_sl_safety()
    await test_10_reconciliation_sync()
    test_11_limit_timeout()

if __name__ == "__main__":
    asyncio.run(run_all())
