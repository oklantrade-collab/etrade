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
    Consolida métricas de todos los mercados activos de forma optimizada.
    """
    from app.core.logger import log_error
    try:
        supabase = get_supabase()
        import pytz
        lima_tz = pytz.timezone('America/Lima')
        now_lima = datetime.now(lima_tz)
        today_start_lima = now_lima.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_lima.astimezone(timezone.utc).isoformat()

        # --- 1. CONFIGURACIÓN ---
        cfg_res = supabase.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
        cfg = cfg_res.data if cfg_res else {}
        
        lev_crypto = float(cfg.get('leverage_crypto') or 5)
        lev_forex  = float(cfg.get('leverage_forex') or 100)
        lev_stocks = float(cfg.get('leverage_stocks') or 1)
        active_crypto_symbols = cfg.get('active_symbols') if cfg else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
        forex_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
        
        # --- 2. CONSULTAS MASIVAS (CONSOLIDADAS) ---
        # Usamos promesas en paralelo para acelerar significativamente la respuesta
        import asyncio
        
        async def fetch_data():
            return await asyncio.gather(
                asyncio.to_thread(supabase.table('positions').select('*').eq('status', 'open').execute),
                asyncio.to_thread(supabase.table('forex_positions').select('*').eq('status', 'open').execute),
                asyncio.to_thread(supabase.table('stocks_positions').select('*').eq('status', 'open').execute),
                asyncio.to_thread(supabase.table('market_snapshot').select('*').in_('symbol', list(set(active_crypto_symbols + forex_symbols))).execute),
                asyncio.to_thread(supabase.table('paper_trades').select('total_pnl_usd').gte('closed_at', today_start).execute),
                asyncio.to_thread(supabase.table('forex_positions').select('pnl_usd').eq('status', 'closed').gte('closed_at', today_start).execute),
                asyncio.to_thread(supabase.table('stocks_positions').select('unrealized_pnl').eq('status', 'closed').gte('updated_at', today_start).execute),
                asyncio.to_thread(supabase.table('market_regime').select('category').order('evaluated_at', desc=True).limit(1).execute),
                # Para Win Rate (Solo traemos counts si es posible, o limitamos)
                asyncio.to_thread(supabase.table('paper_trades').select('total_pnl_usd').not_.is_('closed_at', 'null').execute),
                asyncio.to_thread(supabase.table('forex_positions').select('pnl_usd').eq('status', 'closed').execute)
            )

        results = await fetch_data()
        
        open_crypto_pos_res = results[0]
        open_forex_pos_res  = results[1]
        open_stocks_pos_res = results[2]
        snapshot_res        = results[3]
        closed_crypto_res   = results[4]
        closed_forex_res    = results[5]
        closed_stocks_res   = results[6]
        latest_regime       = results[7]
        all_closed_crypto   = results[8]
        all_closed_forex    = results[9]

        market_snaps = {row['symbol']: row for row in (snapshot_res.data or [])}
        regime = latest_regime.data[0]['category'] if latest_regime.data else 'riesgo_medio'


        # --- 3. PROCESAMIENTO ---
        
        full_history = [float(p['total_pnl_usd'] or 0) for p in (all_closed_crypto.data or [])]
        full_history += [float(p['pnl_usd'] or 0) for p in (all_closed_forex.data or [])]
        
        wins = len([p for p in full_history if p > 0])
        win_rate = (wins / len(full_history) * 100) if full_history else 0.0

        # Daily PnL
        daily_pnl = sum(float(p['total_pnl_usd'] or 0) for p in (closed_crypto_res.data or []))
        daily_pnl += sum(float(p['pnl_usd'] or 0) for p in (closed_forex_res.data or []))
        daily_pnl += sum(float(p['unrealized_pnl'] or 0) for p in (closed_stocks_res.data or []))

        # Build Crypto symbols data
        open_crypto_map = {p['symbol']: p for p in (open_crypto_pos_res.data or [])}
        symbols_data = []
        for sym in active_crypto_symbols:
            snap = market_snaps.get(sym, {})
            pos = open_crypto_map.get(sym)
            cur_price = float(snap.get('price', 0.0))
            
            upnl_usd, upnl_pct, capital = 0.0, 0.0, 0.0
            if pos:
                entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or 0.0)
                # Capital: Notional / Leverage
                capital = (float(pos.get('size') or 0) * entry) / lev_crypto
                if entry > 0:
                    side_mult = 1 if str(pos.get('side', '')).lower() == 'long' else -1
                    upnl_pct = ((cur_price - entry) / entry) * 100 * side_mult
                    upnl_usd = capital * (upnl_pct / 100)

            symbols_data.append({
                'symbol': sym,
                'side': str(pos.get('side', '')).lower() if pos else None,
                'avg_entry_price': float(pos.get('avg_entry_price') or pos.get('entry_price') or 0) if pos else 0,
                'current_price': cur_price,
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'fibonacci_zone': snap.get('fibonacci_zone', 0),
                'rule_code': pos.get('rule_code', 'N/A') if pos else 'N/A',
                'total_investment': round(capital, 2),
                'status': 'active' if pos else 'hold'
            })

        # Build Forex symbols data
        open_forex_map = {p['symbol']: p for p in (open_forex_pos_res.data or [])}
        forex_symbols_data = []
        for sym in forex_symbols:
            snap = market_snaps.get(sym, {})
            pos = open_forex_map.get(sym)
            cur_price = float(snap.get('price', 0.0))
            
            upnl_usd, upnl_pct, total_inv = 0.0, 0.0, 0.0
            if pos:
                entry = float(pos.get('entry_price') or 0)
                lots = float(pos.get('lots') or 0)
                side = str(pos.get('side', '')).lower()
                pip_size = 0.01 if 'JPY' in sym or 'XAU' in sym else 0.0001
                pip_val = 10.0 # Approx
                
                if entry > 0 and cur_price > 0:
                    side_mult = 1 if side in ['long', 'buy'] else -1
                    pips = (cur_price - entry) / pip_size * side_mult
                    upnl_usd = pips * pip_val * lots
                    upnl_pct = (pips * pip_size / entry) * 100
                
                # Notional
                mult = 100.0 if 'XAU' in sym else 100000.0
                total_inv = (lots * mult * (cur_price or entry)) / lev_forex

            forex_symbols_data.append({
                'symbol': sym,
                'side': str(pos.get('side', '')).lower() if pos else None,
                'avg_entry_price': float(pos.get('entry_price') or 0) if pos else 0,
                'current_price': cur_price,
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'total_investment': round(total_inv, 2),
                'rule_code': pos.get('rule_code', 'N/A') if pos else 'N/A',
                'status': 'active' if pos else 'hold'
            })

        # Build Stocks symbols data (NEW)
        stocks_symbols_data = []
        for pos in (open_stocks_pos_res.data or []):
            cur_price = float(pos.get('current_price') or pos.get('avg_price') or 0.0)
            entry = float(pos.get('avg_price') or 0.0)
            shares = float(pos.get('shares') or 0)
            capital = entry * shares
            upnl_usd = (cur_price - entry) * shares
            upnl_pct = ((cur_price - entry) / entry * 100) if entry > 0 else 0

            stocks_symbols_data.append({
                'symbol': pos['ticker'],
                'side': 'long',
                'avg_entry_price': entry,
                'current_price': cur_price,
                'unrealized_pnl_usd': round(upnl_usd, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
                'total_investment': round(capital, 2),
                'quantity': shares,
                'rule_code': pos.get('rule_code', 'N/A'),
                'fibonacci_zone': 0, # Not used for stocks yet
                'status': 'active'
            })

        # Recent Activity (Optimized consolidation)
        # Fetching last 5 from each market
        recent_crypto = supabase.table('paper_trades').select('symbol, closed_at, total_pnl_usd, entry_price').not_.is_('closed_at', 'null').order('closed_at', desc=True).limit(5).execute().data or []
        recent_forex = supabase.table('forex_positions').select('symbol, closed_at, pnl_usd, entry_price').eq('status', 'closed').order('closed_at', desc=True).limit(5).execute().data or []
        recent_stocks = supabase.table('stocks_positions').select('ticker, updated_at, unrealized_pnl, avg_price, shares').eq('status', 'closed').order('updated_at', desc=True).limit(5).execute().data or []
        
        recent_activity = []
        for t in recent_crypto:
            recent_activity.append({'time': t['closed_at'], 'market': 'Crypto', 'symbol': t['symbol'], 'pnl': float(t['total_pnl_usd'] or 0), 'entry_price': t['entry_price'], 'status': 'closed'})
        for t in recent_forex:
            recent_activity.append({'time': t['closed_at'], 'market': 'Forex', 'symbol': t['symbol'], 'pnl': float(t['pnl_usd'] or 0), 'entry_price': t['entry_price'], 'status': 'closed'})
        for t in recent_stocks:
            recent_activity.append({'time': t['updated_at'], 'market': 'Stocks', 'symbol': t['ticker'], 'pnl': float(t['unrealized_pnl'] or 0), 'entry_price': t['avg_price'], 'quantity': t['shares'], 'status': 'closed'})
        
        recent_activity.sort(key=lambda x: x['time'], reverse=True)

        return {
            'daily': {
                'pnl_usd': round(daily_pnl, 2),
                'win_rate': round(win_rate, 1),
                'open_positions': len(open_crypto_pos_res.data or []) + len(open_forex_pos_res.data or []) + len(open_stocks_pos_res.data or []),
                'risk_global': regime,
            },
            'summary': {
                'total_pnl_usd': round(sum(p['unrealized_pnl_usd'] for p in symbols_data + forex_symbols_data + stocks_symbols_data), 2),
                'avg_roi_pct': round(sum(p['unrealized_pnl_pct'] for p in symbols_data + forex_symbols_data + stocks_symbols_data) / max(1, len(symbols_data + forex_symbols_data + stocks_symbols_data)), 2),
            },
            'markets': {
                'crypto': {'symbols': symbols_data, 'positions': len(open_crypto_pos_res.data or [])},
                'forex':  {'symbols': forex_symbols_data, 'positions': len(open_forex_pos_res.data or [])},
                'stocks': {'symbols': stocks_symbols_data, 'positions': len(open_stocks_pos_res.data or [])}
            },
            'recent_activity': recent_activity[:10]
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
        
        # Fetch from all markets (Parallelized)
        import asyncio
        async def fetch_perf():
            return await asyncio.gather(
                asyncio.to_thread(supabase.table('paper_trades').select('id, total_pnl_usd, closed_at, rule_code, mode').eq('mode', 'paper').not_.is_('closed_at', 'null').execute),
                asyncio.to_thread(supabase.table('forex_positions').select('id, pnl_usd, closed_at, rule_code').eq('status', 'closed').execute),
                asyncio.to_thread(supabase.table('stocks_positions').select('id, ticker, unrealized_pnl, updated_at').eq('status', 'closed').execute)
            )
        
        results_perf = await fetch_perf()
        res_crypto = results_perf[0]
        res_forex  = results_perf[1]
        res_stocks = results_perf[2]
        
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
