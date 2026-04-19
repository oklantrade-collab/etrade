import os
import sys
import time
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Load environment variables (needed for logging)
from dotenv import load_dotenv
load_dotenv('backend/.env')

from app.core.logger import log_info, log_error, log_warning
from app.data.ib_provider import IBConnection, IB_AVAILABLE

def place_manual_market_buy(ticker, qty):
    if not IB_AVAILABLE:
        print("ERROR: ibapi not installed")
        return

    ib = IBConnection()
    
    # Try ports
    ports = [7497, 7496]
    connected = False
    for port in ports:
        print(f"Attempting to connect to IB on port {port}...")
        if ib.connect_tws(port=port):
            connected = True
            break
    
    if not connected:
        print("WARNING: Could not connect to IB TWS. Proceeding with PURE PAPER execution (Supabase records only).")
    
    try:
        if connected:
            from ibapi.order import Order
            contract = ib.us_stock_contract(ticker)
            
            order = Order()
            order.action = "BUY"
            order.orderType = "MKT"
            order.totalQuantity = qty
            order.transmit = True
            
            # Wait a moment for order ID
            time.sleep(1)
            order_id = ib.get_next_order_id()
            
            print(f"SUCCESS: Placing MARKET BUY for {qty} shares of {ticker} (Order ID: {order_id})")
            ib.placeOrder(order_id, contract, order)
            time.sleep(2)
        
        # Register in Supabase as a manual order
        try:
            from app.core.supabase_client import get_supabase
            sb = get_supabase()
            now = datetime.now(timezone.utc).isoformat()
            
            # Get current price
            import yfinance as yf
            price = yf.Ticker(ticker).fast_info['lastPrice']
            
            sb.table("stocks_orders").insert({
                "ticker": ticker,
                "rule_code": "S01",
                "order_type": "market",
                "direction": "buy",
                "shares": qty,
                "market_price": price,
                "status": "filled",
                "filled_price": price,
                "filled_at": now,
                "created_at": now
            }).execute()
            
            # Open position
            from app.stocks.stocks_order_executor import _open_or_update_position
            _open_or_update_position(ticker, price, qty, "PRO_BUY_MKT")
            
            print(f"SUCCESS: Order registered in Supabase and position opened/updated at ${price:.2f}.")
        except Exception as e:
            print(f"ERROR: Supabase registration failed: {e}")
            
    finally:
        if connected:
            ib.disconnect_tws()

if __name__ == "__main__":
    place_manual_market_buy("ORC", 100)
