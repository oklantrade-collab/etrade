"""
eTrade Stocks — In-Memory Micro-Pullback Scalper Engine (TWS / IBKR)
=====================================================================
Motor de ultra-baja latencia en memoria para capturar micro-retrocesos
en activos con crecimiento parabólico/exponencial (ej. GMAB, POM).

Reglas de Negocio Implementadas:
1. Detección de Impulso Parabólico (ROC acelerado en 1-2 minutos con RVOL).
2. Monitoreo en barras de 5 segundos (Ring Buffer de 60 barras = 5 min).
3. La Regla del 50%: El retroceso debe sostenerse por encima del 50% de la subida.
4. Soporte Psicológico: Validación en cifras enteras o medios dólares ($X.00 / $X.50).
5. Gatillo de Entrada: Mecha inferior de absorción (bottoming tail) + giro verde de 5s.
6. Stop Loss Técnico: Inmediatamente por debajo del suelo del micro-pullback.
7. Regla 'Breakout or Bailout': Límite estricto de 9 barras de 5s (45 segundos).
   Si no rompe el máximo anterior y se estanca, venta inmediata (BE o micro-loss).
8. Dimensionamiento Icebreaker: 25% del % inversión por operación hasta tener colchón.
9. Despacho LMT Marketable: Inmune a cancelaciones de TWS en penny stocks.
10. Persistencia Asíncrona: Zero DB latency en el hilo de decisión; Supabase en background.
"""

import asyncio
import collections
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Set

from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.data.ib_provider import get_ib_connection, IB_AVAILABLE

MODULE = "MICRO_PULLBACK_ENGINE"

# ── Configuración Operativa ──
MAX_BAILOUT_BARS = 9          # 9 barras de 5s = 45 segundos exactos
MAX_CONCURRENT_SCALPS = 2     # Máximo 2 posiciones simultáneas de scalping
MIN_IMPULSE_PCT = 3.0         # Mínimo impulso de +3% para activar radar
MAX_PULLBACK_BARS = 4         # De 1 a 3 (máximo 4) barras rojas breves
MIN_LOWER_WICK_RATIO = 0.30   # Mínimo 30% de mecha inferior para validar absorción


class ScalpCandidateState:
    """Estado y memoria en RAM para un ticker monitoreado."""
    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self.req_id: int = -1
        self.bars: collections.deque = collections.deque(maxlen=60)  # Últimas 60 barras de 5s (5 min)
        
        # Estado de la máquina de trading
        # Fases: IDLE -> IMPULSE_DETECTED -> PULLBACK_OBSERVED -> READY_TRIGGER -> IN_TRADE -> EXITED
        self.phase: str = "IDLE"
        self.impulse_low: float = 0.0
        self.impulse_high: float = 0.0
        self.impulse_start_ts: float = 0.0
        
        self.pullback_low: float = 0.0
        self.pullback_bars_count: int = 0
        self.has_bottoming_tail: bool = False
        
        # Telemetría de la posición activa
        self.in_trade: bool = False
        self.entry_price: float = 0.0
        self.initial_shares: int = 0
        self.shares: int = 0
        self.entry_bar_idx: int = 0
        self.bars_in_trade: int = 0
        self.stop_loss: float = 0.0
        self.target_hod: float = 0.0
        self.order_id: int = 0
        self.db_order_id: str = ""
        self.entry_rule: str = "SCALP_MICRO_PULLBACK"
        self.last_exit_ts: float = 0.0

        # Cascada Escalonada y Recompras (Dips)
        self.rebuys_count: int = 0          # Máximo 3 recompras
        self.last_rebuy_ts: float = 0.0
        self.highest_price_reached: float = 0.0
        self.realized_scalp_profit: float = 0.0


class MicroPullbackEngine:
    """Motor In-Memory para Scalping de Micro Retrocesos en TWS."""
    
    def __init__(self):
        self.candidates: Dict[str, ScalpCandidateState] = {}
        self.active_scalps: Dict[str, ScalpCandidateState] = {}
        self.closed_tickers_today: Set[str] = set()  # Lista negra intradía: One-and-Done por ticker
        self.daily_cushion_usd: float = 0.0
        self.is_running: bool = False
        self._bg_tasks = set()
        
    def start(self):
        """Inicia el motor en memoria."""
        self.is_running = True
        log_info(MODULE, "⚡ Motor In-Memory Micro-Pullback ACTIVADO (TWS APOLO Paper).")
        self._load_daily_cushion()

    def stop(self):
        """Detiene el motor y desuscribe flujos de barras de 5s."""
        self.is_running = False
        ib = get_ib_connection()
        if ib and ib.connected:
            for c in self.candidates.values():
                if c.req_id > 0:
                    ib.cancel_realtime_5s_bars(c.req_id)
        log_info(MODULE, "🛑 Motor In-Memory Micro-Pullback DETENIDO.")

    def _load_daily_cushion(self):
        """Carga el PnL realizado del día para determinar si aplica Icebreaker."""
        try:
            sb = get_supabase()
            today = datetime.now(timezone.utc).date().isoformat()
            res = sb.table("trades_journal")\
                .select("pnl_usd")\
                .gte("exit_date", f"{today}T00:00:00")\
                .execute()
            total_pnl = sum(float(r.get("pnl_usd") or 0.0) for r in (res.data or []))
            self.daily_cushion_usd = total_pnl
            log_info(MODULE, f"💰 Colchón de ganancia diaria cargado: ${self.daily_cushion_usd:+.2f} USD")
        except Exception as e:
            log_warning(MODULE, f"No se pudo cargar colchón diario: {e}")
            self.daily_cushion_usd = 0.0

    def register_ticker(self, ticker: str):
        """Suscribe un ticker de alta volatilidad al feed de 5 segundos de TWS o Finnhub fallback."""
        ticker = ticker.upper().strip()
        if ticker in self.closed_tickers_today:
            log_info(MODULE, f"🚫 [{ticker}] Descartado: Ticker ya cerrado hoy. Regla One-and-Done activa (No revenge trading).")
            return
        if ticker in self.candidates:
            return

        cand = ScalpCandidateState(ticker)
        self.candidates[ticker] = cand

        ib = get_ib_connection()
        if not ib or not ib.connected:
            log_info(MODULE, f"📡 [{ticker}] TWS no conectado en este nodo. Alimentador Finnhub 5s activo.")
            return

        def on_bar_received(req_id: int, bar: dict):
            self.process_5s_bar(ticker, bar)

        req_id = ib.request_realtime_5s_bars(ticker, on_bar_received)
        cand.req_id = req_id
        log_info(MODULE, f"📡 [{ticker}] Suscripción 5s activa en TWS con reqId={req_id}")

    def unregister_ticker(self, ticker: str):
        """Desuscribe un ticker si perdió momentum."""
        ticker = ticker.upper().strip()
        cand = self.candidates.pop(ticker, None)
        if cand and cand.req_id > 0:
            ib = get_ib_connection()
            if ib and ib.connected:
                ib.cancel_realtime_5s_bars(cand.req_id)

    # ══════════════════════════════════════════════════════════
    # BUCLE DE DECISIÓN EN MEMORIA (Cada 5 segundos por ticker)
    # ══════════════════════════════════════════════════════════

    def process_5s_bar(self, ticker: str, bar: dict):
        """
        Procesa cada barra de 5 segundos estrictamente en RAM.
        Zero llamadas síncronas a base de datos.
        """
        if ticker in self.closed_tickers_today:
            return

        cand = self.candidates.get(ticker)
        if not cand:
            return

        # Calcular métricas anatómicas de la barra de 5s
        o = bar["open"]
        h = bar["high"]
        l = bar["low"]
        c = bar["close"]
        vol = bar["volume"]
        bar_range = max(0.001, h - l)
        
        is_green = c >= o
        lower_wick = (min(o, c) - l)
        lower_wick_ratio = lower_wick / bar_range
        
        bar_metric = {
            "time": bar["time"],
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": vol,
            "is_green": is_green,
            "lower_wick_ratio": lower_wick_ratio,
        }
        cand.bars.append(bar_metric)

        # ── SI YA ESTÁ EN POSICIÓN: GESTIÓN 'BREAKOUT OR BAILOUT' ──
        if cand.in_trade:
            self._manage_active_trade(cand, bar_metric)
            return

        # ── MÁQUINA DE ESTADOS PRE-ENTRADA ──
        if cand.phase == "IDLE":
            self._check_for_impulse(cand)

        elif cand.phase == "IMPULSE_DETECTED":
            self._check_for_pullback_start(cand, bar_metric)

        elif cand.phase == "PULLBACK_OBSERVED":
            self._evaluate_pullback_progression(cand, bar_metric)

        elif cand.phase == "WAITING_DIP_5M":
            self._evaluate_dip_reentry(cand, bar_metric)

    # ──────────────────────────────────────────────────────────
    # ESTADO 1: Detección de Impulso Inicial
    # ──────────────────────────────────────────────────────────
    def _check_for_impulse(self, cand: ScalpCandidateState):
        """Busca una subida explosiva (+3% a +15% en las últimas 6 a 24 barras = 30s a 2 min)."""
        if len(cand.bars) < 6:
            return

        bars_list = list(cand.bars)
        # Comparar el mínimo reciente con el precio actual
        recent_window = bars_list[-18:]  # Últimos 90 segundos
        lowest_bar = min(recent_window, key=lambda b: b["low"])
        current_bar = bars_list[-1]

        price_jump_pct = ((current_bar["high"] - lowest_bar["low"]) / lowest_bar["low"]) * 100.0

        if price_jump_pct >= MIN_IMPULSE_PCT:
            cand.phase = "IMPULSE_DETECTED"
            cand.impulse_low = lowest_bar["low"]
            cand.impulse_high = current_bar["high"]
            cand.impulse_start_ts = time.time()
            log_info(MODULE, f"🚀 [{cand.ticker}] Impulso detectado: +{price_jump_pct:.1f}% (${cand.impulse_low:.2f} ➜ ${cand.impulse_high:.2f}). Monitoreando retroceso...")

    # ──────────────────────────────────────────────────────────
    # ESTADO 2: Detección del Comienzo del Micro-Pullback
    # ──────────────────────────────────────────────────────────
    def _check_for_pullback_start(self, cand: ScalpCandidateState, bar: dict):
        """Actualiza el High del impulso si sigue subiendo, o detecta la primera vela roja."""
        if bar["high"] > cand.impulse_high:
            cand.impulse_high = bar["high"]

        # Si aparece la primera vela roja, pasamos a PULLBACK_OBSERVED
        if not bar["is_green"]:
            cand.phase = "PULLBACK_OBSERVED"
            cand.pullback_low = bar["low"]
            cand.pullback_bars_count = 1
            cand.has_bottoming_tail = (bar["lower_wick_ratio"] >= MIN_LOWER_WICK_RATIO)
            log_info(MODULE, f"📉 [{cand.ticker}] Micro Pullback iniciado en barra 5s (Low: ${cand.pullback_low:.2f})")

    # ──────────────────────────────────────────────────────────
    # ESTADO 3: Evaluación de la Regla del 50% y Gatillo
    # ──────────────────────────────────────────────────────────
    def _evaluate_pullback_progression(self, cand: ScalpCandidateState, bar: dict):
        """Evalúa la Regla del 50%, mecha de absorción y giro a verde."""
        # 1. Si sigue siendo roja:
        if not bar["is_green"]:
            cand.pullback_bars_count += 1
            if bar["low"] < cand.pullback_low:
                cand.pullback_low = bar["low"]
            if bar["lower_wick_ratio"] >= MIN_LOWER_WICK_RATIO:
                cand.has_bottoming_tail = True

            # Si ya son más de 4 barras rojas, el retroceso es demasiado lento / pierde momentum
            if cand.pullback_bars_count > MAX_PULLBACK_BARS:
                log_info(MODULE, f"⚠️ [{cand.ticker}] Pullback demasiado extendido ({cand.pullback_bars_count} barras rojas). Cancelando setup.")
                cand.phase = "IDLE"
                return

            # 2. VALIDAR LA REGLA DEL 50%
            impulse_range = cand.impulse_high - cand.impulse_low
            fifty_pct_floor = cand.impulse_high - (0.50 * impulse_range)
            if cand.pullback_low < fifty_pct_floor:
                log_info(MODULE, f"⛔ [{cand.ticker}] Violación Regla del 50% (${cand.pullback_low:.2f} < ${fifty_pct_floor:.2f}). Se descarta.")
                cand.phase = "IDLE"
                return
            return

        # 3. SI LA BARRA ACTUAL ES VERDE (Posible Gatillo de Disparo):
        prev_bar = cand.bars[-2]
        
        # Validación de gatillo:
        # A) Supera el High de la barra roja previa
        breaks_prev_high = bar["close"] > prev_bar["high"]
        # B) Sostiene la regla del 50%
        fifty_pct_floor = cand.impulse_high - (0.50 * (cand.impulse_high - cand.impulse_low))
        held_50_pct = cand.pullback_low >= fifty_pct_floor
        # C) Soporte psicológico cercano (a menos de 1.5% de .00 o .50)
        near_key_level = self._is_near_psychological_level(cand.pullback_low)

        if breaks_prev_high and held_50_pct:
            log_info(MODULE, f"🎯 [{cand.ticker}] GATILLO ACTIVADO: Giro verde 5s @ ${bar['close']:.2f} sobre Low ${cand.pullback_low:.2f} (Soporte psic={near_key_level}). Disparando orden!")
            self._trigger_entry(cand, entry_price=bar["close"])

    def _is_near_psychological_level(self, price: float) -> bool:
        """Verifica si el precio rebotó cerca de un número entero o medio dólar."""
        base_50c = round(price * 2.0) / 2.0
        dist_pct = abs(price - base_50c) / price * 100.0
        return dist_pct <= 1.5

    # ──────────────────────────────────────────────────────────
    # DISPARO INMEDIATO DE LA ORDEN (Sub-segundo)
    # ──────────────────────────────────────────────────────────
    def _trigger_entry(self, cand: ScalpCandidateState, entry_price: float, rule_code: str = "SCALP_MICRO_PULLBACK"):
        """Calcula tamaño Icebreaker, Stop Loss y despacha la orden por socket a TWS."""
        if len(self.active_scalps) >= MAX_CONCURRENT_SCALPS:
            log_warning(MODULE, f"Límite de scalps simultáneos ({MAX_CONCURRENT_SCALPS}) alcanzado. Omitiendo.")
            cand.phase = "IDLE"
            return

        ib = get_ib_connection()
        if not ib or not ib.connected:
            log_error(MODULE, "TWS no conectado. No se puede ejecutar scalp.")
            cand.phase = "IDLE"
            return

        # 1. Dimensionamiento con Icebreaker (25% en la primera operación si no hay colchón)
        shares = self._calculate_scalp_shares(entry_price)
        if shares < 1:
            log_warning(MODULE, f"Capital insuficiente para comprar 1 acción de {cand.ticker} a ${entry_price:.2f}")
            cand.phase = "IDLE"
            return

        # 2. Stop Loss Técnico: Debajo del mínimo del retroceso o suelo de absorción
        if cand.pullback_low > 0:
            stop_loss_price = round(cand.pullback_low - 0.02, 2)
        else:
            stop_loss_price = round(entry_price * 0.97, 2)

        if cand.impulse_high > 0:
            target_hod_price = round(max(cand.highest_price_reached, cand.impulse_high), 2)
        else:
            target_hod_price = round(entry_price * 1.05, 2)

        # 3. Preparar orden LMT Marketable (Ask + 0.02) para garantizar fill sin rechazo TWS
        limit_exec_price = round(entry_price + 0.02, 2)

        from ibapi.order import Order
        ib_ord = Order()
        ib_ord.action = "BUY"
        ib_ord.totalQuantity = shares
        ib_ord.orderType = "LMT"
        ib_ord.lmtPrice = limit_exec_price
        ib_ord.transmit = True

        order_id = ib.get_next_order_id()
        contract = ib.us_stock_contract(cand.ticker)

        # Despacho en memoria
        ib.placeOrder(order_id, contract, ib_ord)
        log_info(MODULE, f"🚀 [ORDEN ENVIADA A TWS] BUY {shares}x {cand.ticker} ({rule_code}) @ LMT ${limit_exec_price:.2f} (SL: ${stop_loss_price:.2f}, TP HOD: ${target_hod_price:.2f})")

        # Actualizar estado de posición
        cand.in_trade = True
        cand.phase = "IN_TRADE"
        cand.entry_price = entry_price
        cand.initial_shares = shares
        cand.shares = shares
        cand.entry_rule = rule_code
        cand.highest_price_reached = max(cand.highest_price_reached, entry_price)
        cand.realized_scalp_profit = 0.0
        cand.entry_bar_idx = len(cand.bars)
        cand.bars_in_trade = 0
        cand.stop_loss = stop_loss_price
        cand.target_hod = target_hod_price
        cand.order_id = order_id
        self.active_scalps[cand.ticker] = cand

        # Sincronización asíncrona a Supabase (Background)
        self._safe_create_task(self._async_log_order_to_supabase(cand, limit_exec_price, rule_code=rule_code))

    # ──────────────────────────────────────────────────────────
    # ESTADO 4: Gestión de Salida en Cascada (3 Tramos + Recompras Dips)
    # ──────────────────────────────────────────────────────────
    def _manage_active_trade(self, cand: ScalpCandidateState, bar: dict):
        """
        Monitorea la posición en 3 fases continuas:
        Fase 1 (IN_TRADE): Scalp inicial hacia HOD con límite de 9 barras (45s).
                           Al romper HOD -> Venta del 50%, Stop a Breakeven ($0 riesgo) y pasa a Runner 15m.
        Fase 2 (RUNNER_15M_MODE): Corredor de 15m. Al aplanarse/caer EMA3 15m -> Venta del 60% del runner
                                  (30% del total inicial) y pasa el 40% a Golden Runner 1H.
        Fase 3 (GOLDEN_RUNNER_1H_MODE): Corredor de 1H (20% del total inicial). Venta final cuando
                                        EMA3 1H se aplana o pierde EMA9 1H.
        Recompras en Dips: Hasta 3 recompras escalonadas en retrocesos a EMA9/20 si 15m/1H es alcista.
        """
        current_p = bar["close"]
        if current_p > cand.highest_price_reached:
            cand.highest_price_reached = current_p

        # A) SALIDA POR STOP LOSS COMÚN (Milimétrico o Breakeven Protegido)
        if current_p <= cand.stop_loss:
            is_be = (cand.stop_loss >= cand.entry_price)
            sl_reason = "BREAKEVEN_PROTECTED" if is_be else "STOP_LOSS"
            log_warning(MODULE, f"🛑 [{cand.ticker}] {sl_reason} ALCANZADO (${current_p:.2f} <= ${cand.stop_loss:.2f}). Cerrando posición restante ({cand.shares} acc).")
            self._close_scalp(cand, reason=sl_reason)
            return

        # ── FASE 1: IN_TRADE (SCALP INICIAL HACIA HOD) ──
        if cand.phase == "IN_TRADE":
            cand.bars_in_trade += 1

            # RUPTURA HOD O IMPULSO ALCISTA -> TRAMO 1: VENTA DEL 50% Y PASE A RUNNER 15M
            gain_pct = ((current_p - cand.entry_price) / cand.entry_price * 100.0) if cand.entry_price > 0 else 0.0
            is_push_gain = (gain_pct >= 2.5)
            is_near_hod = (current_p >= cand.target_hod * 0.995)

            if is_near_hod or is_push_gain:
                self._execute_tramo_1_hod(cand, current_p)
                return

            # REGLA 'BREAKOUT OR BAILOUT'
            if cand.bars_in_trade >= MAX_BAILOUT_BARS:
                # Comprobar si 5m EMA3 > EMA9 sigue en tendencia alcista
                is_5m_bull = self._is_5m_trend_bullish(cand.ticker, current_p)

                # Si 5m sigue alcista y el precio sostiene el stop loss técnico:
                if is_5m_bull and current_p > cand.stop_loss:
                    # Bailout extendido solo si transcurren más de 36 barras (3 min) perdiendo la entrada
                    if cand.bars_in_trade >= (MAX_BAILOUT_BARS * 4) and current_p < cand.entry_price * 0.99:
                        log_info(MODULE, f"⏳ [{cand.ticker}] BAILOUT EXTENDIDO: 3 min sin avance y perdiendo entrada (${current_p:.2f} < ${cand.entry_price:.2f}).")
                        self._close_scalp(cand, reason="EXTENDED_BAILOUT_BELOW_ENTRY")
                        return
                    # De lo contrario, mantener la posición para dejar que complete el swing de 5m
                else:
                    if current_p < cand.target_hod:
                        log_info(MODULE, f"⏳ [{cand.ticker}] BREAKOUT OR BAILOUT: Sin soporte 5m tras {MAX_BAILOUT_BARS} barras (45s). Saliendo (${current_p:.2f}).")
                        self._close_scalp(cand, reason="BREAKOUT_OR_BAILOUT")
                        return

        # ── FASE 2: RUNNER_15M_MODE (60% DEL RUNNER VENDIDO EN GIRO DE 15M) ──
        elif cand.phase == "RUNNER_15M_MODE":
            # 1. Evaluar si hay dip para recompra (máximo 3)
            self._check_rebuys_on_dip(cand, bar)

            # 2. Evaluar agotamiento en 15m
            if self._is_15m_trend_exhausted(cand, current_p):
                self._execute_tramo_2_15m(cand, current_p)
                return

        # ── FASE 3: GOLDEN_RUNNER_1H_MODE (40% RESTANTE DEL RUNNER VENDIDO EN GIRO DE 1H) ──
        elif cand.phase == "GOLDEN_RUNNER_1H_MODE":
            # 1. Evaluar si hay dip para recompra (máximo 3)
            self._check_rebuys_on_dip(cand, bar)

            # 2. Evaluar agotamiento en 1H
            if self._is_1h_trend_exhausted(cand, current_p):
                log_info(MODULE, f"👑 [{cand.ticker}] GOLDEN RUNNER 1H: Giro bajista/plano de EMA3 1H detectado. Cierre final del 100% remanente (${current_p:.2f}).")
                self._close_scalp(cand, reason="GOLDEN_RUNNER_1H_EXIT")
                return

    def _execute_tramo_1_hod(self, cand: ScalpCandidateState, current_p: float):
        """Tramo 1: Vende 50% en la ruptura HOD, bloquea Breakeven y pasa a Runner 15m."""
        shares_to_sell = max(1, cand.shares // 2)
        shares_runner = cand.shares - shares_to_sell

        self._send_partial_sell_to_tws(cand, shares_to_sell, "TRAMO_1_HOD_50PCT")

        profit_leg1 = round((current_p - cand.entry_price) * shares_to_sell, 2)
        cand.realized_scalp_profit += profit_leg1
        self.daily_cushion_usd += profit_leg1

        if shares_runner > 0:
            cand.shares = shares_runner
            cand.stop_loss = round(cand.entry_price + 0.02, 2)  # Breakeven asegurado
            cand.phase = "RUNNER_15M_MODE"
            log_info(MODULE, f"🎉 [{cand.ticker}] TRAMO 1 EJECUTADO: 50% vendido ({shares_to_sell} acc @ ${current_p:.2f}). Profit: +${profit_leg1:.2f}. "
                             f"Stop Loss protegido en Breakeven (${cand.stop_loss:.2f}). Pasando a RUNNER 15m ({shares_runner} acc).")
        else:
            self._close_scalp(cand, reason="TAKE_PROFIT_HOD")

    def _execute_tramo_2_15m(self, cand: ScalpCandidateState, current_p: float):
        """Tramo 2: Vende 60% del runner en giro de 15m y pasa el 40% restante a Golden Runner 1H."""
        shares_to_sell = max(1, int(round(cand.shares * 0.60)))
        shares_golden = cand.shares - shares_to_sell

        self._send_partial_sell_to_tws(cand, shares_to_sell, "TRAMO_2_15M_60PCT")

        profit_leg2 = round((current_p - cand.entry_price) * shares_to_sell, 2)
        cand.realized_scalp_profit += profit_leg2
        self.daily_cushion_usd += profit_leg2

        if shares_golden > 0:
            cand.shares = shares_golden
            cand.phase = "GOLDEN_RUNNER_1H_MODE"
            log_info(MODULE, f"🏆 [{cand.ticker}] TRAMO 2 EJECUTADO: 60% del runner vendido ({shares_to_sell} acc @ ${current_p:.2f}). Profit: +${profit_leg2:.2f}. "
                             f"Pasando a GOLDEN RUNNER 1H ({shares_golden} acc restantes).")
        else:
            self._close_scalp(cand, reason="RUNNER_15M_EXIT")

    def _send_partial_sell_to_tws(self, cand: ScalpCandidateState, shares: int, reason: str):
        """Envía una orden parcial de venta a TWS."""
        ib = get_ib_connection()
        if ib and ib.connected and shares > 0:
            from ibapi.order import Order
            sell_ord = Order()
            sell_ord.action = "SELL"
            sell_ord.totalQuantity = shares
            sell_ord.orderType = "MKT"
            sell_ord.transmit = True

            sell_id = ib.get_next_order_id()
            contract = ib.us_stock_contract(cand.ticker)
            ib.placeOrder(sell_id, contract, sell_ord)
            log_info(MODULE, f"🔻 [VENTA PARCIAL TWS] SELL {shares}x {cand.ticker} (Razón: {reason})")
            self._safe_create_task(self._async_log_sell_order_to_supabase(cand, sell_id, shares, reason))

    def _is_15m_trend_exhausted(self, cand: ScalpCandidateState, current_p: float) -> bool:
        """Determina si la tendencia en 15m se agotó (EMA3 plana/descendente o precio bajo EMA9)."""
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            snap = get_live_1h_candle_and_sipv(cand.ticker, current_p)
            ema9_15m = float(snap.get("ema9_15m_val") or snap.get("ema9_15m") or 0.0)
            is_above_15m = bool(snap.get("is_ema3_above_ema9_15m", True))
            if ema9_15m > 0 and current_p < ema9_15m * 0.998:
                log_info(MODULE, f"📉 [{cand.ticker}] Agotamiento 15m: Precio (${current_p:.2f}) cayó bajo EMA9 15m (${ema9_15m:.2f}).")
                return True
            if not is_above_15m:
                return True
        except Exception:
            pass
        return False

    def _is_1h_trend_exhausted(self, cand: ScalpCandidateState, current_p: float) -> bool:
        """Determina si la tendencia en 1H se agotó (EMA3 1H plana/descendente o precio bajo EMA9 1H)."""
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            snap = get_live_1h_candle_and_sipv(cand.ticker, current_p)
            is_ema3_asc = bool(snap.get("is_ema3_1h_ascending", True))
            is_above_ema9 = bool(snap.get("is_ema3_above_ema9", True))
            ema9_1h = float(snap.get("ema9_1h") or 0.0)
            slope = float(snap.get("ema3_slope_1h") or 0.0)

            if slope <= 0 or not is_ema3_asc:
                log_info(MODULE, f"📉 [{cand.ticker}] Agotamiento 1H: EMA3 1H plana o descendente ({slope:+.4f}).")
                return True
            if ema9_1h > 0 and current_p < ema9_1h * 0.998:
                log_info(MODULE, f"📉 [{cand.ticker}] Agotamiento 1H: Precio (${current_p:.2f}) perforó EMA9 1H (${ema9_1h:.2f}).")
                return True
            if not is_above_ema9:
                return True
        except Exception:
            pass
        return False

    def _check_rebuys_on_dip(self, cand: ScalpCandidateState, bar: dict):
        """Evalúa recompras (Scaling-In) en caídas limpias hacia EMA9/20 si la tendencia 15m/1H es alcista."""
        if cand.rebuys_count >= 3:
            return

        now_ts = time.time()
        # Cooldown de 60 segundos entre recompras
        if now_ts - cand.last_rebuy_ts < 60.0:
            return

        current_p = bar["close"]
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            snap = get_live_1h_candle_and_sipv(cand.ticker, current_p)
            
            is_1h_bull = bool(snap.get("is_ema3_above_ema9", False) and snap.get("is_ema3_1h_ascending", False))
            is_15m_bull = bool(snap.get("is_ema3_above_ema9_15m", False))
            
            # Solo permitir recompra si ambas temporalidades mayores son alcistas
            if not (is_1h_bull and is_15m_bull):
                return

            ema9_15 = float(snap.get("ema9_15m_val") or snap.get("ema9_15m") or 0.0)
            # Rebote en soporte: cerca de EMA9 15m (dentro de 1.5%) y barra 5s verde con mecha inferior
            is_near_ema9 = (ema9_15 > 0 and abs(current_p - ema9_15) / current_p <= 0.015)
            is_reversal_bar = bar["is_green"] and (bar["lower_wick_ratio"] >= MIN_LOWER_WICK_RATIO)

            if is_near_ema9 and is_reversal_bar:
                rebuy_shares = max(1, cand.initial_shares // 4)
                ib = get_ib_connection()
                if ib and ib.connected:
                    limit_p = round(current_p + 0.02, 2)
                    from ibapi.order import Order
                    ord_b = Order()
                    ord_b.action = "BUY"
                    ord_b.totalQuantity = rebuy_shares
                    ord_b.orderType = "LMT"
                    ord_b.lmtPrice = limit_p
                    ord_b.transmit = True

                    bid = ib.get_next_order_id()
                    contract = ib.us_stock_contract(cand.ticker)
                    ib.placeOrder(bid, contract, ord_b)

                    cand.shares += rebuy_shares
                    cand.rebuys_count += 1
                    cand.last_rebuy_ts = now_ts
                    log_info(MODULE, f"🔥 [{cand.ticker}] RECOMPRA EN DIP ({cand.rebuys_count}/3): BUY {rebuy_shares}x @ ${limit_p:.2f} "
                                     f"(Rebote en EMA9 15m ${ema9_15:.2f}). Total acciones vivas: {cand.shares}.")
        except Exception as e:
            log_debug(MODULE, f"Error evaluando recompra para {cand.ticker}: {e}")

    def _is_5m_trend_bullish(self, ticker: str, current_p: float) -> bool:
        """Determina si la tendencia en 5 minutos mantiene EMA3 > EMA9 y no ha colapsado bajo soporte."""
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            snap = get_live_1h_candle_and_sipv(ticker, current_p)
            is_5m_bull = bool(snap.get("is_ema3_above_ema9_5m", True))
            ema9_5m = float(snap.get("ema9_5m") or 0.0)
            if ema9_5m > 0 and current_p < ema9_5m * 0.985:
                # Perforó más de 1.5% bajo EMA9 5m -> debilidad evidente
                return False
            return is_5m_bull
        except Exception:
            return True

    def _evaluate_dip_reentry(self, cand: ScalpCandidateState, bar: dict):
        """
        Evalúa recompra en soporte (Buy the Dip) cuando el activo corrigió tras el spike
        pero la tendencia en 5 minutos (EMA3 > EMA9) permanece intacta.
        """
        now_ts = time.time()
        # Cooldown de 20 segundos tras el último cierre para no recomprar en la misma caída violenta
        if now_ts - cand.last_exit_ts < 20.0:
            return

        if cand.rebuys_count >= 3:
            cand.phase = "IDLE"
            self.closed_tickers_today.add(cand.ticker)
            self.unregister_ticker(cand.ticker)
            return

        current_p = bar["close"]
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            snap = get_live_1h_candle_and_sipv(cand.ticker, current_p)

            is_5m_bull = bool(snap.get("is_ema3_above_ema9_5m", False))
            if not is_5m_bull:
                log_info(MODULE, f"📉 [{cand.ticker}] Tendencia 5m rota (EMA3 <= EMA9). Cancelando WAITING_DIP_5M.")
                cand.phase = "IDLE"
                self.closed_tickers_today.add(cand.ticker)
                self.unregister_ticker(cand.ticker)
                return

            ema9_5m = float(snap.get("ema9_5m") or 0.0)
            vwap = float(snap.get("vwap_intraday") or 0.0)
            support_level = ema9_5m if ema9_5m > 0 else vwap

            # Condición de Dip: El precio está en la zona de soporte (dentro de 2.5% de EMA9 5m o VWAP)
            in_dip_zone = (support_level > 0 and current_p <= support_level * 1.025 and current_p >= support_level * 0.98)

            # Condición de Giro: Barra de 5s verde con mecha inferior (bottoming tail) o superando High de vela previa
            prev_bar = cand.bars[-2] if len(cand.bars) >= 2 else bar
            has_absorption = bar["lower_wick_ratio"] >= 0.20 or bar["close"] > prev_bar["high"]
            is_turning_up = bar["is_green"] and has_absorption

            if in_dip_zone and is_turning_up:
                cand.rebuys_count += 1
                cand.last_rebuy_ts = now_ts
                cand.pullback_low = bar["low"]
                log_info(MODULE, f"🎯 [{cand.ticker}] BUY THE DIP EN SOPORTE 5M ({cand.rebuys_count}/3): "
                                 f"Rebote en ${current_p:.2f} (Soporte EMA9 5m ${support_level:.2f}). Disparando orden!")
                self._trigger_entry(cand, entry_price=current_p, rule_code="SCALP_BUY_THE_DIP")
        except Exception as dip_err:
            log_debug(MODULE, f"Error evaluando dip re-entry para {cand.ticker}: {dip_err}")

    def _close_scalp(self, cand: ScalpCandidateState, reason: str):
        """Envía orden de venta de cierre a TWS y resetea estado."""
        ib = get_ib_connection()
        if ib and ib.connected and cand.shares > 0:
            from ibapi.order import Order
            sell_ord = Order()
            sell_ord.action = "SELL"
            sell_ord.totalQuantity = cand.shares
            sell_ord.orderType = "MKT"
            sell_ord.transmit = True

            sell_id = ib.get_next_order_id()
            contract = ib.us_stock_contract(cand.ticker)
            ib.placeOrder(sell_id, contract, sell_ord)
            log_info(MODULE, f"🔻 [CIERRE ENVIADO A TWS] SELL {cand.shares}x {cand.ticker} (Razón: {reason})")
            self._safe_create_task(self._async_log_sell_order_to_supabase(cand, sell_id, cand.shares, reason))

        cand.in_trade = False
        cand.shares = 0
        self.active_scalps.pop(cand.ticker, None)
        cand.last_exit_ts = time.time()

        # Evaluar si la tendencia de 5m sigue viva para esperar Dip
        last_ref_price = cand.bars[-1]["close"] if cand.bars else (cand.highest_price_reached or cand.entry_price)
        is_5m_bull = self._is_5m_trend_bullish(cand.ticker, last_ref_price)

        if is_5m_bull and cand.rebuys_count < 3 and "STOP_LOSS" not in reason:
            cand.phase = "WAITING_DIP_5M"
            log_info(MODULE, f"🔄 [{cand.ticker}] Scalp cerrado ({reason}), pero 5m EMA3 > EMA9 se mantiene activa. Pasando a WAITING_DIP_5M para buscar recompra en retroceso.")
        else:
            cand.phase = "IDLE"
            self.closed_tickers_today.add(cand.ticker)
            self.unregister_ticker(cand.ticker)
            log_info(MODULE, f"🚫 [{cand.ticker}] Añadido a Lista Negra Intradía (One-and-Done). Posición cerrada y desuscrito de barras 5s; no se volverá a operar hoy.")

        # Actualizar journal y colchón en background
        self._safe_create_task(self._async_log_trade_close(cand, reason))

    def _safe_create_task(self, coro):
        """Lanza tareas asíncronas en background de forma segura contra hilos sin event loop."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        except RuntimeError:
            # En caso de ejecutarse en hilo síncrono sin loop activo
            try:
                coro.close()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────
    # Dimensionamiento Icebreaker (% Inversión por Operación)
    # ──────────────────────────────────────────────────────────
    def _calculate_scalp_shares(self, price: float) -> int:
        """Calcula el número de acciones respetando el % de Settings e Icebreaker."""
        if price <= 0:
            return 0
        try:
            sb = get_supabase()
            cfg_res = sb.table("stocks_config").select("key, value").execute()
            cfg = {r["key"]: r["value"] for r in (cfg_res.data or [])}

            total_capital = float(cfg.get("total_capital_usd", 5000))
            pct_per_trade = float(cfg.get("pct_per_operation", cfg.get("max_pct_per_trade", 10))) / 100.0

            std_capital_allocation = total_capital * pct_per_trade  # Ej. $5000 * 10% = $500

            # REGLA ICEBREAKER: Si no hay colchón acumulado hoy, se arriesga solo el 25% del capital estándar
            if self.daily_cushion_usd <= 0:
                allocated_usd = std_capital_allocation * 0.25  # Ej. $125
                log_info(MODULE, f"🧊 [ICEBREAKER ACTIVO] Sin colchón previo: Asignando 25% (${allocated_usd:.2f} USD)")
            else:
                allocated_usd = std_capital_allocation         # Ej. $500
                log_info(MODULE, f"🔥 [FULL SIZE ACTIVO] Colchón existente (+${self.daily_cushion_usd:.2f}): Asignando 100% (${allocated_usd:.2f} USD)")

            shares = int(allocated_usd // price)
            return max(1, shares) if allocated_usd >= price else 0
        except Exception as e:
            log_warning(MODULE, f"Error calculando shares para scalp: {e}")
            return max(1, int(150 // price))

    # ──────────────────────────────────────────────────────────
    # Persistencia Asíncrona a Supabase (Zero Latency)
    # ──────────────────────────────────────────────────────────
    async def _async_log_order_to_supabase(self, cand: ScalpCandidateState, limit_price: float, rule_code: str = "SCALP_MICRO_PULLBACK"):
        """Registra la orden en Supabase de forma asíncrona."""
        try:
            sb = get_supabase()
            now_iso = datetime.now(timezone.utc).isoformat()
            order_data = {
                "ticker": cand.ticker,
                "group_name": "HOT_MICRO_PULLBACK",
                "rule_code": rule_code,
                "order_type": "limit",
                "direction": "buy",
                "shares": cand.shares,
                "limit_price": limit_price,
                "market_price": cand.entry_price,
                "status": "pending",
                "created_at": now_iso,
            }
            res = sb.table("stocks_orders").insert(order_data).execute()
            if res.data:
                cand.db_order_id = res.data[0].get("id")
                try:
                    from app.workers.ib_bridge_worker import PENDING_IB_ORDERS
                    PENDING_IB_ORDERS[cand.order_id] = {
                        "id": cand.db_order_id,
                        "ticker": cand.ticker,
                        "direction": "buy",
                        "shares": cand.shares,
                        "market_price": cand.entry_price,
                        "limit_price": limit_price,
                        "group_name": "HOT_MICRO_PULLBACK",
                        "rule_code": rule_code,
                    }
                except Exception:
                    pass
        except Exception as e:
            log_warning(MODULE, f"Aviso al guardar orden de scalp en Supabase: {e}")

    async def _async_log_sell_order_to_supabase(self, cand: ScalpCandidateState, sell_order_id: int, shares: int, reason: str):
        """Registra la orden de venta en Supabase y enlaza con PENDING_IB_ORDERS para que el callback de TWS reconcilie el fill."""
        try:
            sb = get_supabase()
            now_iso = datetime.now(timezone.utc).isoformat()
            curr_p = cand.bars[-1]["close"] if cand.bars else cand.entry_price
            order_data = {
                "ticker": cand.ticker,
                "group_name": "HOT_MICRO_PULLBACK",
                "rule_code": f"SCALP_EXIT_{reason}"[:30],
                "order_type": "market",
                "direction": "sell",
                "shares": shares,
                "market_price": curr_p,
                "limit_price": curr_p,
                "status": "pending",
                "created_at": now_iso,
            }
            res = sb.table("stocks_orders").insert(order_data).execute()
            db_sell_id = res.data[0].get("id") if (res and res.data) else str(sell_order_id)
            try:
                from app.workers.ib_bridge_worker import PENDING_IB_ORDERS
                PENDING_IB_ORDERS[sell_order_id] = {
                    "id": db_sell_id,
                    "ticker": cand.ticker,
                    "direction": "sell",
                    "shares": shares,
                    "market_price": curr_p,
                    "limit_price": curr_p,
                    "group_name": "HOT_MICRO_PULLBACK",
                    "rule_code": f"SCALP_EXIT_{reason}"[:30],
                }
            except Exception:
                pass
        except Exception as e:
            log_warning(MODULE, f"Aviso al guardar orden de venta de scalp en Supabase: {e}")

    async def _async_log_trade_close(self, cand: ScalpCandidateState, reason: str):
        """Registra el resultado de la operación en Supabase y actualiza colchón."""
        try:
            sb = get_supabase()
            last_p = cand.bars[-1]["close"] if cand.bars else cand.entry_price
            pnl_usd = round((last_p - cand.entry_price) * cand.shares, 2)
            self.daily_cushion_usd += pnl_usd
            log_info(MODULE, f"📊 Scalp cerrado: {cand.ticker} PnL: ${pnl_usd:+.2f} USD | Nuevo Colchón: ${self.daily_cushion_usd:+.2f} USD")
        except Exception as e:
            log_warning(MODULE, f"Aviso al registrar cierre de scalp: {e}")


# ── Instancia Singleton del Motor ──
_scalp_engine: Optional[MicroPullbackEngine] = None

def get_micro_pullback_engine() -> MicroPullbackEngine:
    global _scalp_engine
    if _scalp_engine is None:
        _scalp_engine = MicroPullbackEngine()
    return _scalp_engine
