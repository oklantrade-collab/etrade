"""
eTrader v4.5 — Interactive Brokers TWS API Provider
Wrapper for IB TWS API for real-time data and order execution.

PHASE: Paper Trading first (port 7497).
Live trading requires explicit configuration change (port 7496).

Prerequisites:
  - TWS or IB Gateway running with API enabled
  - pip install ibapi (from IB website, not PyPI)
  - TWS → File → Global Config → API → Settings → Enable ActiveX/Socket
"""
import os
import time
import socket
import threading
from typing import Optional, Callable, Dict
from datetime import datetime, timezone
from dotenv import load_dotenv

# Asegurar carga de variables de entorno
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

from app.core.logger import log_info, log_error, log_warning

MODULE = "ib_provider"

# Try importing IB API — it's optional until Sprint 7 execution
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
    class EWrapper: pass
    class EClient:
        def __init__(self, wrapper): pass
    class Contract: pass
    class Order: pass
    log_warning(MODULE, "ibapi not installed — IB TWS features disabled. "
                        "Install from: https://www.interactivebrokers.com/en/trading/ib-api.php")


class IBConnection(EWrapper, EClient):
    """
    Interactive Brokers TWS API connection wrapper.
    
    Handles connection lifecycle, error handling, and order ID management.
    Uses threading for the event loop (IB API is callback-based).
    """

    def __init__(self):
        if not IB_AVAILABLE:
            raise RuntimeError("ibapi is not installed")
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.next_order_id: int = 0
        self.connected: bool = False
        self._data_callbacks: dict = {}
        self._errors: list = []
        self._prices: Dict[str, float] = {}  # {ticker: last_price}
        self._quotes: Dict[str, dict] = {}   # {pos_key: {bid, ask, last, close}}
        self._order_statuses: dict = {}      # {order_id: status_dict}
        self._order_callback: Optional[Callable] = None
        self.accounts: list[str] = []
        self._positions: Dict[str, dict] = {}
        self._positions_event = threading.Event()
        self._portfolio: Dict[str, dict] = {}
        self._portfolio_event = threading.Event()
        self._account_updates_subscribed: bool = False
        self._pnl_single_reqs: Dict[int, str] = {}
        self._pnl_single_conids: set[int] = set()
        self._mkt_data_subscribed: set[str] = set()
        self._contract_details: Dict[int, list] = {}
        self._contract_details_events: Dict[int, threading.Event] = {}
        self._hist_bars: dict = {}
        self._hist_events: dict = {}
        self._realtime_bar_callbacks: dict = {}
        self._thread: threading.Thread | None = None

    # ── Connection ────────────────────────────────────────

    def connect_tws(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> bool:
        """
        Connect to TWS or IB Gateway.
        
        Default: Paper Trading (port 7497).
        Live: port 7496 (requires explicit config).
        """
        env_host = os.getenv("IB_HOST")
        if not host:
            if env_host:
                host = env_host
            else:
                # Probar si 127.0.0.1:7497 está escuchando, de lo contrario fallback a APOLO (192.168.1.105)
                s = socket.socket()
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", 7497)) == 0:
                    host = "127.0.0.1"
                else:
                    host = "192.168.1.105"
                s.close()
        port = port or int(os.getenv("IB_PORT", "7497"))  # 7497=paper, 7496=live
        client_id = client_id or int(os.getenv("IB_CLIENT_ID", "26"))

        try:
            self._errors = []
            self.connected = False
            self.connect(host, port, client_id)
            
            # Start event loop in background thread
            self._thread = threading.Thread(
                target=self.run, daemon=True, name=f"ib-event-loop-{client_id}"
            )
            self._thread.start()

            # Wait for connection confirmation
            timeout = 7
            start = time.time()
            while not self.connected and (time.time() - start) < timeout:
                time.sleep(0.1)

            if self.connected:
                log_info(MODULE, f"Connected to IB TWS at {host}:{port} (client_id={client_id})")
                try:
                    self.reqMarketDataType(4)
                except Exception:
                    pass
                self._ensure_account_updates()
                return True
            else:
                log_warning(MODULE, f"IB TWS not running at {host}:{port} (expected)")
                return False

        except Exception as e:
            log_warning(MODULE, f"IB TWS not available: {e}")
            return False

    def disconnect_tws(self) -> None:
        """Disconnect from TWS gracefully."""
        try:
            self.disconnect()
            self.connected = False
            log_info(MODULE, "Disconnected from IB TWS")
        except Exception as e:
            log_warning(MODULE, f"Error during disconnect: {e}")

    # ── EWrapper Callbacks ────────────────────────────────

    def nextValidId(self, orderId: int):
        """Called when connection is established."""
        self.next_order_id = orderId
        self.connected = True
        log_info(MODULE, f"Connection confirmed. Next order ID: {orderId}")

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors from TWS."""
        # Informational messages (not real errors)
        info_codes = {2104, 2106, 2158, 2119}
        if errorCode in info_codes:
            log_info(MODULE, f"[IB Info {errorCode}] {errorString}")
        else:
            self._errors.append({
                "reqId": reqId,
                "code": errorCode,
                "message": errorString,
                "time": datetime.now(timezone.utc).isoformat()
            })
            # Connection errors (502, 504) should be warnings, not critical Telegram alerts
            if errorCode in [502, 504]:
                log_warning(MODULE, f"[IB Connection] {errorString}")
            else:
                log_error(MODULE, f"[IB Error {errorCode}] reqId={reqId}: {errorString}")
    
    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        """Called when a market price update is received (Live + Delayed + Frozen)."""
        if price is None or price <= 0 or price >= 1e100:
            return
        # Live: 1=Bid, 2=Ask, 4=Last, 9=Close | Delayed/Frozen: 66=Bid, 67=Ask, 68=Last, 75=Close
        if tickType in (1, 2, 4, 9, 66, 67, 68, 75):
            ticker = self._data_callbacks.get(reqId)
            if not ticker:
                return
            q = self._quotes.setdefault(ticker, {"bid": 0.0, "ask": 0.0, "last": 0.0, "close": 0.0})
            if tickType in (1, 66):
                q["bid"] = float(price)
            elif tickType in (2, 67):
                q["ask"] = float(price)
            elif tickType in (4, 68):
                q["last"] = float(price)
            elif tickType in (9, 75):
                q["close"] = float(price)

            if ":OPT:" in ticker:
                if q["bid"] > 0 and q["ask"] > 0:
                    best_p = round((q["bid"] + q["ask"]) / 2.0, 4)
                else:
                    best_p = q["last"] or q["close"] or q["bid"] or q["ask"]
            else:
                if q["last"] > 0:
                    best_p = q["last"]
                elif q["bid"] > 0 and q["ask"] > 0:
                    best_p = round((q["bid"] + q["ask"]) / 2.0, 4)
                else:
                    best_p = q["close"] or q["bid"] or q["ask"]

            if best_p > 0:
                self._prices[ticker] = float(best_p)

    def connectionClosed(self):
        """Called when connection is lost."""
        self.connected = False
        self._account_updates_subscribed = False
        self._mkt_data_subscribed.clear()
        self._pnl_single_conids.clear()
        log_warning(MODULE, "IB TWS connection closed")

    def managedAccounts(self, accountsList: str):
        """Called when account list is received from TWS."""
        self.accounts = [a.strip() for a in accountsList.split(",") if a.strip()]
        log_info(MODULE, f"[IB Accounts] Connected accounts: {self.accounts}")
        try:
            self.reqMarketDataType(4)
        except Exception:
            pass
        self._ensure_account_updates()

    def _ensure_account_updates(self):
        """Subscribe to TWS reqAccountUpdates to receive real-time updatePortfolio (marketPrice and unrealizedPNL)."""
        if not self.connected or self._account_updates_subscribed:
            return
        try:
            acct = self.accounts[0] if self.accounts else ""
            self.reqAccountUpdates(True, acct)
            self._account_updates_subscribed = True
            log_info(MODULE, f"[IB Portfolio] Subscribed to reqAccountUpdates for account='{acct or 'DEFAULT'}'")
        except Exception as e:
            log_warning(MODULE, f"Could not subscribe reqAccountUpdates: {e}")

    def updatePortfolio(
        self,
        contract: "Contract",
        position: float,
        marketPrice: float,
        marketValue: float,
        averageCost: float,
        unrealizedPNL: float,
        realizedPNL: float,
        accountName: str,
    ):
        """Called by TWS with real-time marketPrice, marketValue, averageCost, and unrealizedPNL."""
        if not contract:
            return
        symbol = getattr(contract, "symbol", "").upper()
        if not symbol:
            return
        sec_type = str(getattr(contract, "secType", "STK") or "STK").upper()
        if sec_type == "OPT":
            right = str(getattr(contract, "right", "") or "").upper()
            strike = float(getattr(contract, "strike", 0.0) or 0.0)
            expiry = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "")
            pos_key = f"{symbol}:OPT:{expiry}:{strike}:{right}"
        else:
            pos_key = symbol

        def _clean(val: float) -> float:
            try:
                v = float(val)
                return 0.0 if (abs(v) >= 1e100 or v != v) else v
            except Exception:
                return 0.0

        qty = _clean(position)
        mkt_p = _clean(marketPrice)
        mkt_v = _clean(marketValue)
        avg_c = _clean(averageCost)
        unr_pnl = _clean(unrealizedPNL)
        real_pnl = _clean(realizedPNL)

        if sec_type == "OPT" and qty != 0 and abs(mkt_v) > 0:
            calc_opt_p = round(abs(mkt_v) / (abs(qty) * 100.0), 4)
            if mkt_p <= 0 or mkt_p > calc_opt_p * 20:
                mkt_p = calc_opt_p
        elif sec_type == "STK" and qty != 0 and abs(mkt_v) > 0 and mkt_p <= 0:
            mkt_p = round(abs(mkt_v) / abs(qty), 4)

        if mkt_p > 0:
            self._prices[pos_key] = mkt_p
            if sec_type == "STK":
                self._prices[symbol] = mkt_p

        self._portfolio[pos_key] = {
            "account": accountName,
            "symbol": pos_key,
            "sec_type": sec_type,
            "underlying": symbol,
            "shares": qty,
            "avg_cost": avg_c,
            "market_price": mkt_p,
            "market_value": mkt_v,
            "unrealized_pnl": unr_pnl,
            "realized_pnl": real_pnl,
            "conid": getattr(contract, "conId", None),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if pos_key in self._positions:
            self._positions[pos_key].update({
                "market_price": mkt_p,
                "market_value": mkt_v,
                "unrealized_pnl": unr_pnl,
                "realized_pnl": real_pnl,
            })
        log_info(MODULE, f"[IB UpdatePortfolio] {pos_key} Qty={qty} Avg=${avg_c:.4f} MktPrice=${mkt_p:.4f} UnrealizedPnL=${unr_pnl:+.2f}")

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        pass

    def updateAccountTime(self, timeStamp: str):
        pass

    def accountDownloadEnd(self, accountName: str):
        self._portfolio_event.set()

    def pnlSingle(self, reqId: int, pos: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float, value: float):
        """Real-time single position PnL callback from TWS reqPnLSingle."""
        pos_key = self._pnl_single_reqs.get(reqId)
        if not pos_key:
            return
        def _clean(val: float) -> float:
            try:
                v = float(val)
                return 0.0 if (abs(v) >= 1e100 or v != v) else v
            except Exception:
                return 0.0
        unr = _clean(unrealizedPnL)
        real_p = _clean(realizedPnL)
        val_clean = _clean(value)
        qty = float(pos or 0)
        mkt_p = 0.0
        if qty != 0 and abs(val_clean) > 0:
            if ":OPT:" in pos_key:
                mkt_p = round(abs(val_clean) / (abs(qty) * 100.0), 4)
            else:
                mkt_p = round(abs(val_clean) / abs(qty), 4)
        if mkt_p > 0:
            self._prices[pos_key] = mkt_p
        p_entry = self._portfolio.setdefault(pos_key, {})
        if mkt_p > 0:
            p_entry["market_price"] = mkt_p
        if abs(val_clean) > 0:
            p_entry["market_value"] = val_clean
        if abs(unr) > 0 or mkt_p > 0:
            p_entry["unrealized_pnl"] = unr
        p_entry["realized_pnl"] = real_p

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float = 0.0,
    ):
        """Called whenever an order status changes (Submitted, Filled, Cancelled, etc.)."""
        log_info(MODULE, f"[IB OrderStatus] ID={orderId} Status={status} Filled={filled} AvgPrice=${avgFillPrice:.2f}")
        status_info = {
            "order_id": orderId,
            "status": status.lower(),
            "filled": filled,
            "remaining": remaining,
            "avg_fill_price": avgFillPrice,
            "last_fill_price": lastFillPrice,
            "parent_id": parentId,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self._order_statuses[orderId] = status_info
        if self._order_callback:
            try:
                self._order_callback(orderId, status_info)
            except Exception as e:
                log_error(MODULE, f"Error in order callback for ID {orderId}: {e}")

    def set_order_callback(self, callback: Callable):
        """Register a callback function to receive orderStatus events."""
        self._order_callback = callback

    # ── Portfolio & Positions Callbacks ────────────────────

    def position(self, account: str, contract: "Contract", position: float, avgCost: float):
        """Called by TWS during reqPositions stream."""
        if not contract:
            return
        symbol = getattr(contract, "symbol", "").upper()
        if not symbol:
            return
        sec_type = str(getattr(contract, "secType", "STK") or "STK").upper()
        if sec_type == "OPT":
            right = str(getattr(contract, "right", "") or "").upper()
            strike = float(getattr(contract, "strike", 0.0) or 0.0)
            expiry = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "")
            pos_key = f"{symbol}:OPT:{expiry}:{strike}:{right}"
        else:
            pos_key = symbol

        log_info(MODULE, f"[IB Position] Account={account} Key={pos_key} (Type={sec_type}) Qty={position} AvgCost=${avgCost:.4f}")
        self._positions[pos_key] = {
            "account": account,
            "symbol": pos_key,
            "sec_type": sec_type,
            "underlying": symbol,
            "shares": float(position),
            "avg_cost": float(avgCost),
            "strike": float(getattr(contract, "strike", 0.0) or 0.0) if sec_type == "OPT" else None,
            "right": str(getattr(contract, "right", "") or "").upper() if sec_type == "OPT" else None,
            "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or "") if sec_type == "OPT" else None,
            "conid": getattr(contract, "conId", None),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    def positionEnd(self):
        """Called by TWS when all open positions have been sent."""
        log_info(MODULE, f"[IB PositionEnd] Positions sync finished. Total active symbols: {len(self._positions)}")
        self._positions_event.set()

    # ── Contract Details Callbacks & Resolver ─────────────

    def contractDetails(self, reqId: int, contractDetails):
        """Called by TWS with contract details."""
        if reqId not in self._contract_details:
            self._contract_details[reqId] = []
        self._contract_details[reqId].append(contractDetails)
        con = getattr(contractDetails, "contract", None)
        if con:
            log_info(MODULE, f"[IB ContractDetails] reqId={reqId} conId={getattr(con, 'conId', None)} symbol={getattr(con, 'symbol', '')} localSymbol={getattr(con, 'localSymbol', '')}")

    def contractDetailsEnd(self, reqId: int):
        """Called by TWS when contract details finished."""
        log_info(MODULE, f"[IB ContractDetailsEnd] reqId={reqId} matched={len(self._contract_details.get(reqId, []))}")
        evt = self._contract_details_events.get(reqId)
        if evt:
            evt.set()

    def resolve_contract(self, contract: "Contract", timeout: float = 5.0) -> Optional["Contract"]:
        """Resolve a partial contract into a fully qualified contract with conId."""
        req_id = int(time.time() * 1000) % 90000 + 10000
        evt = threading.Event()
        self._contract_details[req_id] = []
        self._contract_details_events[req_id] = evt
        try:
            self.reqContractDetails(req_id, contract)
            if evt.wait(timeout=timeout) and self._contract_details.get(req_id):
                matched = self._contract_details[req_id][0].contract
                log_info(MODULE, f"Successfully resolved contract {contract.symbol} -> conId {matched.conId}")
                return matched
            else:
                log_warning(MODULE, f"Contract resolution timed out or empty for {contract.symbol}")
        except Exception as e:
            log_warning(MODULE, f"Error resolving contract: {e}")
        finally:
            self._contract_details_events.pop(req_id, None)
            self._contract_details.pop(req_id, None)
        return None

    def _ensure_position_streams(self, pos_key: str, p_data: dict):
        """Subscribe open STK/OPT position to TWS reqMktData and reqPnLSingle for continuous live updates."""
        if not self.connected:
            return
        try:
            sec_type = str(p_data.get("sec_type") or "STK").upper()
            underlying = str(p_data.get("underlying") or pos_key.split(":")[0]).upper()
            conid = p_data.get("conid")
            acct = str(p_data.get("account") or (self.accounts[0] if self.accounts else ""))

            # 1. Subscribe reqPnLSingle by conId
            if conid and acct and int(conid) not in self._pnl_single_conids:
                req_id = self.get_next_order_id()
                self._pnl_single_reqs[req_id] = pos_key
                self._pnl_single_conids.add(int(conid))
                try:
                    self.reqPnLSingle(req_id, acct, "", int(conid))
                except Exception:
                    pass

            # 2. Subscribe reqMktData
            if pos_key not in self._mkt_data_subscribed:
                req_id = self.get_next_order_id()
                self._data_callbacks[req_id] = pos_key
                self._mkt_data_subscribed.add(pos_key)
                if sec_type == "OPT":
                    exp_s = str(p_data.get("expiry") or "")
                    stk_f = float(p_data.get("strike") or 0.0)
                    rgt_s = str(p_data.get("right") or "C")
                    contract = self.us_option_contract(underlying, exp_s, stk_f, rgt_s)
                    if conid:
                        contract.conId = int(conid)
                else:
                    contract = self.us_stock_contract(underlying)
                    if conid:
                        contract.conId = int(conid)
                self.reqMktData(req_id, contract, "", False, False, [])
        except Exception as e:
            log_warning(MODULE, f"Error subscribing streams for {pos_key}: {e}")

    def request_broker_positions(self, timeout: float = 6.0) -> Dict[str, dict]:
        """Request all open positions from TWS and enrich with real-time marketPrice & unrealizedPNL."""
        if not hasattr(self, "_last_valid_positions"):
            self._last_valid_positions = {}
        self._positions = {}
        self._positions_event.clear()
        self._positions_sync_ok = False
        try:
            try:
                self.reqMarketDataType(4)
            except Exception:
                pass
            self._ensure_account_updates()

            self.reqPositions()
            finished = self._positions_event.wait(timeout=timeout)
            self.cancelPositions()
            if not finished:
                log_warning(MODULE, f"[IB Positions] Timeout ({timeout}s) waiting for positionEnd; preserving last valid snapshot ({len(self._last_valid_positions)} items).")
                return dict(self._last_valid_positions)

            self._positions_sync_ok = True

            # Wait briefly if updatePortfolio has not arrived yet
            if self._positions and not self._portfolio:
                self._portfolio_event.wait(timeout=2.0)

            # Subscribe streams and merge portfolio / tick prices
            missing_price_keys = []
            for pos_key, p_data in self._positions.items():
                qty = float(p_data.get("shares") or 0.0)
                if qty == 0:
                    continue
                self._ensure_position_streams(pos_key, p_data)
                port_info = self._portfolio.get(pos_key) or {}
                mkt_p = float(port_info.get("market_price") or self._prices.get(pos_key) or 0.0)
                if mkt_p <= 0:
                    missing_price_keys.append(pos_key)

            # Wait up to 1.2s for initial ticks if any position still lacks a price
            if missing_price_keys:
                for _ in range(12):
                    time.sleep(0.1)
                    if all(
                        (float((self._portfolio.get(k) or {}).get("market_price") or self._prices.get(k) or 0.0) > 0)
                        for k in missing_price_keys
                    ):
                        break

            # Finalize market_price, market_value, and unrealized_pnl for every open position
            for pos_key, p_data in self._positions.items():
                qty = float(p_data.get("shares") or 0.0)
                if qty == 0:
                    continue
                sec_type = str(p_data.get("sec_type") or "STK").upper()
                underlying = str(p_data.get("underlying") or pos_key.split(":")[0]).upper()
                avg_c = float(p_data.get("avg_cost") or 0.0)
                port_info = self._portfolio.get(pos_key) or {}

                # Priority 1: Live tick from reqMktData / reqPnLSingle
                # Priority 2: TWS updatePortfolio market_price
                tick_p = float(self._prices.get(pos_key) or (self._prices.get(underlying) if sec_type == "STK" else 0.0) or 0.0)
                port_p = float(port_info.get("market_price") or 0.0)
                mkt_p = tick_p if tick_p > 0 else port_p

                # Priority 3: If TWS still reports 0 (e.g. weekend reset before market data server responds), fetch latest quote
                if mkt_p <= 0 and sec_type == "STK":
                    try:
                        import yfinance as yf
                        fi = yf.Ticker(underlying).fast_info
                        lp = float(getattr(fi, "last_price", 0.0) or 0.0)
                        if lp > 0:
                            mkt_p = round(lp, 4)
                            self._prices[pos_key] = mkt_p
                            self._prices[underlying] = mkt_p
                    except Exception:
                        pass

                if mkt_p <= 0:
                    mkt_p = round(avg_c / 100.0, 4) if sec_type == "OPT" else avg_c

                port_unr = float(port_info.get("unrealized_pnl") or 0.0)
                if sec_type == "OPT":
                    entry_deb = avg_c / 100.0 if avg_c > 0 else mkt_p
                    calc_unr = round((mkt_p - entry_deb) * 100.0 * qty, 2)
                    mkt_v = round(mkt_p * 100.0 * qty, 2)
                else:
                    calc_unr = round((mkt_p - avg_c) * qty, 2)
                    mkt_v = round(mkt_p * qty, 2)

                # Use TWS unrealized_pnl if valid and consistent, otherwise exact calculated PnL from live TWS price
                unr_pnl = calc_unr if (abs(mkt_p - (avg_c / 100.0 if sec_type == "OPT" else avg_c)) > 0.0001 and abs(port_unr) < 0.0001) else (port_unr if abs(port_unr) > 0.0001 else calc_unr)

                p_data["market_price"] = round(mkt_p, 4)
                p_data["market_value"] = round(float(port_info.get("market_value") or mkt_v), 2)
                p_data["unrealized_pnl"] = round(unr_pnl, 2)
                p_data["realized_pnl"] = round(float(port_info.get("realized_pnl") or 0.0), 2)

            self._last_valid_positions = dict(self._positions)
        except Exception as e:
            log_warning(MODULE, f"Error requesting positions from TWS: {e}")
            return dict(self._last_valid_positions)
        return self._positions

    # ── Historical Data Callbacks & Requester ──────────────

    def historicalData(self, reqId: int, bar):
        """Called when an individual historical bar arrives from TWS."""
        if reqId not in self._hist_bars:
            self._hist_bars[reqId] = []
        self._hist_bars[reqId].append({
            "date": bar.date,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume)
        })

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """Called when historical data stream completes."""
        n_bars = len(self._hist_bars.get(reqId, []))
        log_info(MODULE, f"[IB HistoricalDataEnd] reqId={reqId} loaded {n_bars} bars ({start} to {end})")
        if reqId in self._hist_events:
            self._hist_events[reqId].set()

    def request_historical_1h_bars(
        self,
        ticker: str,
        duration_str: str = "30 D",
        timeout: float = 6.0
    ):
        """
        Request historical 1-hour candles directly from TWS broker.
        Returns pd.DataFrame with index=date and columns ['open', 'high', 'low', 'close', 'volume']
        or None if not connected / timeout.
        """
        if not self.connected or not IB_AVAILABLE:
            return None

        try:
            import pandas as pd
            req_id = self.get_next_order_id()
            event = threading.Event()
            self._hist_bars[req_id] = []
            self._hist_events[req_id] = event

            contract = self.us_stock_contract(ticker)
            self.reqHistoricalData(
                reqId=req_id,
                contract=contract,
                endDateTime="",
                durationStr=duration_str,
                barSizeSetting="1 hour",
                whatToShow="TRADES",
                useRTH=1,
                formatDate=1,
                keepUpToDate=False,
                chartOptions=[]
            )

            finished = event.wait(timeout=timeout)
            bars = self._hist_bars.pop(req_id, [])
            self._hist_events.pop(req_id, None)

            if not finished or not bars:
                log_warning(MODULE, f"[IB History] Timeout ({timeout}s) or empty 1h bars from TWS for {ticker}")
                return None

            df = pd.DataFrame(bars)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
            return df
        except Exception as e:
            log_warning(MODULE, f"Error requesting historical bars from TWS for {ticker}: {e}")
            return None

    # ── Realtime 5-Second Bars Callbacks & Requester ──────

    def realtimeBar(
        self,
        reqId: int,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        wap: float,
        count: int
    ):
        """Called by TWS every 5 seconds with a new 5s bar."""
        bar_data = {
            "req_id": reqId,
            "time": time,
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": int(volume),
            "wap": float(wap),
            "count": int(count)
        }
        cb = self._realtime_bar_callbacks.get(reqId)
        if cb:
            try:
                cb(reqId, bar_data)
            except Exception as e:
                log_error(MODULE, f"Error in realtimeBar callback (reqId={reqId}): {e}")

    def request_realtime_5s_bars(
        self,
        ticker: str,
        callback: Callable,
        what_to_show: str = "TRADES",
        use_rth: bool = False
    ) -> int:
        """
        Subscribes to 5-second real-time bars from TWS.
        Returns reqId, or -1 if not connected.
        """
        if not self.connected or not IB_AVAILABLE:
            log_warning(MODULE, f"Cannot request 5s bars for {ticker}: TWS not connected")
            return -1

        try:
            req_id = self.get_next_order_id()
            self._realtime_bar_callbacks[req_id] = callback
            contract = self.us_stock_contract(ticker)
            self.reqRealTimeBars(req_id, contract, 5, what_to_show, use_rth, [])
            log_info(MODULE, f"Subscribed to 5s real-time bars for {ticker} (reqId={req_id})")
            return req_id
        except Exception as e:
            log_error(MODULE, f"Error requesting 5s bars for {ticker}: {e}")
            return -1

    def cancel_realtime_5s_bars(self, req_id: int):
        """Cancels an active 5-second real-time bar stream."""
        if not self.connected or not IB_AVAILABLE:
            return
        try:
            self.cancelRealTimeBars(req_id)
            self._realtime_bar_callbacks.pop(req_id, None)
            log_info(MODULE, f"Cancelled 5s real-time bars stream (reqId={req_id})")
        except Exception as e:
            log_warning(MODULE, f"Error cancelling 5s bars (reqId={req_id}): {e}")

    # ── Contract Builder ──────────────────────────────────

    @staticmethod
    def us_stock_contract(ticker: str) -> "Contract":
        """Create a Contract object for a US stock."""
        if not IB_AVAILABLE:
            raise RuntimeError("ibapi not installed")
        contract = Contract()
        contract.symbol = ticker.upper()
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    @staticmethod
    def us_option_contract(
        symbol: str,
        expiry: str,
        strike: float,
        right: str = "C",
        multiplier: str = "100",
        exchange: str = "SMART",
        trading_class: Optional[str] = None
    ) -> "Contract":
        """Create a Contract object for a US stock/ETF option."""
        if not IB_AVAILABLE:
            raise RuntimeError("ibapi not installed")
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = "OPT"
        contract.exchange = exchange
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = str(expiry).replace("-", "")
        contract.strike = float(strike)
        contract.right = right.upper()
        contract.multiplier = str(multiplier)
        if trading_class:
            contract.tradingClass = str(trading_class).upper()
        elif symbol.upper() == "SPY":
            contract.tradingClass = "SPY"
        return contract

    # ── Order Builder ─────────────────────────────────────

    def get_next_order_id(self) -> int:
        """Get the next valid order ID and increment."""
        oid = self.next_order_id
        self.next_order_id += 1
        return oid

    def create_bracket_order(
        self,
        action: str,
        qty: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> list:
        """
        Create a Bracket Order (entry + stop + target).
        
        Equivalent to Binance OCO:
        - When target fills → stop is cancelled
        - When stop fills → target is cancelled
        - All three are transmitted together

        Parameters
        ----------
        action       : 'BUY' or 'SELL'
        qty          : Number of shares
        entry_price  : Limit entry price
        stop_price   : ATR-based stop loss (NEVER a round number)
        target_price : Take profit target
        """
        if not IB_AVAILABLE:
            raise RuntimeError("ibapi not installed")

        parent_id = self.get_next_order_id()

        # Parent: Limit entry order
        parent = Order()
        parent.eTradeOnly = False
        parent.firmQuoteOnly = False
        parent.orderId = parent_id
        parent.action = action
        parent.orderType = "LMT"
        parent.totalQuantity = qty
        parent.lmtPrice = round(entry_price, 2)
        parent.transmit = False

        # Child 1: Stop Loss
        reverse_action = "SELL" if action == "BUY" else "BUY"

        stop_order = Order()
        stop_order.eTradeOnly = False
        stop_order.firmQuoteOnly = False
        stop_order.orderId = self.get_next_order_id()
        stop_order.action = reverse_action
        stop_order.orderType = "STP"
        stop_order.totalQuantity = qty
        stop_order.auxPrice = round(stop_price, 2)
        stop_order.parentId = parent_id
        stop_order.transmit = False

        # Child 2: Take Profit
        target_order = Order()
        target_order.eTradeOnly = False
        target_order.firmQuoteOnly = False
        target_order.orderId = self.get_next_order_id()
        target_order.action = reverse_action
        target_order.orderType = "LMT"
        target_order.totalQuantity = qty
        target_order.lmtPrice = round(target_price, 2)
        target_order.parentId = parent_id
        target_order.transmit = True  # Transmit all 3 together

        log_info(MODULE, f"Bracket order created: {action} {qty}x @ ${entry_price:.2f} "
                         f"SL=${stop_price:.2f} TP=${target_price:.2f}")

        return [parent, stop_order, target_order]

    def place_bracket_order(
        self,
        ticker: str,
        action: str,
        qty: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> dict:
        """
        Place a complete bracket order on IB TWS.
        
        Returns dict with order IDs.
        """
        if not self.connected:
            log_error(MODULE, "Cannot place order — not connected to TWS")
            return {"error": "not_connected"}

        contract = self.us_stock_contract(ticker)
        orders = self.create_bracket_order(
            action, qty, entry_price, stop_price, target_price
        )

        order_ids = []
        for order in orders:
            self.placeOrder(order.orderId, contract, order)
            order_ids.append(order.orderId)

        return {
            "parent_id": order_ids[0],
            "stop_id":   order_ids[1],
            "target_id": order_ids[2],
            "ticker":    ticker,
            "action":    action,
            "qty":       qty,
        }

    def req_mkt_data(self, ticker: str):
        """Request real-time market data for a ticker."""
        if not self.connected:
            return
        
        req_id = self.get_next_order_id() # Use same ID pool
        self._data_callbacks[req_id] = ticker.upper()
        contract = self.us_stock_contract(ticker)
        self.reqMktData(req_id, contract, "", False, False, [])
        log_info(MODULE, f"Market data requested for {ticker} (reqId={req_id})")

    # ── Status ────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get current connection status."""
        return {
            "connected":     self.connected,
            "next_order_id": self.next_order_id,
            "errors_count":  len(self._errors),
            "last_error":    self._errors[-1] if self._errors else None,
            "api_available": IB_AVAILABLE,
        }


# ── Singleton instance ───────────────────────────────────

_ib_instance: IBConnection | None = None


def get_ib_connection() -> IBConnection | None:
    """Get or create the singleton IB connection."""
    global _ib_instance
    if not IB_AVAILABLE:
        return None
    if _ib_instance is None:
        _ib_instance = IBConnection()
    return _ib_instance
# ── IBProvider Wrapper (Unified Interface) ────────────────
class IBProvider:
    """
    Async-friendly wrapper for IBConnection to be used by
    Stocks TP Manager and other services.
    """
    def __init__(self):
        self.conn = get_ib_connection()

    async def connect(self):
        if not self.conn:
            raise RuntimeError("IB API not available")
        if not self.conn.connected:
            return self.conn.connect_tws()
        return True

    async def disconnect(self):
        if self.conn:
            self.conn.disconnect_tws()

    async def place_order(
        self,
        ticker: str,
        direction: str,
        shares: int,
        order_type: str = 'market',
        price: float = None,
        reason: str = ''
    ) -> dict:
        """
        Simplified order placement for exits/TPs.
        """
        if not self.conn or not self.conn.connected:
            return {"success": False, "error": "Not connected to IB"}

        contract = self.conn.us_stock_contract(ticker)
        order = Order()
        order.eTradeOnly = False
        order.firmQuoteOnly = False
        order.action = direction.upper() # BUY/SELL
        order.totalQuantity = int(shares)
        
        if order_type.lower() == 'market':
            order.orderType = "MKT"
        elif order_type.lower() == 'limit' and price:
            order.orderType = "LMT"
            order.lmtPrice = round(price, 2)
        else:
            return {"success": False, "error": f"Unsupported order type: {order_type}"}

        order.transmit = True
        order_id = self.conn.get_next_order_id()
        
        log_info(MODULE, f"🚀 Executing {order_type} {direction} {shares}x {ticker} (Reason: {reason})")
        self.conn.placeOrder(order_id, contract, order)
        
        return {
            "success": True,
            "order_id": order_id,
            "ticker": ticker,
            "shares": shares,
            "price": price
        }

    async def get_current_price(self, ticker: str) -> float:
        """
        Get current price from IB memory cache. 
        If not present, trigger a request and wait briefly.
        """
        if not self.conn or not self.conn.connected:
            return 0.0
        
        ticker = ticker.upper()
        if ticker not in self.conn._prices:
            self.conn.req_mkt_data(ticker)
            # Wait up to 2 seconds for first tick
            for _ in range(20):
                await asyncio.sleep(0.1)
                if ticker in self.conn._prices:
                    break
        
        return self.conn._prices.get(ticker, 0.0)

    async def get_multiple_prices(self, tickers: list[str]) -> dict[str, float]:
        """
        Request multiple prices in parallel and wait briefly for them to populate.
        """
        if not self.conn or not self.conn.connected:
            return {t: 0.0 for t in tickers}
        
        missing = [t.upper() for t in tickers if t.upper() not in self.conn._prices]
        for t in missing:
            self.conn.req_mkt_data(t)
        
        if missing:
            # Wait up to 1.5 seconds for results
            for _ in range(15):
                await asyncio.sleep(0.1)
                if all(t.upper() in self.conn._prices for t in missing):
                    break
        
        return {t.upper(): self.conn._prices.get(t.upper(), 0.0) for t in tickers}

    def get_historical_1h_bars(self, ticker: str, duration_str: str = "30 D", timeout: float = 6.0):
        """Request 1H candles from TWS broker connection."""
        if not self.conn or not self.conn.connected:
            return None
        return self.conn.request_historical_1h_bars(ticker, duration_str=duration_str, timeout=timeout)
