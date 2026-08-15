"""
RADAR Shared Signal Bus Service.
eTrade v5.0 — Spec Section 2
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.core.logger import log_info, log_error, log_warning
from app.core.memory_store import MEMORY_STORE, get_memory_df, BOT_STATE, MARKET_SNAPSHOT_CACHE
from app.radar.config import RADAR_PARAMS, MODULE, load_radar_config_from_db
from app.radar.slope_classifier import classify_slope, get_slope_matrix_interpretation
from app.radar.crossover_detector import (
    detect_ema_crossovers, 
    detect_fibonacci_crossover, 
    detect_impulse_candle
)
from app.radar.event_bus import RadarEventBus
from app.radar.logger import log_radar_event, _sanitize_for_json


class RadarService:
    """
    Singleton service that computes all technical indicators and market signals ONCE per cycle
    and publishes state snapshots and discrete events for HALCÓN, REBOTE, ADUANA, and CASCADA.
    """
    _instance = None

    def __init__(self, params: Dict[str, Any] = None):
        self.params = params or load_radar_config_from_db()
        self.event_bus = RadarEventBus.get_instance()
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._prev_fib_zones: Dict[str, int] = {}
        self._prev_adx_regimes: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> 'RadarService':
        if cls._instance is None:
            cls._instance = RadarService()
        return cls._instance

    def update(self, symbol: str, tf_primary: str = '15m') -> Dict[str, Any]:
        """
        Updates the signal calculations for a symbol using in-memory market data.
        Called once per instrument/cycle by the worker or on-demand by API.
        """
        sym = symbol.upper()
        df_15m = get_memory_df(sym, tf_primary)
        raw_snap = MARKET_SNAPSHOT_CACHE.get(sym, {})

        # If primary data is missing from memory, attempt DB candle fetch
        if df_15m is None or len(df_15m) < 10:
            try:
                from app.core.supabase_client import get_supabase
                sb = get_supabase()
                res = sb.table('market_candles')\
                    .select('*')\
                    .eq('symbol', sym)\
                    .eq('timeframe', tf_primary)\
                    .order('open_time', desc=True)\
                    .limit(100)\
                    .execute()
                candles = res.data or []
                if len(candles) >= 10:
                    candles.reverse()
                    df_fetched = pd.DataFrame(candles)
                    return self.update_from_df(sym, df_fetched, tf_primary)
            except Exception as db_err:
                log_warning(f"DB fallback candle fetch failed for {sym}: {db_err}", MODULE)

        if df_15m is None or len(df_15m) < 10:
            snapshot = self._build_sin_datos_snapshot(sym)
            self._snapshots[sym] = snapshot
            return snapshot

        return self.update_from_df(sym, df_15m, tf_primary)

    def update_from_df(self, symbol: str, df_15m: pd.DataFrame, tf_primary: str = '15m') -> Dict[str, Any]:
        """
        Calculates all RADAR indicators from a DataFrame and updates internal snapshots.
        """
        sym = symbol.upper()
        if df_15m is None or len(df_15m) < 5:
            snapshot = self._build_sin_datos_snapshot(sym)
            self._snapshots[sym] = snapshot
            return snapshot

        raw_snap = MARKET_SNAPSHOT_CACHE.get(sym, {})

        try:
            # Standardize numeric columns
            df = df_15m.copy()
            for col in ['open', 'high', 'low', 'close', 'o', 'h', 'l', 'c', 'volume', 'v']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            if 'c' in df.columns and 'close' not in df.columns: df['close'] = df['c']
            if 'h' in df.columns and 'high' not in df.columns: df['high'] = df['h']
            if 'l' in df.columns and 'low' not in df.columns: df['low'] = df['l']
            if 'o' in df.columns and 'open' not in df.columns: df['open'] = df['o']
            if 'v' in df.columns and 'volume' not in df.columns: df['volume'] = df['v']

            # Compute EMAs if not present
            if 'ema_3' not in df.columns and 'ema3' not in df.columns:
                df['ema_3'] = df['close'].ewm(span=3, adjust=False).mean()
            elif 'ema3' in df.columns and 'ema_3' not in df.columns:
                df['ema_3'] = df['ema3']

            if 'ema_9' not in df.columns and 'ema9' not in df.columns:
                df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
            elif 'ema9' in df.columns and 'ema_9' not in df.columns:
                df['ema_9'] = df['ema9']

            if 'ema_20' not in df.columns and 'ema20' not in df.columns:
                df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            elif 'ema20' in df.columns and 'ema_20' not in df.columns:
                df['ema_20'] = df['ema20']

            if 'ema_50' not in df.columns and 'ema50' not in df.columns:
                df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            elif 'ema50' in df.columns and 'ema_50' not in df.columns:
                df['ema_50'] = df['ema50']

            if 'ema_200' not in df.columns and 'ema200' not in df.columns:
                df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
            elif 'ema200' in df.columns and 'ema_200' not in df.columns:
                df['ema_200'] = df['ema200']

            # Compute ATR if not present
            if 'atr' not in df.columns:
                df['tr'] = np.maximum(df['high'] - df['low'], 
                                     np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                                abs(df['low'] - df['close'].shift(1))))
                df['atr'] = df['tr'].rolling(window=14).mean()
                df.loc[df.index[:14], 'atr'] = df['tr'].rolling(window=14, min_periods=1).mean()

            # Compute Bollinger Bands if not present
            basis_col = 'ema_20' if 'ema_20' in df.columns else 'ema20'
            df['basis'] = df[basis_col]
            df['upper_1'] = df['basis'] + (df['atr'] * 1.618)
            df['lower_1'] = df['basis'] - (df['atr'] * 1.618)
            df['bb_width'] = (df['upper_1'] - df['lower_1']) / df['basis']

            # Compute ADX if not present
            if 'adx' not in df.columns:
                df['dm_plus'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']), np.maximum(df['high'] - df['high'].shift(1), 0), 0)
                df['dm_minus'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)), np.maximum(df['low'].shift(1) - df['low'], 0), 0)
                tr_14 = df['atr']
                df['plus_di'] = 100 * (df['dm_plus'].rolling(window=14).mean() / (tr_14 + 1e-10))
                df['minus_di'] = 100 * (df['dm_minus'].rolling(window=14).mean() / (tr_14 + 1e-10))
                dx = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'] + 1e-10)
                df['adx'] = dx.rolling(window=14).mean()

            # 1. Classify Slopes on 15m (Spec Section 3.5)
            lookback = self.params.get('slope_lookback_candles', 3)
            slope_ema3 = classify_slope(df, 'ema_3', lookback=lookback)
            slope_ema9 = classify_slope(df, 'ema_9', lookback=lookback)
            slope_ema20 = classify_slope(df, 'ema_20', lookback=lookback)

            # Slope Matrix Interpretation (EMA3 x EMA20)
            slope_matrix = get_slope_matrix_interpretation(
                slope_ema3['classification'], 
                slope_ema20['classification']
            )

            # 2. Detect EMA Crossovers
            ema_crossovers = detect_ema_crossovers(df)
            for cross_ev in ema_crossovers:
                cross_ev['symbol'] = sym
                cross_ev['timeframe'] = tf_primary
                self.event_bus.publish(sym, cross_ev)
                log_radar_event(sym, cross_ev)

            # 3. Detect Fibonacci Zone & Transitions
            curr_zone = int(df['fibonacci_zone'].iloc[-2]) if 'fibonacci_zone' in df.columns and not pd.isna(df['fibonacci_zone'].iloc[-2]) else int(raw_snap.get('fibonacci_zone', 0))
            prev_zone = self._prev_fib_zones.get(sym)
            price = float(df['close'].iloc[-2]) if 'close' in df.columns else float(raw_snap.get('price', 0.0))

            fib_event = detect_fibonacci_crossover(prev_zone, curr_zone, price)
            if fib_event:
                fib_event['symbol'] = sym
                fib_event['timeframe'] = tf_primary
                self.event_bus.publish(sym, fib_event)
                log_radar_event(sym, fib_event)
            self._prev_fib_zones[sym] = curr_zone

            # 4. Detect Impulse Candle
            impulse_event = detect_impulse_candle(df, self.params.get('impulse_candle_atr_ratio', 1.8))
            if impulse_event:
                impulse_event['symbol'] = sym
                impulse_event['timeframe'] = tf_primary
                self.event_bus.publish(sym, impulse_event)
                log_radar_event(sym, impulse_event)

            # 5. Local Regime 15m (Bullish / Bearish / Neutral)
            last_closed = df.iloc[-2]
            ema_20 = float(last_closed.get('ema_20', 0.0))
            ema_50 = float(last_closed.get('ema_50', 0.0))
            ema_200 = float(last_closed.get('ema_200', 0.0))

            if ema_20 > ema_50 > ema_200 and ema_200 > 0:
                regimen_local = 'bullish'
            elif ema_20 < ema_50 < ema_200 and ema_200 > 0:
                regimen_local = 'bearish'
            else:
                regimen_local = 'neutral'

            # 6. ADX Regime & Directional Movement
            adx_val = float(last_closed.get('adx', 0.0))
            plus_di = float(last_closed.get('plus_di', 0.0))
            minus_di = float(last_closed.get('minus_di', 0.0))

            if adx_val < self.params.get('adx_range_threshold', 15.0):
                regimen_adx = 'choppy'
            elif adx_val > self.params.get('adx_trend_threshold', 30.0):
                regimen_adx = 'strong_trend'
            else:
                regimen_adx = 'moderate'

            # 7. Bollinger Squeeze
            bb_width = float(last_closed.get('bb_width', 0.0))
            squeeze_activo = False
            if 'bb_width' in df.columns and len(df) >= 22:
                avg_bb_width = float(df['bb_width'].iloc[-22:-2].mean())
                squeeze_activo = bb_width < avg_bb_width or bb_width < 0.02

            # 8. Volume Confirmation
            vol_confirmed = False
            if 'volume' in df.columns and len(df) >= 12:
                recent_vol = float(last_closed.get('volume', 0.0))
                avg_vol = float(df['volume'].iloc[-12:-2].mean())
                if avg_vol > 0 and recent_vol >= (avg_vol * self.params.get('volume_expansion_ratio', 1.3)):
                    vol_confirmed = True

            # 9. RSI State
            rsi_val = float(last_closed.get('rsi', 50.0))
            rsi_extremo = 'oversold' if rsi_val <= 20 else 'overbought' if rsi_val >= 80 else 'neutral'

            # 10. Check ORÁCULO Trading Paused
            oraculo_paused = bool(raw_snap.get('trading_paused', False))

            # Build Full Radar Snapshot
            snapshot = {
                'symbol': sym,
                'status': 'ok',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'price': price,
                'timeframe': tf_primary,
                # Slopes
                'pendiente_EMA3': slope_ema3['classification'],
                'pendiente_EMA9': slope_ema9['classification'],
                'pendiente_EMA20': slope_ema20['classification'],
                'slope_ema3_val': slope_ema3['slope_normalized'],
                'slope_ema9_val': slope_ema9['slope_normalized'],
                'slope_ema20_val': slope_ema20['slope_normalized'],
                'slope_matrix': slope_matrix,
                # Regimes
                'regimen_local_15m': regimen_local,
                'regimen_ADX': regimen_adx,
                'adx_val': adx_val,
                'plus_di': plus_di,
                'minus_di': minus_di,
                # Zones & Indicators
                'fibonacci_zone': curr_zone,
                'squeeze_activo': squeeze_activo,
                'bb_width': bb_width,
                'rsi_val': rsi_val,
                'rsi_extremo': rsi_extremo,
                'confirmacion_volumen': vol_confirmed,
                'trading_paused': oraculo_paused,
                # Latest Discreta Events Summary
                'latest_events': self.event_bus.get_events(sym, limit=5)
            }

            self._snapshots[sym] = _sanitize_for_json(snapshot)
            return self._snapshots[sym]

        except Exception as e:
            log_error(MODULE, f"Error updating RADAR for {sym}: {e}")
            return self._build_sin_datos_snapshot(sym, error=str(e))

    def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        """
        Returns the latest computed signal snapshot for a symbol.
        Automatically updates on demand if not present or 'sin_datos'.
        """
        sym = symbol.upper()
        if sym in self._snapshots and self._snapshots[sym].get('status') == 'ok':
            return self._snapshots[sym]
        return self.update(sym)

    def is_data_available(self, symbol: str) -> bool:
        """
        Fail-safe check (Section 2.4): returns True only if valid non-error data is present.
        """
        snap = self.get_snapshot(symbol)
        return snap.get('status') == 'ok'

    def get_events_for_symbol(self, symbol: str, event_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieves discrete events from the event bus.
        """
        return self.event_bus.get_events(symbol, event_type=event_type, limit=limit)

    def _build_sin_datos_snapshot(self, symbol: str, error: str = '') -> Dict[str, Any]:
        """
        Builds an explicit fail-safe 'sin_datos' snapshot.
        """
        return {
            'symbol': symbol.upper(),
            'status': 'sin_datos',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': error,
            'pendiente_EMA3': 'sin_datos',
            'pendiente_EMA9': 'sin_datos',
            'pendiente_EMA20': 'sin_datos',
            'slope_matrix': {'status': 'sin_datos', 'is_strong_trend': False, 'is_pullback_noise': False, 'is_real_reversal': False},
            'regimen_local_15m': 'sin_datos',
            'regimen_ADX': 'sin_datos',
            'fibonacci_zone': 0,
            'squeeze_activo': False,
            'confirmacion_volumen': False,
            'trading_paused': False,
            'latest_events': []
        }
