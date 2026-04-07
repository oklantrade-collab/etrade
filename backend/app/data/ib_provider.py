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
import threading
from typing import Optional, Callable
from datetime import datetime, timezone

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
        host = host or os.getenv("IB_HOST", "127.0.0.1")
        port = port or int(os.getenv("IB_PORT", "7497"))  # 7497=paper, 7496=live
        client_id = client_id or int(os.getenv("IB_CLIENT_ID", "1"))

        try:
            self.connect(host, port, client_id)
            
            # Start event loop in background thread
            self._thread = threading.Thread(
                target=self.run, daemon=True, name="ib-event-loop"
            )
            self._thread.start()

            # Wait for connection confirmation
            timeout = 10
            start = time.time()
            while not self.connected and (time.time() - start) < timeout:
                time.sleep(0.1)

            if self.connected:
                log_info(MODULE, f"Connected to IB TWS at {host}:{port} "
                                 f"(client_id={client_id})")
                return True
            else:
                log_error(MODULE, f"Connection timeout to IB TWS at {host}:{port}")
                return False

        except Exception as e:
            log_error(MODULE, f"Failed to connect to IB TWS: {e}")
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
            log_error(MODULE, f"[IB Error {errorCode}] reqId={reqId}: {errorString}")

    def connectionClosed(self):
        """Called when connection is lost."""
        self.connected = False
        log_warning(MODULE, "IB TWS connection closed")

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
        parent.orderId = parent_id
        parent.action = action
        parent.orderType = "LMT"
        parent.totalQuantity = qty
        parent.lmtPrice = round(entry_price, 2)
        parent.transmit = False

        # Child 1: Stop Loss
        reverse_action = "SELL" if action == "BUY" else "BUY"

        stop_order = Order()
        stop_order.orderId = self.get_next_order_id()
        stop_order.action = reverse_action
        stop_order.orderType = "STP"
        stop_order.totalQuantity = qty
        stop_order.auxPrice = round(stop_price, 2)
        stop_order.parentId = parent_id
        stop_order.transmit = False

        # Child 2: Take Profit
        target_order = Order()
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
