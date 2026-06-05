import os
import sys

# Define 15 recent closed loss-making positions from DB
crypto_trades = [
    {"symbol": "BTCUSDT", "side": "LONG", "size": 0.00596064, "entry": 76606.1, "exit": 76537.8, "loss_usd": -0.4065},
    {"symbol": "ADAUSDT", "side": "LONG", "size": 1860.72129, "entry": 0.2454, "exit": 0.2449, "loss_usd": -0.9304},
    {"symbol": "ADAUSDT", "side": "LONG", "size": 1858.44865, "entry": 0.2457, "exit": 0.2449, "loss_usd": -1.4868},
    {"symbol": "ADAUSDT", "side": "LONG", "size": 1858.44865, "entry": 0.2457, "exit": 0.2455, "loss_usd": -0.3717},
    {"symbol": "ADAUSDT", "side": "LONG", "size": 1856.18294, "entry": 0.2460, "exit": 0.2455, "loss_usd": -0.9281}
]

forex_trades = [
    {"symbol": "USDJPY", "side": "long", "lots": 0.09, "entry": 159.2070, "exit": 158.8050, "loss_usd": -23.52},
    {"symbol": "EURUSD", "side": "short", "lots": 0.05, "entry": 1.16019, "exit": 1.16371, "loss_usd": -17.60},
    {"symbol": "GBPUSD", "side": "long", "lots": 0.03, "entry": 1.34466, "exit": 1.34359, "loss_usd": -3.21},
    {"symbol": "GBPUSD", "side": "long", "lots": 0.03, "entry": 1.34480, "exit": 1.34391, "loss_usd": -2.66},
    {"symbol": "USDJPY", "side": "long", "lots": 0.10, "entry": 159.1325, "exit": 159.0940, "loss_usd": -2.50}
]

stock_trades = [
    {"symbol": "BTQ", "side": "LONG", "shares": 60, "entry": 4.1450, "exit": 3.9283, "loss_usd": -13.00},
    {"symbol": "INFQ", "side": "LONG", "shares": 10, "entry": 17.6700, "exit": 17.3500, "loss_usd": -3.20},
    {"symbol": "INFQ", "side": "LONG", "shares": 10, "entry": 17.8849, "exit": 17.5750, "loss_usd": -3.10},
    {"symbol": "ACHR", "side": "LONG", "shares": 40, "entry": 6.0501, "exit": 6.0501, "loss_usd": 0.00},
    {"symbol": "INFQ", "side": "LONG", "shares": 15, "entry": 14.7250, "exit": 14.4100, "loss_usd": -4.73}
]

EREP_CONFIG = {
    'crypto_futures': {'max_loss': 6.0, 'factor': 1.0, 'round_decimals': 6},
    'forex_futures': {'max_loss': 1.5, 'factor': 1.0, 'round_decimals': 2},
    'stocks_spot': {'max_loss': 8.0, 'factor': 1.0, 'round_decimals': 0}
}

def simulate():
    print("# EREP Simulation Report — Closed Loss Verification")
    print("=" * 115)
    print(f"{'Market':<10} | {'Symbol':<8} | {'Side':<5} | {'Entry (P1)':<12} | {'Loss %':<7} | {'EREP Active?':<12} | {'P2 Qty':<10} | {'Breakeven (P3)':<15} | {'Required Recovery'}")
    print("=" * 115)
    
    # ── 1. CRYPTO ──
    cfg = EREP_CONFIG['crypto_futures']
    for t in crypto_trades:
        loss_pct = abs(t['entry'] - t['exit']) / t['entry'] * 100
        can_activate = loss_pct <= cfg['max_loss']
        status = "YES (Phase 1)" if can_activate else "NO (Exceeded)"
        
        q2 = round(t['size'] * cfg['factor'], cfg['round_decimals'])
        q2 = max(0.000001, q2)
        p2_price = t['exit']
        p3 = (t['entry'] * t['size'] + p2_price * q2) / (t['size'] + q2)
        recovery_needed = abs(p3 - p2_price) / p2_price * 100
        
        print(f"{'Crypto':<10} | {t['symbol']:<8} | {t['side']:<5} | {t['entry']:<12.2f} | {loss_pct:<6.2f}% | {status:<12} | {q2:<10.6f} | {p3:<15.2f} | {recovery_needed:.2f}% to breakeven")

    print("-" * 115)
    # ── 2. FOREX ──
    cfg = EREP_CONFIG['forex_futures']
    for t in forex_trades:
        loss_pct = abs(t['entry'] - t['exit']) / t['entry'] * 100
        can_activate = loss_pct <= cfg['max_loss']
        status = "YES (Phase 1)" if can_activate else "NO (Exceeded)"
        
        q2 = round(t['lots'] * cfg['factor'], cfg['round_decimals'])
        q2 = max(0.01, q2)
        p2_price = t['exit']
        p3 = (t['entry'] * t['lots'] + p2_price * q2) / (t['lots'] + q2)
        recovery_needed = abs(p3 - p2_price) / p2_price * 100
        
        print(f"{'Forex':<10} | {t['symbol']:<8} | {t['side']:<5} | {t['entry']:<12.5f} | {loss_pct:<6.2f}% | {status:<12} | {q2:<10.2f} | {p3:<15.5f} | {recovery_needed:.2f}% to breakeven")

    print("-" * 115)
    # ── 3. STOCKS ──
    cfg = EREP_CONFIG['stocks_spot']
    for t in stock_trades:
        loss_pct = abs(t['entry'] - t['exit']) / t['entry'] * 100
        can_activate = loss_pct <= cfg['max_loss']
        status = "YES (Phase 1)" if can_activate else "NO (Exceeded)"
        
        # Apply stock integer rounding
        q2_raw = t['shares'] * cfg['factor']
        if q2_raw < 10:
            q2 = round(q2_raw / 5) * 5
        elif q2_raw < 100:
            q2 = round(q2_raw / 10) * 10
        else:
            q2 = round(q2_raw / 100) * 100
        q2 = max(5.0, q2)
            
        p2_price = t['exit']
        p3 = (t['entry'] * t['shares'] + p2_price * q2) / (t['shares'] + q2)
        recovery_needed = abs(p3 - p2_price) / p2_price * 100
        
        print(f"{'Stocks':<10} | {t['symbol']:<8} | {t['side']:<5} | {t['entry']:<12.4f} | {loss_pct:<6.2f}% | {status:<12} | {int(q2):<10} | {p3:<15.4f} | {recovery_needed:.2f}% to breakeven")

if __name__ == "__main__":
    simulate()
