from fastapi import APIRouter
from app.core.supabase_client import get_supabase
from datetime import datetime, timezone
try:
    from app.core.memory_store import MEMORY_STORE
except ImportError:
    MEMORY_STORE = {}
import json

from app.analysis.fibonacci_bb import get_next_fibonacci_target
from app.strategy.band_exit import evaluate_band_exit

router = APIRouter()

@router.get("/summary")
async def get_dashboard_summary():
    supabase = get_supabase()
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    
    # 1. Stats globales (Daily PnL, Win Rate, etc)
    # Filter test trades (SL @ -1.50)
    def is_test_trade(p):
        try:
            return (p.get('close_reason') == 'sl' and float(p.get('total_pnl_usd') or 0) == -1.50)
        except: return False

    all_closed_res = supabase.table('paper_trades') \
        .select('total_pnl_usd, closed_at, close_reason') \
        .not_.is_('closed_at', 'null') \
        .execute()
    all_closed = [p for p in (all_closed_res.data or []) if not is_test_trade(p)]
    
    total_trades = len(all_closed)
    winners    = len([p for p in all_closed if float(p['total_pnl_usd'] or 0) > 0])
    win_rate   = (winners / total_trades * 100) if total_trades > 0 else 0.0
    
    closed_today = [p for p in all_closed if p['closed_at'] >= today_start]
    daily_pnl    = sum(float(p['total_pnl_usd'] or 0) for p in closed_today)
    total_pnl    = sum(float(p['total_pnl_usd'] or 0) for p in all_closed)
    
    open_positions_res = supabase.table('positions') \
        .select('id, symbol, unrealized_pnl, side, avg_entry_price, sl_price, tp_partial_price, tp_full_price, bars_held, max_holding_bars, size, rule_code, regime_entry', count='exact') \
        .eq('status', 'open') \
        .execute()
    
    open_positions = open_positions_res.data or []
    live_pnl = sum(float(p.get('unrealized_pnl') or 0) for p in open_positions)
    
    # 2. Get active symbols from config
    cfg = supabase.table('trading_config').select('active_symbols').eq('id', 1).maybe_single().execute().data
    active_symbols = cfg.get('active_symbols') if cfg else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    
    # Helper: convert BTCUSDT -> BTC/USDT for tables that use slash format
    def to_slash(s):
        if '/' in s:
            return s
        if s.endswith('USDT'):
            return s[:-4] + '/USDT'
        return s

    async def get_symbol_market_data(symbols: list, supabase) -> dict:
        """
        Lee el estado técnico actual desde market_snapshot.
        Escrito por el worker cada 15m.
        """
        res = supabase.table('market_snapshot').select('*').in_('symbol', symbols).execute()
        return {row['symbol']: row for row in res.data or []}

    market_data = await get_symbol_market_data(active_symbols, supabase)
    
    # Pre-fetch config for all symbols
    trading_config = supabase.table('trading_config').select('*').eq('id', 1).maybe_single().execute().data or {}

    # 3. Batch fetch for ALL symbols to avoid N+1 issues
    all_sym_slash = [to_slash(s) for s in active_symbols]
    
    # 3a. Batch SIGNALS
    sig_res = supabase.table('trading_signals').select('*').in_('symbol', all_sym_slash).order('created_at', desc=True).execute()
    try:
        log_sig_res = supabase.table('signals_log').select('*').in_('symbol', all_sym_slash).order('detected_at', desc=True).limit(50).execute()
        log_sig_data = log_sig_res.data or []
    except Exception:
        log_sig_data = []
        
    regime_res = supabase.table('market_regime').select('*').in_('symbol', all_sym_slash).order('evaluated_at', desc=True).execute()

    # Map them for quick access
    latest_sigs = {}
    for r in sig_res.data or []:
        if r['symbol'] not in latest_sigs: latest_sigs[r['symbol']] = r
        
    latest_logs = {}
    for r in log_sig_data or []:
        if r['symbol'] not in latest_logs: latest_logs[r['symbol']] = r
        
    latest_regimes = {}
    for r in regime_res.data or []:
        if r['symbol'] not in latest_regimes: latest_regimes[r['symbol']] = r

    # 4. Data for each symbol
    symbols_info = {}
    for sym in active_symbols:
        sym_slash = to_slash(sym)
        snap = market_data.get(sym, {})
        price_now = float(snap.get('price', 0))

        # Latest signal determination (batched)
        sig = latest_sigs.get(sym_slash)
        log_sig = latest_logs.get(sym_slash)
        
        latest_signal_data = None
        if sig and log_sig:
            if sig['created_at'] > log_sig['detected_at']:
                latest_signal_data = sig
                latest_signal_data['type_source'] = 'trading_signals'
            else:
                latest_signal_data = log_sig
                latest_signal_data['type_source'] = 'signals_log'
        elif sig:
            latest_signal_data = sig
            latest_signal_data['type_source'] = 'trading_signals'
        elif log_sig:
            latest_signal_data = log_sig
            latest_signal_data['type_source'] = 'signals_log'

        regime = latest_regimes.get(sym_slash, {})

        card_status = 'hold'
        if any(p['symbol'] == sym for p in open_positions):
            card_status = 'active'
        elif latest_signal_data and latest_signal_data.get('type_source') == 'signals_log':
            card_status = 'signal'
        if regime.get('emergency_active'):
            card_status = 'emergency'

        pos = next((p for p in open_positions if p['symbol'] == sym), None)

        # Calculate unrealized P&L values
        entry_p   = 0.0
        size_val  = 0.0
        upnl_pct  = 0.0
        upnl_usd  = 0.0

        if pos:
            entry_p   = float(pos.get('avg_entry_price') or 0)
            size_val  = float(pos.get('size') or 0)
            side_m    = 1 if pos['side'].lower() in ['long', 'buy'] else -1
            if entry_p > 0:
                upnl_pct = ((price_now - entry_p) / entry_p) * 100 * side_m
                upnl_usd = (size_val * entry_p) * (upnl_pct / 100)

            # ── DYNAMIC TP ──
            ai_result = MEMORY_STORE.get(sym, {}).get('ai_cache_4h', {})
            next_target = get_next_fibonacci_target(
                side=pos['side'], current_price=price_now,
                current_zone=int(snap.get('fibonacci_zone', 0)), levels=snap
            )
            
            # Fallback for next_target
            if not next_target:
                next_target = {
                    'target_name': 'TP AGN',
                    'target_price': float(pos.get('tp_full_price', 0) or 0),
                    'target_zone': 6
                }
            else:
                next_target['target_price'] = float(next_target['target_price'] or 0)
                
            price_for_after = float(next_target['target_price'])
            delta = 0.001 * price_for_after
            if pos['side'].lower() not in ['long', 'buy']:
                delta = -delta

            after_next_target = get_next_fibonacci_target(
                side=pos['side'],
                current_price=price_for_after + delta,
                current_zone=int(next_target['target_zone']), levels=snap
            )
            
            # Fallback for after_next_target
            if not after_next_target:
                after_next_target = next_target
            else:
                after_next_target['target_price'] = float(after_next_target['target_price'] or 0)

            band_decision = evaluate_band_exit(
                position=pos, current_price=price_now, next_target=next_target,
                mtf_score=float(snap.get('mtf_score', 0)), ai_result=ai_result, config=trading_config
            )

            symbols_info[sym] = {
                'dynamic_tp': {
                    'next_target':       next_target,
                    'after_next_target': after_next_target,
                    'decision':          band_decision
                }
            }
        else:
            symbols_info[sym] = {}

        # --- EXTRA METRICS FOR DASHBOARD CUBES (V4.1) ---
        volume_rel = 0.0
        cur_vol = 0.0
        vol_ema = 0.0
        
        # Read last 25 candles to calculate SMA/EMA 20 for volume
        sym_clean_c = sym.replace('/', '')
        candles_res = supabase.table('market_candles') \
            .select('volume') \
            .eq('symbol', sym_clean_c) \
            .eq('timeframe', '15m') \
            .order('open_time', desc=True) \
            .limit(25) \
            .execute()
        
        if candles_res.data and len(candles_res.data) >= 20:
            vols = [float(c['volume']) for c in candles_res.data]
            cur_vol = vols[0]
            vol_ema = sum(vols[:20]) / 20 # Simple Moving Average as fallback for the dashboard view
            if vol_ema > 0:
                volume_rel = cur_vol / vol_ema

        symbols_info[sym].update({
            'price':          price_now,
            'zone':           int(snap.get('fibonacci_zone', 0)),
            'basis':          float(snap.get('basis', 0)),
            'upper_5':        float(snap.get('upper_5', 0)),
            'upper_6':        float(snap.get('upper_6', 0)),
            'lower_5':        float(snap.get('lower_5', 0)),
            'lower_6':        float(snap.get('lower_6', 0)),
            'ema20_phase':    str(snap.get('ema20_phase', 'flat')),
            'adx':            float(snap.get('adx', 0)),
            'dist_basis_pct': float(snap.get('dist_basis_pct', 0)),
            'card_status':    card_status,
            'mtf_score':      float(snap.get('mtf_score', 0)),
            'regime':         snap.get('regime', 'riesgo_medio'),
            'ai_sentiment':   snap.get('ai_sentiment', 'neutral'),
            'sar_4h':         float(snap.get('sar_4h', 0)),
            'sar_trend_4h':   int(snap.get('sar_trend_4h', 0)),
            'sar_phase':      snap.get('sar_phase', 'neutral'),
            'sar_phase_changed_at': snap.get('sar_phase_changed_at'),
            'volume_rel':     volume_rel,
            'cur_vol':        cur_vol,
            'vol_ema':        vol_ema,
            'symbol_state':   snap.get('symbol_state', 'neutral'),
            'waiting_cycles': int(snap.get('waiting_cycles', 0)),
            'position': {
                'side':              pos['side'],
                'avg_entry':         entry_p,
                'sl_price':          float(pos['sl_price'] or 0),
                'tp_partial':        float(pos['tp_partial_price'] or 0),
                'tp_full':           float(pos['tp_full_price'] or 0),
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'bars_held':         int(pos['bars_held'] or 0),
                'rule_code':         pos.get('rule_code', 'Aa01')
            } if pos else None,
            'last_signal': {
                'rule_code':      latest_signal_data.get('rule_code'),
                'direction':      latest_signal_data.get('direction') if 'direction' in latest_signal_data else latest_signal_data.get('signal_type'),
                'status':         'blocked' if latest_signal_data.get('type_source') == 'signals_log' else 'executed',
                'blocked_reason': latest_signal_data.get('reason_skip') or latest_signal_data.get('message')
            } if latest_signal_data else None
        })

    # 4. Calculate Focus Symbol
    # 1. El símbolo con posición abierta de mayor P&L absoluto
    focus_symbol = None
    open_with_pnl = [p for p in open_positions if p['unrealized_pnl'] is not None]
    if open_with_pnl:
        focus_symbol = max(open_with_pnl, key=lambda x: abs(float(x['unrealized_pnl'])))['symbol']
    
    # 2. Si hay empate (or no positions) -> señal más reciente
    if not focus_symbol:
        # Check all symbols for latest signal
        latest_time = None
        for sym, info in symbols_info.items():
            if info['last_signal']:
                # Need to find actual time, let's use a simple comparison if we had it.
                # Since we don't hold full signal objects in symbols_info, we might need a better way.
                # For now, let's just pick one with signal.
                focus_symbol = sym
                break
    
    # 3. Si ninguno tiene posición -> el de mayor ADX
    if not focus_symbol:
        focus_symbol = max(symbols_info.items(), key=lambda x: x[1].get('adx', 0))[0]
    
    # fallback to first active if still none
    if not focus_symbol and active_symbols:
        focus_symbol = active_symbols[0]

    # 5. Recent signals and Spikes (as before)
    recent_signals_res = supabase.table('trading_signals') \
        .select('*') \
        .order('created_at', desc=True) \
        .limit(10) \
        .execute()
    recent_signals = recent_signals_res.data or []
    
    recent_spikes_res = supabase.table('volume_spikes') \
        .select('*') \
        .order('detected_at', desc=True) \
        .limit(10) \
        .execute()
    recent_spikes = recent_spikes_res.data or []

    # 6. Global config for frontend calculations
    capital_per_symbol = (float(cfg.get('capital_operativo', 90)) / len(active_symbols)) if cfg and active_symbols else 18.0
    leverage = int(cfg.get('leverage', 5)) if cfg else 5

    return {
        'daily': {
            'total_pnl':       round(total_pnl + live_pnl, 2),
            'daily_pnl':       round(daily_pnl, 2),
            'live_pnl':        round(live_pnl, 2),
            'total_trades':    total_trades,
            'win_rate':        round(win_rate, 1),
            'open_positions':  len(open_positions),
        },
        'symbols': symbols_info,
        'focus_symbol': focus_symbol,
        'recent_signals':  recent_signals,
        'market_feed':     recent_spikes,
        'config': {
            'capital_per_symbol': capital_per_symbol,
            'leverage': leverage
        }
    }
