"""
Backtester de eTrade Sprint 2.
Actualizado con Capital Dinámico y Cierre Parcial.
"""

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np

# Import EXACT same modules from the real pipeline
from app.analysis.indicators_v2 import calculate_all_indicators
from app.analysis.fibonacci_bb import extract_fib_levels, get_fibonacci_zone
from app.strategy.market_regime import classify_market_risk
from app.strategy.rule_engine import evaluate_all_rules, DEFAULT_RULES
from app.core.parameter_guard import get_active_params, validate_parameter_change
from app.execution.data_provider import BinanceCryptoProvider
from app.core.supabase_client import get_supabase
from app.core.config import settings
from app.core.logger import log_info, log_warning, log_error

MODULE = "BACKTESTER"

async def get_capital_config_from_db(sb) -> dict:
    """
    Lee la configuración de capital desde Supabase.
    Esta es la ÚNICA fuente de verdad para el backtester.
    Nunca usar valores hardcodeados.
    """
    try:
        result = sb.table('trading_config')\
            .select(
                'capital_total,'
                'pct_for_trading,'
                'trade_distribution'
            )\
            .eq('id', 1)\
            .single()\
            .execute()

        cfg           = result.data
        capital_total = float(cfg['capital_total'])
        pct_trading   = float(cfg['pct_for_trading']) / 100
        buffer        = 0.90  # 10% reserva de seguridad (fijo por diseño)
        capital_op    = capital_total * pct_trading * buffer

        # Leer distribución de trades desde la configuración
        distribution  = cfg.get('trade_distribution', {})
        t1_pct        = float(
            distribution.get('3_trades', {}).get('t1', 20)
        ) / 100

        capital_t1 = round(capital_op * t1_pct, 2)

        return {
            'capital_total':  capital_total,
            'capital_op':     round(capital_op, 2),
            'capital_t1':     capital_t1,
            't1_pct':         t1_pct,
            'pct_trading':    pct_trading,
        }

    except Exception as e:
        log_error('BACKTESTER',
            f'Error leyendo capital desde trading_config: {e}')
        raise RuntimeError(
            'No se pudo leer la configuración de capital desde '
            'Supabase. Verificar que trading_config tiene id=1 '
            'con capital_total y pct_for_trading definidos.'
        )

def _evaluate_position_close(position: dict,
                             bar: pd.Series,
                             current_price: float) -> dict:
    """
    Evalúa cierre con lógica de dos etapas igual al pipeline real:
      Etapa 1: cierre parcial en upper_5 / lower_5 (50% posición)
      Etapa 2: cierre total en upper_6 / lower_6 con confirmación
    """
    side = position['side']

    # ── SL HIT ──────────────────────────────────────────
    if side == 'long' and current_price <= position['sl_price']:
        return {
            'should_close':   True,
            'should_partial': False,
            'reason':         'sl',
            'exit_price':     position['sl_price'],
            'close_type':     'full'
        }
    if side == 'short' and current_price >= position['sl_price']:
        return {
            'should_close':   True,
            'should_partial': False,
            'reason':         'sl',
            'exit_price':     position['sl_price'],
            'close_type':     'full'
        }

    # ── CIERRE PARCIAL en upper_5 / lower_5 ─────────────
    # Solo si no se ha cerrado parcialmente antes
    if not position.get('partial_closed', False):
        if (side == 'long' and
                current_price >= position['tp_partial']):
            return {
                'should_close':   False,
                'should_partial': True,
                'reason':         'tp_partial',
                'exit_price':     current_price,
                'close_type':     'partial',
                'partial_pct':    0.50
            }
        if (side == 'short' and
                current_price <= position['tp_partial']):
            return {
                'should_close':   False,
                'should_partial': True,
                'reason':         'tp_partial',
                'exit_price':     current_price,
                'close_type':     'partial',
                'partial_pct':    0.50
            }

    # ── CIERRE TOTAL en upper_6 / lower_6 ───────────────
    # Con confirmación de volumen y vela (igual al pipeline real)
    defensive = (float(bar.get('ema4', 1)) < float(bar.get('ema5', 0)))

    if side == 'long' and current_price >= position['tp_full']:
        vol_ok    = bool(bar.get('vol_decreasing', False))
        candle_ok = (
            bool(bar.get('is_gravestone', False)) or
            bool(bar.get('high_lower_than_prev', False)) or
            bool(bar.get('is_red_candle', False))
        )
        if defensive or (vol_ok and candle_ok):
            return {
                'should_close':   True,
                'should_partial': False,
                'reason':         'tp_full',
                'exit_price':     current_price,
                'close_type':     'full'
            }

    if side == 'short' and current_price <= position['tp_full']:
        vol_ok    = bool(bar.get('vol_increasing', False))
        candle_ok = (
            bool(bar.get('is_dragonfly', False)) or
            bool(bar.get('low_higher_than_prev', False)) or
            bool(bar.get('is_green_candle', False))
        )
        if defensive or (vol_ok and candle_ok):
            return {
                'should_close':   True,
                'should_partial': False,
                'reason':         'tp_full',
                'exit_price':     current_price,
                'close_type':     'full'
            }

    return {'should_close': False, 'should_partial': False}


def _close_position(position: dict, 
                    close_result: dict, 
                    bar: pd.Series,
                    symbol: str, 
                    mode: str, 
                    capital_t1: float) -> dict:
    """Generate the trade record for insertion into paper_trades."""
    entry  = position['entry_price']
    exit_p = close_result.get('exit_price', float(bar['close']))
    side   = position['side']

    # PnL del cierre total (sobre el capital restante)
    if side == 'long':
        full_pnl_pct = (exit_p - entry) / entry * 100
    else:
        full_pnl_pct = (entry - exit_p) / entry * 100

    # Capital restante después del cierre parcial
    remaining = position.get(
        'remaining_capital', capital_t1
    )
    full_pnl_usd = round(remaining * (full_pnl_pct / 100), 4)

    # PnL total = parcial (si hubo) + total
    partial_pnl_usd = position.get('partial_pnl_usd', 0)
    partial_pnl_pct = position.get('partial_pnl_pct', 0)
    total_pnl_usd   = round(partial_pnl_usd + full_pnl_usd, 4)

    # PnL pct ponderado (parcial 50% + total 50%)
    partial_weight = position.get('partial_pct', 0)
    full_weight    = 1 - partial_weight
    total_pnl_pct  = round(
        (partial_pnl_pct * partial_weight) +
        (full_pnl_pct * full_weight), 4
    )

    return {
        'symbol':            symbol,
        'side':              side,
        'entry_price':       entry,
        'exit_price':        exit_p,
        'sl_price':          position['sl_price'],
        'tp_price':          position['tp_full'],
        'close_reason':      close_result.get('reason', 'unknown'),
        'had_partial_close': position.get('partial_closed', False),
        'partial_pnl_usd':   partial_pnl_usd,
        'partial_pnl_pct':   partial_pnl_pct,
        'full_pnl_usd':      full_pnl_usd,
        'full_pnl_pct':      round(full_pnl_pct, 4),
        'total_pnl_usd':     total_pnl_usd,
        'total_pnl_pct':     total_pnl_pct,
        'capital_t1_used':   capital_t1,
        'rule_code':         position.get('rule_code', 'unknown'),
        'regime':            position.get('regime', 'unknown'),
        'ema20_phase':       position.get('ema20_phase', ''),
        'adx_value':         position.get('adx_value', 0),
        'opened_at':         str(position.get('entry_time', '')),
        'closed_at':         str(bar.get("open_time", bar.name)),
        'mode':              mode,
        'market_type':       'futures',
        'leverage':          5, # hardcoded for backtest visualization
    }

async def run_backtest(
    symbol: str,
    timeframe: str = "15m",
    limit: int = 500,
    start_from_bar: int = 200,
    mode: str = "backtest",
) -> dict:
    log_info(MODULE, f"Iniciando backtest {symbol} {timeframe} ({limit} velas)")

    provider = BinanceCryptoProvider(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_secret,
        market="futures",
        testnet=settings.binance_testnet,
    )

    try:
        sb = get_supabase()
        
        # --- MEJORA 1: Capital Dinámico ---
        capital_cfg = await get_capital_config_from_db(sb)
        capital_t1  = capital_cfg['capital_t1']
        log_info(MODULE,
            f'Capital configurado: total=${capital_cfg["capital_total"]} '
            f'| operativo=${capital_cfg["capital_op"]} '
            f'| T1=${capital_t1}')

        # Download historical data
        print(f"  Descargando OHLCV {symbol}...")
        df_15m = await provider.get_ohlcv(symbol, timeframe, limit=limit)
        if df_15m is None or len(df_15m) < start_from_bar:
            log_warning(MODULE, f"Datos insuficientes para {symbol}")
            return {"error": "Datos insuficientes"}

        # Calculate indicators
        print(f"  Calculando indicadores...")
        df = calculate_all_indicators(df_15m)

        trades = []
        open_position = None
        rules_triggered = {}
        signals_evaluated = 0
        bars_with_signals = 0

        print(f"  Simulando barras {start_from_bar} a {len(df)-1}...")

        for i in range(start_from_bar, len(df)):
            bar_window = df.iloc[: i + 1].copy()
            last = bar_window.iloc[-1]
            current_price = float(last["close"])
            current_time = last.get("open_time", bar_window.index[-1])

            # Classify market regime & extract fib
            try:
                fib_levels = extract_fib_levels(bar_window)
                regime = classify_market_risk(bar_window)
            except Exception:
                continue

            # --- Evaluate position close or partial ---
            if open_position:
                close_result = _evaluate_position_close(
                    open_position, last, current_price
                )

                # NUEVO: manejar cierre parcial
                if close_result.get('should_partial'):
                    partial_pnl_pct = (
                        (close_result['exit_price'] -
                         open_position['entry_price'])
                        / open_position['entry_price'] * 100
                        if open_position['side'] == 'long'
                        else
                        (open_position['entry_price'] -
                         close_result['exit_price'])
                        / open_position['entry_price'] * 100
                    )
                    partial_capital = capital_t1 * close_result['partial_pct']
                    partial_pnl_usd = round(
                        partial_capital * (partial_pnl_pct / 100), 4
                    )

                    # Actualizar estado de la posición
                    open_position['partial_closed']     = True
                    open_position['partial_pct']        = close_result['partial_pct']
                    open_position['partial_exit_price'] = close_result['exit_price']
                    open_position['partial_pnl_pct']    = round(partial_pnl_pct, 4)
                    open_position['partial_pnl_usd']    = partial_pnl_usd
                    open_position['remaining_capital']  = (
                        capital_t1 * (1 - close_result['partial_pct'])
                    )

                    log_info('BACKTESTER',
                        f'{symbol}: Cierre parcial en '
                        f'${close_result["exit_price"]:,.2f} | '
                        f'PnL parcial: {partial_pnl_pct:.2f}% '
                        f'(${partial_pnl_usd})')

                # Cierre total: registrar trade completo
                if close_result.get('should_close'):
                    trade = _close_position(
                        open_position, close_result, last,
                        symbol, mode, capital_t1=capital_t1
                    )
                    trades.append(trade)
                    open_position = None

            # --- Evaluate entry ---
            if open_position is None:
                signals_evaluated += 1
                try:
                    rule_match = evaluate_all_rules(
                        df=bar_window,
                        fib_levels=fib_levels,
                        regime=regime,
                        rules=DEFAULT_RULES,
                    )
                except Exception:
                    rule_match = None

                if rule_match:
                    # Check RR
                    _cfg = get_active_params(regime["category"], sb)
                    _atr = float(last.get("atr", 0))
                    if _atr <= 0: _atr = current_price * 0.01
                    
                    _atr_mult = _cfg.get("atr_mult", 2.0)
                    _rr_min = _cfg.get("rr_min", 2.0)
                    _side = rule_match["direction"]
                    
                    # Target TP = upper_6 / lower_6
                    _tp_target = fib_levels.get("upper_6" if _side == "long" else "lower_6", 0)
                    if _tp_target == 0:
                        _tp_target = current_price * (1.05 if _side == "long" else 0.95)
                    
                    _sl = current_price - (_atr * _atr_mult) if _side == "long" else current_price + (_atr * _atr_mult)
                    
                    # Effective RR (including fees)
                    _fee = _cfg.get("fee_pct", 0.001)
                    _entry_eff = current_price * (1 + _fee if _side == "long" else 1 - _fee)
                    _tp_eff = _tp_target * (1 - _fee if _side == "long" else 1 + _fee)
                    _sl_eff = _sl * (1 - _fee if _side == "long" else 1 + _fee)
                    
                    _rr_real = abs(_tp_eff - _entry_eff) / abs(_entry_eff - _sl_eff) if abs(_entry_eff - _sl_eff) > 0 else 0

                    if _rr_real >= _rr_min:
                        bars_with_signals += 1
                        rule_code = rule_match["rule"]["rule_code"]
                        rules_triggered[rule_code] = rules_triggered.get(rule_code, 0) + 1

                        # Open position
                        atr_mult = _cfg.get("atr_mult", 2.0)
                        open_position = {
                            "symbol": symbol,
                            "side": _side,
                            "entry_price": current_price,
                            "entry_time": current_time,
                            "sl_price": _sl,
                            "tp_partial": fib_levels.get("upper_5" if _side == "long" else "lower_5", current_price),
                            "tp_full": _tp_target,
                            "rule_code": rule_code,
                            "regime": regime["category"],
                            "risk_score": regime["risk_score"],
                            "ema20_phase": str(last.get("ema20_phase", "")),
                            "adx_value": float(last.get("adx", 0)),
                            "fibonacci_zone_entry": fib_levels.get("zone", 0),
                            "mode": mode,
                            "partial_closed": False
                        }

        # Metrics
        results = _calculate_performance_metrics(trades, symbol, timeframe)
        results["rules_triggered"] = rules_triggered
        results["trades"] = trades
        results["signals_evaluated"] = signals_evaluated
        results["bars_with_signals"] = bars_with_signals
        results["total_bars_analyzed"] = len(df) - start_from_bar
        results["capital_cfg"] = capital_cfg

        return results

    except Exception as e:
        log_error(MODULE, f"Error en backtest: {e}")
        traceback.print_exc()
        return {"error": str(e)}

def _calculate_performance_metrics(trades: list, symbol: str, timeframe: str) -> dict:
    if not trades:
        return {"symbol": symbol, "timeframe": timeframe, "total_trades": 0, "win_rate_pct": 0, "total_pnl_usd": 0}

    winning = [t for t in trades if t["total_pnl_pct"] > 0]
    total_pnl = sum(t["total_pnl_usd"] for t in trades)
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(trades) - len(winning),
        "win_rate_pct": round(len(winning) / len(trades) * 100, 1),
        "total_pnl_usd": round(total_pnl, 2),
        "avg_rr_real": round(sum(t.get("total_pnl_pct", 0) for t in winning) / len(winning), 2) if winning else 0
    }

async def save_backtest_to_supabase(results: dict) -> bool:
    sb = get_supabase()
    trades = results.pop("trades", [])
    cap_cfg = results.get("capital_cfg", {})
    initial_cap = cap_cfg.get("capital_t1", 18.0)
    
    try:
        total_pnl = results.get("total_pnl_usd", 0)
        start_date = "2026-01-01"
        end_date = "2026-01-01"
        if trades:
            start_date = str(trades[0].get("opened_at"))[:10]
            end_date = str(trades[-1].get("closed_at"))[:10]

        sb.table("backtest_runs").insert({
            "strategy_name": "RuleEngine_v4_PartialClose",
            "symbol": results.get("symbol"),
            "start_date": start_date,
            "end_date": end_date,
            "total_trades": results.get("total_trades"),
            "winning_trades": results.get("winning_trades"),
            "losing_trades": results.get("losing_trades"),
            "win_rate": results.get("win_rate_pct"),
            "initial_capital": initial_cap,
            "final_capital": round(initial_cap + total_pnl, 2),
            "total_return_pct": round((total_pnl / initial_cap * 100), 4) if initial_cap > 0 else 0,
            "status": "completed",
            "params_used": results
        }).execute()
        
        # Batch insert trades
        if trades:
            # Add mode to trades
            for t in trades: t['mode'] = 'backtest'
            for i in range(0, len(trades), 50):
                sb.table("paper_trades").insert(trades[i:i+50]).execute()
        return True
    except Exception as e:
        log_error(MODULE, f"Error saving backtest: {e}")
        return False
