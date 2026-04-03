import os
import sys

# Add backend to sys path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.strategy.band_exit import evaluate_band_exit

def test_band_exit_loss():
    print("Testing evaluate_band_exit with position in loss...")
    
    # BTC en pérdida tocando upper_1
    result = evaluate_band_exit(
        position      = {'side': 'long', 'avg_entry_price': 70934},
        current_price = 70574,  # upper_1 pero en pérdida
        next_target   = {'target_price': 70574, 'target_name': 'upper_1', 'target_zone': 1},
        mtf_score     = 0.55,
        ai_result     = {'market_sentiment': 'neutral', 'is_gravestone': False},
        config        = {'min_profit_exit_pct': 0.30}
    )
    
    print(f"Result: {result}")
    
    expected_action = 'hold'
    if result['action'] == expected_action:
        print("✅ SUCCESS: Action is 'hold' as expected.")
    else:
        print(f"❌ FAILURE: Expected '{expected_action}', got '{result['action']}'")

if __name__ == "__main__":
    test_band_exit_loss()
