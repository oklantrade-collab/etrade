import asyncio
import os
import sys
from unittest.mock import AsyncMock

# Add backend to sys path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock telegram message function before importing position_monitor
import app.workers.performance_monitor
app.workers.performance_monitor.send_telegram_message = AsyncMock()

from app.core.memory_store import BOT_STATE
from app.core.position_monitor import check_sl_proximity_alert

async def test_sl_alerts():
    mock_send = app.workers.performance_monitor.send_telegram_message
    
    print("Iniciando Test de Alertas SL...")
    symbol = 'BTCUSDT'
    sl_price = 68500.0

    # TEST 1 — Primera vez en zona: ALERTAR (2.9% de distancia)
    # Price = 68500 * 1.029 = 70486.5
    await check_sl_proximity_alert(
        symbol        = symbol,
        current_price = 70486.5,
        sl_price      = sl_price,
        danger_threshold_pct = 3.0
    )
    assert mock_send.call_count == 1
    print("TEST 1 PASSED - alerta enviada primera vez")

    # TEST 2 — Mismo precio: NO ALERTAR
    mock_send.reset_mock()
    await check_sl_proximity_alert(
        symbol        = symbol,
        current_price = 70486.5,
        sl_price      = sl_price
    )
    assert mock_send.call_count == 0
    print("TEST 2 PASSED - no spam con mismo precio")

    # TEST 3 — Precio baja a 1.5% (empeoró > 1%): ALERTAR escalación
    # Price = 68500 * 1.015 = 69527.5
    mock_send.reset_mock()
    await check_sl_proximity_alert(
        symbol        = symbol,
        current_price = 69527.5,
        sl_price      = sl_price
    )
    assert mock_send.call_count == 1
    msg = mock_send.call_args[0][0]
    assert 'MÁS CERCANO' in msg or 'PELIGRO' in msg
    print("TEST 3 PASSED - alerta de escalación enviada")

    # TEST 4 — Precio recupera a 4% (fuera de zona): ALERTAR recuperación
    # Price = 68500 * 1.04 = 71240
    mock_send.reset_mock()
    await check_sl_proximity_alert(
        symbol        = symbol,
        current_price = 71240.0,
        sl_price      = sl_price
    )
    assert mock_send.call_count == 1
    msg = mock_send.call_args[0][0]
    assert 'SUPERADA' in msg
    print("TEST 4 PASSED - alerta de recuperación enviada")

    # TEST 5 — Fuera de zona, sin cambio: NO ALERTAR
    mock_send.reset_mock()
    await check_sl_proximity_alert(
        symbol        = symbol,
        current_price = 71500.0,
        sl_price      = sl_price
    )
    assert mock_send.call_count == 0
    print("TEST 5 PASSED - sin alerta fuera de zona")

    print("\nTODOS LOS TESTS PASARON EXITOSAMENTE")

if __name__ == "__main__":
    asyncio.run(test_sl_alerts())
