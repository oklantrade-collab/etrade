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
from typing import Dict, List, Optional, Any, Callable

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
        self.shares: int = 0
        self.entry_bar_idx: int = 0
        self.bars_in_trade: int = 0
        self.stop_loss: float = 0.0
        self.target_hod: float = 0.0
        self.order_id: int = 0
        self.db_order_id: str = ""


class MicroPullbackEngine:
    """Motor In-Memory para Scalping de Micro Retrocesos en TWS."""
    
    def __init__(self):
        self.candidates: Dict[str, ScalpCandidateState] = {}
        self.active_scalps: Dict[str, ScalpCandidateState] = {}
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
        """Suscribe un ticker de alta volatilidad al feed de 5 segundos de TWS."""
        ticker = ticker.upper().strip()
        if ticker in self.candidates:
            return
        
        ib = get_ib_connection()
        if not ib or not ib.connected:
            log_warning(MODULE, f"No se puede suscribir {ticker}: TWS no conectado.")
            return

        cand = ScalpCandidateState(ticker)
        self.candidates[ticker] = cand

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
    def _trigger_entry(self, cand: ScalpCandidateState, entry_price: float):
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

        # 2. Stop Loss Técnico: Debajo del mínimo del retroceso
        stop_loss_price = round(cand.pullback_low - 0.02, 2)
        target_hod_price = round(cand.impulse_high, 2)

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
        log_info(MODULE, f"🚀 [ORDEN ENVIADA A TWS] BUY {shares}x {cand.ticker} @ LMT ${limit_exec_price:.2f} (SL: ${stop_loss_price:.2f}, TP HOD: ${target_hod_price:.2f})")

        # Actualizar estado de posición
        cand.in_trade = True
        cand.entry_price = entry_price
        cand.shares = shares
        cand.entry_bar_idx = len(cand.bars)
        cand.bars_in_trade = 0
        cand.stop_loss = stop_loss_price
        cand.target_hod = target_hod_price
        cand.order_id = order_id
        self.active_scalps[cand.ticker] = cand

        # Sincronización asíncrona a Supabase (Background)
        self._safe_create_task(self._async_log_order_to_supabase(cand, limit_exec_price))

    # ──────────────────────────────────────────────────────────
    # ESTADO 4: Gestión de Salida "Breakout or Bailout" (9 barras = 45s)
    # ──────────────────────────────────────────────────────────
    def _manage_active_trade(self, cand: ScalpCandidateState, bar: dict):
        """Monitorea Stop Loss, Take Profit HOD y la regla estricta de 9 barras."""
        cand.bars_in_trade += 1
        current_p = bar["close"]

        # A) SALIDA POR STOP LOSS TÉCNICO
        if current_p <= cand.stop_loss:
            log_warning(MODULE, f"🛑 [{cand.ticker}] STOP LOSS ALCANZADO (${current_p:.2f} <= ${cand.stop_loss:.2f}). Cerrando posición.")
            self._close_scalp(cand, reason="STOP_LOSS")
            return

        # B) SALIDA POR TAKE PROFIT (Ruptura de High of Day)
        if current_p >= cand.target_hod * 1.002:
            log_info(MODULE, f"🎉 [{cand.ticker}] TAKE PROFIT: Ruptura HOD alcanzada (${current_p:.2f} >= ${cand.target_hod:.2f}). Asegurando ganancia.")
            self._close_scalp(cand, reason="TAKE_PROFIT_HOD")
            return

        # C) REGLA 'BREAKOUT OR BAILOUT' (9 BARRAS DE 5s = 45s)
        # Si han pasado 9 barras y el precio no ha logrado romper el máximo anterior y muestra debilidad:
        if cand.bars_in_trade >= MAX_BAILOUT_BARS:
            if current_p < cand.target_hod:
                log_info(MODULE, f"⏳ [{cand.ticker}] BREAKOUT OR BAILOUT: Cumplidas {MAX_BAILOUT_BARS} barras (45s) sin romper HOD. Saliendo de inmediato (${current_p:.2f}).")
                self._close_scalp(cand, reason="BREAKOUT_OR_BAILOUT")
                return

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

        cand.in_trade = False
        cand.phase = "IDLE"
        self.active_scalps.pop(cand.ticker, None)

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
    async def _async_log_order_to_supabase(self, cand: ScalpCandidateState, limit_price: float):
        """Registra la orden en Supabase de forma asíncrona."""
        try:
            sb = get_supabase()
            now_iso = datetime.now(timezone.utc).isoformat()
            order_data = {
                "ticker": cand.ticker,
                "group_name": "HOT_MICRO_PULLBACK",
                "rule_code": "SCALP_MICRO_PULLBACK",
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
        except Exception as e:
            log_warning(MODULE, f"Aviso al guardar orden de scalp en Supabase: {e}")

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
