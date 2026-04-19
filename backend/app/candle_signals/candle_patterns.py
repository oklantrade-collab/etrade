"""
ANTIGRAVITY · Candle Pattern Detector v1.0
26 Patrones de Velas Japonesas — Detección algorítmica precisa.

Patrones por tipo:
  BUY  (9): 5, 7, 10, 11, 13, 17, 23, 26
  SELL (9): 4, 9, 12, 14, 18, 22, 24, 25
  HOLD (8): 1, 2, 3, 6, 8, 15, 16, 19, 20, 21
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CandleOHLC:
    """Represents a single OHLCV candle."""
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass
class PatternResult:
    """Result of pattern detection."""
    pattern_id: int
    pattern_name: str
    signal: str          # "Alcista" | "Bajista" | "Neutral" | "Reversión Alcista" | "Reversión Bajista"
    action: str          # "BUY" | "SELL" | "HOLD"
    confidence: float    # 0-100 base confidence from pattern purity
    candles_used: int    # 1, 2, or 3


# ─── PATTERN CATALOG ─────────────────────────────────────────────────────────
PATTERN_CATALOG = {
    1:  {"name": "Marubozu Alcista",       "signal": "Alcista",             "action": "BUY",   "candles": 1},
    2:  {"name": "Marubozu Bajista",       "signal": "Bajista",             "action": "SELL",  "candles": 1},
    3:  {"name": "Doji Estándar",          "signal": "Neutral",             "action": "HOLD",  "candles": 1},
    4:  {"name": "Doji Lápida",            "signal": "Reversión Bajista",   "action": "SELL",  "candles": 1},
    5:  {"name": "Doji Libélula",          "signal": "Reversión Alcista",   "action": "BUY",   "candles": 1},
    6:  {"name": "Doji Piernas Largas",    "signal": "Neutral",             "action": "HOLD",  "candles": 1},
    7:  {"name": "Hammer",                 "signal": "Reversión Alcista",   "action": "BUY",   "candles": 1},
    8:  {"name": "Hanging Man",            "signal": "Reversión Bajista",   "action": "SELL",  "candles": 1},
    9:  {"name": "Shooting Star",          "signal": "Reversión Bajista",   "action": "SELL",  "candles": 1},
    10: {"name": "Inverted Hammer",        "signal": "Reversión Alcista",   "action": "BUY",   "candles": 1},
    11: {"name": "Engulfing Alcista",      "signal": "Reversión Alcista",   "action": "BUY",   "candles": 2},
    12: {"name": "Engulfing Bajista",      "signal": "Reversión Bajista",   "action": "SELL",  "candles": 2},
    13: {"name": "Morning Star",           "signal": "Reversión Alcista",   "action": "BUY",   "candles": 3},
    14: {"name": "Evening Star",           "signal": "Reversión Bajista",   "action": "SELL",  "candles": 3},
    15: {"name": "Spinning Top Alcista",   "signal": "Neutral",             "action": "HOLD",  "candles": 1},
    16: {"name": "Spinning Top Bajista",   "signal": "Neutral",             "action": "HOLD",  "candles": 1},
    17: {"name": "Piercing Line",          "signal": "Reversión Alcista",   "action": "BUY",   "candles": 2},
    18: {"name": "Dark Cloud Cover",       "signal": "Reversión Bajista",   "action": "SELL",  "candles": 2},
    19: {"name": "Three White Soldiers",   "signal": "Alcista",             "action": "BUY",   "candles": 3},
    20: {"name": "Three Black Crows",      "signal": "Bajista",             "action": "SELL",  "candles": 3},
    21: {"name": "Harami Alcista",         "signal": "Reversión Alcista",   "action": "BUY",   "candles": 2},
    22: {"name": "Harami Bajista",         "signal": "Reversión Bajista",   "action": "SELL",  "candles": 2},
    23: {"name": "Belt Hold Alcista",      "signal": "Reversión Alcista",   "action": "BUY",   "candles": 1},
    24: {"name": "Belt Hold Bajista",      "signal": "Reversión Bajista",   "action": "SELL",  "candles": 1},
    25: {"name": "Tweezer Top",            "signal": "Reversión Bajista",   "action": "SELL",  "candles": 2},
    26: {"name": "Tweezer Bottom",         "signal": "Reversión Alcista",   "action": "BUY",   "candles": 2},
}


def _approx(a: float, b: float, epsilon: float) -> bool:
    """Check if two values are approximately equal within epsilon."""
    return abs(a - b) <= epsilon


class CandlePatternDetector:
    """
    Detects all 26 candle patterns from OHLCV data.
    
    Usage:
        detector = CandlePatternDetector(market="crypto")
        result = detector.evaluate(current_candle, history=[prev1, prev2, ...])
    """

    # ATR-based epsilon factors per market
    EPSILON_FACTORS = {
        "crypto": 0.12,
        "forex":  0.08,
        "stocks": 0.10,
    }

    def __init__(self, market: str = "crypto"):
        self.market = market.lower()
        self.epsilon_factor = self.EPSILON_FACTORS.get(self.market, 0.10)

    def _calc_epsilon(self, candle: CandleOHLC, atr_14: Optional[float] = None) -> float:
        """Calculate epsilon tolerance — ATR-based if available, else range-based."""
        if atr_14 and atr_14 > 0:
            return atr_14 * self.epsilon_factor
        rng = candle.range
        return rng * 0.05 if rng > 0 else 0.0001

    def _calc_epsilon_doji(self, candle: CandleOHLC, atr_14: Optional[float] = None) -> float:
        """Tighter epsilon for Doji detection (3% of range)."""
        if atr_14 and atr_14 > 0:
            return atr_14 * self.epsilon_factor * 0.6
        rng = candle.range
        return rng * 0.03 if rng > 0 else 0.0001

    def evaluate(
        self,
        candle: CandleOHLC,
        history: list[CandleOHLC] = None,
        atr_14: Optional[float] = None,
        volume_sma20: Optional[float] = None,
    ) -> PatternResult:
        """
        Evaluate the current candle (+ history) against all 26 patterns.
        Returns the highest-priority pattern detected.
        
        Priority: 3-candle patterns > 2-candle patterns > 1-candle patterns
        Within same candle count: BUY/SELL > HOLD
        """
        if history is None:
            history = []

        eps = self._calc_epsilon(candle, atr_14)
        eps_doji = self._calc_epsilon_doji(candle, atr_14)

        results: list[PatternResult] = []

        # ── 3-CANDLE PATTERNS (highest priority) ──
        if len(history) >= 2:
            prev = history[-1]
            prev2 = history[-2]
            results.extend(self._check_3_candle_patterns(candle, prev, prev2, eps))

        # ── 2-CANDLE PATTERNS ──
        if len(history) >= 1:
            prev = history[-1]
            results.extend(self._check_2_candle_patterns(candle, prev, eps))

        # ── 1-CANDLE PATTERNS ──
        results.extend(self._check_1_candle_patterns(candle, history, eps, eps_doji))

        if not results:
            return PatternResult(
                pattern_id=0,
                pattern_name="No Pattern",
                signal="Neutral",
                action="HOLD",
                confidence=0.0,
                candles_used=0,
            )

        # Apply volume confirmation bonus
        if volume_sma20 and volume_sma20 > 0 and candle.volume > 0:
            vol_ratio = candle.volume / volume_sma20
            for r in results:
                if vol_ratio >= 1.5:
                    r.confidence = min(100.0, r.confidence + 15.0)
                elif vol_ratio >= 1.2:
                    r.confidence = min(100.0, r.confidence + 8.0)

        # Sort: BUY/SELL first, then by candles_used desc, then confidence desc
        def sort_key(r: PatternResult):
            action_priority = 0 if r.action in ("BUY", "SELL") else 1
            return (action_priority, -r.candles_used, -r.confidence)

        results.sort(key=sort_key)
        return results[0]

    # ── 1-CANDLE PATTERNS ─────────────────────────────────────────────────────

    def _check_1_candle_patterns(
        self, c: CandleOHLC, history: list[CandleOHLC],
        eps: float, eps_doji: float
    ) -> list[PatternResult]:
        results = []
        rng = c.range
        if rng <= 0:
            return results

        body = c.body
        uw = c.upper_wick
        lw = c.lower_wick

        # ID 1 — Marubozu Alcista → BUY 🟢
        if _approx(c.open, c.low, eps) and _approx(c.close, c.high, eps) and c.is_bullish:
            purity = max(0, 100 - (uw + lw) / rng * 200) if rng > 0 else 70
            results.append(PatternResult(1, "Marubozu Alcista", "Alcista", "BUY", min(95, purity), 1))

        # ID 2 — Marubozu Bajista → SELL 🔴
        if _approx(c.open, c.high, eps) and _approx(c.close, c.low, eps) and c.is_bearish:
            purity = max(0, 100 - (uw + lw) / rng * 200) if rng > 0 else 70
            results.append(PatternResult(2, "Marubozu Bajista", "Bajista", "SELL", min(95, purity), 1))

        # ID 3 — Doji Estándar → HOLD
        if body <= eps_doji and uw > eps and lw > eps:
            results.append(PatternResult(3, "Doji Estándar", "Neutral", "HOLD", 60.0, 1))

        # ID 4 — Doji Lápida → SELL 🔴
        if body <= eps_doji and lw <= eps and uw > rng * 0.60:
            conf = 70.0 + min(20, (uw / rng - 0.60) * 100)
            results.append(PatternResult(4, "Doji Lápida", "Reversión Bajista", "SELL", conf, 1))

        # ID 5 — Doji Libélula → BUY 🟢
        if body <= eps_doji and uw <= eps and lw > rng * 0.60:
            conf = 70.0 + min(20, (lw / rng - 0.60) * 100)
            results.append(PatternResult(5, "Doji Libélula", "Reversión Alcista", "BUY", conf, 1))

        # ID 6 — Doji Piernas Largas → HOLD
        if body <= eps_doji and uw > rng * 0.30 and lw > rng * 0.30:
            results.append(PatternResult(6, "Doji Piernas Largas", "Neutral", "HOLD", 55.0, 1))

        # ID 7 — Hammer → BUY 🟢
        if body > 0 and lw >= body * 2 and uw <= body * 0.30 and body < rng * 0.40:
            conf = 72.0 + min(18, (lw / body - 2) * 10)
            results.append(PatternResult(7, "Hammer", "Reversión Alcista", "BUY", conf, 1))

        # ID 8 — Hanging Man → SELL 🔴
        if body > 0 and lw >= body * 2 and uw <= body * 0.30:
            if len(history) >= 3 and all(h.close > h.open for h in history[-3:]):
                results.append(PatternResult(8, "Hanging Man", "Reversión Bajista", "SELL", 60.0, 1))

        # ID 9 — Shooting Star → SELL 🔴
        if body > 0 and uw >= body * 2 and lw <= body * 0.30 and body < rng * 0.40:
            conf = 72.0 + min(18, (uw / body - 2) * 10)
            results.append(PatternResult(9, "Shooting Star", "Reversión Bajista", "SELL", conf, 1))

        # ID 10 — Inverted Hammer → BUY 🟢
        if body > 0 and uw >= body * 2 and lw <= body * 0.30 and c.is_bullish:
            # Context: previous bearish trend
            if len(history) >= 3 and history[-1].close < history[-3].close:
                conf = 68.0 + min(12, (uw / body - 2) * 8)
                results.append(PatternResult(10, "Inverted Hammer", "Reversión Alcista", "BUY", conf, 1))

        # ID 15 — Spinning Top Alcista → HOLD
        if body < rng * 0.30 and uw > rng * 0.25 and lw > rng * 0.25 and c.is_bullish:
            results.append(PatternResult(15, "Spinning Top Alcista", "Neutral", "HOLD", 45.0, 1))

        # ID 16 — Spinning Top Bajista → HOLD
        if body < rng * 0.30 and uw > rng * 0.25 and lw > rng * 0.25 and c.is_bearish:
            results.append(PatternResult(16, "Spinning Top Bajista", "Neutral", "HOLD", 45.0, 1))

        # ID 23 — Belt Hold Alcista → BUY 🟢
        if _approx(c.open, c.low, eps) and c.is_bullish and body > rng * 0.70:
            conf = 74.0 + min(16, (body / rng - 0.70) * 100)
            results.append(PatternResult(23, "Belt Hold Alcista", "Reversión Alcista", "BUY", conf, 1))

        # ID 24 — Belt Hold Bajista → SELL 🔴
        if _approx(c.open, c.high, eps) and c.is_bearish and body > rng * 0.70:
            conf = 74.0 + min(16, (body / rng - 0.70) * 100)
            results.append(PatternResult(24, "Belt Hold Bajista", "Reversión Bajista", "SELL", conf, 1))

        return results

    # ── 2-CANDLE PATTERNS ─────────────────────────────────────────────────────

    def _check_2_candle_patterns(
        self, c: CandleOHLC, prev: CandleOHLC, eps: float
    ) -> list[PatternResult]:
        results = []

        # ID 11 — Engulfing Alcista → BUY 🟢
        if prev.is_bearish and c.is_bullish:
            if c.open < prev.close and c.close > prev.open:
                # Measure how much the engulfing exceeds the previous body
                coverage = c.body / prev.body if prev.body > 0 else 1.5
                conf = 75.0 + min(15, (coverage - 1.0) * 30)
                results.append(PatternResult(11, "Engulfing Alcista", "Reversión Alcista", "BUY", conf, 2))

        # ID 12 — Engulfing Bajista → SELL 🔴
        if prev.is_bullish and c.is_bearish:
            if c.open > prev.close and c.close < prev.open:
                coverage = c.body / prev.body if prev.body > 0 else 1.5
                conf = 75.0 + min(15, (coverage - 1.0) * 30)
                results.append(PatternResult(12, "Engulfing Bajista", "Reversión Bajista", "SELL", conf, 2))

        # ID 17 — Piercing Line → BUY 🟢
        if prev.is_bearish and c.is_bullish:
            mid_prev = (prev.open + prev.close) / 2
            if c.open < prev.close and c.close > mid_prev and c.close < prev.open:
                penetration = (c.close - prev.close) / prev.body if prev.body > 0 else 0.5
                conf = 70.0 + min(20, penetration * 30)
                results.append(PatternResult(17, "Piercing Line", "Reversión Alcista", "BUY", conf, 2))

        # ID 18 — Dark Cloud Cover → SELL 🔴
        if prev.is_bullish and c.is_bearish:
            mid_prev = (prev.open + prev.close) / 2
            if c.open > prev.close and c.close < mid_prev and c.close > prev.open:
                penetration = (prev.close - c.close) / prev.body if prev.body > 0 else 0.5
                conf = 70.0 + min(20, penetration * 30)
                results.append(PatternResult(18, "Dark Cloud Cover", "Reversión Bajista", "SELL", conf, 2))

        # ID 21 — Harami Alcista → BUY 🟢
        if prev.is_bearish and c.is_bullish:
            if c.open > prev.close and c.open < prev.open and c.close > prev.close and c.close < prev.open:
                results.append(PatternResult(21, "Harami Alcista", "Reversión Alcista", "BUY", 55.0, 2))

        # ID 22 — Harami Bajista → SELL 🔴
        if prev.is_bullish and c.is_bearish:
            if c.open < prev.close and c.open > prev.open and c.close < prev.close and c.close > prev.open:
                results.append(PatternResult(22, "Harami Bajista", "Reversión Bajista", "SELL", 65.0, 2))

        # ID 25 — Tweezer Top → SELL 🔴
        if abs(c.high - prev.high) <= eps and prev.is_bullish and c.is_bearish:
            results.append(PatternResult(25, "Tweezer Top", "Reversión Bajista", "SELL", 68.0, 2))

        # ID 26 — Tweezer Bottom → BUY 🟢
        if abs(c.low - prev.low) <= eps and prev.is_bearish and c.is_bullish:
            results.append(PatternResult(26, "Tweezer Bottom", "Reversión Alcista", "BUY", 68.0, 2))

        return results

    # ── 3-CANDLE PATTERNS ─────────────────────────────────────────────────────

    def _check_3_candle_patterns(
        self, c: CandleOHLC, prev: CandleOHLC, prev2: CandleOHLC, eps: float
    ) -> list[PatternResult]:
        results = []
        # Total range across the 3 candles
        total_high = max(c.high, prev.high, prev2.high)
        total_low = min(c.low, prev.low, prev2.low)
        rango_total = total_high - total_low if total_high != total_low else 0.0001

        # ID 13 — Morning Star → BUY 🟢
        if (prev2.is_bearish
            and prev2.body > rango_total * 0.30
            and prev.body < prev2.body * 0.50
            and c.is_bullish
            and c.body > rango_total * 0.30
            and c.close > (prev2.open + prev2.close) / 2):
            conf = 80.0 + min(10, (c.body / rango_total - 0.30) * 50)
            results.append(PatternResult(13, "Morning Star", "Reversión Alcista", "BUY", conf, 3))

        # ID 14 — Evening Star → SELL 🔴
        if (prev2.is_bullish
            and prev2.body > rango_total * 0.30
            and prev.body < prev2.body * 0.50
            and c.is_bearish
            and c.body > rango_total * 0.30
            and c.close < (prev2.open + prev2.close) / 2):
            conf = 80.0 + min(10, (c.body / rango_total - 0.30) * 50)
            results.append(PatternResult(14, "Evening Star", "Reversión Bajista", "SELL", conf, 3))

        # ID 19 — Three White Soldiers → BUY 🟢
        if (prev2.is_bullish and prev.is_bullish and c.is_bullish
            and prev.open > prev2.open and prev.open < prev2.close
            and c.open > prev.open and c.open < prev.close
            and c.close > prev.close and prev.close > prev2.close):
            results.append(PatternResult(19, "Three White Soldiers", "Alcista", "BUY", 70.0, 3))

        # ID 20 — Three Black Crows → SELL 🔴
        if (prev2.is_bearish and prev.is_bearish and c.is_bearish
            and prev.open < prev2.open and prev.open > prev2.close
            and c.open < prev.open and c.open > prev.close
            and c.close < prev.close and prev.close < prev2.close):
            results.append(PatternResult(20, "Three Black Crows", "Bajista", "SELL", 70.0, 3))

        return results
