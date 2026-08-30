"""
ANCLA — Gestión Dinámica de Stop Loss y Take Profit Estructural por Fibonacci y Bollinger
eTrade v5.0 / v6.0

Componentes:
1. Stop Loss dinámico (15M):
   - Armado: Precio en mitad inferior de zona Fibonacci + EMA3 descendente (LONG).
   - Buffer: max(10% ancho zona, ATR_mult * ATR(14, 15m)), con ATR_mult=0.85 en volatilidad alta.
   - Desarmado: 2 velas consecutivas cerradas con EMA3 ascendente (histéresis).
   - Trailing estructural por salto de zona Fibonacci.
2. Take Profit en 2 etapas:
   - TP1 (50%): Nivel en zona Fibonacci (1D o 4H) con sensor de EMA3 (4H o 1H). Histéresis 2 velas.
   - TP2 (50% remanente): Nivel en Bollinger (1D o 4H) sin condición de momentum.
   - Seguro de Breakeven automático tras ejecución de TP1.
   - Control de tamaño mínimo de broker.
"""

import math
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning, log_error

MODULE = "ANCLA_MANAGER"


class AnclaManager:
    """
    Gestor estructural de Stop Loss y Take Profit ANCLA.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        # Parámetros por defecto según especificación
        self.buffer_zone_pct = self.config.get("buffer_zone_pct", 0.10)        # 10% del ancho de zona
        self.buffer_atr_mult_normal = self.config.get("buffer_atr_mult_normal", 0.50)  # 0.5x ATR
        self.buffer_atr_mult_high = self.config.get("buffer_atr_mult_high", 0.85)      # 0.85x ATR en alta volatilidad
        self.tp1_ratio = self.config.get("tp1_ratio", 0.50)                    # 50% de la posición en TP1
        self.tp1_buffer_pct = self.config.get("tp1_buffer_pct", 0.10)          # 10% del ancho de zona para TP1
        self.tp2_buffer_pct = self.config.get("tp2_buffer_pct", 0.10)          # 10% del ancho Bollinger para TP2
        self.hysteresis_bars_sl = self.config.get("hysteresis_bars_sl", 2)      # 2 velas 15m para desarmar SL
        self.hysteresis_bars_tp1 = self.config.get("hysteresis_bars_tp1", 2)    # 2 velas sensor para cancelar TP1

    def get_mode_for_strategy(self, rule_code: str) -> str:
        """
        Determina si una estrategia opera en Modo Intraday (4H/1H) o Modo Swing (1D/4H).
        """
        code = str(rule_code or "").upper()
        # Scalps y Pullbacks rápidos operan en Modo Intraday
        if any(k in code for k in ("PULLBACK", "SCALP", "CC21", "CC11", "AA21", "BB21", "HOT")):
            return "intraday"
        # Estrategias mayores, Climax, Floors, Traversals operan en Modo Swing
        return "swing"

    def calculate_sl_dynamic(
        self,
        position: Dict[str, Any],
        df_15m: pd.DataFrame,
        fib_levels: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calcula el estado y nivel del Stop Loss dinámico de 15M.
        
        Returns:
            Dict con:
            - armed (bool): si el SL debe estar activo
            - sl_price (float): nivel de SL calculado
            - reason (str): motivo del cálculo o desarmado
            - zone_updated (bool): si hubo salto de zona (trailing estructural)
        """
        result = {
            "armed": False,
            "sl_price": 0.0,
            "reason": "",
            "zone_updated": False,
            "zone_index": 0,
        }

        if df_15m is None or len(df_15m) < 5:
            result["reason"] = "Datos insuficientes de 15M"
            return result

        side = str(position.get("side", "long")).lower()
        is_long = side in ("long", "buy")
        current_price = float(position.get("current_price", 0.0))
        if current_price <= 0:
            current_price = float(df_15m.iloc[-1].get("close", 0.0))

        # 1. Obtener zona Fibonacci actual y sus bandas
        zone_info = self._get_current_fib_zone_bounds(current_price, fib_levels, is_long)
        lower_bound = zone_info["lower_bound"]
        upper_bound = zone_info["upper_bound"]
        zone_idx = zone_info["zone_index"]
        result["zone_index"] = zone_idx

        zone_width = abs(upper_bound - lower_bound)
        if zone_width <= 0:
            zone_width = current_price * 0.01  # Fallback 1% si no hay ancho definido

        zone_midpoint = (upper_bound + lower_bound) / 2.0

        # 2. Pendiente y aceleración de EMA3 en 15M
        ema_col = "ema1" if "ema1" in df_15m.columns else "ema_3"
        ema3_series = pd.to_numeric(df_15m[ema_col], errors="coerce").dropna()
        if len(ema3_series) < 3:
            result["reason"] = "EMA3 insuficiente en 15M"
            return result

        ema3_slope_current = float(ema3_series.iloc[-1] - ema3_series.iloc[-2])
        ema3_slope_prev = float(ema3_series.iloc[-2] - ema3_series.iloc[-3])

        # 3. Buffer de seguridad dinámico (max(10% zona, ATR_mult * ATR))
        atr_val = self._get_atr_15m(df_15m)
        is_high_vol = self._check_high_volatility(df_15m)
        atr_mult = self.buffer_atr_mult_high if is_high_vol else self.buffer_atr_mult_normal
        buffer_atr = atr_mult * atr_val
        buffer_pct = self.buffer_zone_pct * zone_width
        final_buffer = max(buffer_pct, buffer_atr)

        # 4. Chequeo de Histéresis de Desarmado (2 velas consecutivas a favor)
        is_favorable_sustained = False
        if is_long:
            is_favorable_sustained = (ema3_slope_current > 0) and (ema3_slope_prev > 0)
        else:
            is_favorable_sustained = (ema3_slope_current < 0) and (ema3_slope_prev < 0)

        # Estado previo de armado
        was_armed = bool(position.get("ancla_sl_armado", False))
        prev_zone_idx = int(position.get("ancla_zone_idx", zone_idx))

        # Trailing por salto de zona (Mejora 1)
        if is_long and zone_idx > prev_zone_idx:
            result["zone_updated"] = True
        elif not is_long and zone_idx < prev_zone_idx:
            result["zone_updated"] = True

        # 5. Condición de Armado / Desarmado
        if is_long:
            is_in_lower_half = current_price <= zone_midpoint
            is_ema_bearish = ema3_slope_current <= 0

            if is_in_lower_half and is_ema_bearish:
                result["armed"] = True
                result["sl_price"] = lower_bound - final_buffer
                result["reason"] = f"ANCLA SL LONG Armado: Precio en mitad inferior ({current_price:.4f} <= {zone_midpoint:.4f}) y EMA3 desc. SL={result['sl_price']:.4f} (buf={final_buffer:.4f})"
            elif was_armed and is_favorable_sustained:
                result["armed"] = False
                result["sl_price"] = 0.0
                result["reason"] = f"ANCLA SL LONG Desarmado por histéresis: EMA3 ascendente durante 2 velas consecutivas."
            elif was_armed:
                # Se mantiene armado con recálculo dinámico
                result["armed"] = True
                result["sl_price"] = lower_bound - final_buffer
                result["reason"] = f"ANCLA SL LONG Mantenido armado: SL={result['sl_price']:.4f}"
            else:
                result["armed"] = False
                result["reason"] = f"ANCLA SL LONG Inactivo: Precio en mitad superior o EMA3 fuerte."
        else:
            # SHORT
            is_in_upper_half = current_price >= zone_midpoint
            is_ema_bullish = ema3_slope_current >= 0

            if is_in_upper_half and is_ema_bullish:
                result["armed"] = True
                result["sl_price"] = upper_bound + final_buffer
                result["reason"] = f"ANCLA SL SHORT Armado: Precio en mitad superior ({current_price:.4f} >= {zone_midpoint:.4f}) y EMA3 asc. SL={result['sl_price']:.4f} (buf={final_buffer:.4f})"
            elif was_armed and is_favorable_sustained:
                result["armed"] = False
                result["sl_price"] = 0.0
                result["reason"] = f"ANCLA SL SHORT Desarmado por histéresis: EMA3 descendente durante 2 velas consecutivas."
            elif was_armed:
                result["armed"] = True
                result["sl_price"] = upper_bound + final_buffer
                result["reason"] = f"ANCLA SL SHORT Mantenido armado: SL={result['sl_price']:.4f}"
            else:
                result["armed"] = False
                result["reason"] = f"ANCLA SL SHORT Inactivo: Precio en mitad inferior o EMA3 bajista fuerte."

        return result

    def calculate_tp1_stage(
        self,
        position: Dict[str, Any],
        df_macro: pd.DataFrame,   # 1D para Swing, 4H para Intraday
        df_sensor: pd.DataFrame,  # 4H para Swing, 1H para Intraday
        min_broker_lot: float = 0.001,
        mode: str = "swing",
    ) -> Dict[str, Any]:
        """
        Calcula la Etapa 1 del Take Profit (50% de la posición en orden LIMIT condicional).
        """
        result = {
            "should_place_tp1": False,
            "tp1_price": 0.0,
            "volume_pct": 50.0,
            "close_full": False,
            "cancel_pending_tp1": False,
            "reason": "",
        }

        # Control de disparo único
        if position.get("ancla_tp1_fired", False):
            result["reason"] = "TP1 ya fue ejecutado previamente en esta posición."
            return result

        if df_macro is None or df_sensor is None or len(df_macro) < 2 or len(df_sensor) < 3:
            result["reason"] = "Datos insuficientes en macro/sensor para TP1."
            return result

        side = str(position.get("side", "long")).lower()
        is_long = side in ("long", "buy")
        current_price = float(position.get("current_price", 0.0))

        # 1. Zona Fibonacci en temporalidad Macro (1D o 4H)
        macro_zone = self._get_macro_fib_bounds(df_macro, current_price, is_long)
        macro_upper = macro_zone["upper"]
        macro_lower = macro_zone["lower"]
        macro_width = abs(macro_upper - macro_lower)
        if macro_width <= 0:
            macro_width = current_price * 0.02

        # Nivel de TP1: Borde superior - 10% del ancho (LONG) o Borde inferior + 10% (SHORT)
        if is_long:
            tp1_target = macro_upper - (self.tp1_buffer_pct * macro_width)
        else:
            tp1_target = macro_lower + (self.tp1_buffer_pct * macro_width)

        result["tp1_price"] = tp1_target

        # 2. Condición de Agotamiento de Momentum en timeframe Sensor (EMA3 de 4H o 1H)
        ema_col = "ema1" if "ema1" in df_sensor.columns else "ema_3"
        ema3_sensor = pd.to_numeric(df_sensor[ema_col], errors="coerce").dropna()
        if len(ema3_sensor) < 3:
            result["reason"] = "EMA3 sensor insuficiente"
            return result

        slope_current = float(ema3_sensor.iloc[-1] - ema3_sensor.iloc[-2])
        slope_prev = float(ema3_sensor.iloc[-2] - ema3_sensor.iloc[-3])

        # 3. Verificación de tamaño mínimo del broker (Mejora 5 de Spec)
        total_volume = float(position.get("volume", position.get("amount", 0.0)))
        vol_50 = total_volume * 0.50
        if vol_50 < min_broker_lot and total_volume >= min_broker_lot:
            result["close_full"] = True
            result["volume_pct"] = 100.0

        # 4. Evaluación de Disparo vs Cancelación por Histéresis
        is_tp1_placed = bool(position.get("ancla_tp1_placed", False))

        if is_long:
            is_exhaustion = slope_current <= 0  # EMA3 4H plana o descendente
            is_momentum_resumed = (slope_current > 0) and (slope_prev > 0)  # 2 velas 4H alcistas consecutivas

            if is_exhaustion and not is_tp1_placed:
                result["should_place_tp1"] = True
                result["reason"] = f"ANCLA TP1 LONG Activado: Agotamiento EMA3 {mode} (slope={slope_current:.6f}<=0). Orden LIMIT a {tp1_target:.4f} ({result['volume_pct']:.0f}%)."
            elif is_tp1_placed and is_momentum_resumed:
                result["cancel_pending_tp1"] = True
                result["reason"] = f"ANCLA TP1 LONG Cancelado: EMA3 {mode} retomó fuerza durante 2 velas consecutivas."
            elif is_tp1_placed:
                result["reason"] = f"ANCLA TP1 LONG Pendiente en broker a {tp1_target:.4f}."
        else:
            # SHORT
            is_exhaustion = slope_current >= 0  # EMA3 4H plana o ascendente
            is_momentum_resumed = (slope_current < 0) and (slope_prev < 0)  # 2 velas 4H bajistas consecutivas

            if is_exhaustion and not is_tp1_placed:
                result["should_place_tp1"] = True
                result["reason"] = f"ANCLA TP1 SHORT Activado: Agotamiento EMA3 {mode} (slope={slope_current:.6f}>=0). Orden LIMIT a {tp1_target:.4f} ({result['volume_pct']:.0f}%)."
            elif is_tp1_placed and is_momentum_resumed:
                result["cancel_pending_tp1"] = True
                result["reason"] = f"ANCLA TP1 SHORT Cancelado: EMA3 {mode} retomó fuerza bajista durante 2 velas consecutivas."
            elif is_tp1_placed:
                result["reason"] = f"ANCLA TP1 SHORT Pendiente en broker a {tp1_target:.4f}."

        return result

    def calculate_tp2_stage(
        self,
        position: Dict[str, Any],
        df_macro: pd.DataFrame,  # 1D o 4H
        mode: str = "swing",
    ) -> Dict[str, Any]:
        """
        Calcula la Etapa 2 del Take Profit (50% remanente en Bollinger Macro sin condición de momentum).
        Solo se activa tras el fill confirmado de TP1.
        """
        result = {
            "should_place_tp2": False,
            "tp2_price": 0.0,
            "volume_pct": 100.0,  # 100% del remanente restante
            "reason": "",
        }

        # Solo se coloca si TP1 ya fue ejecutado y TP2 aún no
        if not position.get("ancla_tp1_fired", False):
            result["reason"] = "TP2 en espera: TP1 aún no se ha ejecutado."
            return result

        if position.get("ancla_tp2_fired", False):
            result["reason"] = "TP2 ya fue ejecutado previamente."
            return result

        if df_macro is None or len(df_macro) < 20:
            result["reason"] = "Datos insuficientes de Bollinger Macro para TP2."
            return result

        side = str(position.get("side", "long")).lower()
        is_long = side in ("long", "buy")

        # Bandas de Bollinger Macro (1D o 4H)
        close_series = pd.to_numeric(df_macro["close"], errors="coerce").dropna()
        basis = float(close_series.rolling(20).mean().iloc[-1])
        std = float(close_series.rolling(20).std().iloc[-1])
        bb_upper = basis + (2.0 * std)
        bb_lower = basis - (2.0 * std)

        if is_long:
            # TP2 = Upper_BB - 10% * (Upper_BB - Basis)
            tp2_target = bb_upper - (self.tp2_buffer_pct * (bb_upper - basis))
            result["tp2_price"] = tp2_target
            result["should_place_tp2"] = True
            result["reason"] = f"ANCLA TP2 LONG Objetivo Bollinger {mode}: LIMIT a {tp2_target:.4f} para cerrar el 100% remanente."
        else:
            # SHORT: TP2 = Lower_BB + 10% * (Basis - Lower_BB)
            tp2_target = bb_lower + (self.tp2_buffer_pct * (basis - bb_lower))
            result["tp2_price"] = tp2_target
            result["should_place_tp2"] = True
            result["reason"] = f"ANCLA TP2 SHORT Objetivo Bollinger {mode}: LIMIT a {tp2_target:.4f} para cerrar el 100% remanente."

        return result

    def calculate_breakeven_sl_post_tp1(
        self,
        position: Dict[str, Any],
        is_forex: bool = False,
    ) -> float:
        """
        Calcula el Stop Loss protector de Breakeven para el 50% remanente tras ejecutar TP1.
        Precio de Entrada + Buffer de seguridad (3 pips en Forex o 0.15% en Crypto).
        """
        entry_price = float(position.get("entry_price", 0.0))
        side = str(position.get("side", "long")).lower()
        is_long = side in ("long", "buy")

        if entry_price <= 0:
            return 0.0

        if is_forex:
            pip_unit = 0.01 if "JPY" in str(position.get("symbol", "")).upper() else 0.0001
            buffer = 3.0 * pip_unit
        else:
            buffer = entry_price * 0.0015  # +0.15% para cubrir fees

        if is_long:
            return entry_price + buffer
        else:
            return entry_price - buffer

    # ════════════════════════════════════════════════════════════════════════
    # MÉTODOS AUXILIARES DE CÁLCULO DE NIVELES Y VOLATILIDAD
    # ════════════════════════════════════════════════════════════════════════

    def _get_current_fib_zone_bounds(
        self,
        price: float,
        fib_levels: Dict[str, Any],
        is_long: bool,
    ) -> Dict[str, Any]:
        """
        Extrae los límites inferior y superior de la zona Fibonacci actual del precio.
        """
        lower_2 = float(fib_levels.get("lower_2", price * 0.98))
        lower_1 = float(fib_levels.get("lower_1", price * 0.99))
        basis = float(fib_levels.get("basis", price))
        upper_1 = float(fib_levels.get("upper_1", price * 1.01))
        upper_2 = float(fib_levels.get("upper_2", price * 1.02))

        # Determinar zona
        if price >= upper_2:
            return {"lower_bound": upper_2, "upper_bound": upper_2 * 1.015, "zone_index": 2}
        elif price >= upper_1:
            return {"lower_bound": upper_1, "upper_bound": upper_2, "zone_index": 1}
        elif price >= basis:
            return {"lower_bound": basis, "upper_bound": upper_1, "zone_index": 0}
        elif price >= lower_1:
            return {"lower_bound": lower_1, "upper_bound": basis, "zone_index": -1}
        elif price >= lower_2:
            return {"lower_bound": lower_2, "upper_bound": lower_1, "zone_index": -2}
        else:
            return {"lower_bound": lower_2 * 0.985, "upper_bound": lower_2, "zone_index": -3}

    def _get_macro_fib_bounds(
        self,
        df_macro: pd.DataFrame,
        current_price: float,
        is_long: bool,
    ) -> Dict[str, float]:
        """
        Calcula los límites Fibonacci en el timeframe Macro (1D o 4H).
        """
        last_row = df_macro.iloc[-1]
        upper_2 = float(last_row.get("upper_2", current_price * 1.04))
        upper_1 = float(last_row.get("upper_1", current_price * 1.02))
        lower_1 = float(last_row.get("lower_1", current_price * 0.98))
        lower_2 = float(last_row.get("lower_2", current_price * 0.96))

        if is_long:
            return {"upper": upper_2, "lower": upper_1}
        else:
            return {"upper": lower_1, "lower": lower_2}

    def _get_atr_15m(self, df_15m: pd.DataFrame) -> float:
        """Obtiene el ATR de 14 periodos en 15M."""
        if "atr" in df_15m.columns:
            return float(df_15m["atr"].iloc[-1])
        # Cálculo manual si no está en columnas
        high = pd.to_numeric(df_15m["high"], errors="coerce")
        low = pd.to_numeric(df_15m["low"], errors="coerce")
        close = pd.to_numeric(df_15m["close"], errors="coerce")
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
        atr = tr.rolling(14).mean().iloc[-1]
        return float(atr) if pd.notna(atr) else float(close.iloc[-1] * 0.005)

    def _check_high_volatility(self, df_15m: pd.DataFrame) -> bool:
        """Verifica si el ATR actual supera 2.0x su media móvil (noticias macro)."""
        if len(df_15m) < 35:
            return False
        high = pd.to_numeric(df_15m["high"], errors="coerce")
        low = pd.to_numeric(df_15m["low"], errors="coerce")
        close = pd.to_numeric(df_15m["close"], errors="coerce")
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
        atr_series = tr.rolling(14).mean()
        atr_curr = atr_series.iloc[-1]
        atr_sma = atr_series.rolling(20).mean().iloc[-1]
        return bool(pd.notna(atr_curr) and pd.notna(atr_sma) and (atr_curr > 2.0 * atr_sma))
