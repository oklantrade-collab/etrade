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

        # 1. Closed positions for PnL today (Crypto + Forex + Stocks)
        import pytz
        lima_tz = pytz.timezone('America/Lima')
        now_lima = datetime.now(lima_tz)
        today_start_lima = now_lima.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_lima.astimezone(timezone.utc).isoformat()

        # Crypto
        closed_crypto_res = supabase.table('paper_trades') \
            .select('total_pnl_usd, closed_at, close_reason, market_type') \
            .gte('closed_at', today_start) \
            .execute()
        
        # Forex
        closed_forex_res = supabase.table('forex_positions') \
            .select('pnl_usd, closed_at, close_reason, market_type') \
            .eq('status', 'closed') \
            .gte('closed_at', today_start) \
            .execute()

        # Stocks
        closed_stocks_res = supabase.table('stocks_positions') \
            .select('unrealized_pnl, updated_at, status') \
            .eq('status', 'closed') \
            .gte('updated_at', today_start) \
            .execute()

        closed_today = []
        for p in (closed_crypto_res.data or []):
            if not is_test_trade(p):
                closed_today.append({
                    'pnl': float(p['total_pnl_usd'] or 0), 
                    'market': 'crypto',
                    'market_type': p.get('market_type')
                })
        
        for p in (closed_forex_res.data or []):
            closed_today.append({
                'pnl': float(p['pnl_usd'] or 0), 
                'market': 'forex',
                'market_type': p.get('market_type')
            })
            
        for p in (closed_stocks_res.data or []):
            closed_today.append({
                'pnl': float(p['unrealized_pnl'] or 0), 
                'market': 'stocks',
                'market_type': 'stocks'
            })

        daily_pnl = sum(p['pnl'] for p in closed_today)
        
        # All closed for win rate
        all_closed_crypto = supabase.table('paper_trades').select('total_pnl_usd').not_.is_('closed_at', 'null').execute()
        all_closed_forex  = supabase.table('forex_positions').select('pnl_usd').eq('status', 'closed').execute()
        all_closed_stocks = supabase.table('stocks_positions').select('unrealized_pnl').eq('status', 'closed').execute()
        
        full_history = []
        for p in (all_closed_crypto.data or []):
            if not is_test_trade(p):
                full_history.append(float(p['total_pnl_usd'] or 0))
        for p in (all_closed_forex.data or []):
            full_history.append(float(p['pnl_usd'] or 0))
        for p in (all_closed_stocks.data or []):
            full_history.append(float(p['unrealized_pnl'] or 0))

        total_trades = len(full_history)
        wins = len([p for p in full_history if p > 0])
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
        cfg_res = supabase.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
        cfg = cfg_res.data if cfg_res else {}
        
        lev_crypto = float(cfg.get('leverage_crypto') or 5)
        lev_forex  = float(cfg.get('leverage_forex') or 100)
        lev_stocks = float(cfg.get('leverage_stocks') or 1)
        
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
                ents = p.get('entries', [])
                if ents and isinstance(ents, list):
                    tot = sum(float(x.get('usd', 0)) for x in ents)
                    if tot > 0: return round(tot, 2)
                
                if p.get('size') and p.get('avg_entry_price'):
                    s = float(p['size'])
                    e = float(p['avg_entry_price'])
                    if s > 0 and e > 0: 
                        # Return margin: Notional / Leverage
                        return round((s * e) / lev_crypto, 2)
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
                'total_investment': round(capital, 2),
                'quantity': float(pos.get('size') or 0) if pos else 0,
                'status': 'active' if pos else 'hold',
                'trades_count': 1 if pos else 0,
                'bars_held': int(pos.get('bars_held') or 0) if pos else 0,
                'max_bars': int(pos.get('max_holding_bars') or 48) if pos else 0
            })

        # 1.1 Forex Positions (NEW logic implemented)
        forex_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
        forex_market_data = await get_symbol_market_data(forex_symbols, supabase)
        forex_symbols_data = []
        forex_open_count = 0

        for sym in forex_symbols:
            snap = forex_market_data.get(sym, {})
            # Buscar posición activa en forex_positions
            fx_pos_res = supabase.table('forex_positions') \
                .select('*') \
                .eq('symbol', sym) \
                .eq('status', 'open') \
                .limit(1) \
                .execute().data
            
            fx_pos = fx_pos_res[0] if fx_pos_res else None
            cur_price = float(snap.get('price', 0.0))
            
            upnl_usd = 0.0
            upnl_pct = 0.0
            total_inv = 0.0
            
            if fx_pos:
                forex_open_count += 1
                entry = float(fx_pos.get('entry_price') or 0)
                lots = float(fx_pos.get('lots') or 0)
                side = str(fx_pos.get('side', '')).lower()
                
                # PIP scaling logic (simple version for the dashboard)
                # USDJPY uses 0.01 pips, others 0.0001
                pip_size = 0.01 if 'JPY' in sym or 'XAU' in sym else 0.0001
                pip_val = 10.0 # Standard lot pip value approx
                
                if entry > 0 and cur_price > 0:
                    side_mult = 1 if side in ['long', 'buy'] else -1
                    pips = (cur_price - entry) / pip_size * side_mult
                    upnl_usd = pips * pip_val * lots
                    upnl_pct = (pips * pip_size / entry) * 100
                
                # Correct Notional USD calculation for Forex/Gold
                if 'XAU' in sym:
                    notional_usd = lots * 100 * (cur_price or entry)
                elif sym.startswith('USD'):
                    notional_usd = lots * 100000
                else:
                    notional_usd = lots * 100000 * (cur_price or entry)
                
                total_inv = round(notional_usd / lev_forex, 2)

            forex_symbols_data.append({
                'symbol': sym,
                'side': str(fx_pos.get('side', '')).lower() if fx_pos else None,
                'avg_entry_price': float(fx_pos.get('entry_price') or 0) if fx_pos else 0,
                'current_price': cur_price,
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'fibonacci_zone': snap.get('fibonacci_zone') or 0,
                'total_investment': total_inv if fx_pos else 0,
                'quantity': float(fx_pos.get('lots') or 0) if fx_pos else 0,
                'rule_code': fx_pos.get('rule_code', 'N/A') if fx_pos else 'N/A',
                'status': 'active' if fx_pos else 'hold'
            })

        # 1.2 Stocks Positions (NEW logic)
        stocks_pos_res = supabase.table('stocks_positions') \
            .select('*') \
            .eq('status', 'open') \
            .execute().data
        
        active_stocks = []
        stocks_open_count = 0

        if stocks_pos_res:
            stocks_tickers = [p['ticker'] for p in stocks_pos_res]
            stocks_prices_res = supabase.table('watchlist_daily') \
                .select('ticker, price') \
                .in_('ticker', stocks_tickers) \
                .order('date', desc=True) \
                .execute().data
            
            stocks_price_map = {}
            for pr in (stocks_prices_res or []):
                if pr["ticker"] not in stocks_price_map:
                    stocks_price_map[pr["ticker"]] = pr["price"]

            for p in stocks_pos_res:
                stocks_open_count += 1
                ticker = p['ticker']
                cur_price = float(stocks_price_map.get(ticker) or p.get('avg_price') or 0)
                avg_entry = float(p.get('avg_price') or 0)
                shares = float(p.get('shares') or 0)
                
                upnl_usd = (cur_price - avg_entry) * shares
                upnl_pct = ((cur_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else 0
                
                # Fetch Fibonacci Zone for Stocks
                # 1. Try market_snapshot (New unified table)
                fib_zone_stock = 0
                try:
                    snap_stock = supabase.table('market_snapshot') \
                        .select('fibonacci_zone') \
                        .eq('symbol', ticker) \
                        .maybe_single() \
                        .execute()
                    
                    if snap_stock and snap_stock.data:
                        fib_zone_stock = snap_stock.data.get('fibonacci_zone', 0)
                    else:
                        # 2. Try technical_scores (Stocks specific table)
                        tech_res = supabase.table('technical_scores') \
                            .select('signals_json') \
                            .eq('ticker', ticker) \
                            .maybe_single() \
                            .execute()
                        if tech_res and tech_res.data:
                            sigs = tech_res.data.get('signals_json', {})
                            fib_zone_stock = sigs.get('fib_zone_15m', 0)
                except Exception as e:
                    log_error("portfolio", f"Error fetching fib zone for {ticker}: {e}")
                    fib_zone_stock = 0

                active_stocks.append({
                    'symbol': ticker,
                    'side': 'long',
                    'avg_entry_price': avg_entry,
                    'current_price': cur_price,
                    'unrealized_pnl_usd': round(upnl_usd, 2),
                    'unrealized_pnl_pct': round(upnl_pct, 2),
                    'fibonacci_zone': fib_zone_stock,
                    'total_investment': round((avg_entry * shares) / lev_stocks, 2),
                    'quantity': shares,
                    'rule_code': p.get('group_name', 'S01'),
                    'status': 'active'
                })

        # Recent activity (Consolidated last 10)
        recent_crypto = supabase.table('paper_trades').select('symbol, closed_at, total_pnl_usd, entry_price, close_reason, rule_code').not_.is_('closed_at', 'null').order('closed_at', desc=True).limit(10).execute().data or []
        recent_forex = supabase.table('forex_positions').select('symbol, closed_at, pnl_usd, entry_price, close_reason, rule_code').eq('status', 'closed').order('closed_at', desc=True).limit(10).execute().data or []
        recent_stocks = supabase.table('stocks_positions').select('ticker, updated_at, unrealized_pnl, avg_price, status').eq('status', 'closed').order('updated_at', desc=True).limit(10).execute().data or []
        
        combined_recent = []
        for t in recent_crypto:
            combined_recent.append({
                'time': t['closed_at'], 'market': 'Crypto', 'symbol': t['symbol'], 
                'pnl': float(t['total_pnl_usd'] or 0), 'entry': float(t['entry_price'] or 0),
                'status': t['close_reason'], 'rule': t.get('rule_code') or 'Dd61'
            })
        for t in recent_forex:
            combined_recent.append({
                'time': t['closed_at'], 'market': 'Forex', 'symbol': t['symbol'], 
                'pnl': float(t['pnl_usd'] or 0), 'entry': float(t['entry_price'] or 0),
                'status': t['close_reason'], 'rule': t.get('rule_code') or 'FX'
            })
        for t in recent_stocks:
            combined_recent.append({
                'time': t['updated_at'], 'market': 'Stocks', 'symbol': t['ticker'], 
                'pnl': float(t['unrealized_pnl'] or 0), 'entry': float(t['avg_price'] or 0),
                'status': 'closed', 'rule': 'Equity'
            })
        
        combined_recent.sort(key=lambda x: x['time'], reverse=True)
        final_recent = combined_recent[:10]
        
        recent_activity = []
        for t in final_recent:
            recent_activity.append({
                'time': t['time'],
                'market': t['market'],
                'symbol': t['symbol'],
                'rule': t['rule'],
                'dir': 'n/a',
                'status': t['status'],
                'pnl': t['pnl'],
                'entry_price': t['entry'],
                'quantity': 0 # Optional
            })

        # --- TOTALS CONSOLIDATION ---
        all_positions = symbols_data + forex_symbols_data + active_stocks
        active_only = [p for p in all_positions if p['status'] == 'active']
        
        total_pnl = sum(p['unrealized_pnl_usd'] for p in active_only)
        avg_roi = sum(p['unrealized_pnl_pct'] for p in active_only) / len(active_only) if active_only else 0.0

        return {
            'daily': {
                'pnl_usd':        round(daily_pnl, 2),
                'pnl_pct':        0.0,
                'win_rate':       round(win_rate, 1),
                'wins':           wins,
                'losses':         losses,
                'open_positions': len(active_only),
                'risk_global':    regime,
            },
            'summary': {
                'total_pnl_usd': round(total_pnl, 2),
                'avg_roi_pct':   round(avg_roi, 2)
            },
            'markets': {
                'crypto': {
                    'status':   'active',
                    'sprint':   None,
                    'regime':   regime,
                    'symbols':  symbols_data,
                    'pnl_usd':  round(sum(p['pnl'] for p in closed_today if p['market'] == 'crypto' and p.get('market_type') != 'forex_futures'), 2),
                    'positions': open_count,
                },
                'forex': {
                    'status':   'active',
                    'sprint':   None,
                    'regime':   'riesgo_medio',
                    'symbols':  forex_symbols_data,
                    'pnl_usd':  round(sum(p['pnl'] for p in closed_today if p['market'] == 'forex'), 2),
                    'positions': forex_open_count,
                },
                'stocks': {
                    'status':   'active',
                    'sprint':   None,
                    'regime':   'riesgo_controlado',
                    'symbols':  active_stocks,
                    'pnl_usd':  round(sum(p['pnl'] for p in closed_today if p['market'] == 'stocks'), 2),
                    'positions': stocks_open_count,
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
        
        # Fetch from all markets
        res_crypto = supabase.table('paper_trades').select('id, total_pnl_usd, closed_at, rule_code, mode').eq('mode', 'paper').not_.is_('closed_at', 'null').execute()
        res_forex = supabase.table('forex_positions').select('id, pnl_usd, closed_at, rule_code').eq('status', 'closed').execute()
        res_stocks = supabase.table('stocks_positions').select('id, ticker, unrealized_pnl, updated_at').eq('status', 'closed').execute()
        
        raw_combined = []
        for t in (res_crypto.data or []):
            raw_combined.append({**t, 'pnl': t['total_pnl_usd'], 'time': t['closed_at'], 'market': 'crypto'})
        for t in (res_forex.data or []):
            raw_combined.append({**t, 'pnl': t['pnl_usd'], 'time': t['closed_at'], 'market': 'forex'})
        for t in (res_stocks.data or []):
            raw_combined.append({**t, 'pnl': t['unrealized_pnl'], 'time': t['updated_at'], 'market': 'stocks'})

        def is_real_trade(t):
            pnl = t.get('pnl')
            if pnl is None: return False
            try:
                if abs(float(pnl)) < 0.0001: return False
            except: return False
            return True

        # Pre-parse dates
        all_closed = []
        for t in raw_combined:
            if is_real_trade(t):
                try:
                    ts = t['time'].replace('Z', '+00:00')
                    if '.' in ts:
                        prefix, rest = ts.split('.', 1)
                        sep = '+' if '+' in rest else ('-' if '-' in rest else None)
                        if sep:
                            micro_part, tz_part = rest.split(sep, 1)
                            micro_part = micro_part.ljust(6, '0')[:6]
                            ts = f"{prefix}.{micro_part}{sep}{tz_part}"
                        else:
                            micro_part = rest.ljust(6, '0')[:6]
                            ts = f"{prefix}.{micro_part}"
                    
                    t['dt_object'] = datetime.fromisoformat(ts)
                    t['total_pnl_usd'] = t['pnl'] # for calc_stats compatibility
                    all_closed.append(t)
                except Exception as date_e:
                    log_error("portfolio", f"Date parsing error: {date_e}")

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
            pnl = sum(float(t['pnl'] or 0) for t in trades)
            wins = len([t for t in trades if float(t['pnl'] or 0) > 0])
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

        # Combined stats from all markets
        crypto_month = [t for t in month_trades if t.get('market') == 'crypto']
        forex_month  = [t for t in month_trades if t.get('market') == 'forex']
        stocks_month = [t for t in month_trades if t.get('market') == 'stocks']
        
        crypto_stats = calc_stats(crypto_month)
        forex_stats  = calc_stats(forex_month)
        stocks_stats = calc_stats(stocks_month)

        by_market = {
            "crypto": { **crypto_stats, "status": "active" },
            "forex":  { **forex_stats,  "status": "active" },
            "stocks": { **stocks_stats, "status": "active" }
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
