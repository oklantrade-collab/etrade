import sys
import os

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis.ai_candles import apply_ai_binding

def run_tests():
    errores = []

    # TEST 1 — Veto: señal LONG + mercado BEARISH → bloquear
    result = apply_ai_binding(
        ai_result        = {'market_sentiment': 'bearish',
                            'pattern_confidence': 0.75,
                            'agrees_with_signal': False,
                            'key_observation': 'Tendencia bajista clara'},
        signal_direction = 'long'
    )
    assert result['blocked'] == True,  "TEST 1 FALLO"
    assert result['action']  == 'block', "TEST 1 FALLO"
    print("TEST 1 PASSED — LONG vetado por mercado bearish")

    # TEST 2 — Veto: señal SHORT + mercado BULLISH → bloquear
    result = apply_ai_binding(
        ai_result        = {'market_sentiment': 'bullish',
                            'pattern_confidence': 0.80,
                            'agrees_with_signal': False,
                            'key_observation': 'Momentum alcista fuerte'},
        signal_direction = 'short'
    )
    assert result['blocked'] == True,  "TEST 2 FALLO"
    assert result['action']  == 'block', "TEST 2 FALLO"
    print("TEST 2 PASSED — SHORT vetado por mercado bullish")

    # TEST 3 — Permitir: señal LONG + mercado BULLISH → operar
    result = apply_ai_binding(
        ai_result        = {'market_sentiment': 'bullish',
                            'pattern_confidence': 0.70,
                            'agrees_with_signal': True,
                            'key_observation': 'Confirmación alcista'},
        signal_direction = 'long'
    )
    assert result['blocked'] == False, "TEST 3 FALLO"
    assert result['action']  == 'enter', "TEST 3 FALLO"
    print("TEST 3 PASSED — LONG permitido con mercado bullish")

    # TEST 4 — Permitir: baja confianza → ignorar IA
    result = apply_ai_binding(
        ai_result        = {'market_sentiment': 'bearish',
                            'pattern_confidence': 0.25,
                            'agrees_with_signal': False,
                            'key_observation': 'Señal débil'},
        signal_direction = 'long',
        min_confidence   = 0.40
    )
    assert result['blocked']  == False, "TEST 4 FALLO"
    assert result['ai_used']  == False, "TEST 4 FALLO"
    print("TEST 4 PASSED — IA ignorada por baja confianza")

    # TEST 5 — Permitir: señal LONG + mercado INDECISION → operar
    result = apply_ai_binding(
        ai_result        = {'market_sentiment': 'indecision',
                            'pattern_confidence': 0.60,
                            'agrees_with_signal': True,
                            'key_observation': 'Mercado lateral'},
        signal_direction = 'long'
    )
    assert result['blocked'] == False, "TEST 5 FALLO"
    print("TEST 5 PASSED — LONG permitido con mercado neutral")

    print("\nTODOS LOS TESTS PASARON")

if __name__ == "__main__":
    run_tests()
