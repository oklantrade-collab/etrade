from fastapi import APIRouter
from app.core.supabase_client import get_supabase
from app.core.logger import log_error
from datetime import datetime, timezone, timedelta

router = APIRouter()

@router.get("/summary")
async def get_dashboard_summary():
    """Get dashboard summary with real-time symbol data and positions."""
    try:
        sb = get_supabase()
        
        # 1. Counts
        stocks_open = sb.table("stocks_positions").select("id", count="exact").eq("status", "open").execute().count or 0
        crypto_open = sb.table("positions").select("id", count="exact").eq("status", "open").execute().count or 0
        forex_open = sb.table("forex_positions").select("id", count="exact").eq("status", "open").execute().count or 0
        total_open = stocks_open + crypto_open + forex_open
        
        # 2. Config and Active Symbols
        config_res = sb.table("trading_config").select("*").eq("id", 1).execute()
        main_config = config_res.data[0] if config_res.data else {}
        active_symbols = main_config.get("active_symbols", [])
        
        # 3. Market Snapshot
        snap_query = sb.table("market_snapshot").select("*")
        if active_symbols:
            snap_query = snap_query.in_("symbol", active_symbols)
        
        snap_res = snap_query.execute()
        snapshots = snap_res.data or []
        
        # 4. Crypto Positions
        pos_res = sb.table("positions").select("*").eq("status", "open").execute()
        crypto_positions = {p['symbol']: p for p in (pos_res.data or [])}
        
        # 4. Recent Signals
        cutoff_signals = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        signals_res = sb.table("trading_signals")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        recent_signals = signals_res.data or []
        
        # 5. Build symbols dict
        symbols_dict = {}
        for s in snapshots:
            sym = s['symbol']
            
            # Map snapshot to frontend SymbolData
            symbol_data = {
                'price': float(s.get('price', 0) or 0),
                'zone': int(s.get('fibonacci_zone', 0) or 0),
                'basis': float(s.get('basis', 0) or 0),
                'upper_5': float(s.get('upper_5', 0) or 0),
                'upper_6': float(s.get('upper_6', 0) or 0),
                'lower_5': float(s.get('lower_5', 0) or 0),
                'lower_6': float(s.get('lower_6', 0) or 0),
                'mtf_score': float(s.get('mtf_score', 0) or 0),
                'ema20_phase': s.get('ema20_phase', 'neutral'),
                'adx': float(s.get('adx', 0) or 0),
                'dist_basis_pct': float(s.get('dist_basis_pct', 0) or 0),
                'regime': s.get('regime', 'riesgo_bajo'),
                'ai_sentiment': 'bullish' if float(s.get('mtf_score', 0) or 0) > 0.5 else 'neutral',
                'symbol_state': s.get('symbol_state', 'idle'),
                'waiting_cycles': int(s.get('waiting_cycles', 0) or 0),
                'card_status': 'active' if sym in crypto_positions else ('signal' if float(s.get('mtf_score', 0) or 0) > 0.6 else 'idle'),
                'sar_4h': float(s.get('sar_4h', 0) or 0),
                'sar_trend_4h': int(s.get('sar_trend_4h', 0) or 0),
                'sar_phase': s.get('sar_phase', 'neutral'),
                'sar_phase_changed_at': s.get('sar_phase_changed_at')
            }
            
            # Add spike info
            if s.get('spike_detected'):
                symbol_data['spike'] = {
                    'detected': True,
                    'ratio': float(s.get('spike_ratio', 0) or 0),
                    'direction': s.get('spike_direction', 'up')
                }
            
            # Add position info if exists
            if sym in crypto_positions:
                p = crypto_positions[sym]
                symbol_data['position'] = {
                    'side': p.get('side', 'long'),
                    'trades_count': 1,
                    'avg_entry': float(p.get('entry_price', 0) or 0),
                    'sl_price': float(p.get('sl_price', 0) or 0),
                    'tp_partial': float(p.get('tp_partial_price', 0) or 0),
                    'tp_full': float(p.get('tp_full_price', 0) or 0),
                    'unrealized_pnl_usd': float(p.get('unrealized_pnl', 0) or 0),
                    'unrealized_pnl_pct': 0, # Frontend recalculates
                    'breakeven_hit': p.get('breakeven_activated', False),
                    'bars_held': int(p.get('bars_held', 0) or 0),
                    'max_bars': int(p.get('max_holding_bars', 48) or 48),
                    'rule_code': p.get('rule_code', 'V5_INDUSTRIAL'),
                    'regime_entry': p.get('regime_entry', 'RIESGO MEDIO')
                }
            
            # Dynamic TP targets
            symbol_data['dynamic_tp'] = {
                'next_target': {
                    'target_name': 'Upper 6' if symbol_data['zone'] >= 0 else 'Basis',
                    'target_price': symbol_data['upper_6'] if symbol_data['zone'] >= 0 else symbol_data['basis'],
                    'target_zone': 6 if symbol_data['zone'] >= 0 else 0
                },
                'after_next_target': {
                    'target_name': 'Upper 6 (Extreme)' if symbol_data['zone'] >= 0 else 'Upper 5',
                    'target_price': symbol_data['upper_6'] if symbol_data['zone'] >= 0 else symbol_data['upper_5'],
                    'target_zone': 6
                },
                'decision': {
                    'action': 'hold',
                    'reason': 'SI PRECIO PASA EL UPPER_5 SIN SEÑAL -> UPPER_6'
                }
            }
            
            symbols_dict[sym] = symbol_data

        # 6. Market Feed (Spikes)
        market_feed = []
        for s in snapshots:
            if s.get('spike_detected'):
                market_feed.append({
                    'symbol': s['symbol'],
                    'ratio': s.get('spike_ratio'),
                    'direction': s.get('spike_direction'),
                    'timestamp': s.get('updated_at')
                })
        market_feed.sort(key=lambda x: x['timestamp'] or '', reverse=True)

        focus_symbol = None
        if symbols_dict:
            # Pick BTC if available, else first symbol
            if 'BTCUSDT' in symbols_dict: focus_symbol = 'BTCUSDT'
            else: focus_symbol = list(symbols_dict.keys())[0]

        return {
            'daily': {
                'total_pnl': 0, 
                'daily_pnl': 0, 
                'live_pnl': 0, 
                'total_trades': 0, 
                'win_rate': 0, 
                'open_positions': total_open
            },
            'symbols': symbols_dict,
            'focus_symbol': focus_symbol,
            'recent_signals': recent_signals,
            'market_feed': market_feed[:20],
            'config': {
                'capital_per_symbol': float(main_config.get('capital_operativo', 18)), 
                'leverage': int(main_config.get('leverage_crypto', 5))
            }
        }
    except Exception as e:
        log_error("dashboard_api", f"Error in summary: {e}")
        import traceback
        traceback.print_exc()
        return {
            'daily': {'total_pnl': 0, 'daily_pnl': 0, 'live_pnl': 0, 'total_trades': 0, 'win_rate': 0, 'open_positions': 0},
            'symbols': {},
            'focus_symbol': None,
            'recent_signals': [],
            'market_feed': [],
            'config': {'capital_per_symbol': 0, 'leverage': 0},
            'error': str(e)
        }
