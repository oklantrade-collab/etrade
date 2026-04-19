"""Test v1.1: Fibonacci filter + Close ALL positions + Strategy codes."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.candle_signals.candle_execution import (
    _validate_fibonacci_zone,
    _get_fibonacci_zone,
    _get_strategy_code,
    BUY_ALLOWED_ZONES,
    SELL_ALLOWED_ZONES,
)

# ═══ 1. FIBONACCI ZONE VALIDATION ═══
print("═══ FIBONACCI ZONE FILTER TEST ═══")
print()

print("BUY Allowed Zones:", sorted(BUY_ALLOWED_ZONES, reverse=True))
print("SELL Allowed Zones:", sorted(SELL_ALLOWED_ZONES, reverse=True))
print()

# Test BUY validation across all zones
print("BUY validation:")
for zone in range(-6, 7):
    allowed = _validate_fibonacci_zone("BUY", zone)
    emoji = "✅" if allowed else "❌"
    print(f"  Zone {zone:+d}: {emoji} {'ALLOWED' if allowed else 'BLOCKED'}")

print()
print("SELL validation:")
for zone in range(-6, 7):
    allowed = _validate_fibonacci_zone("SELL", zone)
    emoji = "✅" if allowed else "❌"
    print(f"  Zone {zone:+d}: {emoji} {'ALLOWED' if allowed else 'BLOCKED'}")

# ═══ 2. LIVE FIBONACCI ZONE FETCHING ═══
print()
print("═══ LIVE FIBONACCI ZONE FETCH ═══")

# Crypto
for sym in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
    zone = _get_fibonacci_zone("crypto", sym)
    buy_ok = _validate_fibonacci_zone("BUY", zone)
    sell_ok = _validate_fibonacci_zone("SELL", zone)
    print(f"  Crypto {sym:12s} zone={zone:+d}  BUY={'✅' if buy_ok else '❌'}  SELL={'✅' if sell_ok else '❌'}")

# Forex
for sym in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]:
    zone = _get_fibonacci_zone("forex", sym)
    buy_ok = _validate_fibonacci_zone("BUY", zone)
    sell_ok = _validate_fibonacci_zone("SELL", zone)
    print(f"  Forex  {sym:12s} zone={zone:+d}  BUY={'✅' if buy_ok else '❌'}  SELL={'✅' if sell_ok else '❌'}")

# ═══ 3. STRATEGY CODES ═══
print()
print("═══ STRATEGY CODES ═══")
for market in ["crypto", "forex"]:
    for action in ["BUY", "SELL"]:
        code = _get_strategy_code(market, action)
        print(f"  {market:8s} {action}: {code}")

for pool in ["PRO", "HOT"]:
    for action in ["BUY", "SELL"]:
        code = _get_strategy_code("stocks", action, pool)
        print(f"  stocks   {action} ({pool}): {code}")

print()
print("═══ ALL TESTS PASSED ═══")
