from fastapi import APIRouter
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase
try:
    from app.core.memory_store import MEMORY_STORE
except ImportError:
    MEMORY_STORE = {}

router = APIRouter()

@router.get("/global")
async def get_global_portfolio():
    """
    Consolida métricas de todos los mercados activos.
    Por ahora solo Crypto es activo.
    Diseñado para agregar Forex y Bolsa en el futuro
    sin modificar la estructura del endpoint.
    """
    from app.core.logger import log_error
    try:
        supabase = get_supabase()
        import pytz
        lima_tz = pytz.timezone('America/Lima')
        now_lima = datetime.now(lima_tz)
        today_start_lima = now_lima.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_lima.astimezone(timezone.utc).isoformat()

        # 1. Crypto Summary (Existing logic slightly adapted)
        # Filter test trades (SL @ -1.50)
        def is_test_trade(p):
            try:
                reason = p.get('close_reason') or ''
                pnl = float(p.get('total_pnl_usd') or 0)
                return (reason.lower() == 'sl' and pnl == -1.50)
            except: return False

        # Closed positions for PnL today
        closed_today_res = supabase.table('paper_trades') \
            .select('total_pnl_usd, closed_at, close_reason') \
            .gte('closed_at', today_start) \
            .execute()
        closed_today = [p for p in (closed_today_res.data or []) if not is_test_trade(p)]
        
        daily_pnl = sum(float(p['total_pnl_usd'] or 0) for p in closed_today)
        
        # All closed for win rate
        all_closed_res = supabase.table('paper_trades') \
            .select('total_pnl_usd, close_reason') \
            .not_.is_('closed_at', 'null') \
            .execute()
        all_closed = [p for p in (all_closed_res.data or []) if not is_test_trade(p)]
        
        total_trades = len(all_closed)
        wins = len([p for p in all_closed if float(p['total_pnl_usd'] or 0) > 0])
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

        # Open positions
        open_positions = supabase.table('positions') \
            .select('symbol', count='exact') \
            .eq('status', 'open') \
            .execute()
        
        open_count = open_positions.count or 0
        
        # Current Crypto Regime
        latest_regime = supabase.table('market_regime') \
            .select('category') \
            .order('evaluated_at', desc=True) \
            .limit(1) \
            .execute()
        
        regime = latest_regime.data[0]['category'] if latest_regime.data else 'riesgo_medio'
        
        # Symbols in crypto
        cfg_res = supabase.table('trading_config').select('active_symbols').eq('id', 1).maybe_single().execute()
        cfg = cfg_res.data if cfg_res else None
        active_symbols = cfg.get('active_symbols') if cfg else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
        
        def to_slash(s):
            if '/' in s: return s
            if s.endswith('USDT'): return s[:-4] + '/USDT'
            return s

        async def get_symbol_market_data(symbols: list, supabase) -> dict:
            res = supabase.table('market_snapshot').select('*').in_('symbol', symbols).execute()
            return {row['symbol']: row for row in res.data or []}

        market_data = await get_symbol_market_data(active_symbols, supabase)

        # Get latest data for these symbols
        symbols_data = []
        for sym in active_symbols:
            sym_slash = to_slash(sym)
            
            # ════════════════════════════════════════════════════
            # PASO 3 — API lee desde market_snapshot
            # ════════════════════════════════════════════════════
            snap = market_data.get(sym, {})
            fib_zone = snap.get('fibonacci_zone') or 0
            
            # Get position if any
            pos_result = supabase.table('positions') \
                .select('side, avg_entry_price, size, entries, tp_partial_price, tp_full_price, rule_code, bars_held, max_holding_bars, sl_price') \
                .eq('symbol', sym) \
                .eq('status', 'open') \
                .limit(1) \
                .execute().data
            pos = pos_result[0] if pos_result else None
            
            cur_price = float(snap.get('price', 0.0))
            
            def calc_position_capital(p: dict) -> float:
                if p.get('size') and p.get('avg_entry_price'):
                    s = float(p['size'])
                    e = float(p['avg_entry_price'])
                    if s > 0 and e > 0: return round(s * e, 2)
                ents = p.get('entries', [])
                if ents and isinstance(ents, list):
                    tot = sum(float(x.get('usd', 0)) for x in ents)
                    if tot > 0: return round(tot, 2)
                return 0.0

            # Calculate unrealized P&L
            upnl_pct = 0.0
            upnl_usd = 0.0
            if pos:
                entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or 0.0)
                capital = calc_position_capital(pos)
                if entry > 0:
                    side = str(pos.get('side', '')).lower()
                    side_mult = 1 if side == 'long' else -1
                    upnl_pct = ((cur_price - entry) / entry) * 100 * side_mult
                    upnl_usd = capital * (upnl_pct / 100)

            symbols_data.append({
                'symbol': sym,
                'side': str(pos.get('side', '')).lower() if pos else None,
                'avg_entry_price': float(pos.get('avg_entry_price') or pos.get('entry_price') or 0) if pos else 0,
                'current_price': cur_price,
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'tp_partial_price': float(pos.get('tp_partial_price') or 0) if pos else 0,
                'tp_full_price': float(pos.get('tp_full_price') or 0) if pos else 0,
                'fibonacci_zone': fib_zone,
                'rule_code': (pos.get('rule_code') or pos.get('rule_entry') or 'N/A') if pos else 'N/A',
                'sl_price': float(pos.get('sl_price') or 0) if pos else 0,
                'ai_sentiment': snap.get('ai_sentiment', 'neutral'),
                'status': 'active' if pos else 'hold',
                'trades_count': 1 if pos else 0,
                'bars_held': int(pos.get('bars_held') or 0) if pos else 0,
                'max_bars': int(pos.get('max_holding_bars') or 48) if pos else 0
            })

        # Recent activity (last 10)
        recent_trades_res = supabase.table('paper_trades') \
            .select('id, closed_at, symbol, rule_code, side, close_reason, total_pnl_usd') \
            .not_.is_('closed_at', 'null') \
            .order('closed_at', desc=True) \
            .limit(30) \
            .execute()
        
        all_raw = recent_trades_res.data or []
        seen = set()
        cleaned_trades = []
        
        for t in all_raw:
            if is_test_trade(t): continue
            key = f"{t['symbol']}_{t['closed_at']}"
            if key in seen: continue
            seen.add(key)
            cleaned_trades.append(t)
            if len(cleaned_trades) >= 10: break
        
        recent_activity = []
        for t in cleaned_trades:
            recent_activity.append({
                'time': t['closed_at'],
                'market': 'Crypto',
                'symbol': t['symbol'],
                'rule': t.get('rule_code') or ( 'Dd51' if t.get('side') == 'short' else 'Dd61' ),
                'dir': t.get('side', '').lower(),
                'status': t['close_reason'],
                'pnl': float(t['total_pnl_usd'] or 0)
            })

        return {
            'daily': {
                'pnl_usd':        round(daily_pnl, 2),
                'pnl_pct':        0.0,
                'win_rate':       round(win_rate, 1),
                'wins':           wins,
                'losses':         losses,
                'open_positions': open_count,
                'risk_global':    regime,
            },
            'markets': {
                'crypto': {
                    'status':   'active',
                    'sprint':   None,
                    'regime':   regime,
                    'symbols':  symbols_data,
                    'pnl_usd':  round(daily_pnl, 2),
                    'positions': open_count,
                },
                'forex': {
                    'status':   'coming_soon',
                    'sprint':   3,
                    'symbols':  ['EUR/USD','GBP/USD', 'USD/JPY','AUD/USD'],
                },
                'stocks': {
                    'status':   'coming_soon',
                    'sprint':   4,
                    'symbols':  ['AAPL','NVDA','TSLA','SPY'],
                }
            },
            'recent_activity': sorted(recent_activity, key=lambda x: x['time'], reverse=True)[:10]
        }
    except Exception as e:
        log_error("portfolio", f"Internal Error in get_global_portfolio: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance-summary")
async def get_performance_summary():
    """
    Métricas de performance temporales (Hoy, Semana, Mes).
    """
    from app.core.logger import log_error
    try:
        supabase = get_supabase()
        
        # BUG 2 Fix: Use recommended filters for metrics
        res = supabase.table('paper_trades') \
            .select('total_pnl_usd, closed_at, rule_code, mode') \
            .eq('mode', 'paper') \
            .not_.is_('closed_at', 'null') \
            .execute()
        
        def is_real_trade(t):
            pnl = t.get('total_pnl_usd')
            if pnl is None: return False
            try:
                if abs(float(pnl)) < 0.0001: return False
            except: return False
            return True

        # Pre-parse dates to avoid repeated fromisoformat fails
        all_closed = []
        for t in (res.data or []):
            if is_real_trade(t):
                try:
                    # Robust parsing
                    dt_str = t['closed_at'].replace('Z', '+00:00')
                    t['dt_object'] = datetime.fromisoformat(dt_str)
                    all_closed.append(t)
                except Exception as date_e:
                    log_error("portfolio", f"Date parsing error for trade {t.get('id')}: {date_e}")

        import pytz
        lima_tz = pytz.timezone('America/Lima')
        now_lima = datetime.now(lima_tz)
        
        # Inicio del día COMPLETO en Lima (00:00)
        today_start_lima = now_lima.replace(hour=0, minute=0, second=0, microsecond=0)
        # Convertir a UTC para comparar con la DB
        today_start_utc = today_start_lima.astimezone(timezone.utc)

        # Inicio de la semana (Lunes) en Lima
        monday_lima = (now_lima - timedelta(days=now_lima.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        monday_start_utc = monday_lima.astimezone(timezone.utc)

        # Inicio del mes en Lima
        month_lima = now_lima.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start_utc = month_lima.astimezone(timezone.utc)
        
        def calc_stats(trades):
            t_count = len(trades)
            pnl = sum(float(t['total_pnl_usd'] or 0) for t in trades)
            wins = len([t for t in trades if float(t['total_pnl_usd'] or 0) > 0])
            wr = (wins / t_count * 100) if t_count > 0 else 0
            return {"pnl_usd": round(pnl, 2), "trades": t_count, "win_rate": round(wr, 1)}

        today_trades = [t for t in all_closed if t['dt_object'] >= today_start_utc]
        week_trades  = [t for t in all_closed if t['dt_object'] >= monday_start_utc]
        month_trades = [t for t in all_closed if t['dt_object'] >= month_start_utc]
        
        today_res = calc_stats(today_trades)
        week_res  = calc_stats(week_trades)
        month_res = calc_stats(month_trades)

        # Monthly breakdown by week (S1: 1-7, S2: 8-14, ...)
        weekly_res = []
        best_week = {"week_num": 0, "pnl_usd": -999999}
        
        for w in range(1, 5):
            w_start = month_start_utc + timedelta(days=(w-1)*7)
            w_end = w_start + timedelta(days=7)
            w_trades = [t for t in all_closed if w_start <= t['dt_object'] < w_end]
            
            stats = calc_stats(w_trades)
            stats["week_num"] = w
            stats["pct_of_month"] = round((stats['pnl_usd'] / month_res['pnl_usd'] * 100), 1) if month_res['pnl_usd'] != 0 else 0
            weekly_res.append(stats)
            
            if stats['pnl_usd'] > best_week['pnl_usd']:
                best_week = {"week_num": w, "pnl_usd": stats['pnl_usd']}

        today_res["pct_of_month"] = round((today_res['pnl_usd'] / month_res['pnl_usd'] * 100), 1) if month_res['pnl_usd'] != 0 else 0
        week_res["pct_of_month"] = round((week_res['pnl_usd'] / month_res['pnl_usd'] * 100), 1) if month_res['pnl_usd'] != 0 else 0
        month_res["best_week"] = best_week if best_week['week_num'] > 0 else None

        # Market breakdown (Crypto only active)
        by_market = {
            "crypto": {
                "pnl_usd": month_res['pnl_usd'],
                "trades": month_res['trades'],
                "win_rate": month_res['win_rate'],
                "pct_of_total": 100.0,
                "status": "active"
            },
            "forex": {"status": "coming_soon", "sprint": 3},
            "stocks": {"status": "coming_soon", "sprint": 4}
        }

        return {
            "today": today_res,
            "this_week": week_res,
            "this_month": month_res,
            "weekly_breakdown": weekly_res,
            "by_market": by_market
        }
    except Exception as e:
        log_error("portfolio", f"Internal Error in get_performance_summary: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

from datetime import timedelta
