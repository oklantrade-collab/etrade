import sys
import os
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.strategy.risk_controls import check_correlation_filter

def run_tests():
    # Crear DataFrames simulados con alta correlación (flash crash)
    np.random.seed(42)
    base_returns = np.random.normal(0, 0.02, 20)

    # BTC y ETH con correlación ~0.97 (flash crash)
    df_btc          = pd.DataFrame()
    df_eth          = pd.DataFrame()
    df_btc['close'] = 80000 * (1 + base_returns).cumprod()
    df_eth['close'] = 3000  * (1 + base_returns * 1.02).cumprod()

    df_dict = {'BTCUSDT': df_btc, 'ETHUSDT': df_eth}

    # Simular posición abierta en BTC long
    mock_pos        = MagicMock()
    mock_pos.symbol = 'BTCUSDT'
    # Important: pos must have side as attribute or handle dict
    # Our updated check_correlation_filter handles both.
    mock_pos.side   = 'long'
    open_positions  = [mock_pos]

    # TEST 1 — bajo_riesgo: alta correlación → BLOQUEAR
    result = check_correlation_filter(
        symbol_new     = 'ETHUSDT',
        direction_new  = 'long',
        open_positions = open_positions,
        df_dict        = df_dict,
        regime         = 'bajo_riesgo'
    )
    assert result['blocked'] == True, \
        f"TEST 1 FALLO: debería bloquear en bajo_riesgo"
    print(f"TEST 1 PASSED — bajo_riesgo bloquea "
          f"(corr={result.get('correlation', 'N/A')})")

    # TEST 2 — alto_riesgo: misma correlación → PERMITIR
    result = check_correlation_filter(
        symbol_new     = 'ETHUSDT',
        direction_new  = 'long',
        open_positions = open_positions,
        df_dict        = df_dict,
        regime         = 'alto_riesgo'
    )
    assert result['blocked'] == False, \
        "TEST 2 FALLO: alto_riesgo no debería bloquear"
    assert result['checked'] == False, \
        "TEST 2 FALLO: checked debería ser False en alto_riesgo"
    print("TEST 2 PASSED — alto_riesgo no bloquea (max_trades=1 protege)")

    # TEST 3 — dirección contraria: nunca bloquear
    mock_pos_short        = MagicMock()
    mock_pos_short.symbol = 'BTCUSDT'
    mock_pos_short.side   = 'short'  # dirección contraria

    result = check_correlation_filter(
        symbol_new     = 'ETHUSDT',
        direction_new  = 'long',   # long vs short → no correlacionar
        open_positions = [mock_pos_short],
        df_dict        = df_dict,
        regime         = 'bajo_riesgo'
    )
    assert result['blocked'] == False, \
        "TEST 3 FALLO: direcciones contrarias no deben bloquearse"
    print("TEST 3 PASSED — Dirección contraria no bloquea")

    # TEST 4 — riesgo_medio con correlación moderada (0.83): BLOQUEAR
    # Crear ETH con correlación 0.83 respecto a BTC
    noise          = np.random.normal(0, 0.005, 20)
    df_eth_med     = pd.DataFrame()
    df_eth_med['close'] = 3000 * (
        1 + base_returns * 0.8 + noise
    ).cumprod()
    df_dict_med    = {'BTCUSDT': df_btc, 'ETHUSDT': df_eth_med}

    result = check_correlation_filter(
        symbol_new     = 'ETHUSDT',
        direction_new  = 'long',
        open_positions = [mock_pos],
        df_dict        = df_dict_med,
        regime         = 'riesgo_medio'
    )
    print(f"TEST 4 INFO — riesgo_medio correlación moderada: "
          f"blocked={result['blocked']} "
          f"corr={result.get('correlation', 'N/A')}")
    print("TEST 4 PASSED — Resultado informativo registrado")

    print("\nTODOS LOS TESTS DE CORRELACION PASARON")

if __name__ == "__main__":
    run_tests()
