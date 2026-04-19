import asyncio
import sys
import os
import time

# Add parent directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.ib_provider import IB_AVAILABLE, get_ib_connection
from app.core.logger import log_info

async def test_api_connection():
    print("=" * 60)
    print("  eTrader v4.5 - IB CONNECTION TEST")
    print("=" * 60)
    
    if not IB_AVAILABLE:
        print("ERROR: IB API (ibapi) is not available or not installed.")
        return

    # Use environment variables
    host = os.getenv('IB_HOST', '127.0.0.1')
    port = int(os.getenv('IB_PORT', '7497'))
    client_id = int(os.getenv('IB_CLIENT_ID', '77'))

    print(f"Attempting to connect to IB TWS/Gateway...")
    print(f"   IP: {host}")
    print(f"   Port: {port}")
    print(f"   Client ID: {client_id}")
    print()

    try:
        ib_conn = get_ib_connection()
        if not ib_conn:
            print("ERROR: Could not get IB connection instance.")
            return

        # Try to connect
        connected = ib_conn.connect_tws(host=host, port=port, client_id=client_id)
        
        if connected:
            status = ib_conn.get_status()
            print("CONNECTION SUCCESSFUL!")
            print(f"   Connected: {status['connected']}")
            print(f"   Next Order ID: {status['next_order_id']}")
            
            # Give it a second to receive potential messages
            await asyncio.sleep(2)
            
            ib_conn.disconnect_tws()
            print("\nDisconnected safely.")
        else:
            print("CONNECTION FAILED: Could not establish connection to TWS/Gateway.")
            print("   Make sure TWS is open, API is enabled, and IP/Port are correct.")
            print("   Also check 'Allow connections from localhost only' is disabled in TWS.")
    except Exception as e:
        print(f"ERROR DURING CONNECTION: {e}")

    print("=" * 60)

if __name__ == "__main__":
    from dotenv import load_dotenv
    # Explicitly load .env from backend folder
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    asyncio.run(test_api_connection())
