"""Test de apply_ai_binding — 3 casos obligatorios"""
import sys
import os
# Asegurar que el path del backend esté disponible
sys.path.insert(0, os.path.abspath('c:/Fuentes/eTrade/backend'))

try:
    from app.analysis.ai_candles import apply_ai_binding
except ImportError as e:
    print(f"Error al importar apply_ai_binding: {e}")
    sys.exit(1)

errores = []

# TEST 1 — Bloqueo por 'wait'
ai_result     = {'recommendation': 'wait', 'pattern_confidence': 0.75,
                 'key_observation': 'Doji en zona de resistencia',
                 'agrees_with_signal': False}
proposed_sizes = [{'trade_n': 1, 'usd': 18.0}]
resultado = apply_ai_binding(ai_result, proposed_sizes)
assert resultado['action'] == 'block', f"TEST 1 FALLO: action={resultado['action']}"
assert resultado['sizes'] == [],       f"TEST 1 FALLO: sizes={resultado['sizes']}"
print("TEST 1 PASSED — Bloqueo por 'wait' OK")

# TEST 2 — Reducción por 'caution'
ai_result     = {'recommendation': 'caution', 'pattern_confidence': 0.65,
                 'key_observation': 'Volumen decreciente',
                 'agrees_with_signal': False}
proposed_sizes = [{'trade_n': 1, 'usd': 18.0},
                  {'trade_n': 2, 'usd': 27.0}]
resultado = apply_ai_binding(ai_result, proposed_sizes)
assert resultado['action'] == 'reduced',        f"TEST 2 FALLO: action={resultado['action']}"
assert resultado['sizes'][0]['usd'] == 9.0,     f"TEST 2 FALLO: usd={resultado['sizes'][0]['usd']}"
assert resultado['sizes'][1]['usd'] == 13.5,    f"TEST 2 FALLO: usd={resultado['sizes'][1]['usd']}"
print("TEST 2 PASSED — Reducción por 'caution' OK")

# TEST 3 — Ignorar por baja confianza
ai_result     = {'recommendation': 'wait', 'pattern_confidence': 0.30,
                 'key_observation': 'Señal débil',
                 'agrees_with_signal': False}
proposed_sizes = [{'trade_n': 1, 'usd': 18.0}]
resultado = apply_ai_binding(ai_result, proposed_sizes, min_confidence=0.40)
assert resultado['action']  == 'enter', f"TEST 3 FALLO: action={resultado['action']}"
assert resultado['ai_used'] == False,   f"TEST 3 FALLO: ai_used={resultado['ai_used']}"
print("TEST 3 PASSED — Ignorar baja confianza OK")

print("\n[OK] TODOS LOS TESTS DE FASE 2 PASARON")
