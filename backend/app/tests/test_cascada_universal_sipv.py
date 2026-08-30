import pytest
import pandas as pd
import numpy as np
from app.cascada.cascada_manager import CascadaManager
from app.cascada.cascada_engine import CascadaEngine, CascadaResult
from app.cascada.level_evaluator import check_sipv_reversal_15m, check_rebote


def _build_15m_df_for_reversal(direction='short'):
    """
    Construye un DataFrame de 15m simulando el giro SIPV:
    Para SHORT:
      - Vela -3: Cae fuerte y toca/perfora Lower Bollinger Band (1.36180, Lower BB = 1.36200).
      - Vela -2: Higher Low (Low sube a 1.36230).
      - Vela -1: Segundo Higher Low (Low sube a 1.36280) y cierre cruza por encima de MA3 (1.36320).
    """
    rows = []
    base_price = 1.36600
    for i in range(25):
        base_price -= 0.0002
        rows.append({
            'open': base_price + 0.0001,
            'high': base_price + 0.0002,
            'low': base_price - 0.0001,
            'close': base_price,
            'volume': 1000
        })
    df = pd.DataFrame(rows)
    df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
    df['sma3'] = df['close'].rolling(3).mean()
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['lower_2'] = sma20 - (std20 * 2)
    df['upper_2'] = sma20 + (std20 * 2)

    if direction == 'short':
        # Vela -3: Suelo perforando Lower BB
        df.loc[df.index[-3], 'low'] = 1.36180
        df.loc[df.index[-3], 'lower_2'] = 1.36220
        # Vela -2: Higher Low 1
        df.loc[df.index[-2], 'low'] = 1.36230
        df.loc[df.index[-2], 'close'] = 1.36260
        # Vela -1: Higher Low 2 + Cruce MA3 alcista
        df.loc[df.index[-1], 'low'] = 1.36280
        df.loc[df.index[-1], 'close'] = 1.36340
        df.loc[df.index[-1], 'sma3'] = 1.36300
        df.loc[df.index[-1], 'ema3'] = 1.36300
    else:
        # Long reversal: Toque Upper BB + Lower Highs + Cruce MA3 bajista
        df.loc[df.index[-3], 'high'] = 1.36750
        df.loc[df.index[-3], 'upper_2'] = 1.36720
        df.loc[df.index[-2], 'high'] = 1.36700
        df.loc[df.index[-2], 'close'] = 1.36670
        df.loc[df.index[-1], 'high'] = 1.36650
        df.loc[df.index[-1], 'close'] = 1.36600
        df.loc[df.index[-1], 'sma3'] = 1.36640
        df.loc[df.index[-1], 'ema3'] = 1.36640

    return df


class TestCascadaUniversalSIPV:
    def setup_method(self):
        self.engine = CascadaEngine()

    def test_cascada_evaluates_all_strategies(self):
        from unittest.mock import MagicMock, patch
        mock_radar = MagicMock()
        mock_radar.get_snapshot.return_value = {'status': 'ok', 'pendiente_EMA3': 'descending', 'pendiente_EMA20': 'descending'}
        mock_radar.get_recent_events.return_value = []
        
        with patch('app.cascada.cascada_manager.log_cascada_decision'), \
             patch('app.cascada.cascada_manager.get_memory_df', return_value=None):
            manager = CascadaManager(radar_service=mock_radar, params={'enabled': True, 'giveback_threshold_pct': 0.30})
            manager.sb = MagicMock()
            manager.sb.table.return_value.update.return_value.eq.return_value.execute.return_value = None
            
            # Mock de posiciones de distintas estrategias
            open_positions = [
                {'id': 'pos_1', 'symbol': 'GBPUSD', 'side': 'short', 'rule_code': 'BBHOT', 'unrealized_pnl': 1.20, 'status': 'open'},
                {'id': 'pos_2', 'symbol': 'EURUSD', 'side': 'short', 'rule_code': 'Aa61_short', 'unrealized_pnl': 0.80, 'status': 'open'},
                {'id': 'pos_3', 'symbol': 'GBPUSD', 'side': 'short', 'rule_code': 'Bb33_QSHR_HEDGE', 'unrealized_pnl': 0.60, 'status': 'open'},
            ]
            results = manager.evaluate_all_cascade_positions(open_positions, market_type='forex')
            # Verificar que CASCADA evaluó TODAS las posiciones
            evaluated_ids = [r.position_id for r in results]
            assert 'pos_1' in evaluated_ids
            assert 'pos_2' in evaluated_ids
            assert 'pos_3' in evaluated_ids

    def test_cascada_giveback_close(self):
        # Posición que llegó a un pico de +16 pips ($1.60) y devolvió a +10 pips ($1.00) (giveback = 37.5%)
        pos = {
            'id': 'pos_gb',
            'symbol': 'GBPUSD',
            'side': 'short',
            'rule_code': 'BBHOT',
            'unrealized_pnl': 1.00,
            'pnl_pico': 1.60,
            'status': 'open'
        }
        res = self.engine.evaluate(
            position=pos,
            radar_snapshot={'status': 'ok', 'pendiente_EMA3': 'descending', 'pendiente_EMA20': 'descending'},
            radar_events=[],
            df_15m=None
        )
        assert res.decision == 'GIVEBACK_CLOSE'
        assert res.check_type == 'giveback'
        assert res.giveback_pct > 0.30

    def test_sipv_reversal_short_15m(self):
        df_15m = _build_15m_df_for_reversal(direction='short')
        res = check_sipv_reversal_15m(
            direction='short',
            df_15m=df_15m,
            pnl_current=0.60,  # +$0.60 USD (ej. +6 pips en 0.01 lotes)
            position={'symbol': 'GBPUSD', 'highest_band_reached': 'bb_touched'}
        )
        assert res['is_rebote'] is True
        assert res['reason'] == 'SIPV_15M_REVERSAL_CONFIRMED'
        assert 'Higher Lows' in res['detail']

    def test_sipv_reversal_long_15m(self):
        df_15m = _build_15m_df_for_reversal(direction='long')
        res = check_sipv_reversal_15m(
            direction='long',
            df_15m=df_15m,
            pnl_current=0.75,
            position={'symbol': 'EURUSD', 'highest_band_reached': 'bb_touched'}
        )
        assert res['is_rebote'] is True
        assert res['reason'] == 'SIPV_15M_REVERSAL_CONFIRMED'
        assert 'Lower Highs' in res['detail']

    def test_cascada_engine_triggers_close_on_sipv_reversal(self):
        df_15m = _build_15m_df_for_reversal(direction='short')
        pos = {
            'id': 'pos_sipv',
            'symbol': 'GBPUSD',
            'side': 'short',
            'rule_code': 'BBHOT',
            'unrealized_pnl': 0.65,
            'pnl_pico': 0.85,
            'status': 'open',
            'highest_band_reached': 'bb_touched'
        }
        res = self.engine.evaluate(
            position=pos,
            radar_snapshot={'status': 'ok', 'pendiente_EMA3': 'ascending', 'pendiente_EMA20': 'descending'},
            radar_events=[],
            df_15m=df_15m
        )
        assert res.decision == 'CERRAR'
        assert res.check_type == 'rebote'
        assert 'SIPV' in res.detail

    def test_fib_exhaustion_velocity(self):
        from app.cascada.level_evaluator import calculate_fib_exhaustion_velocity
        # Simular 9 velas de 5m con movimiento normal de 0.00030 cada una (0.30 pips/min)
        rows = []
        for _ in range(9):
            rows.append({'open': 1.36500, 'high': 1.36540, 'low': 1.36490, 'close': 1.36530})
        # Vela actual agotada: Open 1.36550, Close 1.36551 (solo +0.00001 en 5m = 0.002 pips/min)
        rows.append({'open': 1.36550, 'high': 1.36559, 'low': 1.36548, 'close': 1.36551})
        df_5m = pd.DataFrame(rows)
        
        vel = calculate_fib_exhaustion_velocity(df_5m, direction='long')
        assert vel['is_exhausted'] is True
        assert vel['k_ratio'] < 0.25

    def test_fib_zone_reversal_long_gbpusd_sunday_scenario(self):
        """
        Simula el caso real de GBPUSD del domingo:
        - Entrada en 1.36526
        - Basis = 1.36446, Std = 0.000725 -> Upper_2 = 1.36529, Upper_3 = 1.36555
        - Vela de 19:46 marca High 1.36559 (alcanza Upper_3) pero cierra en 1.36556
        - Siguiente vela falla nuevo High (1.36550) y cruza por debajo de EMA3
        """
        from app.cascada.level_evaluator import check_fib_zone_reversal_15m
        rows = []
        base_price = 1.36400
        for i in range(25):
            base_price += 0.00005
            rows.append({
                'open': base_price,
                'high': base_price + 0.00010,
                'low': base_price - 0.00005,
                'close': base_price + 0.00005,
                'volume': 1000
            })
        df_15m = pd.DataFrame(rows)
        
        # Penúltima vela: testea Upper 3 (1.36559)
        df_15m.loc[df_15m.index[-2], 'high'] = 1.36559
        df_15m.loc[df_15m.index[-2], 'close'] = 1.36550
        
        # Última vela: pierde EMA3
        df_15m.loc[df_15m.index[-1], 'high'] = 1.36550
        df_15m.loc[df_15m.index[-1], 'low'] = 1.36510
        df_15m.loc[df_15m.index[-1], 'close'] = 1.36520
        df_15m['ema3'] = df_15m['close'].ewm(span=3, adjust=False).mean()
        df_15m['ema9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
        df_15m['ema20'] = df_15m['close'].ewm(span=20, adjust=False).mean()

        res = check_fib_zone_reversal_15m(
            direction='long',
            df_15m=df_15m,
            pnl_current=0.35,  # En ganancia sobre la entrada
            position={'symbol': 'GBPUSD', 'entry_price': 1.36526}
        )
        assert res['is_rebote'] is True
        assert res['reason'] == 'FIB_ZONE_REVERSAL_CONFIRMED'
        assert 'Reversión Fib LONG 15m' in res['detail']

    def test_qshr_evaluate_trailing_and_exit_fib_reversal(self):
        from app.strategy.quantum_squeeze_hedge import evaluate_qshr_trailing_and_exit
        rows = []
        base_price = 1.36400
        for i in range(25):
            base_price += 0.00005
            rows.append({
                'open': base_price,
                'high': base_price + 0.00010,
                'low': base_price - 0.00005,
                'close': base_price + 0.00005,
                'volume': 1000
            })
        df_15m = pd.DataFrame(rows)
        df_15m.loc[df_15m.index[-2], 'high'] = 1.36559
        df_15m.loc[df_15m.index[-2], 'close'] = 1.36550
        df_15m.loc[df_15m.index[-1], 'high'] = 1.36550
        df_15m.loc[df_15m.index[-1], 'close'] = 1.36520
        
        # 5m df
        df_5m = df_15m.copy()
        
        pos = {
            'id': 'pos_gbp_long',
            'symbol': 'GBPUSD',
            'side': 'long',
            'entry_price': 1.36500,
            'lots': 0.01
        }
        
        exit_res = evaluate_qshr_trailing_and_exit(
            position=pos,
            df_5m=df_5m,
            df_15m=df_15m,
            current_price=1.36520,
            symbol='GBPUSD'
        )
        assert exit_res is not None
        assert exit_res['action'] == 'close_fib_zone_reversal'
        assert exit_res['rule_code'] == 'Bb33_FIB_ZONE_REVERSAL_EXIT'
