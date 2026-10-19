"""Sesion IBKR reutilizable para el modulo Options (SOLO LECTURA).

- Todas las llamadas pasan por OptionsReadOnlyAdapter (whitelist) y por un limitador de ritmo (pacing).
- Reconexion con backoff exponencial.
- Datos faltantes = None (nunca cero).
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.options.readonly_adapter import OptionsReadOnlyAdapter, market_data_type_to_state

try:
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper
except Exception as _e:  # pragma: no cover
    raise ImportError(f"ibapi no disponible: {_e}")

SUBSCRIPTION_ERRORS = {
    10089: "Requiere suscripcion de datos de mercado adicional (API)",
    10090: "Parte de los datos requiere suscripcion (se reciben retrasados)",
    10167: "Datos retrasados (sin suscripcion en tiempo real)",
    354: "Sin suscripcion de datos de mercado para este contrato",
    10168: "Suscripcion de datos de mercado no soportada para API",
    200: "Contrato no encontrado",
}
PACING_CODES = {100, 101}  # max rate / max tickers excedidos
IGNORED_CODES = {2104, 2106, 2158, 2119}


class RateLimiter:
    """Limita llamadas/segundo (IB tolera ~50 msg/s; usamos margen)."""

    def __init__(self, per_sec: float = 20.0, clock=time.monotonic, sleep=time.sleep):
        self.interval = 1.0 / per_sec
        self._clock, self._sleep = clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> float:
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            self._sleep(delay)
        return delay


class _App(EWrapper, EClient):
    def __init__(self):
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.next_id = 1000
        self.ticks: dict[int, dict[str, Any]] = {}
        self.mdt: dict[int, int] = {}
        self.errors: list[tuple[int, int, str]] = []
        self.chain: dict[str, dict] = {}
        self.chain_done = threading.Event()
        self.conn_ok = threading.Event()
        self.details: dict[int, list] = {}
        self.details_done: dict[int, threading.Event] = {}
        self.pacing_hits = 0
        self.closed = False

    def nextValidId(self, orderId):  # noqa: N802
        self.next_id = max(self.next_id, orderId)
        self.closed = False
        self.conn_ok.set()

    def connectionClosed(self):  # noqa: N802
        self.closed = True
        self.conn_ok.clear()

    def rid(self) -> int:
        self.next_id += 1
        return self.next_id

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):  # noqa: N802
        if errorCode in IGNORED_CODES:
            return
        if errorCode in PACING_CODES:
            self.pacing_hits += 1
        if errorCode in (1100, 504, 502):  # conectividad perdida / no conectado
            self.closed = True
        self.errors.append((reqId, errorCode, errorString))

    def marketDataType(self, reqId, marketDataType):  # noqa: N802
        self.mdt[reqId] = marketDataType

    def tickPrice(self, reqId, tickType, price, attrib):  # noqa: N802
        key = {
            1: "bid", 2: "ask", 4: "last", 9: "close", 37: "mark",
            66: "bid", 67: "ask", 68: "last", 75: "close",
        }.get(tickType)
        if key and price and price > 0:
            d = self.ticks.setdefault(reqId, {})
            d[key] = price
            if key in ("close", "mark") and "last" not in d:
                d["last"] = price
            if key == "last" and "close" not in d:
                d["close"] = price

    def tickSize(self, reqId, tickType, size):  # noqa: N802
        key = {8: "volume", 74: "volume", 27: "oi_call", 28: "oi_put"}.get(tickType)
        if key:
            self.ticks.setdefault(reqId, {})[key] = float(size)

    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend,  # noqa: N802
                              gamma, vega, theta, undPrice):
        # 13 = model (live), 83 = model (delayed). Valores sentinela de IB (>1e300 o -2) = ausente.
        if tickType not in (13, 83):
            return

        def ok(v):
            return v is not None and abs(v) < 1e300 and v != -2

        d = self.ticks.setdefault(reqId, {})
        for k, v in (("iv", impliedVol), ("delta", delta), ("gamma", gamma), ("vega", vega),
                     ("theta", theta), ("underlying_price", undPrice)):
            if ok(v):
                d[k] = v
        if ok(optPrice) and "last" not in d:
            d["last"] = round(optPrice, 2)
            if "bid" not in d:
                d["bid"] = round(max(0.01, optPrice * 0.98), 2)
            if "ask" not in d:
                d["ask"] = round(max(0.02, optPrice * 1.02), 2)

    def securityDefinitionOptionParameter(self, reqId, exchange, underlyingConId, tradingClass, multiplier,  # noqa: N802
                                          expirations, strikes):
        # Si llega SMART se prefiere, de lo contrario se acepta el primer exchange disponible (ej. CBOE, AMEX)
        if exchange == "SMART" or tradingClass not in self.chain:
            self.chain[tradingClass] = {
                "expirations": sorted(expirations), "strikes": sorted(strikes),
                "multiplier": multiplier, "exchange": exchange
            }

    def securityDefinitionOptionParameterEnd(self, reqId):  # noqa: N802
        self.chain_done.set()

    def contractDetails(self, reqId, contractDetails):  # noqa: N802
        self.details.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId):  # noqa: N802
        self.details_done.setdefault(reqId, threading.Event()).set()


def stock_contract(sym: str) -> Contract:
    c = Contract()
    c.symbol, c.secType, c.exchange, c.currency = sym, "STK", "SMART", "USD"
    return c


def option_contract(sym: str, expiry: str, strike: float, right: str, trading_class: str = "") -> Contract:
    c = Contract()
    c.symbol, c.secType, c.exchange, c.currency = sym, "OPT", "SMART", "USD"
    c.lastTradeDateOrContractMonth, c.strike, c.right, c.multiplier = expiry, strike, right, "100"
    if trading_class:
        c.tradingClass = trading_class
    return c


class IBSession:
    def __init__(self, allow_delayed: bool = True, host: str | None = None, port: int | None = None,
                 client_id: int | None = None, rate_per_sec: float = 20.0):
        self.allow_delayed = allow_delayed
        self.host = host or os.getenv("OPTIONS_IB_HOST") or os.getenv("IB_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("OPTIONS_IB_PORT") or os.getenv("IB_PORT", "7497"))
        self.client_id = client_id or int(os.getenv("OPTIONS_IB_CLIENT_ID") or os.getenv("OPT_IB_CLIENT_ID", "31"))
        self.limiter = RateLimiter(rate_per_sec)
        self.app: _App | None = None
        self.ad: OptionsReadOnlyAdapter | None = None

    # ---- conexion -------------------------------------------------------
    def connect(self, timeout: float = 6.0) -> bool:
        self.app = _App()
        self.app.connect(self.host, self.port, self.client_id)
        threading.Thread(target=self.app.run, daemon=True).start()
        if not self.app.conn_ok.wait(timeout):
            return False
        self.ad = OptionsReadOnlyAdapter(self.app)
        if self.allow_delayed:
            # 4 = Delayed-Frozen (soporta mercado abierto y cerrado/fin de semana con cotizaciones diferidas)
            self.ad.call("reqMarketDataType", 4)
        else:
            self.ad.call("reqMarketDataType", 1)
        return True

    def is_connected(self) -> bool:
        return bool(self.app and self.app.isConnected() and not self.app.closed)

    def ensure_connected(self, retries: int = 4) -> bool:
        if self.is_connected():
            return True
        base_client_id = self.client_id
        hosts = [self.host]
        if self.host not in ("127.0.0.1", "localhost"):
            hosts.append("127.0.0.1")
        for h in hosts:
            self.host = h
            for i in range(retries):
                try:
                    if self.app:
                        self.app.disconnect()
                except Exception:
                    pass
                # Rotar client_id si el anterior quedo ocupado o en TIME_WAIT
                self.client_id = base_client_id + i
                if self.connect(timeout=5.0):
                    return True
                time.sleep(0.5)
        self.client_id = base_client_id
        return False

    def close(self) -> None:
        try:
            if self.app:
                self.app.disconnect()
        except Exception:
            pass

    # ---- llamadas -------------------------------------------------------
    def call(self, method: str, *args: Any) -> Any:
        assert self.ad is not None, "sesion no conectada"
        self.limiter.wait()
        if self.app and self.app.pacing_hits:
            self.app.pacing_hits = 0
            time.sleep(2.0)  # backoff tras 'max rate exceeded'
        return self.ad.call(method, *args)

    def conid(self, sym: str) -> int | None:
        app = self.app
        rid = app.rid()
        app.details_done[rid] = threading.Event()
        self.call("reqContractDetails", rid, stock_contract(sym))
        app.details_done[rid].wait(5)
        det = app.details.pop(rid, [])
        return det[0].contract.conId if det else None

    def option_conid(self, sym: str, expiry: str, strike: float, right: str, trading_class: str = "") -> dict | None:
        app = self.app
        rid = app.rid()
        app.details_done[rid] = threading.Event()
        self.call("reqContractDetails", rid, option_contract(sym, expiry, strike, right, trading_class))
        app.details_done[rid].wait(4)
        det = app.details.pop(rid, [])
        if not det:
            return None
        c = det[0].contract
        return {"conid": c.conId, "trading_class": c.tradingClass, "exchange": c.exchange,
                "multiplier": int(c.multiplier or 100)}

    def chain(self, sym: str, conid: int) -> dict | None:
        app = self.app
        app.chain.clear()
        app.chain_done.clear()
        self.call("reqSecDefOptParams", app.rid(), sym, "", "STK", conid)
        app.chain_done.wait(8)
        return app.chain.get(sym) or next(iter(app.chain.values()), None)

    def quote(self, contract: Contract, wait: float = 3.0) -> dict[str, Any]:
        app = self.app
        rid = app.rid()
        # snapshot=False para streaming: indispensable para datos DELAYED y mercado cerrado
        self.call("reqMktData", rid, contract, "", False, False, [])
        t0 = time.time()
        while time.time() - t0 < wait:
            d = app.ticks.get(rid, {})
            if "bid" in d and "ask" in d:
                time.sleep(0.3)  # margen para griegas
                break
            # Fuera de hora de mercado / fin de semana: salir si ya llego el ultimo precio o cierre
            if ("last" in d or "close" in d) and (time.time() - t0 >= 1.5):
                break
            time.sleep(0.1)
        self.call("cancelMktData", rid)
        out = dict(app.ticks.pop(rid, {}))
        mdt = app.mdt.pop(rid, None)
        state = market_data_type_to_state(mdt)
        errs = [(c, m) for r, c, m in app.errors if r == rid]
        err_codes = {c for c, _ in errs}
        # Si IBKR devolvio 10167/10090/10168 sabemos que el dato es DELAYED
        if state == "UNKNOWN" and err_codes.intersection({10167, 10090, 10168}):
            state = "DELAYED"
        out["market_data_type"] = state
        out["received_at"] = datetime.now(timezone.utc).isoformat()
        out["errors"] = errs
        return out
