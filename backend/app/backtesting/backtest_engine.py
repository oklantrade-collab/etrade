import pandas as pd
import numpy as np
import uuid
import logging
from datetime import datetime

from app.analysis import technical_indicators
from app.strategy import volume_spike
from app.strategy import mtf_scorer

logger = logging.getLogger(__name__)

def run_backtest(params: dict, supabase, run_id: str):
    try:
        timeframes_needed = ['15m', '30m', '1h', '4h', '1d', '1w']
        data = {}

        for tf in timeframes_needed:
            result = supabase.table('market_candles') \
                .select('*') \
                .eq('symbol', params['symbol']) \
                .eq('timeframe', tf) \
                .gte('open_time', params['start_date']) \
                .lte('open_time', params['end_date']) \
                .order('open_time', desc=False) \
                .execute()
            
            data[tf] = pd.DataFrame(result.data)
            
            # Requerimientos dinámicos por timeframe
            min_req = 50
            if tf == '1d': min_req = 20
            if tf == '1w': min_req = 5

            if len(data[tf]) < min_req:
                # Actualizar run en BD con error
                supabase.table('backtest_runs').update({
                    'status': 'error',
                    'error_message': f'Datos insuficientes para {tf}: '
                                    f'{len(data[tf])} velas (mínimo {min_req})'
                }).eq('id', run_id).execute()
                return None

        # PASO 2 — Simulación vela por vela
        capital = params['initial_capital']
        trades = []
        equity_curve = [{
            'timestamp': str(data['15m'].iloc[50]['open_time']),
            'equity': capital
        }]
        open_position = None

        SPREAD_PCT = 0.0005   # 0.05% simulado en cada ejecución
        COMMISSION  = 0.001   # 0.1% comisión Binance por lado

        for i in range(50, len(data['15m'])):
            current_candle = data['15m'].iloc[i]
            current_time   = current_candle['open_time']
            
            # Obtener ventana de datos hasta timestamp actual
            # CRÍTICO: nunca usar índices > i
            windows = {}
            for tf in timeframes_needed:
                df_tf = data[tf]
                # Optimizar búsqueda temporal
                mask = pd.to_datetime(df_tf['open_time']) <= pd.to_datetime(current_time)
                windows[tf] = df_tf[mask].tail(200).copy()
            
            # ── Verificar si posición abierta fue cerrada ──
            if open_position is not None:
                high = float(current_candle['high'])
                low  = float(current_candle['low'])
                
                pnl = None
                close_reason = None
                
                if open_position['side'] == 'LONG':
                    if low <= open_position['sl']:
                        exit_price   = open_position['sl'] * (1 - SPREAD_PCT)
                        pnl          = (exit_price - open_position['entry']) * open_position['size']
                        close_reason = 'SL_HIT'
                    elif high >= open_position['tp']:
                        exit_price   = open_position['tp'] * (1 - SPREAD_PCT)
                        pnl          = (exit_price - open_position['entry']) * open_position['size']
                        close_reason = 'TP_HIT'
                
                elif open_position['side'] == 'SHORT':
                    if high >= open_position['sl']:
                        exit_price   = open_position['sl'] * (1 + SPREAD_PCT)
                        pnl          = (open_position['entry'] - exit_price) * open_position['size']
                        close_reason = 'SL_HIT'
                    elif low <= open_position['tp']:
                        exit_price   = open_position['tp'] * (1 + SPREAD_PCT)
                        pnl          = (open_position['entry'] - exit_price) * open_position['size']
                        close_reason = 'TP_HIT'
                
                if close_reason:
                    commission_exit = exit_price * open_position['size'] * COMMISSION
                    net_pnl = pnl - commission_exit
                    capital += net_pnl
                    
                    duration_hrs = (
                        pd.Timestamp(current_time) -
                        pd.Timestamp(open_position['entry_time'])
                    ).total_seconds() / 3600
                    
                    trades.append({
                        'entry_time':   str(open_position['entry_time']),
                        'exit_time':    str(current_time),
                        'side':         open_position['side'],
                        'entry_price':  open_position['entry'],
                        'exit_price':   round(exit_price, 6),
                        'size':         open_position['size'],
                        'pnl':          round(net_pnl, 4),
                        'close_reason': close_reason,
                        'duration_hrs': round(duration_hrs, 2)
                    })
                    equity_curve.append({
                        'timestamp': str(current_time),
                        'equity':    round(capital, 2)
                    })
                    open_position = None
            
            # ── Si hay posición abierta, no abrir otra ──
            if open_position is not None:
                continue
            
            # ── Calcular indicadores por timeframe ──
            all_indicators = {}
            for tf in timeframes_needed:
                if len(windows[tf]) < 50:
                    continue
                ind = technical_indicators.calculate_indicators(
                    windows[tf], tf, params['symbol']
                )
                if ind:
                    all_indicators[tf] = ind
            
            if '15m' not in all_indicators:
                continue
            
            # ── Detectar spike ──
            spike = volume_spike.detect_spike(
                windows['15m'],
                all_indicators['15m'],
                params   # params acts as config
            )
            if spike is None:
                continue
            
            # ── MTF Score ──
            mtf_result = mtf_scorer.calculate_mtf_score(
                params['symbol'], all_indicators, spike['direction']
            )
            score_final = mtf_result['score']
            threshold   = params['mtf_signal_threshold']
            
            if spike['direction'] == 'BULLISH' and score_final >= threshold:
                signal_type = 'BUY'
            elif spike['direction'] == 'BEARISH' and score_final <= -threshold:
                signal_type = 'SELL'
            else:
                continue
            
            # ── Calcular SL/TP ──
            atr_4h = all_indicators.get('4h', {}).get('atr_14')
            if not atr_4h or atr_4h <= 0:
                continue
            
            entry_raw   = float(current_candle['close'])
            entry_price = entry_raw * (1 + SPREAD_PCT)  # spread en entrada
            
            sl_dist = atr_4h * params['sl_multiplier']
            tp_dist = sl_dist * params['rr_ratio']
            
            if signal_type == 'BUY':
                sl   = entry_price - sl_dist
                tp   = entry_price + tp_dist
                side = 'LONG'
            else:
                sl   = entry_price + sl_dist
                tp   = entry_price - tp_dist
                side = 'SHORT'
            
            # ── Position sizing ──
            risk_usdt   = capital * params['risk_pct']
            size        = risk_usdt / sl_dist
            order_value = size * entry_price
            
            if order_value > capital * 0.95 or order_value <= 0:
                continue
            
            # Comisión de entrada
            capital -= (order_value * COMMISSION)
            
            open_position = {
                'entry_time': current_time,
                'entry':      entry_price,
                'sl':         sl,
                'tp':         tp,
                'size':       size,
                'side':       side
            }

        # ── Cierre forzado al final de los datos (Realizar PnL no realizado) ──
        if open_position is not None:
            last_candle = data['15m'].iloc[-1]
            exit_price  = float(last_candle['close'])
            
            if open_position['side'] == 'LONG':
                pnl = (exit_price - open_position['entry']) * open_position['size']
            else:
                pnl = (open_position['entry'] - exit_price) * open_position['size']
            
            commission_exit = exit_price * open_position['size'] * COMMISSION
            net_pnl = pnl - commission_exit
            capital += net_pnl
            
            trades.append({
                'entry_time':   str(open_position['entry_time']),
                'exit_time':    str(last_candle['open_time']),
                'side':         open_position['side'],
                'entry_price':  open_position['entry'],
                'exit_price':   round(exit_price, 6),
                'size':         open_position['size'],
                'pnl':          round(net_pnl, 4),
                'close_reason': 'DATA_END',
                'duration_hrs': 0
            })
            equity_curve.append({
                'timestamp': str(last_candle['open_time']),
                'equity':    round(capital, 2)
            })

        # PASO 3 — Calcular métricas finales
        total_trades   = len(trades)
        winning_trades = len([t for t in trades if t['pnl'] > 0])
        losing_trades  = len([t for t in trades if t['pnl'] <= 0])
        win_rate       = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit   = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss     = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor  = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        total_return   = ((capital - params['initial_capital']) /
                          params['initial_capital'] * 100)

        # Sharpe anualizado
        pnls = [t['pnl'] for t in trades]
        if len(pnls) > 1 and np.std(pnls) > 0:
            days_total     = (pd.Timestamp(params['end_date']) -
                              pd.Timestamp(params['start_date'])).days
            trades_per_yr  = total_trades / (days_total / 365) if days_total > 0 else 1
            sharpe = (float(np.mean(pnls)) / float(np.std(pnls))) * np.sqrt(trades_per_yr)
        else:
            sharpe = 0.0

        # Max Drawdown
        peak   = params['initial_capital']
        max_dd = 0.0
        for point in equity_curve:
            eq = point['equity']
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        avg_duration = (sum(t['duration_hrs'] for t in trades) /
                        total_trades) if total_trades > 0 else 0.0

        # PASO 4 — Guardar resultado en Supabase
        supabase.table('backtest_runs').update({
            'final_capital':        round(capital, 2),
            'total_return_pct':     round(total_return, 4),
            'win_rate':             round(win_rate, 2),
            'profit_factor':        round(profit_factor, 4),
            'sharpe_ratio':         round(sharpe, 4),
            'max_drawdown_pct':     round(max_dd, 4),
            'total_trades':         total_trades,
            'equity_curve':         equity_curve,
            'params_used':          params,
            'status':               'completed'
        }).eq('id', run_id).execute()

        return {
            'run_id': run_id,
            'metrics': {
                'total_return_pct':    round(total_return, 2),
                'win_rate':            round(win_rate, 2),
                'profit_factor':       round(profit_factor, 4),
                'sharpe_ratio':        round(sharpe, 4),
                'max_drawdown_pct':    round(max_dd, 2),
                'total_trades':        total_trades,
                'winning_trades':      winning_trades,
                'losing_trades':       losing_trades,
                'final_capital':       round(capital, 2),
                'avg_duration_hrs':    round(avg_duration, 2)
            },
            'equity_curve': equity_curve,
            'trades_sample': trades[:10]  # primeros 10 para preview
        }
    except Exception as e:
        logger.error(f"Error executing backtest: {str(e)}", exc_info=True)
        supabase.table('backtest_runs').update({
            'status': 'error',
            'error_message': str(e)
        }).eq('id', run_id).execute()
        return None
