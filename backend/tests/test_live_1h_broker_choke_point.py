import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
from app.stocks.stocks_order_executor import execute_market_order, place_limit_order
from app.stocks.buying_force_detector import detect_pullback_and_climax_1h
from app.stocks.stocks_rule_engine import StocksRuleEngine


class TestLive1HBrokerAndChokePoint:
    """
    Suite de blindaje institucional para asegurar que NUNCA MÁS se ejecuten
    compras cuando EMA3 <= EMA9 en 1H ni cuando haya datos insuficientes.
    """

    def test_fail_closed_on_insufficient_1h_bars(self):
        """Principio Fail-Closed: Si hay menos de 30 velas 1H, el sistema DEBE retornar False."""
        # Simular 10 velas de 1 hora (caso defectuoso anterior)
        short_df = pd.DataFrame({
            'Open': [10.0] * 12,
            'High': [10.5] * 12,
            'Low': [9.8] * 12,
            'Close': [10.2] * 12,
            'Volume': [1000] * 12
        })
        with patch('yfinance.Ticker') as mock_ticker, \
             patch('app.data.ib_provider.get_ib_connection', return_value=None):
            mock_inst = MagicMock()
            mock_inst.history.side_effect = lambda period, interval: short_df if interval == '1h' else None
            mock_ticker.return_value = mock_inst

            # Limpiar cache para la prueba
            from app.stocks.live_1h_candle_service import _1H_CACHE
            _1H_CACHE.pop('SHORT12', None)

            res = get_live_1h_candle_and_sipv('SHORT12', current_price=10.2)
            assert res['is_ema3_above_ema9'] is False
            assert "insuficientes" in res['status_reason'].lower() or "fail-closed" in res['status_reason'].lower()

    def test_broker_first_used_when_connected(self):
        """Verifica que si el Broker TWS está conectado, se usen sus velas de 1H directamente."""
        # 40 velas horarias simuladas desde TWS
        ib_bars = pd.DataFrame({
            'open': [20.0 + i * 0.1 for i in range(40)],
            'high': [20.5 + i * 0.1 for i in range(40)],
            'low': [19.8 + i * 0.1 for i in range(40)],
            'close': [20.2 + i * 0.1 for i in range(40)],
            'volume': [5000 for _ in range(40)]
        })
        mock_ib = MagicMock()
        mock_ib.connected = True
        mock_ib.request_historical_1h_bars.return_value = ib_bars

        with patch('app.data.ib_provider.get_ib_connection', return_value=mock_ib), \
             patch('yfinance.Ticker') as mock_yf:
            from app.stocks.live_1h_candle_service import _1H_CACHE
            _1H_CACHE.pop('IB_STOCK', None)

            res = get_live_1h_candle_and_sipv('IB_STOCK', current_price=24.0)
            mock_ib.request_historical_1h_bars.assert_called_once()
            assert res['is_ema3_above_ema9'] is True
            assert res['ema3_1h_live'] > res['ema9_1h']

    def test_choke_point_in_stocks_order_executor_blocks_any_rule_when_ema3_le_ema9(self):
        """
        El punto de estrangulamiento final (stocks_order_executor) debe rechazar
        CUALQUIER orden BUY si EMA3 <= EMA9 en 1H, sin excepción de estrategia.
        """
        mock_live_1h_bear = {
            'is_ema3_above_ema9': False,
            'is_ema3_1h_ascending': False,
            'ema3_1h_live': 16.08,
            'ema9_1h': 18.17,
            'status_reason': 'EMA3 1H <= EMA9 1H'
        }

        with patch('app.stocks.live_1h_candle_service.get_live_1h_candle_and_sipv', return_value=mock_live_1h_bear), \
             patch('app.stocks.stocks_order_executor._is_after_1515_et', return_value=False), \
             patch('app.stocks.stocks_order_executor.get_supabase'), \
             patch('app.stocks.stocks_order_executor._get_config', return_value={'paper_mode': True}):

            # 1. Probar con APEX_AUTO (como NAUT y NU)
            res_apex = execute_market_order('XP', 'buy', 'APEX_AUTO', {'price': 16.0}, {'group_name': 'AUTO'})
            assert res_apex['success'] is False
            assert "Aduana Choke Point" in res_apex['reason']

            # 2. Probar con LONG_CLIMAX_1H (como XP)
            res_climax = execute_market_order('XP', 'buy', 'LONG_CLIMAX_1H', {'price': 16.0}, {'group_name': 'HOT'})
            assert res_climax['success'] is False
            assert "Aduana Choke Point" in res_climax['reason']

            # 3. Probar con LONG_PULLBACK_1H (como QTEX)
            res_pb = execute_market_order('QTEX', 'buy', 'LONG_PULLBACK_1H', {'price': 1.32}, {'group_name': 'HOT'})
            assert res_pb['success'] is False
            assert "Aduana Choke Point" in res_pb['reason']

            # 4. Probar en place_limit_order
            res_lmt = place_limit_order('XP', 'buy', 'LONG_CLIMAX_1H', {'limit_price': 16.0}, {'group_name': 'HOT'})
            assert res_lmt['success'] is False
            assert "Aduana Choke Point" in res_lmt['reason']

    def test_buying_force_detector_requires_ema3_gt_ema9(self):
        """Verifica que detect_pullback_and_climax_1h no dispare si EMA3 <= EMA9."""
        # 30 velas donde el precio cayó de 20 a 10 (EMA3 < EMA9)
        c = [20.0 - (i * 0.3) for i in range(30)]
        df_1h = pd.DataFrame({
            'open': [p + 0.1 for p in c],
            'high': [p + 0.2 for p in c],
            'low': [p - 0.2 for p in c],
            'close': c,
            'volume': [100_000] * 30
        })

        res = detect_pullback_and_climax_1h(
            current_price=10.0,
            df_1h=df_1h,
            macro_aligned=True,
            df_15m=None
        )
        assert res['triggered'] is False

    def test_stocks_rule_engine_checks_14_and_15_block_when_ema3_le_ema9(self):
        """Verifica que StocksRuleEngine rechace Checks 14 y 15 cuando EMA3 <= EMA9."""
        engine = StocksRuleEngine()
        engine.rules = {
            'LONG_PULLBACK_1H': {
                'rule_code': 'LONG_PULLBACK_1H',
                'direction': 'buy',
                'order_type': 'market',
                'enabled': True,
                'priority': 1
            },
            'LONG_CLIMAX_1H': {
                'rule_code': 'LONG_CLIMAX_1H',
                'direction': 'buy',
                'order_type': 'market',
                'enabled': True,
                'priority': 1
            }
        }

        # Contexto con EMA3 < EMA9
        ctx_bear = {
            'macro_1d_aligned': True,
            'buying_force_score': 85,
            'adr_14_pct': 4.0,
            'entry_route_1h': 'PULLBACK',
            'entry_support_1h': 'EMA9',
            'ema_3_1h': 16.0,
            'ema_9_1h': 18.0,
            'price': 16.0
        }

        res_pb = engine.evaluate_rule(engine.rules['LONG_PULLBACK_1H'], ctx_bear)
        assert res_pb['triggered'] is False
        assert any("Aduana 1H" in f for f in res_pb['failures'])

        ctx_bear['entry_route_1h'] = 'CLIMAX'
        ctx_bear['entry_support_1h'] = 'LOWER_5'
        res_clim = engine.evaluate_rule(engine.rules['LONG_CLIMAX_1H'], ctx_bear)
        assert res_clim['triggered'] is False
        assert any("Aduana 1H" in f for f in res_clim['failures'])
