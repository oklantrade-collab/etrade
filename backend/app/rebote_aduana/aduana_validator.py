import os
import sys
from datetime import datetime, timezone
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from app.rebote_aduana.config import ADUANA_PARAMS, MODULE
from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

@dataclass
class AduanaResult:
    approved: bool = True
    rule_triggered: str = ''    # '' if approved
    reason: str = ''
    step: int = 0               # Pipeline step (1-6)
    detail: dict = field(default_factory=dict)

class AduanaValidator:
    def __init__(self, params: dict = None, oraculo_manager=None):
        self.params = params or ADUANA_PARAMS
        self.oraculo = oraculo_manager

    def _normalize_side(self, side: str) -> str:
        s = side.lower()
        if s in ('buy', 'long'):
            return 'long'
        elif s in ('sell', 'short'):
            return 'short'
        return s

    def _get_fib_zone(self, df_15m: pd.DataFrame) -> int:
        if df_15m is None or df_15m.empty or len(df_15m) < 2:
            return 0
        last_closed = df_15m.iloc[-2] if len(df_15m) > 1 else df_15m.iloc[-1]
        try:
            val = last_closed.get('fibonacci_zone', 0)
            if val is None or pd.isna(val):
                return 0
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    def _get_halcon_macro_scores(self, symbol: str) -> dict:
        try:
            supabase = get_supabase()
            response = supabase.table('halcon_scores_log').select('*').eq('symbol', symbol).order('created_at', desc=True).limit(1).execute()
            if response.data and len(response.data) > 0:
                record = response.data[0]
                scores = record.get('scores_by_layer', {})
                return {
                    'score_1d': float(scores.get('1d', 0)),
                    'score_4h': float(scores.get('4h', 0))
                }
        except Exception as e:
            log_error(f"Error getting halcon macro scores: {e}", MODULE)
        return {'score_1d': 0.0, 'score_4h': 0.0}

    def _check_impulse_candle(self, df_15m: pd.DataFrame, side: str) -> tuple:
        if df_15m is None or df_15m.empty or len(df_15m) < 2:
            return False, ''
            
        last_closed = df_15m.iloc[-2] if len(df_15m) > 1 else df_15m.iloc[-1]
        try:
            high = float(last_closed.get('high', 0))
            low = float(last_closed.get('low', 0))
            close_p = float(last_closed.get('close', 0))
            open_p = float(last_closed.get('open', 0))
            atr = float(last_closed.get('atr', 0))
        except (ValueError, TypeError):
            return False, ''

        if atr == 0:
            return False, ''

        rng = high - low
        ratio = self.params.get('impulse_candle_atr_ratio', 1.8)
        is_impulse = rng > (ratio * atr)
        
        candle_dir = 'bullish' if close_p > open_p else 'bearish'
        
        return is_impulse, candle_dir

    def _check_range_regime(self, df_15m: pd.DataFrame) -> bool:
        if df_15m is None or df_15m.empty or len(df_15m) < 2:
            return False
            
        last_closed = df_15m.iloc[-2] if len(df_15m) > 1 else df_15m.iloc[-1]
        prev_closed = df_15m.iloc[-3] if len(df_15m) > 2 else last_closed
        
        try:
            adx = float(last_closed.get('adx', 0))
            bb_width = float(last_closed.get('bb_width', 100))
            ema20_curr = float(last_closed.get('ema_20', 0))
            ema20_prev = float(prev_closed.get('ema_20', 0))
        except (ValueError, TypeError):
            return False
            
        adx_thresh = self.params.get('adx_range_threshold', 20.0)
        bb_thresh = self.params.get('range_bb_bandwidth_threshold', 0.1)
        
        slope = abs(ema20_curr - ema20_prev) / ema20_prev if ema20_prev > 0 else 0
        
    def _extract_rsi_15m(self, df_15m: pd.DataFrame, market_data: dict) -> float:
        if market_data:
            rsi_val = market_data.get('rsi_15m') or market_data.get('rsi')
            if rsi_val is not None:
                try:
                    return float(rsi_val)
                except (ValueError, TypeError):
                    pass
        if df_15m is not None and not df_15m.empty:
            if 'rsi' in df_15m.columns:
                try:
                    return float(df_15m['rsi'].iloc[-1])
                except (ValueError, TypeError):
                    pass
            if len(df_15m) >= 15 and 'close' in df_15m.columns:
                try:
                    delta = df_15m['close'].diff()
                    gain = delta.clip(lower=0).rolling(window=14).mean()
                    loss = (-delta.clip(upper=0)).rolling(window=14).mean()
                    rs = gain / (loss.replace(0, 1e-9))
                    rsi_series = 100 - (100 / (1 + rs))
                    val = rsi_series.iloc[-1]
                    if not pd.isna(val):
                        return float(val)
                except Exception:
                    pass
        return 50.0

    def _check_pullback_to_ema(self, df_15m: pd.DataFrame, side: str, market_data: dict) -> tuple[bool, str]:
        """
        Para estrategias de tendencia:
        Verifica que la vela reciente haya hecho pullback a EMA9 o EMA20.
        Retorna (passed, reason).
        """
        price = 0.0
        if market_data:
            price = float(market_data.get('price') or 0.0)
        
        last_row = None
        if df_15m is not None and len(df_15m) >= 1:
            last_row = df_15m.iloc[-1]
        
        if last_row is None:
            return True, ""
            
        if price <= 0:
            price = float(last_row.get('close', 0.0))
            
        ema9 = float(last_row.get('ema9') or last_row.get('ema2') or (market_data.get('ema9') if market_data else 0) or 0)
        ema20 = float(last_row.get('ema20') or last_row.get('ema3') or last_row.get('ema_20') or (market_data.get('ema20') if market_data else 0) or 0)
        
        if ema9 <= 0:
            return True, ""
            
        high_curr = float(last_row.get('high', price))
        low_curr = float(last_row.get('low', price))
        
        norm_side = self._normalize_side(side)
        if norm_side == 'short':
            # Si el precio está por debajo de EMA9, exigir que el High de la vela actual haya alcanzado al menos EMA9 * 0.9998
            if price < ema9 * 0.9998:
                has_pullback = (high_curr >= ema9 * 0.9998) or (ema20 > ema9 and high_curr >= ema20 * 0.9998)
                if not has_pullback:
                    return False, f"Sobre-extendido sin pullback a EMA9 (High {high_curr:.5f} < EMA9 {ema9:.5f})"
        elif norm_side == 'long':
            # Si el precio está por encima de EMA9, exigir que el Low de la vela actual haya tocado al menos EMA9 * 1.0002
            if price > ema9 * 1.0002:
                has_pullback = (low_curr <= ema9 * 1.0002) or (0 < ema20 < ema9 and low_curr <= ema20 * 1.0002)
                if not has_pullback:
                    return False, f"Sobre-extendido sin pullback a EMA9 (Low {low_curr:.5f} > EMA9 {ema9:.5f})"
                    
        return True, ""

    def _check_bollinger_curvature(self, df_15m: pd.DataFrame, side: str) -> tuple[bool, str]:
        """
        Verifica que la banda de Bollinger no esté girando/curvándose en contra del trade.
        Retorna (passed, reason).
        """
        if df_15m is None or len(df_15m) < 3:
            return True, ""
            
        norm_side = self._normalize_side(side)
        col_lower = 'lower_2' if 'lower_2' in df_15m.columns else ('bb_lower' if 'bb_lower' in df_15m.columns else ('lower_6' if 'lower_6' in df_15m.columns else None))
        col_upper = 'upper_2' if 'upper_2' in df_15m.columns else ('bb_upper' if 'bb_upper' in df_15m.columns else ('upper_6' if 'upper_6' in df_15m.columns else None))
        
        if norm_side == 'short' and col_lower:
            try:
                b_curr = float(df_15m[col_lower].iloc[-1])
                b_prev1 = float(df_15m[col_lower].iloc[-2])
                b_prev2 = float(df_15m[col_lower].iloc[-3])
                # Si la banda inferior ya subió en las últimas 2 velas continuas (curvando hacia arriba)
                if b_curr > b_prev1 and b_prev1 >= b_prev2:
                    return False, f"Banda inferior de Bollinger curvándose hacia arriba ({b_curr:.5f} > {b_prev1:.5f})"
            except Exception:
                pass
        elif norm_side == 'long' and col_upper:
            try:
                b_curr = float(df_15m[col_upper].iloc[-1])
                b_prev1 = float(df_15m[col_upper].iloc[-2])
                b_prev2 = float(df_15m[col_upper].iloc[-3])
                # Si la banda superior ya bajó en las últimas 2 velas continuas (curvando hacia abajo)
                if b_curr < b_prev1 and b_prev1 <= b_prev2:
                    return False, f"Banda superior de Bollinger curvándose hacia abajo ({b_curr:.5f} < {b_prev1:.5f})"
            except Exception:
                pass
                
        return True, ""

    def _check_consecutive_candles(self, df_15m: pd.DataFrame, side: str, max_consecutive: int = 5) -> tuple[bool, str]:
        """
        Verifica si hay demasiadas velas consecutivas del mismo color (impulso agotado).
        Retorna (passed, reason).
        """
        if df_15m is None or len(df_15m) < max_consecutive + 1:
            return True, ""
            
        norm_side = self._normalize_side(side)
        try:
            count = 0
            for i in range(1, max_consecutive + 3):
                if i > len(df_15m):
                    break
                row = df_15m.iloc[-i]
                c = float(row.get('close', 0))
                o = float(row.get('open', 0))
                if norm_side == 'short' and c < o:
                    count += 1
                elif norm_side == 'long' and c > o:
                    count += 1
                else:
                    break
            if count >= max_consecutive:
                color = "rojas" if norm_side == 'short' else "verdes"
                return False, f"Agotamiento por {count} velas {color} consecutivas en 15m (máx={max_consecutive})"
        except Exception:
            pass
            
        return True, ""

    def validate(self, symbol: str, side: str, order_type: str,
                 market_data: dict, strategy: str = '',
                 halcon_scores: dict = None,
                 contra_trend_confirmed: bool = False,
                 market_type: str = None,
                 **kwargs) -> AduanaResult:
        
        norm_side = self._normalize_side(side)
        df_15m = market_data.get('df_15m')
        df_5m = market_data.get('df_5m')
        is_test = 'PYTEST_CURRENT_TEST' in os.environ or 'pytest' in sys.modules

        # Step 0.1: Check Integridad y Frescura de Datos del Broker (Candle Integrity & Staleness)
        if not market_data.get('is_test', False) and not market_data.get('bypass_data_integrity', False):
            for tf_name, df_check in [('5m', df_5m), ('15m', df_15m)]:
                if df_check is not None:
                    if len(df_check) < 20:
                        return AduanaResult(
                            approved=False,
                            rule_triggered='INSUFFICIENT_CANDLE_DATA',
                            reason=f'Datos incompletos de velas {tf_name} ({len(df_check)} < 20 velas necesarias)',
                            step=0
                        )
                    last_5 = df_check.iloc[-5:]
                    for col in ['open', 'high', 'low', 'close']:
                        if col in last_5.columns and last_5[col].isna().any():
                            return AduanaResult(
                                approved=False,
                                rule_triggered='CANDLE_DATA_CORRUPTED',
                                reason=f'Velas {tf_name} contienen valores nulos (NaN) en columna {col}',
                                step=0
                            )
                    # Comprobación de antigüedad (Staleness)
                    ts_val = None
                    if 'timestamp' in df_check.columns:
                        ts_val = df_check['timestamp'].iloc[-1]
                    elif 'datetime' in df_check.columns:
                        ts_val = df_check['datetime'].iloc[-1]
                    elif isinstance(df_check.index, pd.DatetimeIndex):
                        ts_val = df_check.index[-1]

                    if ts_val is not None:
                        try:
                            if isinstance(ts_val, (int, float)):
                                # Si viene en millisegundos
                                if ts_val > 1e11:
                                    ts_val = ts_val / 1000.0
                                dt_candle = datetime.fromtimestamp(ts_val, timezone.utc)
                            elif isinstance(ts_val, str):
                                dt_candle = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
                            elif hasattr(ts_val, 'to_pydatetime'):
                                dt_candle = ts_val.to_pydatetime()
                                if dt_candle.tzinfo is None:
                                    dt_candle = dt_candle.replace(tzinfo=timezone.utc)
                            else:
                                dt_candle = ts_val

                            now_utc = datetime.now(timezone.utc)
                            age_sec = (now_utc - dt_candle).total_seconds()
                            max_age = 900 if tf_name == '5m' else 2700  # 15m para 5m, 45m para 15m
                            if age_sec > max_age:
                                return AduanaResult(
                                    approved=False,
                                    rule_triggered='STALE_CANDLE_DATA_BLOCKED',
                                    reason=f'Velas de {tf_name} desactualizadas (antigüedad={age_sec/60:.1f} min > límite {max_age/60:.0f} min)',
                                    step=0
                                )
                        except Exception as e_ts:
                            log_warning(MODULE, f"Error validando timestamp de velas {tf_name}: {e_ts}")

        # Step 0.2: Check Discrepancia de Precio con Ticker en Vivo del Broker
        broker_ticker_px = float(market_data.get('broker_ticker_price') or market_data.get('ticker_price') or market_data.get('live_price') or 0.0)
        if broker_ticker_px > 0:
            ref_px = float(market_data.get('price') or (df_5m['close'].iloc[-1] if df_5m is not None and not df_5m.empty else (df_15m['close'].iloc[-1] if df_15m is not None and not df_15m.empty else 0.0)))
            if ref_px > 0:
                disc_pct = abs(ref_px - broker_ticker_px) / broker_ticker_px
                if disc_pct > 0.0040: # > 0.40%
                    return AduanaResult(
                        approved=False,
                        rule_triggered='PRICE_DISCREPANCY_BLOCKED',
                        reason=f'Discrepancia de precio entre vela ({ref_px:.4f}) y Ticker del Broker ({broker_ticker_px:.4f}) es {disc_pct*100:.2f}% (> 0.40%)',
                        step=0
                    )

        # Step 0: Check Cant. Monedas Activas (Forex & Crypto)
        step = 0
        open_symbols = market_data.get('open_symbols')
        max_active_symbols = market_data.get('max_active_symbols')
        
        sym_clean = symbol.replace('/', '').replace('_', '').upper()
        is_forex = sym_clean in ('EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY') or 'XAU' in sym_clean or 'GOLD' in sym_clean

        if not is_test and (open_symbols is None or max_active_symbols is None):
            try:
                supabase_c = get_supabase()
                tbl = 'forex_positions' if is_forex else 'positions'
                if open_symbols is None:
                    valid_statuses = ['open', 'pending', 'pending_limit'] if is_forex else ['open', 'pending']
                    res_sym = supabase_c.table(tbl).select('symbol').in_('status', valid_statuses).execute()
                    open_symbols = list(set([r['symbol'] for r in (res_sym.data or []) if r.get('symbol')]))
                if max_active_symbols is None:
                    tc_res = supabase_c.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
                    rp = (tc_res.data or {}).get('regime_params') or {}
                    max_active_symbols = int(rp.get('max_active_symbols_forex' if is_forex else 'max_active_symbols_crypto', 1))
            except Exception:
                pass

        if open_symbols is not None and max_active_symbols is not None:
            open_set = set(open_symbols)
            if symbol not in open_set and len(open_set) >= int(max_active_symbols):
                return AduanaResult(
                    approved=False,
                    rule_triggered='MAX_ACTIVE_SYMBOLS_REACHED',
                    reason=f'Cant. Monedas Activas alcanzado ({len(open_set)}/{max_active_symbols} activas: {list(open_set)})',
                    step=step
                )

        # Step 1: Check ORÁCULO trading_paused
        step = 1
        is_paused = False
        if self.oraculo and hasattr(self.oraculo, 'is_paused'):
            is_paused = self.oraculo.is_paused(symbol)
        else:
            try:
                supabase = get_supabase()
                resp = supabase.table('trading_state').select('trading_paused').eq('symbol', symbol).execute()
                if resp.data and len(resp.data) > 0:
                    is_paused = bool(resp.data[0].get('trading_paused', False))
            except Exception:
                pass
                
        if is_paused:
            return AduanaResult(approved=False, rule_triggered='ORACULO_PAUSE', reason='Trading is paused by Oraculo', step=step)

        # Step 1.5: Check Cant. Operación x Par (Max Positions Per Symbol)
        step = 1
        current_symbol_positions = market_data.get('current_symbol_positions')
        max_positions_per_symbol = market_data.get('max_positions_per_symbol')
        
        if not is_test and (current_symbol_positions is None or max_positions_per_symbol is None):
            try:
                supabase_c = get_supabase()
                tbl = 'forex_positions' if is_forex else 'positions'
                if current_symbol_positions is None:
                    if is_forex:
                        pos_res = supabase_c.table(tbl).select('id').eq('symbol', symbol).in_('status', ['open', 'pending', 'pending_limit']).execute()
                    else:
                        pos_res = supabase_c.table(tbl).select('id').eq('symbol', symbol).in_('status', ['open', 'pending']).execute()
                    current_symbol_positions = len(pos_res.data or [])
                if max_positions_per_symbol is None:
                    rc_res = supabase_c.table('risk_config').select('max_positions_per_symbol').limit(1).execute()
                    max_positions_per_symbol = int((rc_res.data[0] if rc_res.data else {}).get('max_positions_per_symbol', 3))
            except Exception:
                pass

        if current_symbol_positions is not None and max_positions_per_symbol is not None:
            if int(current_symbol_positions) >= int(max_positions_per_symbol):
                return AduanaResult(
                    approved=False,
                    rule_triggered='MAX_POSITIONS_PER_SYMBOL_REACHED',
                    reason=f'Límite de posiciones por par alcanzado ({current_symbol_positions}/{max_positions_per_symbol}) para orden {order_type.upper()}',
                    step=step
                )

        # Step 1.6: Bloqueo de Re-Entrada en la Misma Dirección ante Drawdown > 5 pips
        is_erep_strategy = strategy.startswith('Bb33_EREP') or 'EREP' in strategy
        is_booster = 'BOOSTER' in strategy.upper()
        if not is_erep_strategy and not is_booster:
            try:
                active_positions = market_data.get('active_positions')
                if active_positions is None and not is_test:
                    supabase_c = get_supabase()
                    tbl = 'forex_positions' if is_forex else 'positions'
                    p_res = supabase_c.table(tbl).select('*').eq('symbol', symbol).in_('status', ['open', 'pending']).execute()
                    active_positions = p_res.data or []
                
                if active_positions:
                    current_px = float(market_data.get('price') or (df_15m['close'].iloc[-1] if df_15m is not None and not df_15m.empty else 0.0))
                    pip_sz = 0.01 if ('JPY' in sym_clean or 'XAU' in sym_clean or 'GOLD' in sym_clean) else 0.0001
                    for p in active_positions:
                        p_side = self._normalize_side(str(p.get('side') or ''))
                        if p_side == norm_side:
                            p_entry = float(p.get('entry_price') or p.get('open_price') or p.get('avg_entry_price') or 0.0)
                            if p_entry > 0 and current_px > 0:
                                if is_forex:
                                    dd_val = (current_px - p_entry) / pip_sz if norm_side == 'short' else (p_entry - current_px) / pip_sz
                                    is_in_dd = dd_val >= 5.0
                                    dd_msg = f"{dd_val:.1f} pips (>= 5.0 pips)"
                                else:
                                    dd_val = ((current_px - p_entry) / p_entry * 100.0) if norm_side == 'short' else ((p_entry - current_px) / p_entry * 100.0)
                                    is_in_dd = dd_val >= 0.50
                                    dd_msg = f"{dd_val:.2f}% (>= 0.50%)"

                                if is_in_dd:
                                    return AduanaResult(
                                        approved=False,
                                        rule_triggered='SAME_SIDE_DRAWDOWN_BLOCKED',
                                        reason=f'Re-entrada {norm_side.upper()} bloqueada en {symbol}: Ya existe posición en la misma dirección con Drawdown de {dd_msg}',
                                        step=step
                                    )
            except Exception as dd_err:
                log_warning(f"Error checking same side drawdown in Aduana: {dd_err}", MODULE)

        # Step 1.7: Macro 1D Direction Check (EMA3 vs EMA9)
        step = 1
        df_1d = market_data.get('df_1d')
        if df_1d is not None and len(df_1d) >= 10:
            ema3_1d = float(df_1d['close'].ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_1d = float(df_1d['close'].ewm(span=9, adjust=False).mean().iloc[-1])
            if norm_side == 'long' and ema3_1d < ema9_1d:
                return AduanaResult(
                    approved=False,
                    rule_triggered='MACRO_BIAS_CONFLICT',
                    reason=f'Operación LONG rechazada por sesgo macro bajista en 1D (EMA3={ema3_1d:.5f} < EMA9={ema9_1d:.5f}) para orden {order_type.upper()}',
                    step=step
                )
            elif norm_side == 'short' and ema3_1d > ema9_1d:
                return AduanaResult(
                    approved=False,
                    rule_triggered='MACRO_BIAS_CONFLICT',
                    reason=f'Operación SHORT rechazada por sesgo macro alcista en 1D (EMA3={ema3_1d:.5f} > EMA9={ema9_1d:.5f}) para orden {order_type.upper()}',
                    step=step
                )

        # Step 1.8: Non-Squeeze 15m RSI Extrema Check (35 / 65)
        step = 1
        df_15m = market_data.get('df_15m')
        is_squeeze = market_data.get('is_squeeze')
        rsi_15m = market_data.get('rsi_15m')
        is_qshr_strategy = strategy.startswith('Bb33_QSHR') or strategy in ('Bb33_QSHR', 'qshr_v5')
        is_erep_strategy = strategy.startswith('Bb33_EREP') or 'EREP' in strategy

        # Auto-detect is_squeeze and rsi_15m from df_15m if not provided
        if df_15m is not None and len(df_15m) >= 20:
            df_calc = df_15m.copy()
            if 'sma20' not in df_calc.columns:
                df_calc['sma20'] = df_calc['close'].rolling(20).mean()
            if 'std20' not in df_calc.columns:
                df_calc['std20'] = df_calc['close'].rolling(20).std()
            
            sma20_val = float(df_calc['sma20'].iloc[-1])
            std20_val = float(df_calc['std20'].iloc[-1])
            bw = (4.0 * std20_val) / sma20_val if sma20_val > 0 else 0.0
            
            if is_squeeze is None:
                sq_thresh = 0.0030 if is_forex else 0.015
                is_squeeze = bool(bw <= sq_thresh)

            if rsi_15m is None:
                if 'rsi' in df_calc.columns and not pd.isna(df_calc['rsi'].iloc[-1]):
                    rsi_15m = float(df_calc['rsi'].iloc[-1])
                elif len(df_calc) >= 15:
                    delta = df_calc['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / (loss + 1e-10)
                    rsi_series = 100 - (100 / (1 + rs))
                    rsi_15m = float(rsi_series.iloc[-1])

        is_trend_strategy = any(k in strategy for k in ('Aa61', 'AaHot', 'BbHot', 'Aa13', 'Bb13', 'Aa21', 'Bb25', 'Aa33', 'Bb33', 'Bb41', 'Bb12', 'Bb40', 'Bb11', 'AaApexEma', 'BbApexEma', 'Breakout', 'breakout', 'Trend', 'trend', 'Momentum', 'momentum'))

        if not is_trend_strategy and not is_qshr_strategy and not is_erep_strategy and rsi_15m is not None and not is_squeeze:
            # 1. No-Trade Deadzone Check (RSI 40 - 60)
            if 40.0 <= rsi_15m <= 60.0:
                return AduanaResult(
                    approved=False,
                    rule_triggered='RSI_DEADZONE_BLOCKED',
                    reason=f'RSI 15m ({rsi_15m:.1f}) en zona muerta (40-60); operaciones bloqueadas para evitar compras/ventas en punto medio para orden {order_type.upper()}',
                    step=step
                )

            # 2. Long Oversold Check (RSI <= 35)
            if norm_side == 'long' and rsi_15m > 35.0:
                return AduanaResult(
                    approved=False,
                    rule_triggered='RSI_NOT_OVERSOLD',
                    reason=f'RSI 15m ({rsi_15m:.1f} > 35) fuera de sobreventa; compras fuera de Squeeze exigen RSI <= 35 para orden {order_type.upper()}',
                    step=step
                )

            # 3. Short Overbought Check (RSI >= 65)
            if norm_side == 'short' and rsi_15m < 65.0:
                return AduanaResult(
                    approved=False,
                    rule_triggered='RSI_NOT_OVERBOUGHT',
                    reason=f'RSI 15m ({rsi_15m:.1f} < 65) fuera de sobrecompra; ventas fuera de Squeeze exigen RSI >= 65 para orden {order_type.upper()}',
                    step=step
                )

        # Step 1.9: Bollinger Bands 15m Extreme Piercing Check
        step = 1
        require_bb_extreme = market_data.get('require_bb_extreme', True)

        if not is_trend_strategy and require_bb_extreme and df_15m is not None and len(df_15m) >= 20 and not is_qshr_strategy and not is_erep_strategy:
            df_bb = df_15m.copy()
            df_bb['sma20'] = df_bb['close'].rolling(20).mean()
            df_bb['std20'] = df_bb['close'].rolling(20).std()
            last_sma20 = float(df_bb['sma20'].iloc[-1])
            last_std20 = float(df_bb['std20'].iloc[-1])
            upper_bb = last_sma20 + 2.0 * last_std20
            lower_bb = last_sma20 - 2.0 * last_std20
            last_high = float(df_bb['high'].iloc[-1])
            last_low = float(df_bb['low'].iloc[-1])
            last_close = float(df_bb['close'].iloc[-1])
            
            # Tolerance in pips (0.00015 for Forex, 0.5 for crypto/metals)
            tol = 0.00015 if is_forex else 0.5
            
            if norm_side == 'long':
                if min(last_low, last_close) > (lower_bb + tol):
                    return AduanaResult(
                        approved=False,
                        rule_triggered='BB_EXTREME_NOT_REACHED',
                        reason=f'Precio no ha cruzado Banda Inferior de 15m (Low={last_low:.5f} > LowerBB={lower_bb:.5f}) para orden {order_type.upper()}',
                        step=step
                    )
            elif norm_side == 'short':
                if max(last_high, last_close) < (upper_bb - tol):
                    return AduanaResult(
                        approved=False,
                        rule_triggered='BB_EXTREME_NOT_REACHED',
                        reason=f'Precio no ha cruzado Banda Superior de 15m (High={last_high:.5f} < UpperBB={upper_bb:.5f}) para orden {order_type.upper()}',
                        step=step
                    )

        # Step 1.95: Micro 5m EMA Alignment Guard (Evitar compras en caída libre o ventas en subida parabólica de 5m)
        df_5m = market_data.get('df_5m')
        if df_5m is not None and len(df_5m) >= 20 and not is_qshr_strategy and not is_erep_strategy:
            c5 = pd.to_numeric(df_5m['Close'] if 'Close' in df_5m.columns else df_5m.get('close', pd.Series()), errors='coerce').dropna()
            o5 = pd.to_numeric(df_5m['Open'] if 'Open' in df_5m.columns else df_5m.get('open', pd.Series()), errors='coerce').dropna()
            
            if len(c5) >= 20 and len(o5) >= 20:
                ema3_5m_series = c5.ewm(span=3, adjust=False).mean()
                ema9_5m_series = c5.ewm(span=9, adjust=False).mean()
                ema20_5m_series = c5.ewm(span=20, adjust=False).mean()
                
                ema3_5m = float(ema3_5m_series.iloc[-1])
                ema9_5m = float(ema9_5m_series.iloc[-1])
                ema20_5m = float(ema20_5m_series.iloc[-1])
                
                last_c5 = float(c5.iloc[-1])
                last_o5 = float(o5.iloc[-1])
                
                is_candle_green_5m = last_c5 > last_o5
                is_candle_red_5m = last_c5 < last_o5
                
                if norm_side == 'long':
                    # Bloqueo 1: Cascada bajista activa en 5m (EMA3 < EMA9 < EMA20)
                    if ema3_5m < ema9_5m < ema20_5m:
                        if not (is_candle_green_5m and last_c5 > ema3_5m):
                            return AduanaResult(
                                approved=False,
                                rule_triggered='REJECT_5M_BEARISH_CASCADE',
                                reason=f'Orden LONG rechazada: Cascada bajista en 5m (EMA3={ema3_5m:.5f} < EMA9={ema9_5m:.5f} < EMA20={ema20_5m:.5f}) sin vela verde de giro sobre EMA3 para {order_type.upper()}',
                                step=1
                            )
                    # Bloqueo 2: Momento bajista con vela roja en 5m (EMA3 < EMA9 y vela roja)
                    elif ema3_5m < ema9_5m and is_candle_red_5m:
                        return AduanaResult(
                            approved=False,
                            rule_triggered='REJECT_5M_RED_MOMENTUM',
                            reason=f'Orden LONG rechazada: Inercia bajista en 5m (EMA3={ema3_5m:.5f} < EMA9={ema9_5m:.5f} con vela roja) para {order_type.upper()}',
                            step=1
                        )
                elif norm_side == 'short':
                    # Bloqueo 1: Cascada alcista activa en 5m (EMA3 > EMA9 > EMA20)
                    if ema3_5m > ema9_5m > ema20_5m:
                        if not (is_candle_red_5m and last_c5 < ema3_5m):
                            return AduanaResult(
                                approved=False,
                                rule_triggered='REJECT_5M_BULLISH_CASCADE',
                                reason=f'Orden SHORT rechazada: Cascada alcista en 5m (EMA3={ema3_5m:.5f} > EMA9={ema9_5m:.5f} > EMA20={ema20_5m:.5f}) sin vela roja de giro bajo EMA3 para {order_type.upper()}',
                                step=1
                            )
                    # Bloqueo 2: Momento alcista con vela verde en 5m (EMA3 > EMA9 y vela verde)
                    elif ema3_5m > ema9_5m and is_candle_green_5m:
                        return AduanaResult(
                            approved=False,
                            rule_triggered='REJECT_5M_GREEN_MOMENTUM',
                            reason=f'Orden SHORT rechazada: Inercia alcista en 5m (EMA3={ema3_5m:.5f} > EMA9={ema9_5m:.5f} con vela verde) para {order_type.upper()}',
                            step=1
                        )

        # Step 2.5: QSHR Squeeze Override & Booster Handling
        squeeze_velocity = float(market_data.get('squeeze_velocity', 0.0))
        min_squeeze_vel = float(self.params.get('qshr_squeeze_velocity_min', 2.5))

        if is_qshr_strategy:
            if squeeze_velocity >= min_squeeze_vel:
                # Si es Booster, validar que la posición existente tenga ganancia positiva
                if 'BOOSTER' in strategy:
                    if 'unrealized_pnl_pct' in market_data:
                        unrealized_pct = float(market_data.get('unrealized_pnl_pct', 0.0))
                        if unrealized_pct < 0.25:
                            return AduanaResult(
                                approved=False,
                                rule_triggered='QSHR_BOOSTER_NO_PROFIT',
                                reason=f'Booster rechazado: Ganancia flotante insuficiente ({unrealized_pct:.2f}% < 0.25%)',
                                step=2
                            )
                    elif 'unrealized_pnl_pips' in market_data:
                        unrealized_profit = float(market_data.get('unrealized_pnl_pips', 0.0))
                        if unrealized_profit < 3.0:
                            return AduanaResult(
                                approved=False,
                                rule_triggered='QSHR_BOOSTER_NO_PROFIT',
                                reason=f'Booster rechazado: Ganancia flotante insuficiente ({unrealized_profit:.1f} < 3.0 pips)',
                                step=2
                            )
                    rule_name = 'QSHR_BOOSTER_APPROVED'
                    log_info(MODULE, f"⚡ [ADUANA {rule_name}] {symbol} {norm_side.upper()} aprobado con V_5m={squeeze_velocity} >= {min_squeeze_vel}")
                    return AduanaResult(approved=True, rule_triggered=rule_name, reason=f'{strategy} aprobado (V_5m={squeeze_velocity})', step=2)

                # Si es Ruptura Directa o Momentum, exigir validación de Pullback (evitar venta en piso / compra en techo)
                if any(k in strategy for k in ('DIRECT', 'direct', 'MOMENTUM', 'momentum')):
                    pb_ok, pb_reason = self._check_pullback_to_ema(df_15m, norm_side, market_data)
                    if not pb_ok:
                        log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} {norm_side.upper()} QSHR Breakout bloqueado por falta de pullback: {pb_reason}")
                        return AduanaResult(
                            approved=False,
                            rule_triggered='NO_PULLBACK_OVEREXTENDED',
                            reason=f'QSHR Breakout rechazado: {pb_reason}',
                            step=2
                        )

                rule_name = 'QSHR_SQUEEZE_OVERRIDE'
                log_info(MODULE, f"⚡ [ADUANA {rule_name}] {symbol} {norm_side.upper()} aprobado con V_5m={squeeze_velocity} >= {min_squeeze_vel}")
                return AduanaResult(approved=True, rule_triggered=rule_name, reason=f'{strategy} aprobado (V_5m={squeeze_velocity})', step=2)
            else:
                return AduanaResult(approved=False, rule_triggered='QSHR_LOW_VELOCITY', reason=f'Squeeze velocity insuficiente ({squeeze_velocity:.2f} < {min_squeeze_vel})', step=2)

        # Step 2.8: EREP Recovery Validation
        is_erep_strategy = strategy.startswith('Bb33_EREP') or 'EREP' in strategy
        if is_erep_strategy:
            if squeeze_velocity >= min_squeeze_vel:
                return AduanaResult(
                    approved=False,
                    rule_triggered='EREP_SQUEEZE_BLOCKED',
                    reason=f'EREP bloqueado por Squeeze activo en contra (V_5m={squeeze_velocity:.2f} >= {min_squeeze_vel})',
                    step=2
                )
            else:
                log_info(MODULE, f"⚡ [ADUANA EREP APPROVED] {symbol} {norm_side.upper()} P2 Rescate aprobado (V_5m={squeeze_velocity:.2f} segura)")
                return AduanaResult(
                    approved=True,
                    rule_triggered='EREP_P2_APPROVED',
                    reason=f'EREP v2.0 P2 Rescate aprobado para {symbol} {norm_side.upper()}',
                    step=2
                )

        # Step 2: Check extreme in SAME direction (para estrategias de rebote)
        step = 2
        fib_zone = self._get_fib_zone(df_15m)
        if norm_side == 'long' and fib_zone >= 4:
            return AduanaResult(approved=False, rule_triggered='SAME_DIR_EXTREME', reason=f'Long at upper extreme (fib {fib_zone})', step=step)
        if norm_side == 'short' and fib_zone <= -4:
            return AduanaResult(approved=False, rule_triggered='SAME_DIR_EXTREME', reason=f'Short at lower extreme (fib {fib_zone})', step=step)

        # Step 2.5: Candados Universales para Estrategias de Tendencia / Breakout
        is_rebound_strategy = any(k in strategy for k in ('Dd11', 'Dd12', 'Reb', 'rebote', 'rebound', 'ERE_P2', 'EREP', 'CLIMAX', 'climax'))
        if is_trend_strategy and not is_rebound_strategy:
            # Candado 1: Agotamiento de RSI en 15m
            rsi_15m = self._extract_rsi_15m(df_15m, market_data)
            if norm_side == 'short' and rsi_15m < 35.0:
                log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} SHORT bloqueado: RSI 15m sobrevendido ({rsi_15m:.1f} < 35)")
                return AduanaResult(
                    approved=False,
                    rule_triggered='RSI_EXHAUSTION_OVERSOLD',
                    reason=f'Short bloqueado por RSI 15m sobrevendido ({rsi_15m:.1f} < 35)',
                    step=2
                )
            elif norm_side == 'long' and rsi_15m > 65.0:
                log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} LONG bloqueado: RSI 15m sobrecomprado ({rsi_15m:.1f} > 65)")
                return AduanaResult(
                    approved=False,
                    rule_triggered='RSI_EXHAUSTION_OVERBOUGHT',
                    reason=f'Long bloqueado por RSI 15m sobrecomprado ({rsi_15m:.1f} > 65)',
                    step=2
                )

            # Candado 2: Pullback Obligatorio a EMA9/EMA20 (Anti Venta en el Suelo / Anti Compra en el Techo)
            pb_ok, pb_reason = self._check_pullback_to_ema(df_15m, norm_side, market_data)
            if not pb_ok:
                log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} {norm_side.upper()} bloqueado: {pb_reason}")
                return AduanaResult(
                    approved=False,
                    rule_triggered='NO_PULLBACK_OVEREXTENDED',
                    reason=pb_reason,
                    step=2
                )

            # Candado 3: Curvatura de Bandas de Bollinger (Pérdida de Expansión)
            bb_curve_ok, bb_curve_reason = self._check_bollinger_curvature(df_15m, norm_side)
            if not bb_curve_ok:
                log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} {norm_side.upper()} bloqueado: {bb_curve_reason}")
                return AduanaResult(
                    approved=False,
                    rule_triggered='BOLLINGER_BAND_CURVING_AGAINST',
                    reason=bb_curve_reason,
                    step=2
                )

            # Candado 4: Límite de Velas Consecutivas de Impulso
            cand_ok, cand_reason = self._check_consecutive_candles(df_15m, norm_side, max_consecutive=5)
            if not cand_ok:
                log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} {norm_side.upper()} bloqueado: {cand_reason}")
                return AduanaResult(
                    approved=False,
                    rule_triggered='CONSECUTIVE_CANDLES_EXHAUSTION',
                    reason=cand_reason,
                    step=2
                )

            # Candado 5: Alineación Estricta EMA3 vs EMA9 en 15m (Anti Inercia en Contra)
            if df_15m is not None and len(df_15m) >= 5:
                ema3_15m = float(df_15m['close'].ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_15m = float(df_15m['close'].ewm(span=9, adjust=False).mean().iloc[-1])
                if norm_side == 'short' and ema3_15m > ema9_15m:
                    log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} SHORT bloqueado: EMA3 ({ema3_15m:.5f}) > EMA9 ({ema9_15m:.5f}) en 15m")
                    return AduanaResult(
                        approved=False,
                        rule_triggered='TREND_15M_EMA_CONFLICT',
                        reason=f'Short bloqueado por inercia alcista en 15m (EMA3={ema3_15m:.5f} > EMA9={ema9_15m:.5f})',
                        step=2
                    )
                elif norm_side == 'long' and ema3_15m < ema9_15m:
                    log_info(MODULE, f"⛔ [ADUANA REJECT] {symbol} LONG bloqueado: EMA3 ({ema3_15m:.5f}) < EMA9 ({ema9_15m:.5f}) en 15m")
                    return AduanaResult(
                        approved=False,
                        rule_triggered='TREND_15M_EMA_CONFLICT',
                        reason=f'Long bloqueado por inercia bajista en 15m (EMA3={ema3_15m:.5f} < EMA9={ema9_15m:.5f})',
                        step=2
                    )

        # Step 2.9: Asset-Specific Shields (XAUUSD Anti-Spike NY & JPY Prime Hours)
        now_utc = datetime.now(timezone.utc)
        current_minute_utc = now_utc.hour * 60 + now_utc.minute

        # A) XAUUSD Anti-Spike Shield en apertura de Wall Street & Cierre Semanal
        if symbol in ('XAUUSD', 'XAU/USD') and not is_qshr_strategy:
            is_friday = (now_utc.weekday() == 4)
            # Viernes: bloqueo desde 12:00 UTC (720 min) a 16:00 UTC (960 min) por alta volatilidad de noticias y cierres semanales
            # Lunes a Jueves: bloqueo de 13:30 a 15:30 UTC (810 a 930 min)
            is_shield_time = (720 <= current_minute_utc <= 960) if is_friday else (810 <= current_minute_utc <= 930)
            if is_shield_time and abs(fib_zone) < 5:
                window_desc = "12:00-16:00 UTC (Viernes)" if is_friday else "13:30-15:30 UTC (Lun-Jue)"
                log_info(MODULE, f"🛡️ [ADUANA XAUUSD SHIELD] {symbol} {norm_side.upper()} bloqueado por apertura de Wall Street / Noticias EE.UU. ({window_desc})")
                return AduanaResult(
                    approved=False,
                    rule_triggered='XAUUSD_NEWS_SPIKE_SHIELD',
                    reason=f'Ventana de alta volatilidad NY en Oro ({window_desc}): Solo se permiten rebotes extremos Level 5/6 o QSHR Breakout',
                    step=2
                )

        # Step 3: Check contra macro HALCÓN bias without reinforced confirmation
        step = 3
        if not halcon_scores:
            halcon_scores = self._get_halcon_macro_scores(symbol)
            
        score_1d = float(halcon_scores.get('score_1d', 0))
        score_4h = float(halcon_scores.get('score_4h', 0))
        macro_avg = (score_1d + score_4h) / 2.0
        
        macro_thresh = self.params.get('macro_score_threshold', 40.0)
        
        if macro_avg < -macro_thresh and norm_side == 'long' and not contra_trend_confirmed:
            return AduanaResult(approved=False, rule_triggered='CONTRA_MACRO_NO_CONFIRM', reason=f'Long against strong macro bearish bias ({macro_avg})', step=step)
            
        if macro_avg > macro_thresh and norm_side == 'short' and not contra_trend_confirmed:
            return AduanaResult(approved=False, rule_triggered='CONTRA_MACRO_NO_CONFIRM', reason=f'Short against strong macro bullish bias ({macro_avg})', step=step)

        # Step 4: Check impulse candle
        step = 4
        if not is_rebound_strategy:
            is_impulse, candle_dir = self._check_impulse_candle(df_15m, norm_side)
            if is_impulse:
                if candle_dir == 'bearish' and norm_side == 'long':
                    return AduanaResult(approved=False, rule_triggered='IMPULSE_CANDLE', reason='Strong bearish impulse candle against long entry', step=step)
                if candle_dir == 'bullish' and norm_side == 'short':
                    return AduanaResult(approved=False, rule_triggered='IMPULSE_CANDLE', reason='Strong bullish impulse candle against short entry', step=step)

        # Step 4.5: Check CASCADA Hold Conflict (Spec 3.9 & 4.2.3)
        cascade_hold_active = market_data.get('cascade_hold_active', False)
        cascade_hold_side = market_data.get('cascade_hold_side', '')
        if cascade_hold_active and cascade_hold_side and cascade_hold_side != norm_side:
            # An order contradicting an active CASCADE_HOLD requires reinforced confirmation
            if not contra_trend_confirmed:
                return AduanaResult(
                    approved=False, 
                    rule_triggered='CONTRA_CASCADE_HOLD_NO_CONFIRM', 
                    reason=f"Order {norm_side} contradicts active CASCADE_HOLD in {cascade_hold_side} without reinforced confirmation", 
                    step=step
                )

        # Step 5: Range regime explicit approval
        step = 5
        is_range = self._check_range_regime(df_15m)
        if is_range:
            if norm_side == 'long' and fib_zone <= -3:
                return AduanaResult(approved=True, rule_triggered='RANGE_EXPLICIT_APPROVAL', reason='Long at lower extreme in range regime', step=step)
            if norm_side == 'short' and fib_zone >= 3:
                return AduanaResult(approved=True, rule_triggered='RANGE_EXPLICIT_APPROVAL', reason='Short at upper extreme in range regime', step=step)

        # Step 6: No rejection rule triggered -> APPROVE
        step = 6
        return AduanaResult(approved=True, rule_triggered='', reason='Passed all checks', step=step)
