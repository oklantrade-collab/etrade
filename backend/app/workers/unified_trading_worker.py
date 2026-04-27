"""
eTrader v2 — Unified Trading Worker
Main pipeline: fetches data, calculates indicators, detects spikes,
scores with MTF, analyses sentiment, and generates trading signals.
Processes symbols in parallel using ThreadPoolExecutor.
"""
import sys
import os
import time
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings, DEFAULT_CONFIG, EXCLUDED_SYMBOLS
from app.core.supabase_client import get_supabase, get_system_config, get_risk_config
from app.core.logger import log_info, log_warning, log_error, log_debug
from app.analysis.data_fetcher import fetch_all_timeframes, get_top_symbols, to_internal_symbol
from app.analysis.technical_indicators import calculate_all_timeframes
from app.strategy.volume_spike import detect_spike
from app.strategy.mtf_scorer import calculate_mtf_score
from app.strategy.signal_generator import generate_signal
from app.sentiment.gemini_sentiment import get_sentiment
from app.analysis.candle_patterns import detect_patterns

from app.strategy.risk_manager import validate_signal, check_daily_loss_at_cycle_start
from app.execution import binance_connector, order_manager, oco_builder
from app.execution.binance_connector import get_symbol_info_cached
from app.workers import alerts_service

MODULE = "pipeline"

def sync_closed_positions(supabase, binance_client):
    try:
        open_positions = supabase.table('positions').select('*, orders(oco_list_client_id, symbol)').eq('status', 'open').execute().data
        if not open_positions: return

        for position in open_positions:
            symbol_binance = position['symbol'].replace('/', '')
            oco_list_id = position.get('orders', {}).get('oco_list_client_id')
            
            if not oco_list_id:
                continue
            
            oco_status = binance_client.get_order_list(orderListId=int(oco_list_id))
            list_order_status = oco_status.get('listOrderStatus', '')
            
            if list_order_status == 'ALL_DONE':
                orders_in_oco = oco_status.get('orders', [])
                close_reason = 'UNKNOWN'
                realized_pnl = 0.0
                fill_price = position['entry_price']
                
                for oco_order in orders_in_oco:
                    order_detail = binance_client.get_order(symbol=symbol_binance, orderId=oco_order['orderId'])
                    if order_detail['status'] == 'FILLED':
                        fill_price = float(order_detail.get('avgPrice', order_detail.get('price', 0)))
                        order_type = order_detail.get('type', '')
                        
                        if 'STOP' in order_type:
                            close_reason = 'SL_HIT'
                        elif order_type == 'LIMIT_MAKER':
                            close_reason = 'TP_HIT'
                        
                        size = position['size']
                        entry = position['entry_price']
                        if position['side'] == 'LONG':
                            realized_pnl = (fill_price - entry) * size
                        else:
                            realized_pnl = (entry - fill_price) * size
                        break
                
                supabase.table('positions').update({
                    'status': 'closed',
                    'close_reason': close_reason,
                    'realized_pnl': round(realized_pnl, 4),
                    'current_price': fill_price,
                    'unrealized_pnl': 0.0,
                    'closed_at': datetime.now(timezone.utc).isoformat()
                }).eq('id', position['id']).execute()

                # ── REGISTRAR PN EN CAPITAL ACUMULADO (Interés Compuesto) ──
                try:
                    from app.core.capital_manager import register_realized_pnl
                    register_realized_pnl('crypto', realized_pnl)
                except Exception as cap_e:
                    log_warning(MODULE, f"Error updating accumulated capital: {cap_e}")
                
                if position.get('order_id'):
                    supabase.table('orders').update({
                        'status': close_reason.lower(),
                        'closed_at': datetime.now(timezone.utc).isoformat()
                    }).eq('id', position['order_id']).execute()
                
                emoji = '✅' if close_reason == 'TP_HIT' else '🛑'
                supabase.table('alert_events').insert({
                    'event_type': close_reason.lower(),
                    'symbol': position['symbol'],
                    'message': f"{emoji} {close_reason}: {position['symbol']} | PnL: {'+'if realized_pnl>=0 else ''}{realized_pnl:.2f} USDT",
                    'severity': 'info',
                    'data': { 'position_id': position['id'], 'realized_pnl': realized_pnl }
                }).execute()
                
                alerts_service.send_position_closed_alert(position, close_reason, realized_pnl)
                log_info(MODULE, f"{position['symbol']}: {close_reason} | PnL: {realized_pnl:+.2f} USDT")
    except Exception as e:
        log_error(MODULE, f"Error en sync_closed_positions: {e}")


def _create_cycle() -> str | None:
    """Create a new cron_cycle record, return its UUID."""
    sb = get_supabase()
    try:
        result = sb.table("cron_cycles").insert({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        log_error(MODULE, f"Failed to create cycle: {e}")
    return None


def _update_cycle(
    cycle_id: str,
    symbols_analyzed: int,
    spikes_detected: int,
    signals_generated: int,
    orders_executed: int,
    errors: int,
    duration_seconds: float,
) -> None:
    """Update the cron_cycle record with final stats."""
    sb = get_supabase()
    status = "success" if errors == 0 else "partial_error"
    try:
        sb.table("cron_cycles").update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "symbols_analyzed": symbols_analyzed,
            "spikes_detected": spikes_detected,
            "signals_generated": signals_generated,
            "orders_executed": orders_executed,
            "errors": errors,
            "status": status,
        }).eq("id", cycle_id).execute()
    except Exception as e:
        log_error(MODULE, f"Failed to update cycle {cycle_id}: {e}")


def _load_config() -> dict:
    """Load system_config from Supabase, fall back to defaults."""
    try:
        config = get_system_config()
        # Merge with defaults for any missing keys
        merged = {**DEFAULT_CONFIG, **config}
        return merged
    except Exception as e:
        log_warning(MODULE, f"Failed to load system_config, using defaults: {e}")
        return DEFAULT_CONFIG.copy()


def _load_excluded_symbols(config: dict) -> list[str]:
    """Load excluded symbols from config, fall back to defaults."""
    excluded = config.get("excluded_symbols")
    if isinstance(excluded, list):
        return excluded
    return EXCLUDED_SYMBOLS


def _process_symbol(
    symbol: str,
    config: dict,
    cycle_id: str | None,
    counters: dict,
    lock: threading.Lock,
    binance_client,
    risk_config: dict
) -> None:
    """
    Process a single symbol through the entire pipeline:
    1. Fetch candles for 6 timeframes
    2. Calculate indicators
    3. Detect volume spike on 15m
    4-9. MTF scoring, patterns, sentiment, signal generation
    """
    try:
        # ── Step 5a: Fetch all 6 timeframes ──
        all_candles = fetch_all_timeframes(symbol, cycle_id)
        if all_candles is None:
            log_warning(
                MODULE,
                f"{symbol}: Skipped (sanity check failed or no data)",
                cycle_id=cycle_id,
            )
            return

        # ── Step 5b: Calculate indicators for each timeframe ──
        all_indicators = calculate_all_timeframes(all_candles, symbol, cycle_id)

        # ── Step 5c: Volume Spike Detection on 15m ──
        if "15m" not in all_indicators:
            log_debug(
                MODULE,
                f"{symbol}: No 15m indicators available, skipping spike detection",
                cycle_id=cycle_id,
            )
            return

        spike = detect_spike(
            all_candles.get("15m"),
            all_indicators["15m"],
            config,
            cycle_id,
        )

        if spike is None:
            # No actionable spike — log and continue
            vol = float(all_candles["15m"].iloc[-1]["volume"]) if "15m" in all_candles else 0
            vol_sma = all_indicators["15m"].get("volume_sma_20", 0)
            ratio = vol / vol_sma if vol_sma and vol_sma > 0 else 0
            log_info(
                MODULE,
                f"{symbol}: No spike detected. ratio={ratio:.2f}x",
                {"symbol": symbol, "spike_ratio": round(ratio, 4)},
                cycle_id,
            )
            return

        # ── HAY SPIKE ──
        with lock:
            counters["spikes"] += 1

        log_info(
            MODULE,
            f"{symbol}: {spike['direction']} spike x{spike['spike_ratio']:.2f}",
            {
                "symbol": symbol,
                "direction": spike["direction"],
                "spike_ratio": spike["spike_ratio"],
            },
            cycle_id,
        )

        # ════════════════════════════════════════════════════
        # STEP 6 — MTF Scoring
        # ════════════════════════════════════════════════════
        log_info(
            MODULE,
            f"{symbol}: Calculating MTF score...",
            cycle_id=cycle_id,
        )

        mtf_result = calculate_mtf_score(
            symbol=symbol,
            all_indicators=all_indicators,
            spike_direction=spike["direction"],
            cycle_id=cycle_id,
        )

        log_info(
            "mtf_scorer",
            f"{symbol}: MTF score={mtf_result['score']} | "
            f"votos={mtf_result['votes']} | "
            f"alineación={mtf_result['alignment']}",
            cycle_id=cycle_id,
        )

        # ════════════════════════════════════════════════════
        # STEP 7 — Candle Pattern Detection
        # ════════════════════════════════════════════════════
        patterns = detect_patterns(
            all_candles.get("15m"), symbol, "15m", cycle_id
        )
        if patterns:
            log_info(
                "patterns",
                f"{symbol}: Patrones detectados: "
                f"{[p['pattern_name'] for p in patterns]}",
                cycle_id=cycle_id,
            )

        # ════════════════════════════════════════════════════
        # STEP 8 — Sentiment Analysis with Gemini
        # ════════════════════════════════════════════════════
        # Only call Gemini if MTF score passes 50% of threshold
        # to avoid wasting API quota on signals that won't pass
        threshold = float(config.get("mtf_signal_threshold", 0.65))
        half_threshold = threshold * 0.5

        if abs(mtf_result["score"]) >= half_threshold:
            sentiment = get_sentiment(symbol, cycle_id)
            log_info(
                "sentiment",
                f"{symbol}: Sentiment={sentiment['sentiment_score']} | "
                f"Adjustment={sentiment['adjustment']}",
                cycle_id=cycle_id,
            )
        else:
            sentiment = {
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "key_factors": ["score_too_low_skip_gemini"],
                "adjustment": 0.0,
                "headlines_count": 0,
            }

        # ════════════════════════════════════════════════════
        # STEP 9 — Generate Final Signal
        # ════════════════════════════════════════════════════
        signal = generate_signal(
            symbol=symbol,
            spike=spike,
            mtf_result=mtf_result,
            sentiment=sentiment,
            all_indicators=all_indicators,
            cycle_id=cycle_id,
            config=config,
        )

        if signal is None:
            return

        log_info(
            "signal_generator",
            f"{symbol}: Señal={signal['signal_type']} | "
            f"Score={signal['score_final']} | "
            f"SL={signal['stop_loss']} | TP={signal['take_profit']}",
            cycle_id=cycle_id,
        )

        if signal.get("should_execute"):
            sb = get_supabase()
            from app.core.position_sizing import calculate_position_size
            
            # PASO 10: Calcular sizing basado en capital_config (NO en balance real)
            sizing = calculate_position_size(
                symbol       = symbol,
                entry_price  = signal['entry_price'],
                sl_price     = signal['stop_loss'],
                market_type  = 'crypto_futures',
                trade_number = 1,  # T1 inicial
                regime       = mtf_result.get('regime', 'riesgo_medio'),
                supabase     = sb
            )
            
            if not sizing:
                log_error(MODULE, f"{symbol}: Error calculating position sizing")
                return

            # PASO 11: Construir OCO Params usando la cantidad calculada
            binance_client_pass = binance_client
            symbol_binance = signal['symbol'].replace('/', '')
            symbol_info = get_symbol_info_cached(binance_client_pass, symbol_binance)
            
            oco_params = oco_builder.build_oco_params(
                signal=signal,
                balance_usdt=sizing['capital_base'], # Simulamos balance como el capital_base
                symbol_info=symbol_info,
                risk_config=risk_config
            )
            
            if oco_params:
                # Forzar la cantidad calculada por nuestro módulo de sizing
                oco_params['quantity'] = sizing['quantity']
                oco_params['order_value_usdt'] = sizing['nocional']

            if oco_params is None:
                sb.table('trading_signals').update({
                    'status': 'rejected',
                    'rejection_reason': 'OCO_PARAMS_CALCULATION_FAILED'
                }).eq('id', signal['signal_id']).execute()
                return

            log_info(MODULE, f"{symbol}: OCO params -> qty={oco_params['quantity']} | SL=${oco_params['stop_loss']:,.4f} | TP=${oco_params['take_profit']:,.4f} | Valor=${oco_params['order_value_usdt']:,.2f}", cycle_id=cycle_id)

            risk_result = validate_signal(
                signal=signal,
                oco_params=oco_params,
                risk_config=risk_config,
                supabase_client=sb
            )
            
            if not risk_result['approved']:
                sb.table('trading_signals').update({
                    'status': 'rejected',
                    'rejection_reason': risk_result['reason']
                }).eq('id', signal['signal_id']).execute()
                log_warning(MODULE, f"{symbol}: Señal RECHAZADA -> {risk_result['reason']}", cycle_id=cycle_id)
                return

            log_info(MODULE, f"{symbol}: ✅ Validación OK | Balance: ${risk_result['balance_usdt']:,.2f} | Posiciones: {risk_result['open_positions']}", cycle_id=cycle_id)

            executed_order = order_manager.execute_trade(
                signal=signal,
                oco_params=oco_params,
                cycle_id=cycle_id,
                supabase_client=sb,
                binance_client=binance_client_pass
            )
            
            if executed_order is None:
                log_error(MODULE, f"{symbol}: execute_trade retornó None", cycle_id=cycle_id)
                return

            with lock:
                counters["signals"] += 1
                counters["orders"] = counters.get("orders", 0) + 1

            log_info(MODULE, f"{symbol}: ✅ ORDEN EJECUTADA | Entry: ${executed_order['entry_price']:,.4f} | SL: ${executed_order['stop_loss']:,.4f} | TP: ${executed_order['take_profit']:,.4f}", cycle_id=cycle_id)
            alerts_service.send_trade_alert(executed_order)

    except Exception as e:
        with lock:
            counters["errors"] += 1
        log_error(
            MODULE,
            f"{symbol}: {str(e)}",
            {
                "symbol": symbol,
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
            cycle_id,
        )


def run_pipeline():
    """
    Main pipeline entry point. Executes one full cycle:
    1. Create cycle record
    2. Load config & risk
    3. Check kill switch
    4. Get top symbols
    5. Process each symbol (parallel)
    6. Update cycle stats
    """
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
          f"eTrader v2 — Starting pipeline cycle")
    print(f"{'='*60}")

    # ── Step 1: Create cycle record ──
    cycle_id = _create_cycle()
    if cycle_id:
        log_info(MODULE, f"Cycle started: {cycle_id}", cycle_id=cycle_id)
    else:
        log_warning(MODULE, "Failed to create cycle record, continuing without tracking")

    # ── Step 2: Load configuration ──
    config = _load_config()
    top_n = int(config.get("top_symbols", 20))
    log_info(
        MODULE,
        f"Config loaded: top_symbols={top_n}, spike_multiplier={config.get('spike_multiplier')}",
        cycle_id=cycle_id,
    )

    # ── Step 3: Load risk config & check kill switch ──
    sb = get_supabase()
    
    try:
        risk = get_risk_config()
        if not risk.get("bot_active", True):
            log_info(MODULE, "Bot desactivado (kill switch). Ciclo omitido.", cycle_id=cycle_id)
            if cycle_id:
                _update_cycle(cycle_id, 0, 0, 0, 0, 0, time.time() - start_time)
                sb.table("cron_cycles").update({"status": "skipped"}).eq("id", cycle_id).execute()
            return
        check_daily_loss_at_cycle_start(risk, sb)
    except Exception as e:
        log_warning(MODULE, f"Failed to load risk_config: {e}. Continuing...", cycle_id=cycle_id)

    binance_client = binance_connector.get_client()
    sync_closed_positions(sb, binance_client)


    # ── Step 4: Get top symbols ──
    excluded = _load_excluded_symbols(config)
    allowed_symbols = config.get("allowed_symbols")
    symbols = get_top_symbols(top_n, excluded, allowed_symbols)

    if not symbols:
        log_error(MODULE, "No symbols retrieved from Binance. Aborting cycle.", cycle_id=cycle_id)
        if cycle_id:
            _update_cycle(cycle_id, 0, 0, 0, 0, 1, time.time() - start_time)
        return

    log_info(
        MODULE,
        f"Processing {len(symbols)} symbols: {', '.join(symbols[:5])}...",
        {"count": len(symbols), "symbols": symbols},
        cycle_id,
    )

    # ── Step 5: Process each symbol in parallel ──
    counters = {"spikes": 0, "signals": 0, "errors": 0, "orders": 0}
    lock = threading.Lock()
    max_workers = settings.max_pipeline_workers

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_symbol, symbol, config, cycle_id, counters, lock, binance_client, risk
            ): symbol
            for symbol in symbols
        }

        for future in as_completed(futures):
            symbol = futures[future]
            try:
                future.result()
            except Exception as e:
                with lock:
                    counters["errors"] += 1
                log_error(
                    MODULE,
                    f"{symbol}: Unhandled error in thread: {e}",
                    {"symbol": symbol, "traceback": traceback.format_exc()},
                    cycle_id,
                )

    # ── Step 6: Update cycle with stats ──
    elapsed = time.time() - start_time
    spikes_detected = counters["spikes"]
    signals_generated = counters["signals"]
    errors = counters["errors"]
    orders_executed = counters.get("orders", 0)

    # Actualizar posiciones abiertas con precio actual
    try:
        open_positions = sb.table('positions').select('id, symbol, side, entry_price, size').eq('status', 'open').execute().data
        if open_positions:
            for position in open_positions:
                current_price = binance_connector.get_current_price(position['symbol'].replace('/', ''))
                if position['side'] == 'LONG':
                    upnl = (current_price - float(position['entry_price'])) * float(position['size'])
                else:
                    upnl = (float(position['entry_price']) - current_price) * float(position['size'])
                
                sb.table('positions').update({
                    'current_price': current_price,
                    'unrealized_pnl': round(upnl, 4)
                }).eq('id', position['id']).execute()
    except Exception as e:
        log_error(MODULE, f"Could not update unrealized pnl: {e}")

    # Enviar resumen si es pertinente
    try:
        alerts_service.send_daily_summary(sb)
    except Exception as e:
        log_error(MODULE, f'Error resumen diario: {e}', cycle_id=cycle_id)

    if cycle_id:
        _update_cycle(
            cycle_id,
            symbols_analyzed=len(symbols),
            spikes_detected=spikes_detected,
            signals_generated=signals_generated,
            orders_executed=orders_executed,
            errors=errors,
            duration_seconds=elapsed,
        )

    print(f"\n{'='*60}")
    print(f"Cycle completed in {elapsed:.1f}s")
    print(f"  Symbols analyzed:  {len(symbols)}")
    print(f"  Spikes detected:   {spikes_detected}")
    print(f"  Signals generated: {signals_generated}")
    print(f"  Errors:            {errors}")
    print(f"{'='*60}\n")

    log_info(
        MODULE,
        f"Cycle finished: {len(symbols)} symbols · {spikes_detected} spikes · "
        f"{signals_generated} signals · {errors} errors · {elapsed:.1f}s",
        {
            "symbols_analyzed": len(symbols),
            "spikes_detected": spikes_detected,
            "signals_generated": signals_generated,
            "errors": errors,
            "duration_seconds": round(elapsed, 2),
        },
        cycle_id,
    )


if __name__ == "__main__":
    run_pipeline()
    sys.exit(0)
