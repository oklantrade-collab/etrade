"""
HALCÓN Engine — Motor de decisión puro multi-timeframe.
Dado datos de mercado + posición + entry_profile, devuelve score_final y decisión.
Sin efectos secundarios — facilita testing unitario.
"""
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional, Any

from app.halcon_centinela.config import (
    HALCON_PARAMS, HalconProfile, Semaforo, CentinelaDecision, EntryProfile,
    get_profile, classify_entry_profile, load_halcon_config_from_db
)
from app.halcon_centinela.scoring.score_1d import calculate_score_1d
from app.halcon_centinela.scoring.score_4h import calculate_score_4h
from app.halcon_centinela.scoring.score_15m import calculate_score_15m
from app.halcon_centinela.scoring.score_5m import calculate_score_5m
from app.halcon_centinela.scoring.score_1m import calculate_score_1m
from app.halcon_centinela.scoring.rsi_component import calculate_rsi_adjustment
from app.halcon_centinela.scoring.regime_filter import classify_regime, apply_regime_adjustments
from app.halcon_centinela.scoring.compression_index import (
    calculate_compression_index, apply_fibonacci_multiplier, select_compression_timeframe
)
from app.halcon_centinela.scoring.volume_confirmation import check_volume_confirmation
from app.core.logger import log_error, log_info

MODULE = "HALCON_ENGINE"


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _safe_df(df) -> pd.DataFrame:
    """Returns an empty DataFrame if input is None."""
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame()
    return df


@dataclass
class HalconResult:
    """Resultado completo de la evaluación HALCÓN para una posición."""
    score_final: float
    scores_by_layer: Dict[str, int]       # {1d: x, 4h: x, 15m: x, 5m: x, 1m: x}
    rsi_adjustments: Dict[str, int]       # RSI adjustment per layer
    regime: dict
    compression: dict
    volume_confirmation: dict
    semaforo: str                          # Semaforo enum value
    decision: str                         # CentinelaDecision enum value
    squeeze_active: bool
    detail: dict                          # Full breakdown for logging


class HalconEngine:
    """Motor de decisión HALCÓN — evaluación pura sin efectos secundarios."""

    def __init__(self, params: dict = None):
        self.params = params or HALCON_PARAMS

    def evaluate(self, position: dict, market_data: dict) -> HalconResult:
        """Pipeline principal de evaluación multi-timeframe.

        Args:
            position: Posición normalizada con fields: id, symbol, direction,
                      entry_price, current_pnl, position_size, entry_profile, etc.
            market_data: {df_1d, df_4h, df_15m, df_5m, df_1m, snapshot}

        Returns: HalconResult con score_final, decisión, y detalle completo.
        """
        try:
            direction = (position.get('direction') or position.get('side', '')).lower()
            if direction not in ('long', 'short'):
                return self._default_result("Dirección inválida o ausente")

            symbol = position.get('symbol', 'UNKNOWN')

            # ── 1. Determinar perfil de entrada ──
            entry_profile_str = position.get('entry_profile', EntryProfile.TENDENCIA_SOSTENIDA.value)
            profile = get_profile(entry_profile_str)
            weights = {k: v / 100.0 for k, v in profile.weights.items()}  # normalize to 0-1

            # ── 2. Preparar DataFrames seguros ──
            df_1d = _safe_df(market_data.get('df_1d'))
            df_4h = _safe_df(market_data.get('df_4h'))
            df_15m = _safe_df(market_data.get('df_15m'))
            df_5m = _safe_df(market_data.get('df_5m'))
            df_1m = _safe_df(market_data.get('df_1m'))

            # ── 3. Calcular scores por capa ──
            result_1d = calculate_score_1d(df_1d, direction, self.params)
            result_4h = calculate_score_4h(df_4h, direction, self.params)
            result_15m = calculate_score_15m(df_15m, direction, self.params)
            result_5m = calculate_score_5m(df_5m, direction, self.params)
            result_1m = calculate_score_1m(df_1m, result_5m, direction, self.params)

            raw_scores = {
                '1d': result_1d.get('score', 0),
                '4h': result_4h.get('score', 0),
                '15m': result_15m.get('score', 0),
                '5m': result_5m.get('score', 0),
                '1m': result_1m.get('score', 0),
            }

            squeeze_active = result_5m.get('squeeze_active', False)

            # ── 4. Régimen ADX (desde el timeframe relevante) ──
            regime = self._extract_regime(df_15m, df_4h)

            # ── 5. RSI transversal por capa ──
            rsi_adjustments = {}
            rsi_dfs = {'1d': df_1d, '4h': df_4h, '15m': df_15m, '5m': df_5m}
            for tf, df in rsi_dfs.items():
                if not df.empty:
                    rsi_adj = calculate_rsi_adjustment(
                        df, tf, regime.get('regime', 'moderate'),
                        entry_profile_str, self.params
                    )
                    rsi_adjustments[tf] = rsi_adj
                else:
                    rsi_adjustments[tf] = 0

            # Aplicar RSI a scores (sumar y clampear)
            adjusted_scores = {}
            for layer in raw_scores:
                adj = rsi_adjustments.get(layer, 0)
                adjusted_scores[layer] = int(_clamp(raw_scores[layer] + adj))

            # ── 6. Aplicar ajustes de régimen a pesos y scores ──
            regime_result = apply_regime_adjustments(
                adjusted_scores, regime, weights, self.params
            )
            final_weights = regime_result.get('adjusted_weights', weights)
            regime_adjusted_scores = regime_result.get('adjusted_scores', adjusted_scores)
            close_threshold_override = regime_result.get('close_threshold_override')

            # ── 7. Compresión EMA + Fibonacci ──
            compression = self._compute_compression(
                market_data, df_15m, df_4h, self.params
            )
            fib_multiplier = compression.get('fib_multiplier', 1.0)

            # ── 8. Confirmación por volumen ──
            volume_conf = self._compute_volume_confirmation(df_15m, direction)

            # ── 9. Score final ponderado ──
            score_final = 0.0
            total_weight = 0.0
            for layer, score_val in regime_adjusted_scores.items():
                w = final_weights.get(layer, 0.0)
                # Aplicar reducción de volumen a capa 15m si cruce no confirmado
                if layer == '15m' and not volume_conf.get('confirmed', True):
                    score_val = int(score_val * volume_conf.get('score_multiplier', 0.5))
                score_final += score_val * w
                total_weight += w

            if total_weight > 0:
                score_final = score_final / total_weight

            # Aplicar multiplicador de compresión/Fibonacci
            if compression.get('compressed', False):
                score_final = score_final * fib_multiplier

            score_final = _clamp(score_final)

            # ── 10. Semáforo ──
            semaforo = self._map_to_semaforo(score_final, direction)

            # ── 11. Decisión ──
            current_pnl = _safe_float(position.get('current_pnl', 0.0))
            min_profit = self.params.get('min_profit_usd', 1.0)
            effective_threshold = close_threshold_override or profile.close_threshold

            decision = self._determine_decision(
                score_final, direction, squeeze_active,
                current_pnl, min_profit, effective_threshold,
                (profile.partial_threshold_low, profile.partial_threshold_high)
            )

            detail = {
                'profile': entry_profile_str,
                'raw_scores': raw_scores,
                'adjusted_scores': dict(regime_adjusted_scores),
                'rsi_adjustments': rsi_adjustments,
                'regime': regime,
                'compression': compression,
                'volume': volume_conf,
                'base_weights': profile.weights,
                'final_weights': {k: round(v, 4) for k, v in final_weights.items()},
                'current_pnl': current_pnl,
                'effective_threshold': effective_threshold,
                'components': {
                    '1d': result_1d.get('components', {}),
                    '4h': result_4h.get('components', {}),
                    '15m': result_15m.get('components', {}),
                    '5m': result_5m.get('components', {}),
                    '1m': result_1m.get('components', {}),
                },
            }

            return HalconResult(
                score_final=round(score_final, 2),
                scores_by_layer=dict(regime_adjusted_scores),
                rsi_adjustments=rsi_adjustments,
                regime=regime,
                compression=compression,
                volume_confirmation=volume_conf,
                semaforo=semaforo.value,
                decision=decision.value,
                squeeze_active=squeeze_active,
                detail=detail,
            )

        except Exception as e:
            log_error(f"Error evaluating HALCÓN for {position.get('id', '?')}: {e}", MODULE)
            return self._default_result(str(e))

    # ─────────────────────────── Helpers ───────────────────────────

    def _default_result(self, error: str) -> HalconResult:
        return HalconResult(
            score_final=0.0,
            scores_by_layer={},
            rsi_adjustments={},
            regime={},
            compression={},
            volume_confirmation={},
            semaforo=Semaforo.AMBAR.value,
            decision=CentinelaDecision.MANTENER.value,
            squeeze_active=False,
            detail={'error': error},
        )

    def _extract_regime(self, df_15m: pd.DataFrame, df_4h: pd.DataFrame) -> dict:
        """Extrae ADX/DI del timeframe disponible más relevante."""
        for df in (df_15m, df_4h):
            if not df.empty and 'adx' in df.columns:
                last = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
                adx = _safe_float(last.get('adx'))
                plus_di = _safe_float(last.get('plus_di'))
                minus_di = _safe_float(last.get('minus_di'))
                return classify_regime(adx, plus_di, minus_di)
        return classify_regime(20.0, 25.0, 25.0)  # moderate default

    def _compute_compression(self, market_data: dict, df_15m: pd.DataFrame,
                              df_4h: pd.DataFrame, params: dict) -> dict:
        """Calcula índice de compresión EMA y multiplicador Fibonacci."""
        # Determinar ATR% diario
        df_1d = _safe_df(market_data.get('df_1d'))
        atr_daily = 0.0
        current_price = 1.0
        if not df_1d.empty and 'atr' in df_1d.columns:
            last_1d = df_1d.iloc[-1]
            atr_daily = _safe_float(last_1d.get('atr'))
            current_price = _safe_float(last_1d.get('close', 1.0), 1.0)

        atr_pct = atr_daily / current_price if current_price > 0 else 0.0
        compression_tf = select_compression_timeframe(atr_pct, params)
        df_comp = df_4h if compression_tf == '4h' else df_15m

        if df_comp.empty:
            return {'index': 0.0, 'compressed': False, 'fib_multiplier': 1.0,
                    'timeframe': compression_tf, 'atr_pct_daily': atr_pct}

        compression = calculate_compression_index(df_comp, atr_daily, params)

        # Obtener fib_zone del último candle cerrado
        fib_zone = 0
        if 'fibonacci_zone' in df_comp.columns and len(df_comp) > 1:
            fib_zone = int(_safe_float(df_comp.iloc[-2].get('fibonacci_zone', 0)))

        fib_mult = apply_fibonacci_multiplier(compression, fib_zone) if compression.get('compressed') else 1.0

        return {
            **compression,
            'fib_multiplier': fib_mult,
            'fib_zone': fib_zone,
            'timeframe': compression_tf,
            'atr_pct_daily': round(atr_pct, 6),
        }

    def _compute_volume_confirmation(self, df_15m: pd.DataFrame, direction: str) -> dict:
        """Verifica confirmación por volumen en la capa 15m."""
        if df_15m.empty or len(df_15m) < 12:
            return {'confirmed': True, 'score_multiplier': 1.0, 'detail': 'Insufficient data'}

        # Buscar el último cruce EMA en las últimas 5 velas cerradas
        closed = df_15m.iloc[:-1]
        cross_idx = len(closed) - 1  # último candle cerrado por defecto
        if 'ema_3' in closed.columns and 'ema_9' in closed.columns:
            for i in range(len(closed) - 1, max(len(closed) - 6, 0), -1):
                prev = closed.iloc[i - 1] if i > 0 else None
                curr = closed.iloc[i]
                if prev is not None:
                    prev_diff = _safe_float(prev.get('ema_3')) - _safe_float(prev.get('ema_9'))
                    curr_diff = _safe_float(curr.get('ema_3')) - _safe_float(curr.get('ema_9'))
                    if (prev_diff <= 0 and curr_diff > 0) or (prev_diff >= 0 and curr_diff < 0):
                        cross_idx = i
                        break

        return check_volume_confirmation(closed, cross_idx, self.params, market_type='forex')

    def _map_to_semaforo(self, score_final: float, direction: str) -> Semaforo:
        """Mapea score final a semáforo. Para SHORT, se invierte el signo."""
        effective_score = score_final if direction == 'long' else -score_final

        if effective_score <= -60:
            return Semaforo.ROJO_FUERTE
        elif effective_score <= -25:
            return Semaforo.ROJO_DEBIL
        elif effective_score >= 60:
            return Semaforo.VERDE_FUERTE
        elif effective_score >= 25:
            return Semaforo.VERDE_DEBIL
        else:
            return Semaforo.AMBAR

    def _determine_decision(self, score_final: float, direction: str,
                             squeeze_active: bool, current_pnl: float,
                             min_profit: float, close_threshold: float,
                             partial_range: tuple) -> CentinelaDecision:
        """Determina decisión de cierre basada en score, dirección y PNL.

        Para LONG: score negativo = presión de cierre
        Para SHORT: score positivo = presión de cierre (se invierte internamente)
        """
        if current_pnl < min_profit:
            return CentinelaDecision.MANTENER

        # Normalizar: usar score "contra la posición"
        # Para LONG: score negativo es malo → |score| es la presión de cierre
        # Para SHORT: score positivo es malo → score directo es la presión
        if direction == 'long':
            close_pressure = -score_final  # -(-60) = 60 de presión
        else:
            close_pressure = score_final   # +60 = 60 de presión

        partial_low, partial_high = partial_range

        if close_pressure >= close_threshold:
            return CentinelaDecision.CIERRE_TOTAL
        elif partial_low <= close_pressure < close_threshold and squeeze_active:
            return CentinelaDecision.CIERRE_PARCIAL

        return CentinelaDecision.MANTENER
