import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.position_monitor import check_open_positions_5m
from app.core.memory_store import BOT_STATE

async def test_liquidation_detection():

    # Simular posición abierta en BOT_STATE
    BOT_STATE.positions['BTCUSDT'] = {
        'is_open':   True,
        'avg_entry': 80000.0,
        'sl_price':  76000.0,
        'side':      'long'
    }

    # TEST 1: Posición cerrada por Binance (liquidación)
    mock_provider = AsyncMock()
    mock_provider.get_position.return_value = {
        'positionAmt':     '0',      # cerrada en Binance
        'liquidationPrice': '64000',
        'markPrice':        '63500'
    }
    mock_supabase    = MagicMock()
    mock_supabase.table.return_value.update.return_value\
        .eq.return_value.eq.return_value.execute = AsyncMock()
    mock_telegram    = AsyncMock()

    # NOTE: position_monitor imports send_telegram from app.workers.performance_monitor
    # We should patch it to avoid real network calls
    with patch('app.workers.performance_monitor.send_telegram_message', new_callable=AsyncMock) as mock_send_telegram:
        events = await check_open_positions_5m(
            mock_provider, mock_supabase, mock_telegram
        )

        assert len(events) == 1,                     "TEST 1 FALLO"
        assert events[0]['event'] == 'unexpected_close', "TEST 1 FALLO"
        assert mock_send_telegram.called,             "TEST 1 FALLO — no envió Telegram"
        print("TEST 1 PASSED — Liquidación detectada y alertada")

    # TEST 2: Precio cerca de liquidación (< 5%)
    BOT_STATE.positions['ETHUSDT'] = {
        'is_open':   True,
        'avg_entry': 3000.0,
        'sl_price':  2800.0,
        'side':      'long'
    }
    mock_provider.get_position.return_value = {
        'positionAmt':     '0.5',   # sigue abierta
        'liquidationPrice': '2880', # a 4% del precio actual (3000-2880)/3000 = 0.04
        'markPrice':        '3000'
    }

    with patch('app.workers.performance_monitor.send_telegram_message', new_callable=AsyncMock) as mock_send_telegram:
        events = await check_open_positions_5m(
            mock_provider, mock_supabase, mock_telegram
        )

        liquidation_events = [e for e in events
                              if e['event'] == 'near_liquidation']
        assert len(liquidation_events) >= 1,  "TEST 2 FALLO"
        assert mock_send_telegram.called,     "TEST 2 FALLO — no envió alerta"
        print("TEST 2 PASSED — Alerta de proximidad a liquidación enviada")

    print("\nTODOS LOS TESTS DE POSITION MONITOR PASARON")

from unittest.mock import patch

if __name__ == "__main__":
    asyncio.run(test_liquidation_detection())
