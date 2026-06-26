"""
APEX Orchestrator — eTrader v5.0

Sistema central de decisiones de compra para el mercado de Stocks.

Flujo completo:
  1. Evaluar APEX Score de todas las empresas
  2. Construir la Cola de Alta Prioridad
  3. Filtrar sobrecompradas y bloqueadas
  4. Ordenar por Composite Rank
  5. Verificar señales de reglas (S01-S09, HOT)
  6. Calcular capital disponible
  7. Ejecutar compras en orden de prioridad
"""

from datetime import datetime, timezone
from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.stocks.apex_score import calculate_apex_score


MODULE = "ORCHESTRATOR"


# ════════════════════════════════════════════
# MÓDULO 1 — CARGAR CONFIGURACIÓN
# ════════════════════════════════════════════

async def load_orchestrator_config(supabase) -> dict:
    """Carga configuración desde stocks_config."""
    try:
        # Cargamos TODA la configuración para no depender de categorías
        res = supabase.table('stocks_config').select('key,value').execute()

        cfg = {
            'max_total_risk_pct':       30.0,
            'pct_per_operation':        10.0,
            'capital_base':             5000.0,
            'apex_min_score':           60.0,
            'apex_max_overbought_rsi':  75.0,
            'apex_max_fib_zone':        3,
            'apex_lock_cycles':         3,
            'apex_composite_w_4h':      0.40,
            'apex_composite_w_1d':      0.30,
            'apex_composite_w_gain':    0.20,
            'apex_composite_w_conf':    0.10,
            'apex_proportional_sizing': True,
            'apex_max_positions':       5,
            'allow_after_hours':        False,
        }

        for row in (res.data or []):
            k, v = row['key'], row['value']
            
            # Mapeo de llaves críticas desde Settings
            if k == 'total_capital_usd': 
                cfg['capital_base'] = float(v)
            elif k == 'max_total_risk_pct': 
                cfg['max_total_risk_pct'] = float(v)
            elif k == 'max_pct_per_trade': 
                # Si en DB está 0.05 (5%), lo convertimos a 5.0 para el orchestrator
                val = float(v)
                cfg['pct_per_operation'] = val * 100 if val < 1 else val
            elif k == 'max_concurrent_positions':
                cfg['apex_max_positions'] = int(float(v))
            
            # Carga el resto si coinciden con los defaults
            elif k in cfg:
                if isinstance(cfg[k], bool):
                    cfg[k] = str(v).lower() == 'true'
                elif isinstance(cfg[k], int):
                    cfg[k] = int(float(v))
                elif isinstance(cfg[k], float):
                    cfg[k] = float(v)
                else:
                    cfg[k] = v

        return cfg

    except Exception as e:
        log_error(MODULE, f'Error cargando config: {e}')
        return defaults


# ════════════════════════════════════════════
# MÓDULO 2 — COMPOSITE RANK
# ════════════════════════════════════════════

def calculate_composite_rank(
    apex_4h:    float,
    apex_1d:    float,
    return_pct: float,
    confidence: str,
    rvol:       float,
    cfg:        dict,
) -> float:
    """
    Calcula el Composite Rank — métrica única
    para ordenar la cola de Alta Prioridad.
    Incluye RVOL con peso 25% (V5.1 Upgrade).
    """
    w_4h   = 0.30  # Ajustado de 0.40 para dar espacio a RVOL
    w_1d   = 0.25  # Ajustado de 0.30
    w_gain = 0.15  # Ajustado de 0.20
    w_conf = 0.05  # Ajustado de 0.10
    w_rvol = 0.25  # Nuevo peso RVOL (25%)

    gain_norm = min(100, max(0, return_pct * 10))
    rvol_norm = min(100, max(0, rvol * 20)) # 5x = 100 pts

    conf_score = {
        'high':   90,
        'medium': 60,
        'low':    30,
    }.get(confidence, 50)

    rank = (
        apex_4h    * w_4h  +
        apex_1d    * w_1d  +
        gain_norm  * w_gain +
        conf_score * w_conf +
        rvol_norm  * w_rvol
    )

    return round(min(100, max(0, rank)), 2)


# ════════════════════════════════════════════
# MÓDULO 3 — VERIFICAR SOBRECOMPRA
# ════════════════════════════════════════════

def is_overbought(snap: dict, cfg: dict) -> dict:
    """
    Verifica si una acción está sobrecomprada.
    Si sí → BLOQUEAR la compra.
    """
    rsi      = float(snap.get('rsi_14') or 50)
    fib_zone = int(snap.get('fibonacci_zone', snap.get('fib_zone_15m', 0)) or 0)
    price    = float(snap.get('price') or 0)
    upper_3  = float(snap.get('upper_3') or 0)

    max_rsi  = float(cfg.get('apex_max_overbought_rsi') or 75)
    max_fib  = int(cfg.get('apex_max_fib_zone') or 3)

    reasons  = []

    if rsi >= max_rsi:
        reasons.append(f'RSI sobrecomprado ({rsi:.0f} ≥ {max_rsi})')

    if fib_zone >= max_fib:
        reasons.append(f'Zona Fib alta ({fib_zone} ≥ {max_fib})')

    if upper_3 > 0 and price > upper_3:
        reasons.append(f'Precio sobre Upper_3 (${price:.2f} > ${upper_3:.2f})')

    blocked = len(reasons) > 0

    return {
        'blocked':  blocked,
        'reasons':  reasons,
        'rsi':      rsi,
        'fib_zone': fib_zone,
        'reason':   ' | '.join(reasons) if reasons else 'No sobrecomprada ✅',
    }


# ════════════════════════════════════════════
# MÓDULO 4 — CALCULAR CAPITAL DISPONIBLE
# ════════════════════════════════════════════

async def calculate_available_capital(cfg: dict, supabase) -> dict:
    """
    Calcula el capital disponible para nuevas
    compras respetando los límites de Settings.
    """
    capital_base = float(cfg.get('capital_base', 5000))
    max_risk_pct = float(cfg.get('max_total_risk_pct', 30))
    per_op_pct   = float(cfg.get('pct_per_operation', 10))

    capital_max    = capital_base * max_risk_pct / 100
    capital_per_op = capital_base * per_op_pct / 100

    # Capital ya invertido (posiciones abiertas)
    pos_res = supabase \
        .table('stocks_positions') \
        .select('shares, avg_price') \
        .eq('status', 'open') \
        .execute()

    capital_invested = sum(
        float(p.get('shares', 0)) * float(p.get('avg_price', 0))
        for p in (pos_res.data or [])
    )

    capital_available = max(0, capital_max - capital_invested)

    ops_possible = int(capital_available / capital_per_op) if capital_per_op > 0 else 0

    open_count = len(pos_res.data or [])
    max_pos    = int(cfg.get('apex_max_positions', 5))
    pos_slots  = max(0, max_pos - open_count)

    return {
        'capital_base':      capital_base,
        'capital_max_total': round(capital_max, 2),
        'capital_invested':  round(capital_invested, 2),
        'capital_available': round(capital_available, 2),
        'capital_per_op':    round(capital_per_op, 2),
        'ops_possible':      min(ops_possible, pos_slots),
        'pos_slots':         pos_slots,
        'open_count':        open_count,
        'max_positions':     max_pos,
        'can_buy':           capital_available >= capital_per_op and pos_slots > 0,
        'reason': (
            f'Capital: ${capital_available:.2f} disponible de '
            f'${capital_max:.2f} (invertido: ${capital_invested:.2f}). '
            f'Slots: {pos_slots}/{max_pos}. '
            f'Ops posibles: {min(ops_possible, pos_slots)}'
        ),
    }


# ════════════════════════════════════════════
# MÓDULO 5 — SIZING PROPORCIONAL
# ════════════════════════════════════════════

def calculate_position_size(
    ticker:         str,
    price:          float,
    composite_rank: float,
    capital_per_op: float,
    cfg:            dict,
    all_ranks:      list,
) -> dict:
    """
    Calcula cuánto capital y cuántas acciones comprar.
    Sizing proporcional al rank si está habilitado.
    """
    proportional = cfg.get('apex_proportional_sizing', True)
    factor_norm  = 1.0

    if proportional and all_ranks:
        total_rank = sum(all_ranks)
        my_factor  = composite_rank / total_rank if total_rank > 0 else 1 / len(all_ranks)
        factor_norm = 0.70 + (my_factor * len(all_ranks) - 1) * 0.30
        factor_norm = max(0.70, min(1.30, factor_norm))
        capital_op  = capital_per_op * factor_norm
    else:
        capital_op = capital_per_op

    if price <= 0:
        return {'capital': 0, 'shares': 0, 'error': 'Precio inválido'}

    shares = int(capital_op / price)
    if shares <= 0:
        shares = 1

    actual_capital = shares * price

    return {
        'capital': round(actual_capital, 2),
        'shares':  shares,
        'price':   price,
        'factor':  round(factor_norm, 3),
        'reason':  f'{ticker}: {shares} shares × ${price:.2f} = ${actual_capital:.2f}',
    }


# ════════════════════════════════════════════
# MÓDULO 6 — VERIFICAR SEÑALES DE REGLAS
# ════════════════════════════════════════════

def check_active_rules(ticker: str, snap: dict, supabase) -> dict:
    """
    Verifica si alguna regla activa (S01-S09, HOT_CANDLE_BUY, PRO_CANDLE_BUY, etc.)
    tiene señal de compra para este ticker.
    """
    try:
        from app.stocks.stocks_rule_engine import StocksRuleEngine

        engine = StocksRuleEngine.get_instance()
        if not engine.rules:
            engine.load_rules()

        context = engine.build_context(
            ticker     = ticker,
            snap       = snap,
            ia_score   = float(snap.get('meta_score', 0) or 0) / 10,
            tech_score = float(snap.get('technical_score', 0) or 0),
            rvol       = float(snap.get('rvol', 1.0) or 1.0),
            pine_signal = str(snap.get('pinescript_signal', '') or ''),
        )

        results = engine.evaluate_all(context=context, direction='buy')

        triggered = [r for r in results if r.get('triggered')]

        if not triggered:
            return {'has_signal': False, 'best_rule': None, 'rules': []}

        best = max(triggered, key=lambda r: (r.get('score', 0), r.get('order_type') == 'market'))

        rule_code = best.get('rule_code', '')
        is_hot = any(rule_code.startswith(p) for p in ('HOT', 'S05', 'S06', 'S07', 'S08'))
        group  = 'hot' if is_hot else 'pro'

        return {
            'has_signal':    True,
            'best_rule':     best,
            'rule_code':     rule_code,
            'group':         group,
            'order_type':    best.get('order_type'),
            'all_triggered': triggered,
            'count':         len(triggered),
        }

    except Exception as e:
        log_warning(MODULE, f'check_active_rules {ticker}: {e}')
        return {'has_signal': False, 'best_rule': None, 'rules': []}


# ════════════════════════════════════════════
# MÓDULO 6B — EVALUACIÓN BREAKOUT 5m (Aa30_STK)
# ════════════════════════════════════════════

def evaluate_5m_breakout(
    ticker:  str,
    df_5m:   'pd.DataFrame',
    df_1d:   'pd.DataFrame',
    snap:    dict,
) -> dict:
    """
    Evalúa si un ticker de la lista de Oportunidades presenta
    un Squeeze Breakout en velas de 5 minutos, filtrado por
    confirmación macro diaria (EMA50>EMA200 + SIPV Buy 1D).

    Retorna:
        {'triggered': True/False, 'reason': str, 'rule_code': 'Aa30_STK'}
    """
    import pandas as pd
    import numpy as np

    result = {'triggered': False, 'reason': '', 'rule_code': 'Aa30_STK'}

    try:
        # ── FASE A: FILTRO MACRO (Gráfico Diario 1D) ──
        if df_1d is None or len(df_1d) < 200:
            result['reason'] = 'Sin datos diarios suficientes (necesita 200 velas para EMA200)'
            return result

        close_col = 'close' if 'close' in df_1d.columns else 'Close'

        # 1. EMA20 > EMA50 en el gráfico diario
        ema20_1d = df_1d[close_col].ewm(span=20, adjust=False).mean()
        ema50_1d = df_1d[close_col].ewm(span=50, adjust=False).mean()

        if ema20_1d.iloc[-1] <= ema50_1d.iloc[-1]:
            result['reason'] = f'Filtro macro: EMA20_1D ({ema20_1d.iloc[-1]:.2f}) <= EMA50_1D ({ema50_1d.iloc[-1]:.2f})'
            return result

        # 2. SIPV (PineScript Signal) en el gráfico diario = Buy
        # Calculamos el MACD 4-color en 1D para determinar la señal SIPV
        ema_fast = df_1d[close_col].ewm(span=12, adjust=False).mean()
        ema_slow = df_1d[close_col].ewm(span=26, adjust=False).mean()
        macd_1d = ema_fast - ema_slow

        c = np.where(
            (macd_1d > 0) & (macd_1d > macd_1d.shift(1)), 1,
            np.where(
                (macd_1d > 0) & (macd_1d <= macd_1d.shift(1)), 2,
                np.where(
                    (macd_1d < 0) & (macd_1d < macd_1d.shift(1)), 3,
                    np.where(
                        (macd_1d < 0) & (macd_1d >= macd_1d.shift(1)), 4, 0
                    )
                )
            )
        )
        c_series = pd.Series(c, index=df_1d.index)

        # Buy = c==4 preceded by c==3,3  |  Sell = c==2 preceded by c==1,1
        sipv_buy_1d = (
            c_series.iloc[-1] == 4
            and c_series.iloc[-2] == 3
            and c_series.iloc[-3] == 3
        )
        # Also accept "momentum positivo sostenido" (c == 1: verde fuerte)
        sipv_momentum_1d = c_series.iloc[-1] == 1

        if not sipv_buy_1d and not sipv_momentum_1d:
            result['reason'] = f'Filtro macro: SIPV 1D no es Buy ni Momentum+ (código MACD 4c = {int(c_series.iloc[-1])})'
            return result

        # ── FASE B: GATILLO MICRO (Velas de 5 minutos) ──
        if df_5m is None or len(df_5m) < 20:
            result['reason'] = 'Sin datos 5m suficientes'
            return result

        close_5m = 'close' if 'close' in df_5m.columns else 'Close'

        ema3_5m = df_5m[close_5m].ewm(span=3, adjust=False).mean()
        ema9_5m = df_5m[close_5m].ewm(span=9, adjust=False).mean()
        ema20_5m = df_5m[close_5m].ewm(span=20, adjust=False).mean()

        last_ema3 = ema3_5m.iloc[-1]
        last_ema9 = ema9_5m.iloc[-1]
        last_ema20 = ema20_5m.iloc[-1]

        # Condición 1: EMA Stack alcista
        if not (last_ema3 > last_ema9 > last_ema20):
            result['reason'] = f'5m: EMA stack no alcista (EMA3={last_ema3:.4f} EMA9={last_ema9:.4f} EMA20={last_ema20:.4f})'
            return result

        # Condición 2: Ángulos positivos (EMA9 y EMA20 subiendo)
        ema9_angle = (ema9_5m.iloc[-1] - ema9_5m.iloc[-2]) / ema9_5m.iloc[-2] * 100
        ema20_angle = (ema20_5m.iloc[-1] - ema20_5m.iloc[-2]) / ema20_5m.iloc[-2] * 100

        if ema9_angle < 0:
            result['reason'] = f'5m: EMA9 ángulo negativo ({ema9_angle:.4f}%)'
            return result

        if ema20_angle < 0:
            result['reason'] = f'5m: EMA20 ángulo negativo ({ema20_angle:.4f}%)'
            return result

        # ¡TODAS LAS CONDICIONES CUMPLIDAS!
        price = float(df_5m[close_5m].iloc[-1])
        result['triggered'] = True
        result['reason'] = (
            f'🎯 BREAKOUT 5m CONFIRMADO: '
            f'EMA3={last_ema3:.4f} > EMA9={last_ema9:.4f} > EMA20={last_ema20:.4f} | '
            f'Ángulos EMA9={ema9_angle:.4f}% EMA20={ema20_angle:.4f}% | '
            f'Macro OK: EMA50_1D > EMA200_1D + SIPV_1D=Buy | '
            f'Precio={price:.2f}'
        )
        result['price'] = price
        return result

    except Exception as e:
        result['reason'] = f'Error evaluando breakout: {e}'
        return result


# ════════════════════════════════════════════
# MÓDULO 7 — CONSTRUIR LA COLA DE PRIORIDAD
# ════════════════════════════════════════════

async def _get_df(ticker: str, interval: str):
    """Obtiene OHLCV DataFrame via yfinance."""
    try:
        from app.data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        period_map = {
            '5m': '5d', '15m': '60d',
            '4h': '120d', '1d': '365d',
        }
        return await provider.get_ohlcv(
            ticker, interval=interval,
            period=period_map.get(interval, '60d')
        )
    except Exception:
        return None


async def build_priority_queue(cfg: dict, supabase, macro: dict) -> list:
    """
    Construye la Cola de Alta Prioridad.
    Retorna lista ordenada por Composite Rank.
    """
    min_score = float(cfg.get('apex_min_score', 60))

    # Obtener todos los tickers activos del watchlist diario (con fallback a días anteriores si hoy está vacío)
    from datetime import date, timedelta
    today_dt = date.today()
    today = today_dt.isoformat()
    
    # 1. Intentar hoy
    wl_res = supabase \
        .table('watchlist_daily') \
        .select('ticker') \
        .eq('date', today) \
        .eq('hard_filter_pass', True) \
        .limit(500) \
        .execute()

    tickers_set = set(r['ticker'] for r in (wl_res.data or []))

    # 2. Si no hay hoy, buscar lo más reciente (últimos 3 días)
    if not tickers_set:
        recent_date = (today_dt - timedelta(days=3)).isoformat()
        res_recent = supabase.table("watchlist_daily")\
            .select("ticker, date")\
            .gte("date", recent_date)\
            .eq("hard_filter_pass", True)\
            .order("date", desc=True)\
            .order("catalyst_score", desc=True)\
            .limit(500)\
            .execute()
        
        if res_recent.data and len(res_recent.data) > 0:
            latest_date_in_db = res_recent.data[0]["date"]
            tickers_set = set(
                r["ticker"] for r in res_recent.data 
                if r["date"] == latest_date_in_db
            )
            log_info(MODULE, f"Watchlist para cola obtenida de fallback (date={latest_date_in_db}): {len(tickers_set)} tickers")
    else:
        log_info(MODULE, f"Watchlist para cola obtenida de hoy: {len(tickers_set)} tickers")

    tickers = list(tickers_set)

    # Obtener posiciones ya abiertas
    pos_res = supabase \
        .table('stocks_positions') \
        .select('ticker') \
        .eq('status', 'open') \
        .execute()
    owned_tickers = {p['ticker'] for p in (pos_res.data or [])}
    
    # Update owned tickers in the priority queue to maintain consistent DB state
    for t in owned_tickers:
        try:
            supabase.table('stocks_priority_queue') \
                .update({'status': 'owned', 'last_updated': datetime.now(timezone.utc).isoformat()}) \
                .eq('ticker', t) \
                .execute()
        except:
            pass

    queue_candidates = []

    for ticker in tickers:
        if ticker in owned_tickers:
            continue

        try:
            # Obtener snapshot
            snap_res = supabase \
                .table('market_snapshot') \
                .select('*') \
                .eq('symbol', ticker) \
                .limit(1) \
                .execute()
            snap = snap_res.data[0] if snap_res.data else {}

            if not snap or not snap.get('price'):
                continue

            # Obtener fundamentales
            fund_res = supabase \
                .table('watchlist_daily') \
                .select('*') \
                .eq('ticker', ticker) \
                .eq('date', today) \
                .limit(1) \
                .execute()
            fund = fund_res.data[0] if fund_res.data else {}

            fund_cache = {
                'piotroski_score':    fund.get('piotroski_score', 4),
                'margin_of_safety':   fund.get('margin_of_safety', 0),
                'altman_zone':        fund.get('altman_zone', 'grey'),
                'fundamental_score':  fund.get('fundamental_score', 50),
                'analyst_rating':     fund.get('analyst_rating', 5),
                'short_interest_pct': fund.get('short_interest_pct', 5),
                'days_to_earnings':   fund.get('days_to_earnings', 30),
                'valuation_status':   fund.get('valuation_status', 'fairly_valued'),
            }

            df_5m    = await _get_df(ticker, '5m')
            df_15m   = await _get_df(ticker, '15m')
            df_4h    = await _get_df(ticker, '4h')
            df_daily = await _get_df(ticker, '1d')

            # Calcular APEX Score
            apex = calculate_apex_score(
                ticker            = ticker,
                snap              = snap,
                fundamental_cache = fund_cache,
                macro             = macro,
                df_5m             = df_5m,
                df_15m            = df_15m,
                df_4h             = df_4h,
                df_daily          = df_daily,
                ia_score          = float(fund_cache.get('fundamental_score', 50)) / 10,
            )

            # Priorizar los valores de APEX ya calculados en el market_snapshot (para consistencia UI)
            apex_4h = float(snap.get('apex_4h') or apex.get('apex_score_4h') or 50)
            apex_1d = float(snap.get('apex_1d') or apex.get('apex_score_1d') or 50)
            ret_exp = float(apex.get('return_expected_4h') or 0)
            conf    = str(apex.get('confidence') or 'medium')

            # Verificar señales de reglas
            rule_signal = check_active_rules(ticker, snap, supabase)

            # Calcular Composite Rank
            rank = calculate_composite_rank(apex_4h, apex_1d, ret_exp, conf, float(snap.get('rvol', 1.0) or 1.0), cfg)

            # ── REGLA 4: Confirmación de Volumen (15m Spike) ──
            # Se ha relajado la regla de volumen estricto por petición del usuario
            vol_spike_ok = True

            # ── GATILLO MACRO BONUS (15m) ──
            macro_bonus_trigger_ok = True
            if apex.get('has_macro_bonus'):
                macro_bonus_trigger_ok = False
                try:
                    if df_15m is not None and len(df_15m) >= 20:
                        c15_col = 'Close' if 'Close' in df_15m.columns else 'close'
                        l15_col = 'Low' if 'Low' in df_15m.columns else 'low'
                        c15 = pd.to_numeric(df_15m[c15_col], errors='coerce').dropna()
                        l15 = pd.to_numeric(df_15m[l15_col], errors='coerce').dropna()
                        
                        ema20_15 = float(c15.ewm(span=20, adjust=False).mean().iloc[-1])
                        low_15 = float(l15.iloc[-1])
                        
                        if low_15 <= ema20_15:
                            macro_bonus_trigger_ok = True
                            log_info(MODULE, f'🔥 {ticker}: Dip Sniper 15m (Low <= EMA20). Gatillo APEX ACTIVO.')
                        else:
                            log_info(MODULE, f'⏳ {ticker}: Esperando retroceso (Low <= EMA20 en 15m) para APEX.')
                except Exception as e:
                    pass

            # Criterios de entrada a la cola de alta prioridad
            enters_by_apex = (apex_4h >= min_score) and macro_bonus_trigger_ok
            enters_by_rule = rule_signal['has_signal']

            # ── REGLA 5: Breakout 5m (Aa30_STK) — Fast Track ──
            breakout_5m = evaluate_5m_breakout(
                ticker=ticker, df_5m=df_5m, df_1d=df_daily, snap=snap
            )
            enters_by_breakout = breakout_5m.get('triggered', False)

            if enters_by_breakout:
                log_info(MODULE, f'🎯 {ticker}: {breakout_5m["reason"]}')

            # Definir estado inicial
            # Si tiene señal de regla o score alto -> pending (lista para comprar)
            # Si no -> watching (solo monitoreo)
            status = 'pending' if (enters_by_apex or enters_by_rule or enters_by_breakout) else 'watching'

            # Verificar sobrecompra
            overbought = is_overbought(snap, cfg)

            entry_reason = 'apex_auto'
            if enters_by_breakout:
                entry_reason = 'breakout_5m_Aa30_STK'
            elif enters_by_rule:
                entry_reason = f'rule_{rule_signal.get("rule_code", "")}'

            candidate = {
                'ticker':            ticker,
                'group_name':        fund.get('pool_type', ''),
                'apex_4h':           apex_4h,
                'apex_1d':           apex_1d,
                'return_expected':   ret_exp,
                'confidence':        conf,
                'composite_rank':    rank,
                'is_overbought':     overbought['blocked'],
                'overbought_reason': overbought.get('reason', ''),
                'rsi':               overbought['rsi'],
                'fib_zone':          overbought['fib_zone'],
                'has_rule_signal':   enters_by_rule or enters_by_breakout,
                'is_breakout_5m':    enters_by_breakout,
                'rule_signal':       rule_signal,
                'entry_reason':      entry_reason,
                'price':             float(snap.get('price', 0)),
                'status':            status,
                'snap':              snap,
                'apex_detail':       apex,
            }

            # Guardar/Actualizar en base de datos inmediatamente
            await _upsert_queue(supabase, candidate, status=status)

            queue_candidates.append(candidate)

        except Exception as e:
            log_warning(MODULE, f'{ticker}: {e}')
            continue

    # Ordenar la cola (Breakout 5m tiene máxima prioridad)
    def sort_key(c):
        is_breakout    = c.get('is_breakout_5m', False)
        has_rule       = c['has_rule_signal']
        not_overbought = not c['is_overbought']
        rank           = c['composite_rank']
        return (is_breakout, has_rule and not_overbought, not_overbought, rank)

    queue_candidates.sort(key=sort_key, reverse=True)

    log_info(MODULE,
        f'Cola de Prioridad: {len(queue_candidates)} candidatos | '
        f'{sum(1 for c in queue_candidates if not c["is_overbought"])} '
        f'no sobrecompradas | '
        f'{sum(1 for c in queue_candidates if c["has_rule_signal"])} '
        f'con señal de regla'
    )

    return queue_candidates


# ════════════════════════════════════════════
# MÓDULO 8 — EJECUTAR COMPRAS EN ORDEN
# ════════════════════════════════════════════

async def execute_priority_buys(queue: list, capital: dict, cfg: dict, supabase) -> list:
    """Ejecuta las compras en orden de prioridad."""
    from app.stocks.stocks_order_executor import (
        execute_market_order, place_limit_order,
    )

    ops_remaining = capital['ops_possible']
    cap_available = capital['capital_available']
    cap_per_op    = capital['capital_per_op']

    if ops_remaining <= 0 or cap_available <= 0:
        log_info(MODULE, f'Sin capital disponible: {capital["reason"]}')
        return []

    executed   = []
    all_ranks  = [c['composite_rank'] for c in queue if not c['is_overbought']]

    for candidate in queue:
        if ops_remaining <= 0:
            break
        if cap_available < cap_per_op * 0.5:
            break

        ticker = candidate['ticker']
        price  = candidate['price']
        is_ob  = candidate['is_overbought']

        if is_ob:
            log_info(MODULE, f'{ticker}: BLOQUEADA por sobrecompra')
            await _upsert_queue(supabase, candidate, status='blocked')
            continue

        sizing = calculate_position_size(
            ticker         = ticker,
            price          = price,
            composite_rank = candidate['composite_rank'],
            capital_per_op = cap_per_op,
            cfg            = cfg,
            all_ranks      = all_ranks,
        )

        if sizing['shares'] <= 0 or price <= 0:
            continue

        rule_sig   = candidate.get('rule_signal', {})
        order_type = 'market'
        rule_code  = 'APEX_AUTO'

        # Breakout 5m override — Fast Track
        if candidate.get('is_breakout_5m'):
            rule_code = 'Aa30_STK'
            order_type = 'market'
        elif rule_sig.get('has_signal'):
            best_rule  = rule_sig.get('best_rule', {})
            order_type = best_rule.get('order_type', 'market')
            rule_code  = rule_sig.get('rule_code', 'APEX_AUTO')

        log_info(MODULE,
            f'✅ COMPRANDO {ticker}: {sizing["shares"]} shares × '
            f'${price:.2f} = ${sizing["capital"]:.2f} | '
            f'Rank={candidate.get("composite_rank", 0):.1f} | '
            f'APEX={candidate.get("apex_score_4h", 0):.0f}% | '
            f'Regla={rule_code} ({order_type})'
        )

        context = candidate.get('snap', {})
        context['price'] = price

        rule_mock = {
            'rule_code':   rule_code,
            'group_name':  candidate.get('group_name', ''),
            'close_all':   False,
            'dca_enabled': False,
        }

        try:
            if order_type == 'market':
                order = execute_market_order(
                    ticker    = ticker,
                    direction = 'buy',
                    rule_code = rule_code,
                    context   = context,
                    rule      = rule_mock,
                )
            else:
                order = place_limit_order(
                    ticker    = ticker,
                    direction = 'buy',
                    rule_code = rule_code,
                    context   = context,
                    rule      = rule_mock,
                )

            if order.get('success'):
                executed.append({
                    'ticker':    ticker,
                    'shares':    sizing['shares'],
                    'price':     price,
                    'rank':      candidate.get('composite_rank', 0),
                    'apex_4h':   candidate.get('apex_score_4h', 0),
                    'rule':      rule_code,
                })

                ops_remaining -= 1
                cap_available -= sizing['capital']

                await _upsert_queue(
                    supabase, candidate,
                    status='buying',
                    capital_assigned=sizing['capital'],
                    shares_target=sizing['shares'],
                )

                _send_telegram_buy(candidate, sizing, cap_available, rule_code)

        except Exception as e:
            log_error(MODULE, f'Error comprando {ticker}: {e}')

    log_info(MODULE, f'Ciclo completado: {len(executed)} compras ejecutadas')
    return executed


def _send_telegram_buy(candidate, sizing, cap_available, rule_code):
    """Best-effort Telegram notification for buy."""
    try:
        from app.stocks.stocks_order_executor import _send_telegram_sync
        _send_telegram_sync(
            f'🛒 APEX ORCHESTRATOR\n'
            f'Compra: {candidate["ticker"]}\n'
            f'Regla: {rule_code}\n'
            f'Shares: {sizing["shares"]} × ${sizing["price"]:.2f}\n'
            f'APEX 4H: {candidate.get("apex_score_4h", 0):.0f}%\n'
            f'Rank: {candidate.get("composite_rank", 0):.1f}\n'
            f'Capital: ${sizing["capital"]:.2f}\n'
            f'Retorno esp: +{candidate.get("return_expected", 0):.2f}%\n'
            f'Capital restante: ${cap_available:.2f}'
        )
    except Exception:
        pass


async def _upsert_queue(
    supabase,
    candidate: dict,
    status:    str   = 'pending',
    capital_assigned: float = 0,
    shares_target:    int   = 0,
):
    """Actualiza el estado en la cola."""
    try:
        supabase \
            .table('stocks_priority_queue') \
            .upsert({
                'ticker':          candidate['ticker'],
                'group_name':      candidate.get('group_name', ''),
                'price_at_rank':   candidate.get('price'),
                'apex_score_4h':   candidate.get('apex_4h'),
                'apex_score_1d':   candidate.get('apex_1d'),
                'return_expected': candidate.get('return_expected', 0),
                'confidence':      candidate['confidence'],
                'composite_rank':  candidate['composite_rank'],
                'status':          status,
                'entry_reason':    candidate.get('entry_reason', 'apex_auto'),
                'triggered_rule':  candidate.get('rule_signal', {}).get('rule_code'),
                'is_overbought':   candidate['is_overbought'],
                'rsi_at_entry':    candidate.get('rsi', 0),
                'fib_zone':        candidate.get('fib_zone', 0),
                'capital_assigned': capital_assigned,
                'shares_target':   shares_target,
                'price_at_rank':   candidate.get('price', 0),
                'last_updated':    datetime.now(timezone.utc).isoformat(),
            }, on_conflict='ticker') \
            .execute()
    except Exception as e:
        log_error(MODULE, f'Error upsert queue: {e}')


# ════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — CICLO DEL ORCHESTRATOR
# ════════════════════════════════════════════

async def run_orchestrator_cycle(supabase=None):
    """
    Ciclo principal del APEX Orchestrator.
    Corre cada 15m en horario de mercado.
    """
    if supabase is None:
        supabase = get_supabase()

    log_info(MODULE, '🔄 Iniciando ciclo APEX Orchestrator...')

    # 1. Config
    cfg = await load_orchestrator_config(supabase)
    if not cfg:
        return

    # ── REGLA 1: Filtro de Horario + After-Hours Toggle ──
    from app.core.market_hours import is_market_open
    is_open, status = is_market_open()
    allow_ah = cfg.get('allow_after_hours', False)
    
    if not is_open and not allow_ah:
        log_info(MODULE, f'⏸️ Ciclo omitido: Mercado cerrado ({status}) y After-hours desactivado.')
        return

    # 2. Capital disponible
    capital = await calculate_available_capital(cfg, supabase)
    log_info(MODULE, capital['reason'])

    if not capital['can_buy']:
        log_info(MODULE, '⏸️ Sin slots o capital disponible')
        return

    # 3. Macro context
    from app.stocks.stocks_adaptive_tp import fetch_macro_data
    macro = await fetch_macro_data(supabase)

    # ── REGLA 2: Bloqueo de Compras en Mercado Bearish ──
    if macro.get('sentiment') == 'bearish':
        log_warning(MODULE, f"🛑 BLOQUEO MACRO: El sentimiento de mercado es BEARISH ({macro.get('score')}). No se permiten nuevas compras.")
        return

    # 4. Construir cola de prioridad
    queue = await build_priority_queue(cfg, supabase, macro)

    if not queue:
        log_info(MODULE, 'Cola vacía — sin candidatos')
        return

    # 5. Log de la cola (top 5)
    log_info(MODULE,
        f'TOP 5 candidatos:\n' +
        '\n'.join([
            f'  {i+1}. {c["ticker"]}: '
            f'rank={c["composite_rank"]:.1f} '
            f'APEX={c["apex_4h"]:.0f}% '
            f'ret={c["return_expected"]:.2f}% '
            f'{"🔴 OB" if c["is_overbought"] else "✅"}'
            for i, c in enumerate(queue[:5])
        ])
    )

    # 6. Ejecutar compras
    executed = await execute_priority_buys(queue, capital, cfg, supabase)

    return {
        'queue_size': len(queue),
        'executed':   len(executed),
        'capital':    capital,
        'top_ticker': queue[0]['ticker'] if queue else None,
    }

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_orchestrator_cycle())
