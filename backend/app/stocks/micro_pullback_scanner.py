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
        self._fallback_task: asyncio.Task | None = None

    def start(self):
        """Inicia el bucle de escaneo y el alimentador de soporte."""
        if self.is_running:
            return
        self.is_running = True
        engine = get_micro_pullback_engine()
        engine.start()
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._scan_loop())
            self._fallback_task = loop.create_task(self._fallback_bar_feeder())
        except RuntimeError:
            self._task = asyncio.ensure_future(self._scan_loop())
            self._fallback_task = asyncio.ensure_future(self._fallback_bar_feeder())
        log_info(MODULE, "🔎 Escáner de Momentum Micro-Pullbacks INICIADO (Refresco cada 15s con fallback automático).")

    def stop(self):
        """Detiene los bucles y desuscribe candidatos."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if self._fallback_task and not self._fallback_task.done():
            self._fallback_task.cancel()
        engine = get_micro_pullback_engine()
        engine.stop()
        log_info(MODULE, "🛑 Escáner de Momentum Micro-Pullbacks DETENIDO.")

    async def _fallback_bar_feeder(self):
        """
        Alimentador de alta frecuencia para Micro-Pullbacks:
        Prioridad 1: Finnhub REST Quotes en paralelo (sub-segundo con FINNHUB_API_KEY).
        Prioridad 2: YFinance 1m download como respaldo de emergencia.
        Genera barras de 5 segundos de ultra-baja latencia para alimentar el motor en memoria
        cuando TWS Paper no cuenta con suscripción L1 (IB Error 420).
        """
        import os
        import httpx
        from app.core.config import settings

        finnhub_key = (os.getenv("FINNHUB_API_KEY") or getattr(settings, "FINNHUB_API_KEY", "") or "").strip()
        if finnhub_key:
            log_info(MODULE, f"⚡ Alimentador de Micro-Barras 5s activo: FINNHUB REST API (Key: {finnhub_key[:4]}***).")
        else:
            log_warning(MODULE, "⚠️ FINNHUB_API_KEY no detectada. Usando YFinance como fallback secundario.")

        while self.is_running:
            try:
                engine = get_micro_pullback_engine()
                now_ts = time.time()
                stalled_tickers = []
                for ticker, cand in list(engine.candidates.items()):
                    last_bar_ts = cand.bars[-1]["time"] if cand.bars else 0
                    # Si no ha recibido barras de TWS en más de 4.5 segundos:
                    if (now_ts - last_bar_ts) >= 4.5:
                        stalled_tickers.append(ticker)

                if stalled_tickers:
                    bar_dict = {}

                    # ── PRIORIDAD 1: FINNHUB REST EN PARALELO ──
                    if finnhub_key:
                        try:
                            async with httpx.AsyncClient(timeout=2.5) as client:
                                tasks = [
                                    client.get(f"https://finnhub.io/api/v1/quote?symbol={t}&token={finnhub_key}")
                                    for t in stalled_tickers
                                ]
                                responses = await asyncio.gather(*tasks, return_exceptions=True)
                                for t, resp in zip(stalled_tickers, responses):
                                    if isinstance(resp, httpx.Response) and resp.status_code == 200:
                                        data = resp.json()
                                        c = float(data.get("c") or 0.0)
                                        if c > 0:
                                            cand = engine.candidates.get(t)
                                            prev_c = cand.bars[-1]["close"] if (cand and cand.bars) else c
                                            bar_h = max(c, prev_c)
                                            bar_l = min(c, prev_c)
                                            bar_dict[t] = {
                                                "open": prev_c,
                                                "high": bar_h,
                                                "low": bar_l,
                                                "close": c,
                                                "volume": int(data.get("v") or 1000),
                                                "time": now_ts,
                                            }
                        except Exception as e_fh:
                            log_debug(MODULE, f"Aviso en Finnhub feeder: {e_fh}")

                    # ── PRIORIDAD 2: YFINANCE PARA TICKERS RESTANTES ──
                    missing_tickers = [t for t in stalled_tickers if t not in bar_dict]
                    if missing_tickers:
                        try:
                            import yfinance as yf
                            loop = asyncio.get_running_loop()

                            def _fetch_yf():
                                res = {}
                                data = yf.download(missing_tickers, period="1d", interval="1m", progress=False, timeout=4)
                                if data is not None and not data.empty:
                                    for t in missing_tickers:
                                        try:
                                            df_t = data if len(missing_tickers) == 1 else (data.xs(t, axis=1, level=1) if (hasattr(data.columns, 'levels') and t in data.columns.levels[1]) else None)
                                            if df_t is not None and not df_t.empty:
                                                df_t = df_t.dropna()
                                                if not df_t.empty:
                                                    last_row = df_t.iloc[-1]
                                                    res[t] = {
                                                        "open": float(last_row["Open"]),
                                                        "high": float(last_row["High"]),
                                                        "low": float(last_row["Low"]),
                                                        "close": float(last_row["Close"]),
                                                        "volume": int(last_row["Volume"]),
                                                        "time": now_ts,
                                                    }
                                        except Exception:
                                            pass
                                return res

                            yf_dict = await loop.run_in_executor(None, _fetch_yf)
                            bar_dict.update(yf_dict)
                        except Exception:
                            pass

                    # Despachar cada barra sintetizada al motor en memoria
                    for t, b in bar_dict.items():
                        engine.process_5s_bar(t, b)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_debug(MODULE, f"Error en ciclo de alimentador de barras: {e}")

            await asyncio.sleep(5)

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
        Descubre los Top Gainers con volumen > 300k de forma no bloqueante.
        Usa Yahoo Finance Screener rápido en thread pool (sin llamadas de AI/noticias).
        """
        try:
            # Si no hay conexión con TWS en este nodo, pausar escaneo
            from app.data.ib_provider import get_ib_connection
            ib = get_ib_connection()
            if not ib or not ib.connected:
                return []

            loop = asyncio.get_running_loop()
            
            def get_screener_sync():
                try:
                    from yfinance.screener import EquityQuery, screen
                    q = EquityQuery('and', [
                        EquityQuery('gt', ['percentchange', 3.0]),
                        EquityQuery('gt', ['dayvolume', 300000]),
                        EquityQuery('gte', ['intradayprice', 1.0]),
                        EquityQuery('lte', ['intradayprice', 80.0]),
                        EquityQuery('eq', ['region', 'us'])
                    ])
                    res = screen(q, sortField='percentchange', sortAsc=False, size=15)
                    quotes = res.get("quotes", [])
                    filtered = []
                    for q_item in quotes:
                        sym = str(q_item.get("symbol") or "").upper().strip()
                        chg = float(q_item.get("regularMarketChangePercent") or 0.0)
                        vol = int(q_item.get("regularMarketVolume") or 0)
                        price = float(q_item.get("regularMarketPrice") or 0.0)
                        
                        # Excluir warrants, preferred shares y símbolos raros
                        if '.' in sym or '-' in sym or len(sym) > 5:
                            continue
                        # Filtro de candidatos viables para micro-pullbacks:
                        # Precio $1.00 a $80.00, Volumen >= 300k, Ganancia del día >= +3.0%
                        if 1.0 <= price <= 80.0 and vol >= 300_000 and chg >= 3.0:
                            filtered.append({"ticker": sym, "change": chg, "volume": vol, "price": price})
                    
                    filtered.sort(key=lambda x: x["change"], reverse=True)
                    return [x["ticker"] for x in filtered[:MAX_TRACKED_TICKERS]]
                except Exception as ex:
                    log_warning(MODULE, f"Aviso al obtener gainers rápidos: {ex}")
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
