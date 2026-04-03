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
        basis_info = detect_basis_horizontal(df_15m, lookback=10, slope_threshold=0.8)
        basis_info_4h = detect_basis_horizontal(df_4h, lookback=10, slope_threshold=0.8) if df_4h is not None else {}

        return {
            # Precio
            'price':             safe_float(snap.get('price')),
            'dist_basis_pct':    safe_float(snap.get('dist_basis_pct')),
            # ADX
            'adx':               adx,
            'plus_di':           safe_float(last_15m.get('plus_di')),
            'minus_di':          safe_float(last_15m.get('minus_di')),
            'adx_velocity':      velocity,
            # EMAs
            'ema3':              safe_float(last_15m.get('ema3')),
            'ema9':              safe_float(last_15m.get('ema9')),
            'ema20':             safe_float(last_15m.get('ema20')),
            'ema50':             safe_float(last_15m.get('ema50')),
            'ema200':            safe_float(last_15m.get('ema200')),
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

    def evaluate_rule(
        self,
        rule:    dict,
        context: dict
    ) -> dict:
        """
        Evalúa una regla completa.
        Calcula score ponderado de condiciones.
        """
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
