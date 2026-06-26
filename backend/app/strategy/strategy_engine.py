import pandas as pd
import numpy as np
from typing import Optional
from app.core.memory_store import MEMORY_STORE
from app.core.logger import log_info, log_error


class StrategyEngine:
    """
    Motor de evaluación de estrategias v1.0.
    Lee reglas y condiciones desde Supabase.
    Evalúa contra el contexto de mercado actual.
    Soporta lógica AND/OR con pesos por condición.
    """
    _instance = None

    @classmethod
    def get_instance(cls, supabase=None):
        if cls._instance is None:
            cls._instance = cls(supabase)
        return cls._instance

    def __init__(self, supabase):
        self.sb         = supabase
        self.rules      = {}
        self.conditions = {}
        self.variables  = {}
        self.loaded     = False

    async def load(self):
        """
        Cargar todas las reglas, condiciones
        y variables desde Supabase al inicio.
        Se llama una vez en el warm-up.
        """
        try:
            # Cargar variables
            vars_res = self.sb\
                .table('strategy_variables')\
                .select('*')\
                .eq('enabled', True)\
                .execute()
            self.variables = {
                v['id']: v for v in vars_res.data
            }

            # Cargar condiciones
            conds_res = self.sb\
                .table('strategy_conditions')\
                .select('*, variable:strategy_variables(*)')\
                .eq('enabled', True)\
                .execute()
            self.conditions = {
                c['id']: c for c in conds_res.data
            }

            # Cargar reglas
            rules_res = self.sb\
                .table('strategy_rules_v2')\
                .select('*')\
                .eq('enabled', True)\
                .order('priority')\
                .execute()
            self.rules = {
                r['rule_code']: r
                for r in rules_res.data
            }

            self.loaded = True
            log_info('STRATEGY_ENGINE',
                f'Cargado: {len(self.rules)} reglas | '
                f'{len(self.conditions)} condiciones | '
                f'{len(self.variables)} variables'
            )

        except Exception as e:
            log_error('STRATEGY_ENGINE',
                f'Error cargando reglas: {e}'
            )

    async def reload(self):
        """Recargar reglas desde Supabase."""
        self.rules      = {}
        self.conditions = {}
        self.variables  = {}
        self.loaded     = False
        await self.load()

    def calculate_momentum_explosive(
        self,
        df_4h: pd.DataFrame,
        direction: str,  # 'up' o 'down'
        lookback: int = 3,
        threshold_pct: float = 3.0
    ) -> bool:
        """
        Retorna True si el movimiento es EXPLOSIVO
        (precio se movió > threshold% en N velas)
        Retorna False si el movimiento es normal.
        """
        if df_4h is None or len(df_4h) < lookback + 1:
            return False

        price_now  = float(df_4h['close'].iloc[-1])
        price_prev = float(
            df_4h['close'].iloc[-(lookback + 1)]
        )

        if price_prev == 0:
            return False

        change_pct = (
            (price_now - price_prev) / price_prev * 100
        )

        if direction == 'down':
            # Explosivo bajista: cayó > threshold
            return change_pct < -threshold_pct
        else:
            # Explosivo alcista: subió > threshold
            return change_pct > threshold_pct

    def build_context(
        self,
        snap:   dict,
        df_15m: pd.DataFrame,
        df_4h:  pd.DataFrame,
        df_5m:  pd.DataFrame = None
    ) -> dict:
        """
        Construye el contexto de mercado unificado
        con todos los valores de variables
        disponibles para la evaluación.
        """
        def safe_float(val, default=0.0):
            try:
                return float(val) if val is not None \
                       else default
            except (TypeError, ValueError):
                return default

        def safe_int(val, default=0):
            try:
                return int(val) if val is not None \
                       else default
            except (TypeError, ValueError):
                return default

        def safe_bool(val, default=False):
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(val)
            return default

        # Obtener última fila de cada DataFrame
        last_15m = df_15m.iloc[-1].to_dict() \
                   if df_15m is not None \
                   and len(df_15m) > 0 else {}
        last_4h  = df_4h.iloc[-1].to_dict() \
                   if df_4h is not None \
                   and len(df_4h) > 0 else {}
        last_5m  = df_5m.iloc[-1].to_dict() \
                   if df_5m is not None \
                   and len(df_5m) > 0 else {}

        # ── 5m/15m Indicators ──
        # Obtener SAR 5m y Pine 5m si hay df_5m
        sar_ini_high_5m = False
        sar_ini_low_5m  = False
        pine_buy_5m     = False
        pine_sell_5m    = False
        
        if df_5m is not None and not df_5m.empty:
            from app.analysis.parabolic_sar import calculate_parabolic_sar
            df_5m_local = calculate_parabolic_sar(df_5m.copy())
            last_5m_row = df_5m_local.iloc[-1]
            sar_ini_high_5m = bool(last_5m_row.get('sar_ini_high', False))
            sar_ini_low_5m  = bool(last_5m_row.get('sar_ini_low', False))
            sar_trend_5m    = int(last_5m_row.get('sar_trend', 0))
            pine_buy_5m     = (str(last_5m_row.get('pinescript_signal', '')) == 'Buy')
            pine_sell_5m    = (str(last_5m_row.get('pinescript_signal', '')) == 'Sell')

        # ADX velocity
        adx = safe_float(snap.get('adx', 25))
        if adx < 20:
            velocity = 'debil'
        elif adx < 35:
            velocity = 'moderado'
        elif adx < 50:
            velocity = 'agresivo'
        else:
            velocity = 'explosivo'

        # Spike direccional
        spike_det = safe_bool(snap.get('spike_detected'))
        spike_dir = str(snap.get('spike_direction', ''))
        spike_bullish = spike_det and spike_dir == 'bullish'
        spike_bearish = spike_det and spike_dir == 'bearish'

        # ── MOMENTUM EXPLOSIVO (Anti-explosividad) ──
        momentum_down_not_explosive = not self.calculate_momentum_explosive(
            df_4h, 'down', lookback=3, threshold_pct=3.0
        )
        momentum_up_not_explosive = not self.calculate_momentum_explosive(
            df_4h, 'up',   lookback=3, threshold_pct=3.0
        )

        # Basis Horizontal
        from app.analysis.swing_detector import detect_basis_horizontal
        basis_info = detect_basis_horizontal(df_15m, lookback=10, slope_threshold=0.5)
        basis_info_4h = detect_basis_horizontal(df_4h, lookback=10, slope_threshold=0.5) if df_4h is not None else {}

        # ── EMA3 OPEN_UP LOGIC ──
        # 15m
        ema3_15m = safe_float(last_15m.get('ema_3') if last_15m.get('ema_3') is not None else last_15m.get('ema3'))
        open_15m = safe_float(last_15m.get('open'))
        low_15m  = safe_float(last_15m.get('low'))
        high_15m = safe_float(last_15m.get('high'))
        ema3_open_up_15m = ((low_15m < ema3_15m and high_15m > ema3_15m) or (open_15m > ema3_15m)) if ema3_15m else False

        # 5m
        ema3_open_up_5m = False
        if last_5m:
            ema3_5m = safe_float(last_5m.get('ema_3') if last_5m.get('ema_3') is not None else last_5m.get('ema3'))
            open_5m = safe_float(last_5m.get('open'))
            low_5m  = safe_float(last_5m.get('low'))
            high_5m = safe_float(last_5m.get('high'))
            if ema3_5m:
                ema3_open_up_5m = ((low_5m < ema3_5m and high_5m > ema3_5m) or (open_5m > ema3_5m))

        # ── 1H EMAs ──
        ema3_above_ema9_1h = False
        ema3_below_ema9_1h = False
        symbol = snap.get('symbol', '')
        if symbol:
            df_1h = MEMORY_STORE.get(symbol, {}).get('1h', {}).get('df')
            if df_1h is not None and not df_1h.empty:
                last_1h = df_1h.iloc[-1]
                ema3_1h = safe_float(last_1h.get('ema_3', last_1h.get('ema1')))
                ema9_1h = safe_float(last_1h.get('ema_9', last_1h.get('ema2')))
                if ema3_1h > 0 and ema9_1h > 0:
                    ema3_above_ema9_1h = ema3_1h > ema9_1h
                    ema3_below_ema9_1h = ema3_1h < ema9_1h

        ema20_ascending_1h = False
        ema20_descending_1h = False
        if symbol:
            df_1h = MEMORY_STORE.get(symbol, {}).get('1h', {}).get('df')
            if df_1h is not None and len(df_1h) >= 2:
                c1h_col = 'Close' if 'Close' in df_1h.columns else 'close'
                c1h = pd.to_numeric(df_1h[c1h_col], errors='coerce').dropna()
                if len(c1h) >= 2:
                    ema20_series_1h = c1h.ewm(span=20, adjust=False).mean()
                    if float(ema20_series_1h.iloc[-1]) > float(ema20_series_1h.iloc[-2]):
                        ema20_ascending_1h = True
                    if float(ema20_series_1h.iloc[-1]) < float(ema20_series_1h.iloc[-2]):
                        ema20_descending_1h = True

        # ── Aa13 & Bb13 Custom Variables ──
        bb_lower_ascending_15m = False
        bb_lower_ascending_2c_15m = False
        prev_low_touch_lower56_15m = False
        bb_lower_descending_15m = False
        bb_upper_descending_15m = False
        high_above_ema20_15m = False
        high_above_ema20_5m = False
        ema20_below_ema50_15m = False
        ema50_below_ema200_15m = False
        ema9_below_ema20_15m = False
        ema9_above_ema20_15m = False
        low_below_ema20_15m = False
        high_above_ema20_15m = False

        if df_15m is not None and len(df_15m) >= 3:
            # BB Lower Ascending / Descending
            b_l_0 = safe_float(df_15m['lower_2'].iloc[-1] if 'lower_2' in df_15m.columns else df_15m.get('bb_lower', pd.Series()).iloc[-1] if 'bb_lower' in df_15m.columns else 0)
            b_l_1 = safe_float(df_15m['lower_2'].iloc[-2] if 'lower_2' in df_15m.columns else df_15m.get('bb_lower', pd.Series()).iloc[-2] if 'bb_lower' in df_15m.columns else 0)
            b_l_2 = safe_float(df_15m['lower_2'].iloc[-3] if 'lower_2' in df_15m.columns else df_15m.get('bb_lower', pd.Series()).iloc[-3] if 'bb_lower' in df_15m.columns else 0)
            if b_l_0 > b_l_1 and b_l_1 > b_l_2 and b_l_2 > 0:
                bb_lower_ascending_15m = True
            if b_l_0 > b_l_1 and b_l_1 > 0:
                bb_lower_ascending_2c_15m = True
            if b_l_0 < b_l_1 and b_l_1 < b_l_2 and b_l_0 > 0:
                bb_lower_descending_15m = True

            # BB Upper Descending
            b_u_0 = safe_float(df_15m['upper_2'].iloc[-1] if 'upper_2' in df_15m.columns else df_15m.get('bb_upper', pd.Series()).iloc[-1] if 'bb_upper' in df_15m.columns else 0)
            b_u_1 = safe_float(df_15m['upper_2'].iloc[-2] if 'upper_2' in df_15m.columns else df_15m.get('bb_upper', pd.Series()).iloc[-2] if 'bb_upper' in df_15m.columns else 0)
            b_u_2 = safe_float(df_15m['upper_2'].iloc[-3] if 'upper_2' in df_15m.columns else df_15m.get('bb_upper', pd.Series()).iloc[-3] if 'bb_upper' in df_15m.columns else 0)
            if b_u_0 < b_u_1 and b_u_1 < b_u_2 and b_u_0 > 0:
                bb_upper_descending_15m = True

            # Prev Low Touch Lower 5 or 6
            prev_low = safe_float(df_15m['low'].iloc[-2] if 'low' in df_15m.columns else 0)
            prev_basis = safe_float(df_15m['basis'].iloc[-2] if 'basis' in df_15m.columns else df_15m.get('sma_20', pd.Series()).iloc[-2] if 'sma_20' in df_15m.columns else 0)
            if prev_basis > 0 and b_l_1 > 0:
                std_15m = (prev_basis - b_l_1) / 2.0
                prev_lower_5 = prev_basis - 5.0 * std_15m
                prev_lower_6 = prev_basis - 6.0 * std_15m
                if prev_low > 0 and (prev_low <= prev_lower_5 or prev_low <= prev_lower_6):
                    prev_low_touch_lower56_15m = True

            # EMAs and High
            ema9_15m = safe_float(last_15m.get('ema_9') if last_15m.get('ema_9') is not None else last_15m.get('ema9'))
            ema20_15m = safe_float(last_15m.get('ema_20') if last_15m.get('ema_20') is not None else last_15m.get('ema20'))
            ema50_15m = safe_float(last_15m.get('ema_50') if last_15m.get('ema_50') is not None else last_15m.get('ema50'))
            ema200_15m = safe_float(last_15m.get('ema_200') if last_15m.get('ema_200') is not None else last_15m.get('ema200'))
            
            if ema20_15m and ema50_15m and ema20_15m < ema50_15m:
                ema20_below_ema50_15m = True
                
            ema3_ascending_15m = False
            ema3_descending_15m = False
            
            if df_15m is not None and len(df_15m) >= 2:
                c15_col = 'Close' if 'Close' in df_15m.columns else 'close'
                c15 = pd.to_numeric(df_15m[c15_col], errors='coerce').dropna()
                if len(c15) >= 2:
                    ema3_series = c15.ewm(span=3, adjust=False).mean()
                    if float(ema3_series.iloc[-1]) > float(ema3_series.iloc[-2]):
                        ema3_ascending_15m = True
                    if float(ema3_series.iloc[-1]) < float(ema3_series.iloc[-2]):
                        ema3_descending_15m = True

            if ema50_15m and ema200_15m:
                if ema50_15m < ema200_15m:
                    ema50_below_ema200_15m = True
                
            if ema9_15m and ema20_15m:
                if ema9_15m < ema20_15m:
                    ema9_below_ema20_15m = True
                if ema9_15m > ema20_15m:
                    ema9_above_ema20_15m = True
                    
            if low_15m and ema20_15m and low_15m < ema20_15m:
                low_below_ema20_15m = True
            
            if ema20_15m and high_15m >= ema20_15m:
                high_above_ema20_15m = True

        if last_5m:
            ema20_5m_val = safe_float(last_5m.get('ema_20') if last_5m.get('ema_20') is not None else last_5m.get('ema20'))
            high_5m_val = safe_float(last_5m.get('high'))
            if ema20_5m_val and high_5m_val >= ema20_5m_val:
                high_above_ema20_5m = True

        return {
            # Precio
            'symbol':            str(symbol),
            'price':             safe_float(snap.get('price')),
            'dist_basis_pct':    safe_float(snap.get('dist_basis_pct')),
            # ADX
            'adx':               adx,
            'plus_di':           safe_float(last_15m.get('plus_di')),
            'minus_di':          safe_float(last_15m.get('minus_di')),
            'adx_velocity':      velocity,
            'bb_expanding':      safe_bool(last_15m.get('bb_expanding')),
            # EMAs
            'ema3':              safe_float(last_15m.get('ema_3') if last_15m.get('ema_3') is not None else last_15m.get('ema3')),
            'ema9':              safe_float(last_15m.get('ema_9') if last_15m.get('ema_9') is not None else last_15m.get('ema9')),
            'ema20':             safe_float(last_15m.get('ema_20') if last_15m.get('ema_20') is not None else last_15m.get('ema20')),
            'ema50':             safe_float(last_15m.get('ema_50') if last_15m.get('ema_50') is not None else last_15m.get('ema50')),
            'ema200':            safe_float(last_15m.get('ema_200') if last_15m.get('ema_200') is not None else last_15m.get('ema200')),
            
            # EMAs 5m
            'ema3_5m':           safe_float(last_5m.get('ema_3') if last_5m.get('ema_3') is not None else last_5m.get('ema1')),
            'ema9_5m':           safe_float(last_5m.get('ema_9') if last_5m.get('ema_9') is not None else last_5m.get('ema2')),
            'ema20_5m':          safe_float(last_5m.get('ema_20') if last_5m.get('ema_20') is not None else last_5m.get('ema3')),
            'ema9_angle_5m':     safe_float(last_5m.get('ema9_angle', 0.0)),
            'ema20_angle_5m':    safe_float(last_5m.get('ema20_angle', 0.0)),
            
            # EMAs 1h
            'ema3_above_ema9_1h': ema3_above_ema9_1h,
            'ema3_below_ema9_1h': ema3_below_ema9_1h,
            'ema20_ascending_1h': ema20_ascending_1h,
            'ema20_descending_1h': ema20_descending_1h,
            'ema3_open_up_15m':  ema3_open_up_15m,
            'ema3_open_up_5m':   ema3_open_up_5m,
            'ema3_cross_ema9_up': safe_bool(last_15m.get('ema3_cross_ema9_up') if last_15m.get('ema3_cross_ema9_up') is not None else (safe_float(last_15m.get('ema_3') or last_15m.get('ema3')) > safe_float(last_15m.get('ema_9') or last_15m.get('ema9')))),
            'ema3_ema9_trend_ok': safe_bool(last_15m.get('ema3_ema9_trend_ok') if last_15m.get('ema3_ema9_trend_ok') is not None else (safe_float(last_15m.get('ema_9') or last_15m.get('ema9')) > safe_float(last_15m.get('ema_20') or last_15m.get('ema20')) or safe_float(last_15m.get('ema_3') or last_15m.get('ema3')) > safe_float(last_15m.get('ema_20') or last_15m.get('ema20')))),
            'close_below_upper':  safe_bool(last_15m.get('close_below_upper') if last_15m.get('close_below_upper') is not None else (safe_float(snap.get('price')) < safe_float(snap.get('upper_2') or 999999))),
            'close_above_lower':  safe_bool(last_15m.get('close_above_lower') if last_15m.get('close_above_lower') is not None else (safe_float(snap.get('price')) > safe_float(snap.get('lower_2') or 0))),
            'ema3_angle':        safe_float(last_15m.get('ema3_angle')),
            'ema9_angle':        safe_float(last_15m.get('ema9_angle')),
            'ema20_angle':       safe_float(last_15m.get('ema20_angle')),
            'ema50_angle':       safe_float(last_15m.get('ema50_angle')),
            'ema20_phase':       str(snap.get('ema20_phase', '')),
            # Fibonacci
            'fibonacci_zone':    safe_int(snap.get('fibonacci_zone')),
            'basis':             safe_float(snap.get('basis')),
            'basis_slope':       basis_info.get('slope_pct', 0.0),
            'is_flat':           basis_info.get('is_flat', False),
            'upper_1':           safe_float(snap.get('upper_1')),
            'upper_2':           safe_float(snap.get('upper_2')),
            'upper_3':           safe_float(snap.get('upper_3')),
            'upper_4':           safe_float(snap.get('upper_4')),
            'upper_5':           safe_float(snap.get('upper_5')),
            'upper_6':           safe_float(snap.get('upper_6')),
            'lower_1':           safe_float(snap.get('lower_1')),
            'lower_2':           safe_float(snap.get('lower_2')),
            'lower_3':           safe_float(snap.get('lower_3')),
            'lower_4':           safe_float(snap.get('lower_4')),
            'lower_5':           safe_float(snap.get('lower_5')),
            'lower_6':           safe_float(snap.get('lower_6')),
            # SAR
            'sar_trend_15m':     safe_int(snap.get('sar_trend_15m')),
            'sar_trend_4h':      safe_int(snap.get('sar_trend_4h')),
            'sar_ini_high_15m':  safe_bool(snap.get('sar_ini_high_15m')),
            'sar_ini_low_15m':   safe_bool(snap.get('sar_ini_low_15m')),
            'sar_ini_high_4h':   safe_bool(snap.get('sar_ini_high_4h')),
            'sar_ini_low_4h':    safe_bool(snap.get('sar_ini_low_4h')),
            'sar_trend_5m':      sar_trend_5m if df_5m is not None and not df_5m.empty else 0,
            # Sistema
            'mtf_score':         safe_float(snap.get('mtf_score')),
            'pinescript_signal': str(snap.get('pinescript_signal', '')),
            'pinescript_signal_age': safe_int(snap.get('pinescript_signal_age', 999)),
            'spike_bullish':     spike_bullish,
            'spike_bearish':     spike_bearish,
            'spike_ratio':       safe_float(snap.get('spike_ratio')),
            'regime':            str(snap.get('regime', '')),
            # Estructura
            'structure_15m':     str(snap.get('structure_15m', 'unknown')),
            'structure_4h':      str(snap.get('structure_4h', 'unknown')),
            'allow_long_4h':     safe_bool(snap.get('allow_long_4h', True)),
            'allow_short_4h':    safe_bool(snap.get('allow_short_4h', True)),
            # MOMENTUM
            'momentum_down_not_explosive': momentum_down_not_explosive,
            'momentum_up_not_explosive':   momentum_up_not_explosive,
            # COMBINED
            'is_range_or_fall': basis_info.get('is_flat', False) or (basis_info.get('slope_pct', 0) < 0),
            'is_range_or_rise': basis_info.get('is_flat', False) or (basis_info.get('slope_pct', 0) > 0),
            'is_range_or_rise_4h': basis_info_4h.get('is_flat', False) or (basis_info_4h.get('slope_pct', 0) > 0),
            'is_range_or_fall_4h': basis_info_4h.get('is_flat', False) or (basis_info_4h.get('slope_pct', 0) < 0),
            
            # Rangos / Tendencias por Timeframe (OR) - Explícitos
            'is_range_or_rise_15m': basis_info.get('is_flat', False) or (basis_info.get('slope_pct', 0) > 0),
            'is_range_or_fall_15m': basis_info.get('is_flat', False) or (basis_info.get('slope_pct', 0) < 0),
            
            # Status 5m (para reglas de scalping 5m como Aa12)
            'is_sar_high_5m':    sar_ini_high_5m,
            'is_sar_low_5m':     sar_ini_low_5m,
            'is_pine_buy_5m':    pine_buy_5m,
            'is_pine_sell_5m':   pine_sell_5m,
            'sar_or_pine_5m':    sar_ini_high_5m or pine_buy_5m,
            'sar_or_pine_sell_5m': sar_ini_low_5m or pine_sell_5m,

            # ── 4h Candle State ──
            'is_4h_green':       (float(last_4h.get('close', 0)) > float(last_4h.get('open', 0))) if last_4h else False,
            'is_4h_red':         (float(last_4h.get('close', 0)) < float(last_4h.get('open', 0))) if last_4h else False,

            # ── AI Context (v2) ──
            'ai_opportune_buy':  safe_bool(MEMORY_STORE.get(snap.get('symbol', ''), {}).get('ai_cache_15m', {}).get('opportune_buy', False)),
            'ai_opportune_sell': safe_bool(MEMORY_STORE.get(snap.get('symbol', ''), {}).get('ai_cache_15m', {}).get('opportune_sell', False)),
            'ai_candle_color':   str(MEMORY_STORE.get(snap.get('symbol', ''), {}).get('ai_cache_15m', {}).get('current_candle_color', 'neutral')),
            
            # Custom Aa13/Bb13 variables
            'bb_lower_ascending_15m': bb_lower_ascending_15m,
            'bb_lower_ascending_2c_15m': bb_lower_ascending_2c_15m,
            'prev_low_touch_lower56_15m': prev_low_touch_lower56_15m,
            'bb_lower_descending_15m': bb_lower_descending_15m,
            'bb_upper_descending_15m': bb_upper_descending_15m,
            'ema3_ascending_15m': ema3_ascending_15m,
            'ema3_descending_15m': ema3_descending_15m,
            'high_above_ema20_15m': high_above_ema20_15m,
            'high_above_ema20_5m': high_above_ema20_5m,
            'ema20_below_ema50_15m': ema20_below_ema50_15m,
            'ema50_below_ema200_15m': ema50_below_ema200_15m,
            'ema9_below_ema20_15m': ema9_below_ema20_15m,
            'ema9_above_ema20_15m': ema9_above_ema20_15m,
            'low_below_ema20_15m': low_below_ema20_15m,

            # Referencia al DataFrame original para reglas personalizadas avanzadas
            'df_15m': df_15m
        }


    def evaluate_condition(
        self,
        cond:    dict,
        context: dict
    ) -> tuple:
        """
        Evalúa una condición contra el contexto.
        Retorna (passed: bool, score: float)
        """
        # Obtener el campo source de la variable
        variable = cond.get('variable') or {}
        source   = variable.get('source_field', '')
        value    = context.get(source)

        if value is None:
            return False, 0.0

        op       = cond.get('operator', '==')
        val_type = cond.get('value_type', 'literal')
        val_lit  = cond.get('value_literal')
        val_var  = cond.get('value_variable')
        val_list = cond.get('value_list') or []
        val_min  = cond.get('value_min')
        val_max  = cond.get('value_max')

        # Valor de comparación
        if val_type == 'variable' and val_var:
            compare_to = context.get(val_var, 0)
        elif val_type in ('literal', 'range'):
            compare_to = val_lit
        else:
            compare_to = None

        try:
            if op == '>':
                result = float(value) > float(compare_to)
            elif op == '>=':
                result = float(value) >= float(compare_to)
            elif op == '<':
                result = float(value) < float(compare_to)
            elif op == '<=':
                result = float(value) <= float(compare_to)
            elif op in ('==', 'IN'):
                if val_type == 'list' or op == 'IN':
                    result = str(value) in [
                        str(x) for x in val_list
                    ]
                else:
                    # Robust boolean/string comparison
                    v_str = str(value).lower()
                    c_str = str(compare_to).lower()
                    if v_str in ('true', '1') and c_str in ('true', '1'):
                        result = True
                    elif v_str in ('false', '0') and c_str in ('false', '0'):
                        result = True
                    else:
                        result = v_str == c_str
            elif op == '!=':
                result = str(value) != str(compare_to)
            elif op == 'NOT_IN':
                result = str(value) not in [
                    str(x) for x in val_list
                ]
            elif op == 'BETWEEN':
                result = float(val_min) \
                         <= float(value) \
                         <= float(val_max)
            elif op == 'CROSS_ABOVE':
                result = float(value) > float(
                    context.get(val_var, 0)
                )
            elif op == 'CROSS_BELOW':
                result = float(value) < float(
                    context.get(val_var, 0)
                )
            else:
                result = False

        except (TypeError, ValueError):
            result = False

        return result, 1.0 if result else 0.0

    def _check_mtf_entry_filter(self, symbol: str, mtf: float, rule_code: str) -> dict:
        """
        Verifica el filtro MTF para entradas.
        Bloquea señales cuando el MTF es neutro en activos muy volátiles.
        """
        try:
            from app.strategy.capital_protection import VOLATILE_TRAILING_CONFIG
            cfg = VOLATILE_TRAILING_CONFIG.get(symbol)
        except ImportError:
            cfg = None
            
        if not cfg:
            return {'blocked': False}

        mtf_min = cfg.get('mtf_entry_min', 0.15)

        scalping_rules = [
            'Aa31a', 'Aa31b',
            'Bb31a', 'Bb31b',
            'Aa11', 'Aa12',
            'Bb11', 'Bb12',
        ]
        if rule_code not in scalping_rules:
            return {'blocked': False}

        if abs(mtf) < mtf_min:
            return {
                'blocked': True,
                'mtf':     mtf,
                'mtf_min': mtf_min,
                'reason': (
                    f'FILTRO MTF: {symbol}/{rule_code} bloqueada. MTF={mtf:.2f} '
                    f'< mínimo {mtf_min:.2f}. Sin confirmación de tendencia '
                    f'en 4H/1H → alta probabilidad de reversión rápida en activo volátil'
                ),
            }

        return {
            'blocked': False,
            'mtf':     mtf,
            'reason':  f'MTF={mtf:.2f} OK >= {mtf_min:.2f}',
        }

    def evaluate_rule(
        self,
        rule:    dict,
        context: dict
    ) -> dict:
        """
        Evalúa una regla completa.
        Calcula score ponderado de condiciones.
        """
        symbol = context.get('symbol', '')
        mtf = context.get('mtf_score', 0.0)
        rule_code = rule.get('rule_code', '')
        price = context.get('price', 0.0)
        
        # --- PROPOSAL: CUSTOM PROCEDURAL OVERRIDES FOR VOLATILE SWING/PINE RULES ---
        if rule_code in ['Aa31a', 'Bb31a', 'Aa31b', 'Bb31b']:
            direction = rule.get('direction', 'long')
            
            sar_4h = context.get('sar_trend_4h', 0)
            sar_15m = context.get('sar_trend_15m', 0)
            pine = context.get('pinescript_signal', '')
            struct_ok = context.get('allow_long_4h', True) if direction == 'long' else context.get('allow_short_4h', True)
            fib_zone = context.get('fibonacci_zone', 0)
            adx = context.get('adx', 0.0)
            
            ema3 = context.get('ema3', 0.0)
            ema9 = context.get('ema9', 0.0)
            ema20 = context.get('ema20', 0.0)
            bb_exp = context.get('bb_expanding', False)
            
            # Extract SIPV
            df_15m = context.get('df_15m')
            sipv_buy = False
            sipv_sell = False
            if df_15m is not None and len(df_15m) > 0:
                last_row = df_15m.iloc[-1].to_dict()
                sipv_buy = (bool(last_row.get('is_dragonfly', False)) or
                            bool(last_row.get('is_bullish_engulfing', False)) or
                            bool(last_row.get('low_higher_than_prev', False)) or
                            bool(last_row.get('is_doji', False)))
                sipv_sell = (bool(last_row.get('is_gravestone', False)) or
                             bool(last_row.get('is_bearish_engulfing', False)) or
                             bool(last_row.get('high_lower_than_prev', False)) or
                             bool(last_row.get('is_doji', False)))
            
            pb_pct = 0.0015  # 0.15% dynamic pullback window suitable for Crypto
            
            if direction == 'long':
                sar_4h_ok = (sar_4h > 0)
                sar_15m_ok = (sar_15m > 0)
                pine_not_opposite = (pine != 'Sell')
                
                # REFINAMIENTO V4: Pullback ordenado + gatillo de ruptura EMA3 + confirmación de giro
                pullback_confirmed = (ema9 > ema20) and (ema20 <= price <= ema9 * (1.0 + pb_pct)) and (price > ema3) and (ema3 > ema9) if (ema3 and ema9 and ema20) else False
                
                # Para la variante 'b' (zona extrema), exigimos zona lower_3 o inferior
                zone_ok = (fib_zone <= -3) if '31b' in rule_code else (fib_zone <= 3)
                
                triggered = (
                    sar_15m_ok and sar_4h_ok and
                    mtf >= 0.4 and pine_not_opposite and
                    struct_ok and zone_ok and
                    adx > 25 and pullback_confirmed and
                    (not bb_exp) and sipv_buy
                )
                
                min_score = float(rule.get('min_score', 0.70))
                score = 0.75 if triggered else 0.40
                
                details = {
                    'sar_15m_ok': {'name': 'SAR 15m alcista', 'passed': sar_15m_ok, 'weight': 0.15, 'current_value': sar_15m},
                    'sar_4h_ok': {'name': 'SAR 4h alcista', 'passed': sar_4h_ok, 'weight': 0.15, 'current_value': sar_4h},
                    'mtf_ok': {'name': 'MTF Score >= 0.4', 'passed': mtf >= 0.4, 'weight': 0.20, 'current_value': mtf},
                    'pine_not_opposite': {'name': 'Pine no opuesto (No Sell)', 'passed': pine_not_opposite, 'weight': 0.15, 'current_value': pine},
                    'struct_ok': {'name': 'allow_long_4h', 'passed': struct_ok, 'weight': 0.10, 'current_value': struct_ok},
                    'zone_ok': {'name': f"Fibonacci Zone {'<= -3' if '31b' in rule_code else '<= 3'}", 'passed': zone_ok, 'weight': 0.10, 'current_value': fib_zone},
                    'adx_ok': {'name': 'ADX > 25', 'passed': adx > 25, 'weight': 0.10, 'current_value': adx},
                    'pullback_confirmed': {'name': 'Pullback EMA ordenado', 'passed': pullback_confirmed, 'weight': 0.05, 'current_value': f"price={price}, ema3={ema3}, ema9={ema9}, ema20={ema20}"}
                }
            else:  # short
                sar_4h_ok = (sar_4h < 0)
                sar_15m_ok = (sar_15m < 0)
                pine_not_opposite = (pine != 'Buy')
                
                # REFINAMIENTO V4: Pullback ordenado + gatillo de ruptura EMA3 + confirmación de giro
                pullback_confirmed = (ema9 < ema20) and (ema9 * (1.0 - pb_pct) <= price <= ema20) and (price < ema3) and (ema3 < ema9) if (ema3 and ema9 and ema20) else False
                
                # Para la variante 'b' (zona extrema), exigimos zona upper_3 o superior
                zone_ok = (fib_zone >= 3) if '31b' in rule_code else (fib_zone >= -3)
                
                triggered = (
                    sar_15m_ok and sar_4h_ok and
                    mtf <= -0.4 and pine_not_opposite and
                    struct_ok and zone_ok and
                    adx > 25 and pullback_confirmed and
                    (not bb_exp) and sipv_sell
                )
                
                min_score = float(rule.get('min_score', 0.70))
                score = 0.75 if triggered else 0.40
                
                details = {
                    'sar_15m_ok': {'name': 'SAR 15m bajista', 'passed': sar_15m_ok, 'weight': 0.15, 'current_value': sar_15m},
                    'sar_4h_ok': {'name': 'SAR 4h bajista', 'passed': sar_4h_ok, 'weight': 0.15, 'current_value': sar_4h},
                    'mtf_ok': {'name': 'MTF Score <= -0.4', 'passed': mtf <= -0.4, 'weight': 0.20, 'current_value': mtf},
                    'pine_not_opposite': {'name': 'Pine no opuesto (No Buy)', 'passed': pine_not_opposite, 'weight': 0.15, 'current_value': pine},
                    'struct_ok': {'name': 'allow_short_4h', 'passed': struct_ok, 'weight': 0.10, 'current_value': struct_ok},
                    'zone_ok': {'name': f"Fibonacci Zone {'>= 3' if '31b' in rule_code else '>= -3'}", 'passed': zone_ok, 'weight': 0.10, 'current_value': fib_zone},
                    'adx_ok': {'name': 'ADX > 25', 'passed': adx > 25, 'weight': 0.10, 'current_value': adx},
                    'pullback_confirmed': {'name': 'Pullback EMA ordenado', 'passed': pullback_confirmed, 'weight': 0.05, 'current_value': f"price={price}, ema3={ema3}, ema9={ema9}, ema20={ema20}"}
                }
                
            return {
                'triggered':  triggered,
                'score':      score,
                'min_score':  min_score,
                'rule_code':  rule_code,
                'rule_name':  rule.get('name'),
                'direction':  direction,
                'cycle':      rule.get('cycle'),
                'conditions': details,
                'all_passed': triggered,
                'reason': f"{'✅' if triggered else '❌'} {rule_code} score={score:.2f}/{min_score} (pullback={pullback_confirmed}, adx={adx:.1f})"
            }

        if rule_code in ['Aa61', 'Aa61_short']:
            direction = rule.get('direction', 'long')
            
            sar_15m = context.get('sar_trend_15m', 0)
            pine = context.get('pinescript_signal', '')
            fib_zone = context.get('fibonacci_zone', 0)
            adx = context.get('adx', 0.0)
            bb_exp = context.get('bb_expanding', False)
            
            ema3 = context.get('ema3', 0.0)
            ema9 = context.get('ema9', 0.0)
            ema20 = context.get('ema20', 0.0)
            
            if direction == 'long':
                sar_15m_ok = (sar_15m > 0)
                pine_not_opposite = (pine != 'Sell')
                ema_alignment = (ema3 > ema9 > ema20) if (ema3 and ema9 and ema20) else False
                price_above_basis = (price > ema20) if ema20 else True
                
                triggered = (
                    ema_alignment and
                    price_above_basis and
                    bb_exp and
                    adx > 20 and
                    sar_15m_ok and
                    pine_not_opposite and
                    fib_zone <= 2
                )
                min_score = float(rule.get('min_score', 0.95))
                score = 0.98 if triggered else 0.40
                
                details = {
                    'ema_alignment': {'name': 'EMA3 > EMA9 > EMA20', 'passed': ema_alignment, 'weight': 0.20, 'current_value': f"ema3={ema3:.5f}, ema9={ema9:.5f}, ema20={ema20:.5f}"},
                    'price_above_basis': {'name': 'Price > EMA20', 'passed': price_above_basis, 'weight': 0.15, 'current_value': f"price={price:.5f}, ema20={ema20:.5f}"},
                    'bb_expanding': {'name': 'Bollinger Bands expanding', 'passed': bb_exp, 'weight': 0.20, 'current_value': bb_exp},
                    'adx_ok': {'name': 'ADX > 20', 'passed': adx > 20, 'weight': 0.15, 'current_value': adx},
                    'sar_15m_ok': {'name': 'SAR 15m alcista', 'passed': sar_15m_ok, 'weight': 0.10, 'current_value': sar_15m},
                    'pine_not_opposite': {'name': 'Pine no opuesto (No Sell)', 'passed': pine_not_opposite, 'weight': 0.10, 'current_value': pine},
                    'zone_ok': {'name': 'Fibonacci Zone <= 2', 'passed': fib_zone <= 2, 'weight': 0.10, 'current_value': fib_zone}
                }
            else: # short
                sar_15m_ok = (sar_15m < 0)
                pine_not_opposite = (pine != 'Buy')
                ema_alignment = (ema3 < ema9 < ema20) if (ema3 and ema9 and ema20) else False
                price_below_basis = (price < ema20) if ema20 else True
                
                triggered = (
                    ema_alignment and
                    price_below_basis and
                    bb_exp and
                    adx > 20 and
                    sar_15m_ok and
                    pine_not_opposite and
                    fib_zone >= -2
                )
                min_score = float(rule.get('min_score', 0.95))
                score = 0.98 if triggered else 0.40
                
                details = {
                    'ema_alignment': {'name': 'EMA3 < EMA9 < EMA20', 'passed': ema_alignment, 'weight': 0.20, 'current_value': f"ema3={ema3:.5f}, ema9={ema9:.5f}, ema20={ema20:.5f}"},
                    'price_below_basis': {'name': 'Price < EMA20', 'passed': price_below_basis, 'weight': 0.15, 'current_value': f"price={price:.5f}, ema20={ema20:.5f}"},
                    'bb_expanding': {'name': 'Bollinger Bands expanding', 'passed': bb_exp, 'weight': 0.20, 'current_value': bb_exp},
                    'adx_ok': {'name': 'ADX > 20', 'passed': adx > 20, 'weight': 0.15, 'current_value': adx},
                    'sar_15m_ok': {'name': 'SAR 15m bajista', 'passed': sar_15m_ok, 'weight': 0.10, 'current_value': sar_15m},
                    'pine_not_opposite': {'name': 'Pine no opuesto (No Buy)', 'passed': pine_not_opposite, 'weight': 0.10, 'current_value': pine},
                    'zone_ok': {'name': 'Fibonacci Zone >= -2', 'passed': fib_zone >= -2, 'weight': 0.10, 'current_value': fib_zone}
                }
                
            return {
                'triggered':  triggered,
                'score':      score,
                'min_score':  min_score,
                'rule_code':  rule_code,
                'rule_name':  rule.get('name'),
                'direction':  direction,
                'cycle':      rule.get('cycle'),
                'conditions': details,
                'all_passed': triggered,
                'reason': f"{'✅' if triggered else '❌'} {rule_code} score={score:.2f}/{min_score} (bb_exp={bb_exp}, adx={adx:.1f})"
            }

        if rule_code == 'Dd61_15m':
            df_15m = context.get('df_15m')
            
            # 1. Pendiente de lower_6 (Desaceleración de Bollinger Band inferior)
            lower6_flat = False
            lower6_slope = 0.0
            if df_15m is not None and len(df_15m) >= 6:
                lower6_now = float(df_15m['lower_6'].iloc[-1]) if 'lower_6' in df_15m.columns else 0
                lower6_prev = float(df_15m['lower_6'].iloc[-5]) if 'lower_6' in df_15m.columns else 0
                if lower6_prev > 0:
                    lower6_slope = (lower6_now - lower6_prev) / lower6_prev * 100
                    lower6_flat = lower6_slope >= -0.15

            # 2. Señal SIPV de reversión alcista
            last_row = df_15m.iloc[-1].to_dict() if df_15m is not None and len(df_15m) > 0 else {}
            sipv_signal = (
                bool(last_row.get('is_dragonfly', False)) or
                bool(last_row.get('is_bullish_engulfing', False)) or
                bool(last_row.get('low_higher_than_prev', False)) or
                bool(last_row.get('is_doji', False))
            )

            # 3. RSI en zona de sobreventa
            rsi_val = float(last_row.get('rsi_14', 30.0))
            rsi_ok = rsi_val <= 35

            # 4. Precio interactuando con las bandas inferiores
            price = float(context.get('price', 0))
            lower5 = float(context.get('lower_5', 0))
            near_support = price <= lower5 if lower5 > 0 else True

            # 5. Tendencia macro no bajista (No 4h red candle)
            is_4h_red = context.get('is_4h_red', False)
            macro_ok = not is_4h_red

            triggered = lower6_flat and sipv_signal and rsi_ok and near_support and macro_ok
            min_score = float(rule.get('min_score', 0.75))

            details = {
                'lower6_flat': {'name': 'lower_6 Flat (slope >= -0.15%)', 'passed': lower6_flat, 'weight': 0.35, 'current_value': f"{lower6_slope:.4f}%"},
                'sipv_signal': {'name': 'Vela de Reversión SIPV', 'passed': sipv_signal, 'weight': 0.30, 'current_value': sipv_signal},
                'rsi_ok': {'name': 'RSI en Sobreventa (15-35)', 'passed': rsi_ok, 'weight': 0.20, 'current_value': rsi_val},
                'macro_ok': {'name': 'No 4h Red Candle', 'passed': macro_ok, 'weight': 0.15, 'current_value': not is_4h_red}
            }

            return {
                'triggered':  triggered,
                'score':      1.0 if triggered else 0.4,
                'min_score':  min_score,
                'rule_code':  rule_code,
                'rule_name':  rule.get('name'),
                'direction':  rule.get('direction'),
                'cycle':      rule.get('cycle'),
                'conditions': details,
                'all_passed': triggered,
                'reason': f"{'✅' if triggered else '❌'} Dd61_15m score={1.0 if triggered else 0.4:.2f}/{min_score} (lower6_slope={lower6_slope:.4f}%, rsi={rsi_val:.1f})"
            }
        
        if symbol:
            mtf_filter = self._check_mtf_entry_filter(symbol, mtf, rule_code)
            if mtf_filter.get('blocked'):
                log_info('STRATEGY_ENGINE', f'🚫 {mtf_filter["reason"]}')
                return {
                    'triggered': False,
                    'score': 0.0,
                    'min_score': float(rule.get('min_score', 0.60)),
                    'rule_code': rule_code,
                    'rule_name': rule.get('name'),
                    'direction': rule.get('direction'),
                    'cycle': rule.get('cycle'),
                    'conditions': {},
                    'all_passed': False,
                    'blocked_by': 'mtf_filter',
                    'reason': mtf_filter['reason'],
                }

        cond_ids  = rule.get('condition_ids', [])
        weights   = rule.get('condition_weights') or {}
        min_score = float(rule.get('min_score', 0.60))
        logic     = rule.get('condition_logic', 'AND')

        details      = {}
        total_score  = 0.0
        total_weight = 0.0
        all_passed   = True

        for cid in cond_ids:
            cond = self.conditions.get(int(cid))
            if not cond:
                continue

            weight  = float(
                weights.get(str(cid),
                            1.0 / max(len(cond_ids), 1))
            )
            passed, score_val = self.evaluate_condition(
                cond, context
            )
            
            var = cond.get('variable') or {}
            source = var.get('source_field', '')

            details[cid] = {
                'name':   cond.get('name', ''),
                'passed': passed,
                'weight': weight,
                'current_value': context.get(source, 'N/A'),
                'target_value': cond.get('value_literal') if cond.get('value_type') == 'literal' else context.get(cond.get('value_variable'), 'N/A'),
                'operator': cond.get('operator', '==')
            }

            total_score  += weight * score_val
            total_weight += weight
            if not passed:
                all_passed = False

        score = total_score / total_weight \
                if total_weight > 0 else 0.0

        # Lógica AND: todas deben pasar
        if logic == 'AND':
            triggered = all_passed and score >= min_score
        else:
            triggered = score >= min_score

        return {
            'triggered':  triggered,
            'score':      round(score, 4),
            'min_score':  min_score,
            'rule_code':  rule['rule_code'],
            'rule_name':  rule['name'],
            'direction':  rule['direction'],
            'cycle':      rule['cycle'],
            'conditions': details,
            'all_passed': all_passed,
            'reason': (
                f"{'✅' if triggered else '❌'} "
                f"{rule['rule_code']} "
                f"score={score:.2f}/{min_score} "
                f"({'TRIGGERED' if triggered else 'NO'})"
            )
        }

    def evaluate_all(
        self,
        context:       dict,
        direction:     str,
        strategy_type: str,
        cycle:         str
    ) -> list:
        """
        Evalúa todas las reglas para una
        dirección/tipo/ciclo específico.
        Retorna lista ordenada por score.
        """
        if not self.loaded:
            log_error('STRATEGY_ENGINE',
                'Motor no cargado — llamar load()'
            )
            return []

        results = []
        for code, rule in self.rules.items():
            if rule['direction']     != direction:
                continue
            if rule['strategy_type'] != strategy_type:
                continue
            
            # Verificar applicable_cycles (nuevo)
            applicable = rule.get('applicable_cycles') or [rule.get('cycle', '15m')]
            if cycle not in applicable and 'all' not in applicable:
                continue

            result = self.evaluate_rule(rule, context)
            results.append(result)

        return sorted(
            results,
            key=lambda x: x['score'],
            reverse=True
        )

    def get_best_signal(
        self,
        context:       dict,
        strategy_type: str,
        cycle:         str
    ) -> Optional[dict]:
        """
        Retorna la mejor señal disponible.
        Evalúa LONG primero, luego SHORT.
        Retorna None si no hay señal válida.
        """
        for direction in ['long', 'short']:
            results = self.evaluate_all(
                context, direction,
                strategy_type, cycle
            )
            triggered = [
                r for r in results if r['triggered']
            ]
            if triggered:
                best = triggered[0]
                log_info('STRATEGY_ENGINE',
                    f'{direction.upper()} → '
                    f'{best["rule_code"]} '
                    f'score={best["score"]:.2f}'
                )
                return best

        return None

    async def log_evaluation(
        self,
        symbol:  str,
        result:  dict,
        context: dict
    ):
        """
        Guarda el resultado de evaluación
        en strategy_evaluations para diagnóstico.
        Solo guarda cuando triggered=True o
        cuando score > 0.40 (near-miss).
        """
        if not result:
            return
        if not result.get('triggered') \
           and result.get('score', 0) < 0.40:
            return

        try:
            await self.sb\
                .table('strategy_evaluations')\
                .insert({
                    'symbol':    symbol,
                    'rule_code': result['rule_code'],
                    'cycle':     result['cycle'],
                    'direction': result['direction'],
                    'score':     result['score'],
                    'triggered': result['triggered'],
                    'context':   {
                        k: v for k, v in context.items()
                        if isinstance(v, (int, float,
                                         str, bool))
                    },
                    'conditions': result['conditions']
                })\
                .execute()
        except Exception as e:
            pass  # No interrumpir el ciclo por logs
