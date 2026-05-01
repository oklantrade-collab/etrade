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
    
    def to_slash(s):
        if '/' in s: return s
        if s.endswith('USDT'): return s[:-4] + '/USDT'
        return s

    async def get_symbol_market_data(symbols: list, supabase) -> dict:
        res = supabase.table('market_snapshot').select('*').in_('symbol', symbols).execute()
        return {row['symbol']: row for row in res.data or []}

    market_data = await get_symbol_market_data(active_symbols, supabase)
    trading_config = supabase.table('trading_config').select('*').eq('id', 1).maybe_single().execute().data or {}

    # 3. Batch fetch for ALL symbols to avoid N+1 issues
    all_sym_slash = [to_slash(s) for s in active_symbols]
    all_sym_clean = [s.replace('/', '') for s in active_symbols]
    
    # --- BATCH SIGNALS, LOGS, REGIMES ---
    sig_res = supabase.table('trading_signals').select('*').in_('symbol', all_sym_slash).order('created_at', desc=True).execute()
    try:
        log_sig_res = supabase.table('signals_log').select('*').in_('symbol', all_sym_slash).order('detected_at', desc=True).limit(50).execute()
        log_sig_data = log_sig_res.data or []
    except: log_sig_data = []
        
    regime_res = supabase.table('market_regime').select('*').in_('symbol', all_sym_slash).order('evaluated_at', desc=True).execute()

    latest_sigs = {r['symbol']: r for r in (sig_res.data or [])}
    latest_logs = {r['symbol']: r for r in log_sig_data}
    latest_regimes = {r['symbol']: r for r in (regime_res.data or [])}

    # --- BATCH CANDLE FETCH (New Optimization) ---
    candles_map = {}
    try:
        candles_res = supabase.table('market_candles') \
            .select('symbol, volume, open_time') \
            .in_('symbol', all_sym_clean) \
            .eq('timeframe', '15m') \
            .order('open_time', desc=True) \
            .limit(len(all_sym_clean) * 25) \
            .execute()
        for c in (candles_res.data or []):
            s = c['symbol']
            if s not in candles_map: candles_map[s] = []
            if len(candles_map[s]) < 25: candles_map[s].append(float(c['volume']))
    except: pass

    # 4. Data for each symbol
    symbols_info = {}
    for sym in active_symbols:
        sym_slash = to_slash(sym)
        snap = market_data.get(sym, {})
        price_now = float(snap.get('price', 0))

        sig = latest_sigs.get(sym_slash)
        log_sig = latest_logs.get(sym_slash)
        
        latest_signal_data = None
        if sig and log_sig:
            if sig['created_at'] > log_sig['detected_at']:
                latest_signal_data = sig; latest_signal_data['type_source'] = 'trading_signals'
            else:
                latest_signal_data = log_sig; latest_signal_data['type_source'] = 'signals_log'
        elif sig:
            latest_signal_data = sig; latest_signal_data['type_source'] = 'trading_signals'
        elif log_sig:
            latest_signal_data = log_sig; latest_signal_data['type_source'] = 'signals_log'

        regime = latest_regimes.get(sym_slash, {})
        card_status = 'hold'
        if any(p['symbol'] == sym for p in open_positions): card_status = 'active'
        elif latest_signal_data and latest_signal_data.get('type_source') == 'signals_log': card_status = 'signal'
        if regime.get('emergency_active'): card_status = 'emergency'

        pos = next((p for p in open_positions if p['symbol'] == sym), None)
        entry_p = 0.0; size_val = 0.0; upnl_pct = 0.0; upnl_usd = 0.0

        if pos:
            entry_p = float(pos.get('avg_entry_price') or 0)
            size_val = float(pos.get('size') or 0)
            side_m = 1 if pos['side'].lower() in ['long', 'buy'] else -1
            if entry_p > 0:
                upnl_pct = ((price_now - entry_p) / entry_p) * 100 * side_m
                upnl_usd = (size_val * entry_p) * (upnl_pct / 100)

            ai_result = MEMORY_STORE.get(sym, {}).get('ai_cache_4h', {})
            next_target = get_next_fibonacci_target(
                side=pos['side'], current_price=price_now,
                current_zone=int(snap.get('fibonacci_zone', 0)), levels=snap
            )
            if not next_target:
                next_target = {'target_name': 'TP AGN', 'target_price': float(pos.get('tp_full_price', 0) or 0), 'target_zone': 6}
            
            band_decision = evaluate_band_exit(
                position=pos, current_price=price_now, next_target=next_target,
                mtf_score=float(snap.get('mtf_score', 0)), ai_result=ai_result, config=trading_config
            )
            symbols_info[sym] = {'dynamic_tp': {'next_target': next_target, 'decision': band_decision}}
        else:
            symbols_info[sym] = {}

        # Use batched candles
        sym_clean = sym.replace('/', '')
        vols = candles_map.get(sym_clean, [])
        volume_rel = 0.0; cur_vol = 0.0; vol_ema = 0.0
        if len(vols) >= 20:
            cur_vol = vols[0]
            vol_ema = sum(vols[:20]) / 20
            if vol_ema > 0: volume_rel = cur_vol / vol_ema

        symbols_info[sym].update({
            'price': price_now,
            'zone': int(snap.get('fibonacci_zone', 0)),
            'basis': float(snap.get('basis', 0)),
            'ema20_phase': str(snap.get('ema20_phase', 'flat')),
            'adx': float(snap.get('adx', 0)),
            'card_status': card_status,
            'mtf_score': float(snap.get('mtf_score', 0)),
            'regime': snap.get('regime', 'riesgo_medio'),
            'volume_rel': volume_rel,
            'position': {
                'side': pos['side'],
                'avg_entry': entry_p,
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'rule_code': pos.get('rule_code', 'Aa01')
            } if pos else None,
            'last_signal': {
                'rule_code': latest_signal_data.get('rule_code'),
                'direction': latest_signal_data.get('direction') if 'direction' in latest_signal_data else latest_signal_data.get('signal_type'),
                'status': 'blocked' if latest_signal_data.get('type_source') == 'signals_log' else 'executed'
            } if latest_signal_data else None
        })

    focus_symbol = None
    open_with_pnl = [p for p in open_positions if p['unrealized_pnl'] is not None]
    if open_with_pnl:
        focus_symbol = max(open_with_pnl, key=lambda x: abs(float(x['unrealized_pnl'])))['symbol']
    if not focus_symbol:
        for sym, info in symbols_info.items():
            if info.get('last_signal'): focus_symbol = sym; break
    if not focus_symbol:
        focus_symbol = max(symbols_info.items(), key=lambda x: x[1].get('adx', 0))[0]
    if not focus_symbol and active_symbols: focus_symbol = active_symbols[0]

    recent_signals = supabase.table('trading_signals').select('*').order('created_at', desc=True).limit(10).execute().data or []
    recent_spikes = supabase.table('volume_spikes').select('*').order('detected_at', desc=True).limit(10).execute().data or []

    return {
        'daily': {
            'total_pnl': round(total_pnl + live_pnl, 2),
            'daily_pnl': round(daily_pnl, 2),
            'live_pnl': round(live_pnl, 2),
            'total_trades': total_trades,
            'win_rate': round(win_rate, 1),
            'open_positions': len(open_positions),
        },
        'symbols': symbols_info,
        'focus_symbol': focus_symbol,
        'recent_signals': recent_signals,
        'market_feed': recent_spikes,
        'config': {
            'capital_per_symbol': (float(cfg.get('capital_operativo', 90)) / len(active_symbols)) if cfg and active_symbols else 18.0,
            'leverage': int(cfg.get('leverage', 5)) if cfg else 5
        }
    }

