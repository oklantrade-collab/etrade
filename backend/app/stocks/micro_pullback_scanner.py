"""
eTrade Stocks — Real-Time Momentum Tracker for Micro-Pullbacks
==============================================================
Rastreador en memoria que descubre y actualiza los Top 5 activos
con mayor aceleración porcentual y volumen en el mercado.
Alimenta continuamente al MicroPullbackEngine para que abra sus
feeds de barras de 5 segundos directamente con Interactive Brokers TWS.
"""

import asyncio
import time
from typing import List, Dict, Set
from app.core.logger import log_info, log_warning, log_error
from app.stocks.micro_pullback_engine import get_micro_pullback_engine

MODULE = "MICRO_PULLBACK_SCANNER"

SCAN_INTERVAL_SECONDS = 15.0  # Cada 15 segundos refresca el Top 5 en RAM
MAX_TRACKED_TICKERS = 5       # Top 5 simultáneos


class MicroPullbackScanner:
    """Escáner ultrarrápido sin sobrecarga de base de datos."""

    def __init__(self):
        self.is_running: bool = False
        self.current_top_tickers: Set[str] = set()
        self._task: asyncio.Task | None = None

    def start(self):
        """Inicia el bucle de escaneo."""
        if self.is_running:
            return
        self.is_running = True
        engine = get_micro_pullback_engine()
        engine.start()
        self._task = asyncio.create_task(self._scan_loop())
        log_info(MODULE, "🔎 Escáner de Momentum Micro-Pullbacks INICIADO (Refresco cada 15s).")

    def stop(self):
        """Detiene el bucle y desuscribe candidatos."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        engine = get_micro_pullback_engine()
        engine.stop()
        log_info(MODULE, "🛑 Escáner de Momentum Micro-Pullbacks DETENIDO.")

    async def _scan_loop(self):
        """Bucle continuo de descubrimiento de líderes."""
        while self.is_running:
            try:
                top_tickers = await self._fetch_rapid_top_gainers()
                if top_tickers:
                    self._update_engine_tickers(top_tickers)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(MODULE, f"Error en ciclo de escáner: {e}")

            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    async def _fetch_rapid_top_gainers(self) -> List[str]:
        """
        Descubre los Top Gainers con volumen > 500k de forma no bloqueante.
        Usa TWS Scanner primario si está activo, o screener ligero como respaldo.
        """
        try:
            # 1. Intentar con Yahoo Finance Screener rápido en thread pool (sin llamadas de AI/noticias)
            import yfinance as yf
            loop = asyncio.get_running_loop()
            
            def get_screener_sync():
                try:
                    s = yf.Screen('day_gainers')
                    quotes = (s.response or {}).get("quotes", [])
                    filtered = []
                    for q in quotes:
                        sym = str(q.get("symbol") or "").upper().strip()
                        chg = float(q.get("regularMarketChangePercent") or 0.0)
                        vol = int(q.get("regularMarketVolume") or 0)
                        price = float(q.get("regularMarketPrice") or 0.0)
                        
                        # Filtro de candidatos viables para micro-pullbacks:
                        # Precio $1.00 a $80.00, Volumen >= 500k, Ganancia del día >= +4.0%
                        if 1.0 <= price <= 80.0 and vol >= 500_000 and chg >= 4.0:
                            filtered.append({"ticker": sym, "change": chg, "volume": vol, "price": price})
                    
                    filtered.sort(key=lambda x: x["change"], reverse=True)
                    return [x["ticker"] for x in filtered[:MAX_TRACKED_TICKERS]]
                except Exception:
                    return []

            top_syms = await loop.run_in_executor(None, get_screener_sync)
            return top_syms
        except Exception as e:
            log_warning(MODULE, f"Error obteniendo gainers rápidos: {e}")
            return []

    def _update_engine_tickers(self, new_top_tickers: List[str]):
        """Sincroniza los tickers en el MicroPullbackEngine."""
        engine = get_micro_pullback_engine()
        new_set = set(new_top_tickers)

        # Activos que salieron del Top 5
        removed = self.current_top_tickers - new_set
        for sym in removed:
            # No desuscribir si actualmente está dentro de una operación abierta
            cand = engine.candidates.get(sym)
            if cand and not cand.in_trade:
                engine.unregister_ticker(sym)
                log_info(MODULE, f"➖ [{sym}] Salió del Top 5 de momentum. Desuscrito de barras 5s.")

        # Activos que entraron al Top 5
        added = new_set - self.current_top_tickers
        for sym in added:
            engine.register_ticker(sym)
            log_info(MODULE, f"➕ [{sym}] Nuevo líder detectado en Top 5. Conectado a barras 5s en TWS.")

        self.current_top_tickers = new_set


# ── Instancia Singleton del Escáner ──
_scanner_instance: MicroPullbackScanner | None = None

def get_micro_pullback_scanner() -> MicroPullbackScanner:
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = MicroPullbackScanner()
    return _scanner_instance
