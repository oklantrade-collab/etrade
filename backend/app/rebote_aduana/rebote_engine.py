import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List

from app.rebote_aduana.config import REBOTE_PARAMS, MODULE
from app.rebote_aduana.scoring.signal_fib_extreme import calculate_signal_fib_extreme
from app.rebote_aduana.scoring.signal_double_bottom import calculate_signal_double_bottom
from app.rebote_aduana.scoring.signal_ema_squeeze import calculate_signal_ema_squeeze
from app.rebote_aduana.scoring.signal_rsi_extreme import calculate_signal_rsi_extreme
from app.rebote_aduana.scoring.signal_zone_confluence import calculate_signal_zone_confluence
from app.rebote_aduana.scoring.signal_rebote_cascada_1h import calculate_signal_rebote_cascada_1h
from app.rebote_aduana.scoring.signal_rebote_pullback_ema20 import calculate_signal_rebote_pullback_ema20
from app.rebote_aduana.scoring.signal_rebote_cascada_multitf import calculate_signal_rebote_cascada_multitf
from app.rebote_aduana.scoring.regime_local import classify_regime_local, check_contra_trend_confirmation
from app.core.logger import log_error, log_info

@dataclass
class ReboteResult:
    symbol: str
    direction: str              # 'long' | 'short'
    score_raw: float = 0.0
    score_final: float = 0.0
    decision: str = 'PENDING'   # 'ENTER' | 'SKIP' | 'PENDING'
    signals: List[dict] = field(default_factory=list)  # list of {name, score, triggered, detail}
    regime_adx: str = ''        # 'choppy' | 'moderate' | 'strong_trend'
    regime_adx_multiplier: float = 1.0
    regime_local: str = ''      # 'bullish' | 'bearish' | 'neutral'
    contra_trend: bool = False
    contra_trend_confirmed: bool = False
    volume_confirmed: bool = False
    fib_zone: int = 0
    sl_price: float = 0.0       # Suggested stop loss
    tp_price: float = 0.0       # Suggested take profit
    detail: dict = field(default_factory=dict)

class ReboteEngine:
    def __init__(self, params: dict = None):
        self.params = params or REBOTE_PARAMS

    def _safe_float(self, val, default=0.0) -> float:
        try:
            if val is None or pd.isna(val):
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    def _safe_df(self, df) -> pd.DataFrame:
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return pd.DataFrame()
        return df

    def _classify_adx_regime(self, df_15m: pd.DataFrame) -> tuple:
        if df_15m.empty or 'adx' not in df_15m.columns:
            return 'moderate', 1.0
            
        last = df_15m.iloc[-1]
        adx = self._safe_float(last.get('adx'))
        
        if adx < 15.0:
            return 'choppy', self.params.get('adx_range_multiplier', 1.2)
        elif adx > 30.0:
            return 'strong_trend', self.params.get('adx_trend_multiplier', 0.5)
        return 'moderate', 1.0

    def _check_volume(self, df_15m: pd.DataFrame, params: dict) -> bool:
        if df_15m.empty or len(df_15m) < 10 or 'volume' not in df_15m.columns:
            return False
            
        # exclude forming candle
        closed = df_15m.iloc[:-1]
        if closed.empty:
            return False
            
        last_closed = closed.iloc[-1]
        vol = self._safe_float(last_closed.get('volume'))
        
        avg_vol = closed['volume'].tail(10).mean()
        if avg_vol == 0 or pd.isna(avg_vol):
            return False
            
        return vol > (1.3 * avg_vol)

    def _check_wick_rejection(self, df_15m: pd.DataFrame, df_5m: pd.DataFrame, direction: str) -> tuple:
        """
        Verifica si existe mecha de absorción / rechazo institucional (>= 25% del rango total de la vela)
        o vela verde/roja de giro en la última vela cerrada de 5m o 15m para evitar caídas/subidas libres.
        """
        df_target = df_5m if (df_5m is not None and not df_5m.empty and len(df_5m) >= 2) else df_15m
        if df_target is None or df_target.empty or len(df_target) < 2:
            return True, "Data insufficient, default pass"

        # Evaluar última vela cerrada
        c = df_target.iloc[-2] if len(df_target) >= 2 else df_target.iloc[-1]
        o = self._safe_float(c.get('open', 0))
        h = self._safe_float(c.get('high', 0))
        l = self._safe_float(c.get('low', 0))
        close_px = self._safe_float(c.get('close', 0))

        candle_range = h - l
        if candle_range <= 0:
            return True, "Zero range candle"

        if direction.lower() in ('long', 'buy'):
            lower_wick = min(o, close_px) - l
            wick_ratio = lower_wick / candle_range
            is_bullish_close = close_px > o
            if wick_ratio >= 0.25 or is_bullish_close:
                return True, f"Rejection wick ok ({wick_ratio:.1%}) or bullish close"
            return False, f"Falling knife warning: lower wick ({wick_ratio:.1%}) < 25% on bearish candle"
        else: # short
            upper_wick = h - max(o, close_px)
            wick_ratio = upper_wick / candle_range
            is_bearish_close = close_px < o
            if wick_ratio >= 0.25 or is_bearish_close:
                return True, f"Rejection wick ok ({wick_ratio:.1%}) or bearish close"
            return False, f"Rising spike warning: upper wick ({wick_ratio:.1%}) < 25% on bullish candle"

    def _calculate_sl_tp(self, df_15m: pd.DataFrame, direction: str, fib_zone: int) -> tuple:
        if df_15m.empty:
            return 0.0, 0.0
            
        last = df_15m.iloc[-1]
        atr = self._safe_float(last.get('atr', 0.0))
        basis = self._safe_float(last.get('basis', 0.0))
        
        lower_6 = self._safe_float(last.get('lower_6', 0.0))
        upper_6 = self._safe_float(last.get('upper_6', 0.0))
        lower_1 = self._safe_float(last.get('lower_1', 0.0))
        upper_1 = self._safe_float(last.get('upper_1', 0.0))

        sl = 0.0
        tp = 0.0
        
        if direction == 'long':
            sl = lower_6 - (atr * 0.2)
            tp = basis if basis > 0 else upper_1
        else:
            sl = upper_6 + (atr * 0.2)
            tp = basis if basis > 0 else lower_1
            
        return sl, tp

    def evaluate(self, symbol: str, direction: str, market_data: dict) -> ReboteResult:
        result = ReboteResult(symbol=symbol, direction=direction)
        
        if direction not in ('long', 'short'):
            result.detail = {'error': 'Invalid direction'}
            return result
            
        df_15m = self._safe_df(market_data.get('df_15m'))
        df_5m = self._safe_df(market_data.get('df_5m'))
        
        if df_15m.empty or df_5m.empty:
            result.detail = {'error': 'Missing market data'}
            return result
            
        # Get Fib Zone from last closed candle
        closed_15m = df_15m.iloc[:-1]
        if not closed_15m.empty and 'fibonacci_zone' in closed_15m.columns:
            raw_fib = self._safe_float(closed_15m.iloc[-1].get('fibonacci_zone', 0))
            result.fib_zone = int(raw_fib) if not pd.isna(raw_fib) else 0

        # S1: Fib Extreme
        s1 = calculate_signal_fib_extreme(df_15m, direction, self.params)
        s1['name'] = 'fib_extreme'
        result.signals.append(s1)
        
        # S2: Double Bottom
        s2 = calculate_signal_double_bottom(df_5m, df_15m, direction, self.params)
        s2['name'] = 'double_bottom'
        result.signals.append(s2)
        
        # S3: EMA Squeeze
        s3 = calculate_signal_ema_squeeze(df_5m, df_15m, direction, self.params)
        s3['name'] = 'ema_squeeze'
        result.signals.append(s3)
        
        # S4: RSI Extreme
        s4 = calculate_signal_rsi_extreme(df_15m, df_5m, direction, self.params)
        s4['name'] = 'rsi_extreme'
        result.signals.append(s4)
        
        # S5: Zone Confluence
        s5 = calculate_signal_zone_confluence(df_5m, df_15m, direction, self.params)
        s5['name'] = 'zone_confluence'
        result.signals.append(s5)
        
        # S6: Rebote Cascada 1H (15m Cascada + 1h Bollinger Double Penetration/Climax + SIPV/Mecha)
        df_1h = self._safe_df(market_data.get('df_1h'))
        s6 = calculate_signal_rebote_cascada_1h(df_15m, df_1h, direction, self.params)
        s6['name'] = 'rebote_cascada_1h'
        result.signals.append(s6)
        if s6.get('triggered', False):
            result.detail['rule_code'] = 'REB_CASCADA_1H'
            result.contra_trend_confirmed = True

        # S7: Rebote Pullback EMA20 (15m Trend + 1h EMA20 Pullback Rebound)
        s7 = calculate_signal_rebote_pullback_ema20(df_15m, df_1h, direction, self.params)
        s7['name'] = 'rebote_pullback_ema20'
        result.signals.append(s7)
        if s7.get('triggered', False):
            result.detail['rule_code'] = 'REB_PULLBACK_EMA20'
            result.contra_trend_confirmed = True

        # S8: Rebote Cascada 30M (Multi-TF 5m/15m + 30m Bollinger Rebound)
        df_30m = self._safe_df(market_data.get('df_30m'))
        if df_30m.empty and not df_15m.empty and len(df_15m) >= 4:
            df_30m = df_15m.resample('30min').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna().copy()
        s8 = calculate_signal_rebote_cascada_multitf(df_5m if not df_5m.empty else df_15m, df_30m, direction, higher_tf='30m', params=self.params)
        s8['name'] = 'rebote_cascada_30m'
        result.signals.append(s8)
        if s8.get('triggered', False) and 'rule_code' not in result.detail:
            result.detail['rule_code'] = 'REB_CASCADA_30M'
            result.contra_trend_confirmed = True

        # S9: Rebote Cascada 15M (Multi-TF 5m + 15m Bollinger Rebound)
        s9 = calculate_signal_rebote_cascada_multitf(df_5m, df_15m, direction, higher_tf='15m', params=self.params)
        s9['name'] = 'rebote_cascada_15m'
        result.signals.append(s9)
        if s9.get('triggered', False) and 'rule_code' not in result.detail:
            result.detail['rule_code'] = 'REB_CASCADA_15M'
            result.contra_trend_confirmed = True
        
        # Score raw
        score_raw = 0.0
        for s in result.signals:
            if s.get('triggered', False):
                score_raw += s.get('score', 0.0)
        result.score_raw = score_raw
        
        # ADX Regime
        if not closed_15m.empty:
            regime_adx, adx_multiplier = self._classify_adx_regime(closed_15m)
        else:
            regime_adx, adx_multiplier = 'moderate', 1.0
            
        result.regime_adx = regime_adx
        result.regime_adx_multiplier = adx_multiplier
        
        score_after_adx = score_raw * adx_multiplier
        
        # Regime Local
        if not closed_15m.empty:
            result.regime_local = classify_regime_local(closed_15m)
        else:
            result.regime_local = 'neutral'
            
        # Contra-trend
        regime_name = result.regime_local.get('regime', 'neutral') if isinstance(result.regime_local, dict) else str(result.regime_local)
        if direction == 'long' and regime_name == 'bearish':
            result.contra_trend = True
        elif direction == 'short' and regime_name == 'bullish':
            result.contra_trend = True
            
        # Check CASCADA interaction (Spec 3.8 & 4.2.2)
        # If position in CASCADA mode determined movement is pullback in intact trend, do not propose contra-trend entry
        cascade_info = market_data.get('cascade_info', {})
        if cascade_info.get('is_pullback_noise', False):
            # If CASCADA identified this as short-term pullback in intact trend
            trend_direction = cascade_info.get('intact_trend_direction', '')
            if direction != trend_direction and trend_direction != '':
                result.decision = 'SKIP'
                result.detail['reason'] = f"Blocked by CASCADA: pullback noise against intact {trend_direction} trend"
                return result

        if result.contra_trend:
            if not result.contra_trend_confirmed:
                contra_result = check_contra_trend_confirmation(df_15m, direction)
                result.contra_trend_confirmed = contra_result.get('confirmed', False) if isinstance(contra_result, dict) else bool(contra_result)
                if not result.contra_trend_confirmed:
                    result.decision = 'SKIP'
                    result.detail['reason'] = 'Contra-trend not confirmed'
                # Volume might be unchecked here since it skips anyway, but let's check it for completeness
        
        # Volume Confirmed
        result.volume_confirmed = self._check_volume(df_15m, self.params)
        
        volume_bonus = self.params.get('volume_bonus_multiplier', 1.1) if result.volume_confirmed else 1.0
        
        result.score_final = score_after_adx * volume_bonus
        
        score_min_entry = self.params.get('score_min_entry', 50.0)
        
        if result.decision != 'SKIP':
            if result.score_final >= score_min_entry:
                wick_ok, wick_reason = self._check_wick_rejection(df_15m, df_5m, direction)
                if not wick_ok:
                    result.decision = 'PENDING'
                    result.detail['reason'] = f"Wick filter: {wick_reason}"
                else:
                    result.decision = 'ENTER'
            else:
                result.decision = 'SKIP'
                
        sl, tp = self._calculate_sl_tp(df_15m, direction, result.fib_zone)
        result.sl_price = sl
        result.tp_price = tp
        
        return result

    def evaluate_climax_exit(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        df_15m: pd.DataFrame,
        df_5m: Optional[pd.DataFrame] = None,
        position: Optional[dict] = None,
        snap: Optional[dict] = None
    ) -> tuple:
        """
        Evalúa si una posición abierta ha alcanzado el clímax de recorrido banda a banda
        (LOWER_5/6 para SHORT o UPPER_5/6 para LONG) y presenta confirmación técnica de rebote
        para emitir la orden de cierre con máxima ganancia.
        Retorna: (should_exit: bool, reason: str, metadata: dict)
        """
        if df_15m is None or df_15m.empty or len(df_15m) < 20 or current_price <= 0:
            return False, "Datos insuficientes para evaluar clímax", {}

        pos = position or {}
        entry_p = float(pos.get('entry_price') or pos.get('avg_entry_price') or current_price)
        dir_clean = str(direction).lower()
        is_long = dir_clean in ('long', 'buy')
        
        pnl_pct = ((current_price - entry_p) / entry_p * 100.0) if is_long else ((entry_p - current_price) / entry_p * 100.0)
        
        # 1. Obtener niveles de Bollinger y Fibonacci
        col = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else None)
        closes = pd.to_numeric(df_15m[col], errors='coerce').dropna()
        sma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        upper_bb = float((sma20 + 2.0 * std20).iloc[-1]) if len(sma20) > 0 else 0.0
        lower_bb = float((sma20 - 2.0 * std20).iloc[-1]) if len(sma20) > 0 else 0.0

        snap_data = snap or {}
        upper_5 = float(snap_data.get('upper_5') or upper_bb)
        upper_6 = float(snap_data.get('upper_6') or (upper_bb * 1.01))
        lower_5 = float(snap_data.get('lower_5') or lower_bb)
        lower_6 = float(snap_data.get('lower_6') or (lower_bb * 0.99))

        # 2. Calcular pendiente de EMA3
        ema3_series = closes.ewm(span=3, adjust=False).mean()
        slope_ema3 = (float(ema3_series.iloc[-1]) - float(ema3_series.iloc[-2])) / float(ema3_series.iloc[-2]) * 100.0 if len(ema3_series) >= 2 else 0.0

        # 3. Evaluar clímax para SHORT
        if not is_long:
            # SHORT: Buscamos piso extremo (LOWER_5, LOWER_6 o Banda Inferior)
            is_lower_reached = (current_price <= lower_5) or (current_price <= lower_6) or (lower_bb > 0 and current_price <= lower_bb * 1.002)
            
            # Confirmación de rebote: giro alcista de EMA3 o mecha de absorción en 5m/15m
            wick_confirmed, _ = self._check_wick_rejection(df_15m, df_5m, 'long') # vela de rechazo alcista
            has_rebound_turn = (slope_ema3 > 0.01) or wick_confirmed
            
            if is_lower_reached and has_rebound_turn and pnl_pct > 0.3:
                return True, f"🎯 REBOTE Clímax SHORT confirmado: Precio en zona LOWER ({current_price:.4f} <= {lower_5:.4f}) con rebote alcista detectado (+{pnl_pct:.2f}% PnL)", {
                    "climax_type": "SHORT_LOWER_REBOUND",
                    "price": current_price,
                    "target_lower": lower_5,
                    "pnl_pct": pnl_pct
                }

        # 4. Evaluar clímax para LONG
        else:
            # LONG: Buscamos techo extremo (UPPER_5, UPPER_6 o Banda Superior)
            is_upper_reached = (current_price >= upper_5) or (current_price >= upper_6) or (upper_bb > 0 and current_price >= upper_bb * 0.998)
            
            # Confirmación de giro: giro bajista de EMA3 o mecha de rechazo superior
            wick_confirmed, _ = self._check_wick_rejection(df_15m, df_5m, 'short') # vela de rechazo bajista
            has_exhaustion_turn = (slope_ema3 < -0.01) or wick_confirmed
            
            if is_upper_reached and has_exhaustion_turn and pnl_pct > 0.3:
                return True, f"🎯 REBOTE Clímax LONG confirmado: Precio en zona UPPER ({current_price:.4f} >= {upper_5:.4f}) con agotamiento/giro detectado (+{pnl_pct:.2f}% PnL)", {
                    "climax_type": "LONG_UPPER_EXHAUSTION",
                    "price": current_price,
                    "target_upper": upper_5,
                    "pnl_pct": pnl_pct
                }

        return False, "Acompañando recorrido hacia bandas extremas", {}

