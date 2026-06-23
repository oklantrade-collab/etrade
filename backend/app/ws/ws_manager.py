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
        """Initialize and start the WebSocket connection with robust reconnection."""
        self._running = True
        
        # Combine streams for all symbols
        streams = [f"{s}@ticker" for s in self.symbols]
        
        if not streams:
            log_warning(MODULE, "No symbols provided for WebSocket Monitor. Exiting gracefully.")
            self._running = False
            return
            
        log_info(MODULE, f"Starting WebSocket Speed 1 for symbols: {self.symbols}")
        
        while self._running:
            client = None
            try:
                client = await AsyncClient.create(self.api_key, self.api_secret, testnet=self.testnet)
                bsm = BinanceSocketManager(client)
                
                async with bsm.multiplex_socket(streams) as ms:
                    while self._running:
                        try:
                            res = await ms.recv()
                            if res:
                                await self._process_message(res)
                        except Exception as recv_err:
                            err_str = str(recv_err)
                            if "Read loop has been closed" in err_str or "disconnect" in err_str.lower():
                                log_warning(MODULE, f"WebSocket read error (will reconnect): {recv_err}")
                            else:
                                log_error(MODULE, f"WebSocket read error (will reconnect): {recv_err}")
                            break  # Break inner loop to exit context manager and reconnect
            except Exception as e:
                err_str = str(e)
                if "502" in err_str or "503" in err_str or "504" in err_str or "Gateway" in err_str or "disconnect" in err_str or "timed out" in err_str:
                    log_warning(MODULE, f"Transient WebSocket error (Bad Gateway/Disconnect/Timeout): {e}. Retrying gracefully.")
                else:
                    log_error(MODULE, f"WebSocket connection/manager error: {e}")
            
            if client:
                try:
                    await client.close_connection()
                except Exception as close_err:
                    log_warning(MODULE, f"Error closing connection: {close_err}")
                    
            if self._running:
                wait_time = min(5 * (self._retry_count if hasattr(self, '_retry_count') else 1), 60)
                self._retry_count = (self._retry_count + 1) if hasattr(self, '_retry_count') else 2
                log_info(MODULE, f"Attempting WebSocket reconnection in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                
            # If we successfully connected and received data before failing, reset retry count
            # but since we are just inside the while loop, we can reset it in the inner loop


    async def _process_message(self, msg: dict):
        """
        Process incoming ticker/price messages.
        Logic: compare real-time price against 15m basis or last ATR.
        """
        self._retry_count = 1  # Reset retry count
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
        from app.core.position_monitor import _execute_paper_close
        from app.core.crypto_symbols import normalize_crypto_symbol
        
        # --- 1. HARD CAP & SL MONITORING (SPEED 1) ---
        # Checks every price tick for open positions to trigger emergency exits
        norm_symbol = normalize_crypto_symbol(symbol)
        open_positions = BOT_STATE.get_positions_by_symbol(symbol)
        
        if open_positions:
            sb = get_supabase()
            for pos in open_positions:
                entry = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                sl = float(pos.get('sl_price') or pos.get('stop_loss') or 0)
                side = str(pos.get('side', 'long')).lower()
                is_long = side in ('long', 'buy')
                
                # A. Check Stop Loss Hit (Direct breach)
                # Skip tight SL check if EREP is already active or in recovery mode
                if pos.get('erep_active') or pos.get('erep_phase', 0) > 0 or pos.get('recovery_mode'):
                    pass
                else:
                    sl_hit = (is_long and price <= sl) or (not is_long and price >= sl)
                    if sl > 0 and sl_hit:
                        sl_type = str(pos.get('sl_type') or '')
                        if sl_type.startswith('trailing'):
                            log_warning(MODULE, f"EMERGENCY SL HIT (trailing) for {symbol}! Price {price} reached SL {sl}. Closing...")
                            await _execute_paper_close(pos, price, 'emergency_sl_ws', sb)
                            continue
                        else:
                            log_warning(MODULE, f"EMERGENCY SL HIT for {symbol}! Price {price} reached SL {sl}. Routing to EREP Phase 1...")
                            from app.core.crypto_symbols import resolve_crypto_position_quantity
                            qty = resolve_crypto_position_quantity(sb, pos)
                            
                            try:
                                sb.table('positions').update({
                                    'erep_phase': 1,
                                    'erep_p1_price': entry,
                                    'erep_q1': qty,
                                    'erep_market_type': 'crypto_futures',
                                }).eq('id', pos['id']).execute()
                                
                                pos['erep_phase'] = 1
                                pos['erep_p1_price'] = entry
                                pos['erep_q1'] = qty
                                pos['erep_market_type'] = 'crypto_futures'
                            except Exception as db_err:
                                log_error(MODULE, f"Error routing {symbol} to EREP Phase 1: {db_err}")
                            continue 
                    
                # B. Check Hard Cap (-5% from entry as ultimate safety net)
                pnl_pct = ((price - entry) / entry * 100) if is_long else ((entry - price) / entry * 100)
                if pnl_pct <= -5.0:
                    log_warning(MODULE, f"HARD CAP BREACH for {symbol}! PnL {pnl_pct:.2f}% <= -5%. Forced closure.")
                    await _execute_paper_close(pos, price, 'hard_cap_ws', sb)
                    continue
                    
                # C. EREP 60-Minute Timeout: force close if recovery is taking too long
                erep_active = pos.get('erep_active', False)
                erep_activated_at = pos.get('erep_activated_at')
                if erep_active and erep_activated_at:
                    from datetime import datetime, timezone
                    try:
                        if isinstance(erep_activated_at, str):
                            activated_dt = datetime.fromisoformat(erep_activated_at.replace('Z', '+00:00'))
                        else:
                            activated_dt = erep_activated_at
                        elapsed = (datetime.now(timezone.utc) - activated_dt).total_seconds()
                        if elapsed >= 3600:  # 60 minutos
                            log_warning(MODULE, 
                                f"EREP TIMEOUT for {symbol}! {elapsed:.0f}s elapsed (>3600s). "
                                f"PnL={pnl_pct:.2f}%. Forcing closure to limit loss.")
                            await _execute_paper_close(pos, price, 'erep_timeout_60m', sb)
                            continue
                    except Exception as dt_err:
                        log_warning(MODULE, f"Error parsing erep_activated_at for {symbol}: {dt_err}")

                # D. Check Sharp Drop from Peak (ONLY for non-EREP positions)
                # EREP positions: SKIP sharp_drop — let the dip happen, wait for 5min recovery
                # Normal positions: 3% drop triggers close
                if not erep_active:
                    peak = float(pos.get('highest_price_reached') or entry if is_long else pos.get('lowest_price_reached') or entry)
                    if peak > 0:
                        drop_from_peak = ((peak - price) / peak * 100) if is_long else ((price - peak) / peak * 100)
                        if drop_from_peak >= 3.0:
                            log_warning(MODULE, f"SHARP DROP for {symbol}! Price dropped {drop_from_peak:.2f}% from peak {peak}. Routing to EREP Phase 1...")
                            from app.core.crypto_symbols import resolve_crypto_position_quantity
                            qty = resolve_crypto_position_quantity(sb, pos)
                            
                            try:
                                sb.table('positions').update({
                                    'erep_phase': 1,
                                    'erep_p1_price': entry,
                                    'erep_q1': qty,
                                    'erep_market_type': 'crypto_futures',
                                }).eq('id', pos['id']).execute()
                                
                                pos['erep_phase'] = 1
                                pos['erep_p1_price'] = entry
                                pos['erep_q1'] = qty
                                pos['erep_market_type'] = 'crypto_futures'
                            except Exception as db_err:
                                log_error(MODULE, f"Error routing {symbol} to EREP Phase 1 on Sharp Drop: {db_err}")
                            continue

        # --- 2. ATR SPIKE MONITORING (Existing) ---
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
