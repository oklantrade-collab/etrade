import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')

from app.strategy.forex_adaptive_exit import evaluate_forex_tp
from app.strategy.capital_protection import PROTECTION_CONFIG

def test_forex():
    print("="*60)
    print("=== VERIFICACION DE FEE-NET GUARD PARA FOREX (IC MARKETS) ===")
    print("="*60)
    
    # 1. Protection Config Break-Even check
    cfg = PROTECTION_CONFIG['forex_futures']
    print(f"1. Break-Even Trigger Pips (Forex): {cfg['be_trigger_pips']} pips (BE +1 pip)")
    print(f"   Trailing levels: {cfg['trailing_levels_pips']}")
    
    # 2. Test EURUSD with +1.5 pips (< 3.0 pips min) -> Should NOT close
    pos_eur = [{'side': 'long', 'avg_entry_price': 1.0850}]
    res_eur_small = evaluate_forex_tp('EURUSD', pos_eur, 1.08515, {'mtf_score': -0.8, 'fibonacci_zone': 4, 'sar_trend_4h': -1})
    print(f"\n2. EURUSD PnL +1.5 pips (< +3.0 pips min comisión IC Markets):")
    print(f"   ¿Autoriza Cierre? {res_eur_small.get('should_close')}")
    print(f"   Motivo: {res_eur_small.get('reason')}")
    
    # 3. Test EURUSD with +4.0 pips (>= 3.0 pips min) -> Authorized
    res_eur_ok = evaluate_forex_tp('EURUSD', pos_eur, 1.08540, {'mtf_score': -0.8, 'fibonacci_zone': 4, 'sar_trend_4h': -1})
    print(f"\n3. EURUSD PnL +4.0 pips (>= +3.0 pips min comisión IC Markets):")
    print(f"   ¿Autoriza Cierre? {res_eur_ok.get('should_close')}")
    print(f"   Motivo: {res_eur_ok.get('reason')}")

    # 4. Test XAUUSD (Gold) with +8.0 pips (< 15.0 pips min gold) -> Should NOT close
    pos_gold = [{'side': 'long', 'avg_entry_price': 2400.00}]
    res_gold_small = evaluate_forex_tp('XAUUSD', pos_gold, 2400.08, {'mtf_score': -0.8, 'fibonacci_zone': 4, 'sar_trend_4h': -1})
    print(f"\n4. XAUUSD (Oro) PnL +8.0 pips (< +15.0 pips min oro):")
    print(f"   ¿Autoriza Cierre? {res_gold_small.get('should_close')}")
    print(f"   Motivo: {res_gold_small.get('reason')}")

    # 5. Test XAUUSD (Gold) with +20.0 pips (>= 15.0 pips min gold) -> Authorized
    res_gold_ok = evaluate_forex_tp('XAUUSD', pos_gold, 2400.20, {'mtf_score': -0.8, 'fibonacci_zone': 4, 'sar_trend_4h': -1})
    print(f"\n5. XAUUSD (Oro) PnL +20.0 pips (>= +15.0 pips min oro):")
    print(f"   ¿Autoriza Cierre? {res_gold_ok.get('should_close')}")
    print(f"   Motivo: {res_gold_ok.get('reason')}")

if __name__ == "__main__":
    test_forex()
