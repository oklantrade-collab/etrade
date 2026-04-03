"""
eTrade v3 — WebSocket Manager (Speed 1)
High-frequency emergency monitoring via Binance WebSocket.
Focuses on capturing real-time price spikes (ATR) that occur between 5m/15m cycles.
"""
import asyncio
import json
import threading
from datetime import datetime, timezone

from binance import AsyncClient, BinanceSocketManager
from app.core.logger import log_info, log_error, log_warning
from app.strategy.market_regime import check_emergency

MODULE = "ws_manager"

class WebSocketManager:
    """
    Manages real-time data streams for emergency monitoring.
    Speed 1: Only monitors for ATR spikes or extreme price deviations.
    """
    def __init__(self, symbols: list[str], api_key: str, api_secret: str, testnet: bool = True):
        self.symbols = [s.replace("/", "").lower() for s in symbols]
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._running = False
        self._loop = None
        self._last_processed_price = {}

    async def start(self):
        """Initialize and start the WebSocket connection."""
        self._running = True
        client = await AsyncClient.create(self.api_key, self.api_secret, testnet=self.testnet)
        bsm = BinanceSocketManager(client)
        
        # Combine streams for all symbols
        # For simplicity in Sprint 1, we monitor the 1m candle or ticker
        streams = [f"{s}@ticker" for s in self.symbols]
        
        log_info(MODULE, f"Starting WebSocket Speed 1 for symbols: {self.symbols}")
        
        async with bsm.multiplex_socket(streams) as ms:
            while self._running:
                try:
                    res = await ms.recv()
                    if res:
                        await self._process_message(res)
                except Exception as e:
                    log_error(MODULE, f"WebSocket error: {e}")
                    await asyncio.sleep(5) # Auto-reconnect delay
                    
        await client.close_connection()

    async def _process_message(self, msg: dict):
        """
        Process incoming ticker/price messages.
        Logic: compare real-time price against 15m basis or last ATR.
        """
        data = msg.get('data', {})
        symbol_raw = data.get('s')
        if not symbol_raw:
            return
            
        # Map back to standard symbol name
        symbol = f"{symbol_raw[:-4]}/{symbol_raw[-4:]}".upper() # e.g. BTCUSDT -> BTC/USDT
        price = float(data.get('c', 0))
        
        if price <= 0:
            return

        from app.core.memory_store import MEMORY_STORE, BOT_STATE
        from app.core.supabase_client import get_supabase
        
        # CORRECT LOGIC: Compare Current ATR (last closed) vs Average ATR 20
        mem = MEMORY_STORE.get(symbol, {})
        current_atr = mem.get('current_atr', 0.0)
        avg_atr_20 = mem.get('avg_atr_20', 0.0)
        
        if avg_atr_20 > 0:
            atr_ratio = current_atr / avg_atr_20
            
            # Threshold from config or default (Requirement 4.2: 2.0x)
            threshold = BOT_STATE.config_cache.get("atr_emergency_mult", 2.0)
            
            if atr_ratio > threshold:
                log_warning(MODULE, f"EMERGENCY TRIGGERED for {symbol}! ATR Spike: {atr_ratio:.2f}x average")
                BOT_STATE.emergency[symbol] = True
                # Update global state
                try:
                    sb = get_supabase()
                    sb.table("bot_global_state").update({
                        "emergency_mode": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", 1).execute()
                except Exception as e:
                    log_error(MODULE, f"Failed to set global emergency flag: {e}")

        # Simple throttling for ticker logs
        if symbol not in self._last_processed_price or abs(price - self._last_processed_price[symbol]) / price > 0.005:
            self._last_processed_price[symbol] = price

    def stop(self):
        self._running = False

def run_ws_monitor(symbols: list[str], api_key: str, api_secret: str, testnet: bool = True):
    """Entry point for the WebSocket background thread."""
    manager = WebSocketManager(symbols, api_key, api_secret, testnet)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(manager.start())
    except KeyboardInterrupt:
        manager.stop()
    finally:
        loop.close()

if __name__ == "__main__":
    # Test symbols
    test_symbols = ["BTC/USDT", "ETH/USDT"]
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    run_ws_monitor(
        test_symbols, 
        os.getenv("BINANCE_API_KEY", ""), 
        os.getenv("BINANCE_SECRET", ""), 
        os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    )
