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
from app.stocks.apex_score import calculate_apex_score, calculate_apex_score_v2


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
    trade_score: float = None,
    etv:         float = None,
    buying_force_score: float = None,
    is_high_priority_growth: bool = False,
    is_intraday_alpha: bool = False,
    change_pct: float = None,
    has_news: bool = False,
    is_ema3_1h_ascending: bool = True,
    is_gap_runner: bool = False,
) -> float:
    """
    Calcula el Composite Rank — métrica única para ordenar la cola de Alta Prioridad.
    Prioriza la POTENCIALIDAD DE GANANCIA y RALLY DEL DÍA:
      1. Fuerza Compradora 5m (Buying Force): 45%
      2. Volumen Relativo (RVOL Institucional): 25%
      3. Potencial de Expansión / Catalizador / Top Gainer: 20%
      4. Alineación de Tendencia Horaria (EMA3 > EMA9 en 1H): 10%
    APEX Score actúa como filtro de salud técnica (penaliza si < 25%).
    """
    bf_val = float(buying_force_score if buying_force_score is not None else 50.0)

    # 1. Fuerza Compradora 5m (0 a 100) -> 45%
    score_bf = max(0.0, min(100.0, bf_val)) * 0.45

    # 2. RVOL Institucional (Normalizado: 4.0x = 100 pts) -> 25%
    rvol_float = float(rvol or 1.0)
    score_rvol = min(100.0, max(0.0, rvol_float * 25.0)) * 0.25

    # 3. Potencial de Ganancia y Catalizadores del Día -> 20%
    chg = float(change_pct if change_pct is not None else (return_pct or 0.0))
    # Una subida de +20% en el día equivale a 80 pts base
    gain_score = min(80.0, max(0.0, chg * 4.0))
    if has_news or is_intraday_alpha:
        gain_score += 20.0
    score_potential = min(100.0, gain_score) * 0.20

    # 4. Tendencia Horaria Favorable -> 10%
    score_trend = (100.0 if is_ema3_1h_ascending else 20.0) * 0.10

    rank = score_bf + score_rvol + score_potential + score_trend

    # Filtro de seguridad: penalizar si el gráfico macro está roto o en caída libre (< 25 APEX)
    if apex_4h < 25.0:
        rank = max(0.0, rank - 20.0)

    # ── BOOSTS DE MÁXIMA PRIORIDAD PARA RALLIES ACTIVOS ──
    if is_gap_runner:
        rank = max(rank + 25.0, 99.5)
    elif is_intraday_alpha:
        rank = max(rank, 98.5)
    elif is_high_priority_growth or bf_val >= 85.0:
        rank = max(rank, 95.0)
    elif bf_val >= 70.0:
        rank = max(rank, 88.0)

    max_cap = 99.9 if is_gap_runner else 99.0
    return round(min(max_cap, max(0.0, rank)), 2)



# ════════════════════════════════════════════
# MÓDULO 3 — VERIFICAR SOBRECOMPRA
# ════════════════════════════════════════════

def is_overbought(snap: dict, cfg: dict) -> dict:
    """
    Verifica si una acción está sobrecomprada.
    Si sí → BLOQUEAR la compra.
    Para Alpha Runners y Super-Runners de expansión, las zonas Fib altas y Upper_3 son normales en breakout y no deben bloquear.
    """
    rsi      = float(snap.get('rsi_14') or 50)
    fib_zone = int(snap.get('fibonacci_zone', snap.get('fib_zone_15m', 0)) or 0)
    price    = float(snap.get('price') or 0)
    upper_3  = float(snap.get('upper_3') or 0)

    max_rsi  = float(cfg.get('apex_max_overbought_rsi') or 75)
    max_fib  = int(cfg.get('apex_max_fib_zone') or 3)

    is_alpha = bool(
        snap.get('is_intraday_alpha') or 
        snap.get('is_expansion_runner') or 
        snap.get('is_early_momentum') or
        snap.get('is_momentum_runner') or
        snap.get('source') == 'live_top_gainers' or
        (float(snap.get('rvol') or 1.0) >= 2.5 and float(snap.get('change_pct') or 0.0) >= 5.0)
    )

    reasons  = []

    # EXENCIÓN INTELIGENTE PARA MOMENTUM RUNNERS:
    # En un rally de momentum/breakout explosivo (como TANH), RSI 15m se ubica naturalmente en 75-90.
    # Bloquear por RSI > 75 castiga a los verdaderos líderes institucionales.
    # Para runners calificados solo se bloquea ante clímax extremo (RSI >= 92).
    if not is_alpha:
        if rsi >= max_rsi:
            reasons.append(f'RSI sobrecomprado ({rsi:.0f} ≥ {max_rsi})')
        if fib_zone >= max_fib:
            reasons.append(f'Zona Fib alta ({fib_zone} ≥ {max_fib})')
        if upper_3 > 0 and price > upper_3:
            reasons.append(f'Precio sobre Upper_3 (${price:.2f} > ${upper_3:.2f})')
    else:
        if rsi >= 92.0:
            reasons.append(f'RSI Clímax Extremo ({rsi:.0f} ≥ 92)')

    # Trap Shield: Bloqueo innegociable de trampas de apertura
    if bool(snap.get('is_trap', False)):
        trap_msg = snap.get('trap_reason') or 'Apertura tramposa detectada por Trap Shield'
        reasons.append(f'Trap Shield: {trap_msg}')

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
    rule_code:      str = '',
) -> dict:
    """
    Calcula cuánto capital y cuántas acciones comprar.
    Sizing proporcional al rank si está habilitado.
    Para GAP_TRANCHE_1 se asigna un tercio (1/3 = 33.3%) del capital por operación.
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

    # Si es Tranche 1 de Open Gap Runner, aplicar 1/3 (33.3%)
    if str(rule_code).startswith('GAP_TRANCHE_1') or 'TRANCHE_1' in str(rule_code):
        capital_op = capital_op * 0.3333

    if price <= 0:
        return {'capital': 0, 'shares': 0, 'error': 'Precio inválido'}

    raw_shares = int(capital_op / price)
    shares = int(raw_shares // 5) * 5
    if shares < 5 and raw_shares >= 1:
        shares = raw_shares

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

    # 3. Inyectar Top Gainers y Alpha Runners en tiempo real (Rallies del día)
    try:
        from app.stocks.alpha_runner_scanner import scan_top_gainers_live
        live_gainers = scan_top_gainers_live(limit=25)
        for g in (live_gainers or []):
            tg = g.get('ticker')
            if tg and tg not in tickers_set:
                tickers_set.add(tg)
                log_info(MODULE, f"🚀 Inyectando Top Gainer en vivo a la cola: {tg} ({g.get('change_pct',0):+.1f}%, BF={g.get('buying_force_5m',0)})")
    except Exception as e_live:
        log_warning(MODULE, f"Bypass inyección live gainers a cola: {e_live}")

    tickers = list(tickers_set)

    # Obtener posiciones ya abiertas
    pos_res = supabase \
        .table('stocks_positions') \
        .select('ticker') \
        .eq('status', 'open') \
        .execute()
    owned_tickers = {p['ticker'] for p in (pos_res.data or [])}

    # ── COOLDOWN POST-CIERRE (60 MIN), LISTA NEGRA Y GUARDIA POST-CLÍMAX 1H ──
    cooling_down_tickers = set()
    blacklisted_tickers = set()
    climax_exited_tickers = set()
    try:
        now_utc = datetime.now(timezone.utc)
        start_of_day_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        journal_res = supabase.table('trades_journal') \
            .select('ticker, exit_date, pnl_pct, exit_reason') \
            .gte('exit_date', start_of_day_utc) \
            .execute()

        for jr in (journal_res.data or []):
            t = jr.get('ticker')
            if not t:
                continue
            exit_d_str = jr.get('exit_date')
            pnl_p = float(jr.get('pnl_pct') or 0.0)
            reason = str(jr.get('exit_reason') or '').lower()

            # Si sufrió una pérdida >= 2.5% o fue cortada por hard_cap / stop loss hoy, bloquear por el resto del día
            if pnl_p <= -2.5 or 'hard_cap' in reason or 'sl_' in reason:
                blacklisted_tickers.add(t)
                continue

            # Si salió hoy por Clímax 1H (1a/1b UPPER_6), registrar para evitar re-entrada prematura en 3a
            if '1b_upper6' in reason or 'climax' in reason or '2d3_' in reason:
                climax_exited_tickers.add(t)

            # Cooldown de 60 minutos después de cualquier cierre (ej. toma de ganancias o salida manual)
            if exit_d_str:
                try:
                    exit_dt = datetime.fromisoformat(str(exit_d_str).replace('Z', '+00:00'))
                    mins_since = (now_utc - exit_dt).total_seconds() / 60.0
                    if mins_since < 60.0:
                        cooling_down_tickers.add(t)
                except Exception:
                    pass
    except Exception as cd_err:
        log_warning(MODULE, f"Error verificando cooldown/lista negra intradía: {cd_err}")
    
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
        if ticker in blacklisted_tickers:
            log_info(MODULE, f"⛔ {ticker}: Bloqueada por Lista Negra intradía (Stop Loss o Hard Cap previo hoy).")
            continue
        if ticker in cooling_down_tickers:
            log_info(MODULE, f"⏳ {ticker}: En Cooldown post-cierre (<60 min). Omitiendo re-entrada prematura.")
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
                try:
                    import yfinance as yf
                    p_curr = float(yf.Ticker(ticker).fast_info.last_price or 0.0)
                    if p_curr > 0:
                        snap = {
                            'symbol': ticker,
                            'price': p_curr,
                            'change_pct': float(snap.get('change_pct') or 0.0) if isinstance(snap, dict) else 0.0,
                            'gap_pct': float(snap.get('gap_pct') or 0.0) if isinstance(snap, dict) else 0.0,
                        }
                    else:
                        continue
                except Exception:
                    continue

            # Enriquecer snap con signals_json de technical_scores (para disponer de pullback_triggered, pool_type, etc.)
            try:
                ts_res = supabase.table('technical_scores').select('signals_json').eq('ticker', ticker).limit(1).execute()
                if ts_res.data and isinstance(ts_res.data[0].get('signals_json'), dict):
                    for k_sig, v_sig in ts_res.data[0]['signals_json'].items():
                        if snap.get(k_sig) is None:
                            snap[k_sig] = v_sig
            except Exception:
                pass

            # Obtener fundamentales
            fund_res = supabase \
                .table('watchlist_daily') \
                .select('*') \
                .eq('ticker', ticker) \
                .eq('date', today) \
                .limit(1) \
                .execute()
            fund = fund_res.data[0] if fund_res.data else {}

            try:
                cache_res = supabase.table('fundamental_cache') \
                    .select('*') \
                    .eq('ticker', ticker) \
                    .limit(1) \
                    .execute()
                if cache_res.data:
                    fund.update(cache_res.data[0])
            except Exception:
                pass

            fund_cache = {
                'piotroski_score':    fund.get('piotroski_score', 4),
                'margin_of_safety':   fund.get('margin_of_safety', 0),
                'altman_zone':        fund.get('altman_zone', 'grey'),
                'fundamental_score':  fund.get('fundamental_score', 50),
                'analyst_rating':     fund.get('analyst_rating', 5),
                'short_interest_pct': fund.get('short_interest_pct', fund.get('short_percent_float', 5)),
                'days_to_earnings':   fund.get('days_to_earnings', 30),
                'valuation_status':   fund.get('valuation_status', 'fairly_valued'),
                
                # Nuevas métricas v2.0
                'peg_ratio':           fund.get('peg_ratio', 0),
                'pe_ratio':            fund.get('pe_ratio', 0),
                'forward_pe':          fund.get('forward_pe', 0),
                'free_cash_flow':      fund.get('free_cash_flow', 0),
                'market_cap':          float(fund.get('market_cap') or (fund.get('market_cap_mln', 1000) * 1e6)),
                'eps_growth_pct':      fund.get('eps_growth_qoq', 0),
                'revenue_growth_yoy':  fund.get('revenue_growth_yoy', 0),
                'revenue_growth_qoq':  fund.get('revenue_growth_qoq', 0),
                'fcf_growth_pct':      fund.get('fcf_growth_pct', 0),
                'short_percent_float': fund.get('short_percent_float', 5),
            }

            df_5m    = await _get_df(ticker, '5m')
            df_15m   = await _get_df(ticker, '15m')
            df_4h    = await _get_df(ticker, '4h')
            df_daily = await _get_df(ticker, '1d')

            # ── ESCUDO ANTI-CLÍMAX PARABÓLICO (NO COMPRAR EL BACKSIDE DE UN PUMP) ──
            chg_pct = float(snap.get('change_pct') or snap.get('gap_pct') or 0.0)
            if chg_pct >= 25.0 and df_15m is not None and len(df_15m) >= 10:
                try:
                    c15_col = 'Close' if 'Close' in df_15m.columns else 'close'
                    c15_s = pd.to_numeric(df_15m[c15_col], errors='coerce').dropna()
                    if len(c15_s) >= 10:
                        ema9_15 = float(c15_s.ewm(span=9, adjust=False).mean().iloc[-1])
                        cur_p = float(snap.get('price') or c15_s.iloc[-1])
                        if cur_p < ema9_15:
                            log_info(MODULE, f"⛔ {ticker}: Bloqueada por caída post-clímax (+{chg_pct:.1f}% hoy, pero Precio ${cur_p:.2f} < EMA9 15m ${ema9_15:.2f}).")
                            continue
                except Exception:
                    pass

            # Calcular APEX Score v2.0
            apex = calculate_apex_score_v2(
                ticker            = ticker,
                snap              = snap,
                fundamental_cache = fund_cache,
                macro             = macro,
                df_5m             = df_5m,
                df_15m            = df_15m,
                df_4h             = df_4h,
                df_daily          = df_daily,
                ia_score          = float(fund_cache.get('fundamental_score', 50)) / 10.0,
            )

            # Priorizar los valores de APEX ya calculados en el market_snapshot (para consistencia UI)
            apex_4h = float(snap.get('apex_4h') or apex.get('apex_score_4h') or 50)
            apex_1d = float(snap.get('apex_1d') or apex.get('apex_score_1d') or 50)
            ret_exp = float(apex.get('return_expected_4h') or 0)
            conf    = str(apex.get('confidence') or 'medium')
            trade_s = float(snap.get('trade_score') or apex.get('trade_score') or 50)
            etv_val = float(snap.get('etv') or apex.get('etv') or 0.0)

            # Verificar señales de reglas
            rule_signal = check_active_rules(ticker, snap, supabase)

            # Criterios e indicadores de fuerza compradora y momentum del día
            bf_score = float(snap.get('buying_force_score') or snap.get('buying_force_5m') or 0.0)
            is_trap = bool(snap.get('is_trap', False))
            is_intraday_alpha = bool(snap.get('is_intraday_alpha', False)) and (not is_trap)
            change_p_val = float(snap.get('change_pct') or snap.get('gap_pct') or 0.0)
            has_news_val = bool(snap.get('has_news', False))
            is_ema3_asc = bool(snap.get('is_ema3_1h_ascending', True))

            # ── REGLA 4: Confirmación de Volumen (15m Spike) ──
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

            # Verificar sobrecompra (con exención para Alpha Runners / Breakouts)
            overbought = is_overbought(snap, cfg)

            # Sección B: Gatillos de Compra/Recompra (3a, 4a, 4b, 4c, 4d)
            pullback_triggered = bool(snap.get('pullback_triggered', False)) and (not is_trap)
            pullback_type = str(snap.get('pullback_type') or '')
            # Guardia Post-Clímax 1H: Si ya salió por clímax 1H hoy, bloquear re-entrada 3a en EMA3_1H
            if ticker in climax_exited_tickers and '3A' in pullback_type.upper():
                log_info(MODULE, f"⛔ {ticker}: Regla 3a bloqueada porque el activo ya ejecutó salida de Clímax 1H hoy.")
                pullback_triggered = False

            # Detección de Super-Runner en Expansión (Open Gap Up con espacio libre en 1D a Bollinger Superior)
            enters_by_expansion = bool(snap.get('is_expansion_runner', False)) or (
                float(snap.get('gap_pct') or snap.get('change_pct') or 0.0) >= 5.0 and
                float(snap.get('room_to_bb_upper_1d') or 0.0) >= 20.0 and
                float(snap.get('rvol') or 1.0) >= 1.5
            )

            enters_by_pullback = pullback_triggered and (not overbought['blocked'] or 'LOWER' in pullback_type.upper() or '3A' in pullback_type.upper() or '4C' in pullback_type.upper())
            is_high_growth = bool(snap.get('is_high_growth_opp', False)) or enters_by_expansion or (bf_score >= 70 and not overbought['blocked'])
            enters_by_growth = is_high_growth and bool(snap.get('entry_route_1h') or enters_by_expansion)
            enters_by_alpha = (is_intraday_alpha or enters_by_expansion) and (not overbought['blocked'])

            enters_by_apex = (apex_4h >= min_score) and macro_bonus_trigger_ok
            enters_by_rule = rule_signal['has_signal']

            # ── REGLA 5: Breakout 5m (Aa30_STK) — Fast Track ──
            breakout_5m = evaluate_5m_breakout(
                ticker=ticker, df_5m=df_5m, df_1d=df_daily, snap=snap
            )
            enters_by_breakout = breakout_5m.get('triggered', False)

            # Detección y Priorización Institucional ADUANA OPEN GAP UP (LONGs)
            from app.options.aduana_gap_runner_options import get_min_gap_threshold
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            min_thresh = get_min_gap_threshold(ticker)
            gap_val = float(snap.get('gap_pct') or 0.0)
            chg_val = float(snap.get('change_pct') or 0.0)
            eff_gap = gap_val if gap_val != 0.0 else chg_val
            is_trap = bool(snap.get('is_trap', False))

            # Requisito Mínimo en 1H: (EMA3 > EMA9) Y (EMA3 ascendente) Y (RSI <= 70)
            h1_snap = get_live_1h_candle_and_sipv(ticker, float(snap.get('price') or 0.0))
            is_ema3_above_ema9 = bool(h1_snap.get('is_ema3_above_ema9', False))
            rsi_1h_snap = float(h1_snap.get('rsi_1h') or snap.get('rsi') or 50.0)
            meets_1h_req = is_ema3_above_ema9 and is_ema3_asc and (rsi_1h_snap <= 70.0)

            is_open_gap_runner = (eff_gap >= min_thresh) and (not is_trap) and meets_1h_req

            # Calcular Composite Rank centrado en Fuerza Compradora y Potencial de Ganancia
            rank = calculate_composite_rank(
                apex_4h, apex_1d, ret_exp, conf, float(snap.get('rvol', 1.0) or 1.0), cfg,
                trade_score=trade_s, etv=etv_val,
                buying_force_score=bf_score,
                is_high_priority_growth=enters_by_growth,
                is_intraday_alpha=enters_by_alpha,
                change_pct=change_p_val,
                has_news=has_news_val,
                is_ema3_1h_ascending=is_ema3_asc,
                is_gap_runner=is_open_gap_runner,
            )

            if enters_by_expansion:
                log_info(MODULE, f'🟢 {ticker}: SUPER-RUNNER EXPANSION (Espacio 1D: +{snap.get("room_to_bb_upper_1d", 0):.1f}%, Gap: +{snap.get("gap_pct", 0):.1f}%, RVOL: {snap.get("rvol", 1):.1f}x) | COMPRA HABILITADA')
            elif enters_by_pullback:
                log_info(MODULE, f'🎯 {ticker}: Gatillo Sección B [{pullback_type}] — {snap.get("pullback_reason", "")}')
            elif enters_by_alpha:
                log_info(MODULE, f'🚀 {ticker}: Intraday Alpha Sweet-Spot (Potencial +{snap.get("growth_potential_pct", 5.0)}%, Gap +{snap.get("gap_pct", 0.0)}%)')
            elif enters_by_breakout:
                log_info(MODULE, f'🎯 {ticker}: {breakout_5m["reason"]}')
            elif enters_by_growth:
                log_info(MODULE, f'🔥 {ticker}: High Growth Swing 1H ({snap.get("entry_route_1h")} en {snap.get("entry_support_1h")}) | BF Score={bf_score}')

            # Definir estado inicial
            status = 'pending' if (enters_by_expansion or enters_by_pullback or enters_by_alpha or enters_by_growth or enters_by_apex or enters_by_rule or enters_by_breakout) else 'watching'

            if is_open_gap_runner:
                rank = max(rank + 25.0, 99.8)   # Prioridad 1 Absoluta para el BOT
                status = 'pending'
                entry_reason = f'gap_runner_open_{eff_gap:.1f}%'
                log_info(MODULE, f'🚀 {ticker}: ADUANA OPEN GAP RUNNER (+{eff_gap:.1f}%) | PRIORIDAD INSTITUCIONAL 1')

            # Recalcular rank con boost si es super-runner expansión, pullback Sección B, intraday alpha o alto crecimiento
            if is_open_gap_runner:
                rank = max(rank, 99.8)
            elif enters_by_expansion:
                rank = max(rank, 99.5)
            elif enters_by_pullback:
                rank = max(rank, 98.8)
            elif enters_by_alpha:
                rank = max(rank, 98.5)
            elif enters_by_breakout:
                rank = max(rank, 98.0)
            elif enters_by_growth:
                rank = max(rank, 95.0)

            if is_open_gap_runner:
                entry_reason = f'gap_runner_open_{eff_gap:.1f}%'
            elif enters_by_expansion:
                entry_reason = f'expansion_runner_bb1d_{snap.get("room_to_bb_upper_1d", 0):.0f}%'
            elif enters_by_pullback:
                entry_reason = f'{pullback_type}: {snap.get("pullback_reason", "")}'[:50]
            elif enters_by_alpha:
                entry_reason = f'intraday_alpha_pot_{snap.get("growth_potential_pct", 5.0)}%'
            elif enters_by_growth:
                entry_reason = f'high_growth_1h_{snap.get("entry_route_1h", "pullback")}_{snap.get("entry_support_1h", "")}'
            elif enters_by_breakout:
                entry_reason = 'breakout_5m_Aa30_STK'
            elif enters_by_rule:
                entry_reason = f'rule_{rule_signal.get("rule_code", "")}'

            group_val = str(snap.get('pool_type') or fund.get('pool_type', '') or '')
            if is_intraday_alpha and 'ALPHA_RUNNER' not in group_val:
                group_val = f"ALPHA_RUNNER, {group_val}".strip(", ") if group_val else "ALPHA_RUNNER"

            candidate = {
                'ticker':            ticker,
                'group_name':        group_val,
                'apex_4h':           apex_4h,
                'apex_1d':           apex_1d,
                'return_expected':   ret_exp,
                'confidence':        conf,
                'composite_rank':    rank,
                'is_overbought':     False if (enters_by_pullback or enters_by_expansion or is_open_gap_runner) else overbought['blocked'],
                'is_expansion_runner': enters_by_expansion,
                'is_gap_runner':     is_open_gap_runner,
                'gap_pct':           eff_gap if is_open_gap_runner else float(snap.get('gap_pct') or 0.0),
                'overbought_reason': overbought.get('reason', ''),
                'rsi':               overbought['rsi'],
                'fib_zone':          overbought['fib_zone'],
                'has_rule_signal':   enters_by_expansion or enters_by_pullback or enters_by_rule or enters_by_breakout or enters_by_growth or is_open_gap_runner,
                'is_pullback_b':     enters_by_pullback,
                'pullback_rule_code': pullback_type if enters_by_pullback else '',
                'is_breakout_5m':    enters_by_breakout,
                'is_high_growth_opp': enters_by_growth,
                'buying_force_score': bf_score,
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

    # Ordenar la cola (Prioriza: 1. No sobrecompradas, 2. Open Gap Runner / VME Expansion (Prioridad 1 Institucional), 3. Señal activa, 4. Alta Fuerza Compradora BF >= 70, 5. Composite Rank descendente)
    def sort_key(c):
        is_runner      = bool(c.get('is_gap_runner') or 'VME' in str(c.get('triggered_rule', '')) or 'VOLATILITY' in str(c.get('group_name', '')))
        has_signal     = bool(c.get('has_rule_signal') or c.get('is_pullback_b') or c.get('is_breakout_5m'))
        not_overbought = not bool(c.get('is_overbought'))
        bf             = float(c.get('buying_force_score') or 0.0)
        rank           = float(c.get('composite_rank') or 0.0)
        return (not_overbought, is_runner, has_signal, bf >= 70.0, rank)

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

async def execute_priority_buys(queue: list, capital: dict, cfg: dict, supabase, is_macro_bearish: bool = False) -> list:
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
            log_info(MODULE, f'{ticker}: BLOQUEADA por sobrecompra ({candidate.get("overbought_reason", "")})')
            await _upsert_queue(supabase, candidate, status='blocked')
            continue

        # ── DISYUNTOR DIARIO & COOLDOWN (Propuesta #3) ──
        try:
            from app.core.circuit_breaker import can_open_new_trade
            can_open, cb_reason = can_open_new_trade(ticker)
            if not can_open:
                log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por Disyuntor/Cooldown ({cb_reason})")
                await _upsert_queue(supabase, candidate, status='blocked')
                continue
        except Exception as e_cb:
            log_warning(MODULE, f"Aviso evaluando disyuntor para {ticker}: {e_cb}")

        # ── MACRO SENTIMENT & RELATIVE STRENGTH vs SPY (Propuesta #1) ──
        try:
            from app.core.macro_sentiment_engine import evaluate_macro_sentiment
            from app.core.relative_strength import evaluate_relative_strength_qualification
            macro_eval = evaluate_macro_sentiment()
            macro_regime = macro_eval.get("regime", "NEUTRAL")
            spy_chg = float(macro_eval.get("spy_change_pct", 0.0))

            # Si el mercado está en RISK-OFF, compras long bloqueadas salvo catalizador extremo
            if not macro_eval.get("allow_stock_buys", True):
                has_catalyst = bool(candidate.get('has_news') or candidate.get('snap', {}).get('has_news', False))
                rvol_val = float(candidate.get('snap', {}).get('rvol', 1.0) or 1.0)
                if not (has_catalyst and rvol_val >= 3.0):
                    log_info(MODULE, f"⏸️ {ticker}: BLOQUEADA por Macro Sentiment ({macro_eval.get('label')})")
                    await _upsert_queue(supabase, candidate, status='blocked')
                    continue

            # Evaluar Fuerza Relativa (RS vs SPY)
            asset_chg = float(candidate.get('gap_pct') or candidate.get('snap', {}).get('change_pct', 0.0) or 0.0)
            rs_res = evaluate_relative_strength_qualification(asset_chg, spy_chg, macro_regime)
            if not rs_res.get("qualified", True):
                log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por Fuerza Relativa ({rs_res.get('reason')})")
                await _upsert_queue(supabase, candidate, status='blocked')
                continue
        except Exception as e_macro_rs:
            log_warning(MODULE, f"Aviso evaluando Macro/RS para {ticker}: {e_macro_rs}")

        # ── COST GUARD: SPREAD BID/ASK & VIABILIDAD DE COSTO (Propuesta #2) ──
        lmt_marketable = price
        try:
            from app.core.cost_guard import evaluate_stock_cost_feasibility, calculate_limit_marketable_price
            snap_c = candidate.get('snap', {}) or {}
            bid_val = float(snap_c.get('bid') or 0.0)
            ask_val = float(snap_c.get('ask') or 0.0)
            target_p = float(candidate.get('tactical_target_ceiling') or (price * 1.05))

            if bid_val > 0 and ask_val > 0:
                cost_res = evaluate_stock_cost_feasibility(bid_val, ask_val, price, target_p)
                if not cost_res.get("passed", True):
                    log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por Cost Guard ({cost_res.get('reason')})")
                    await _upsert_queue(supabase, candidate, status='blocked')
                    continue

            lmt_marketable = calculate_limit_marketable_price("buy", bid_val, ask_val, price)
        except Exception as e_cg:
            log_warning(MODULE, f"Aviso evaluando Cost Guard para {ticker}: {e_cg}")

        # En mercado BEARISH (SP500/Nasdaq en caída y VIX alto), BLOQUEO ESTRICTO:
        # SOLO se permite comprar si tiene catalizador genuino institucional (Noticia confirmada) O es Super-Runner de expansión con RVOL >= 3.0x y tendencia 1H confirmada
        # ── EVALUACIÓN DE RÉGIMEN ESTRUCTURAL 1D (EMA 3/9/20/50/200 + VWAP + ATR) ──
        try:
            from app.core.structural_regime_engine import evaluate_structural_regime
            st_regime = evaluate_structural_regime(ticker, price)
        except Exception as e_reg_orch:
            st_regime = {}

        # 1. CANDADO MACRO SECULAR: DEEP BEAR WINTER (Bajo EMA50/200)
        # Evita atrapar capital durante meses en activos en invierno bajista
        if st_regime.get("is_deep_bear_excluded"):
            log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por DEEP BEAR WINTER (Precio muy por debajo de EMA50/200, riesgo de meses atrapado).")
            await _upsert_queue(supabase, candidate, status='blocked')
            continue

        # 2. ADAPTACIÓN DE TAKE PROFIT PARA COUNTER_TREND_BOUNCE (Caso AAL)
        # Si la acción está rebotando en contratendencia, el TP se fija estrictamente en la EMA20 diaria
        if st_regime.get("regime_code") == "COUNTER_TREND_BOUNCE":
            candidate["tactical_target_ceiling"] = st_regime.get("target_ceiling", price * 1.03)
            log_info(MODULE, f"🟡 {ticker}: COUNTER TREND BOUNCE detectado. Techo dinámico fijado en EMA20 (${st_regime.get('target_ceiling'):.2f}).")

        # ── BLINDAJE ANTI-AGOTAMIENTO Y GAPS FALSOS (Módulos 1, 2, 3, 4, 5, 6) ──
        try:
            from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
            live_intraday = get_live_1h_candle_and_sipv(ticker, price)

            c_gap_pct = float(candidate.get('gap_pct') or candidate.get('snap', {}).get('gap_pct', 0.0) or 0.0)
            c_has_catalyst = bool(candidate.get('has_news') or candidate.get('snap', {}).get('has_news', False))
            c_cat_tier = int(candidate.get('catalyst_tier') or candidate.get('snap', {}).get('catalyst_tier', 3) or 3)
            c_rvol = float(candidate.get('snap', {}).get('rvol', 1.0) or candidate.get('rvol', 1.0) or 1.0)
            c_mcap = float(candidate.get('market_cap') or candidate.get('snap', {}).get('market_cap', 0.0) or 0.0)

            c_day_open = float(live_intraday.get('day_open_price', 0.0))
            c_vwap = float(live_intraday.get('vwap_intraday', 0.0))
            c_is_15m_growing = bool(live_intraday.get('is_15m_high_growing', False))
            c_is_15m_bb_break = bool(live_intraday.get('is_15m_bb_breakout', False))
            c_is_bb_opening = bool(live_intraday.get('is_bb_15m_opening', False))
            c_vol_decay = float(live_intraday.get('vol_decay_ratio_15m', 1.0))

            effective_float = (c_mcap / max(0.01, price)) if c_mcap > 0 else 0

            # 1. CANDADO VELA ROJA INTRADÍA (Precio < Open del Día con Gap >= 5%)
            if c_gap_pct >= 5.0 and c_day_open > 0 and price < c_day_open * 0.998:
                log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por VELA ROJA INTRADÍA (Precio ${price:.2f} < Open ${c_day_open:.2f} con Gap +{c_gap_pct:.1f}%).")
                await _upsert_queue(supabase, candidate, status='blocked')
                continue

            # 2. CANDADO VWAP INTRADÍA (Anti Bear Flag)
            if c_gap_pct >= 5.0 and c_vwap > 0 and price < c_vwap * 0.998:
                log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por BEAR FLAG (Precio ${price:.2f} < VWAP ${c_vwap:.2f} con Gap +{c_gap_pct:.1f}%).")
                await _upsert_queue(supabase, candidate, status='blocked')
                continue

            # 3. CANDADO GAP SIN CATALIZADOR NI MOMENTUM 15M (Anti Gap & Crap)
            if c_gap_pct >= 5.0 and not c_has_catalyst and c_cat_tier > 2:
                has_15m_ladder = (c_is_15m_growing and c_is_15m_bb_break and c_rvol >= 2.5)
                if not has_15m_ladder:
                    log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por GAP & CRAP (Gap +{c_gap_pct:.1f}% sin catalizador Tier 1/2 y sin escalera 15m).")
                    await _upsert_queue(supabase, candidate, status='blocked')
                    continue

            # 4. CANDADO FLOAT MASIVO EN GAP (Caso QS)
            if c_gap_pct >= 5.0 and (effective_float >= 50_000_000 or c_mcap >= 1_000_000_000):
                if c_rvol < 3.5 and c_cat_tier > 1:
                    log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por FLOAT MASIVO EN GAP ({effective_float/1e6:.1f}M sh, RVOL {c_rvol:.1f}x < 3.5x sin Tier 1).")
                    await _upsert_queue(supabase, candidate, status='blocked')
                    continue

            # 5. CANDADO SECADO DE VOLUMEN EN CONSOLIDACIÓN
            if c_gap_pct >= 5.0 and c_vol_decay < 0.35 and not c_is_15m_growing:
                log_info(MODULE, f"⛔ {ticker}: BLOQUEADA por VOLUME DECAY (Vol 15m cayó -{(1-c_vol_decay)*100:.0f}% en consolidación sin nuevo High).")
                await _upsert_queue(supabase, candidate, status='blocked')
                continue

            # 6. CANDADO MACRO BEARISH / RISK-OFF
            if is_macro_bearish:
                is_alpha_runner = (candidate.get('is_early_momentum') or candidate.get('semaphore') == 'EARLY_MOMENTUM' or c_rvol >= 3.0)
                is_healthy_tape = (price >= c_vwap * 0.998 and price >= c_day_open * 0.998)
                is_small_float = (effective_float < 50_000_000 or c_mcap < 250_000_000)
                is_exempt_bearish = is_alpha_runner and is_healthy_tape and is_small_float and (c_has_catalyst or (c_is_15m_growing and c_is_bb_opening))
                if not is_exempt_bearish:
                    log_info(MODULE, f"⏸️ {ticker}: BLOQUEADA por VIENTO EN CONTRA MACRO (Risk-Off. Solo runners descorrelacionados con RVOL >= 3.0x y float pequeño).")
                    await _upsert_queue(supabase, candidate, status='blocked')
                    continue

        except Exception as e_anti_ex:
            log_warning(MODULE, f"Aviso evaluando Blindaje Anti-Agotamiento para {ticker}: {e_anti_ex}")

        rule_sig   = candidate.get('rule_signal', {})
        order_type = 'market'
        rule_code  = 'APEX_AUTO'

        # Prioridad 0: Bull Expansion Ignition, Bear Rollover PUT, Early Momentum Runner, Open Gap Runner o VME Expansion
        if candidate.get('triggered_rule') and (str(candidate.get('triggered_rule')).startswith('STE_') or str(candidate.get('triggered_rule')).startswith('OPT_BEAR_')):
            rule_code = candidate['triggered_rule']
            order_type = 'market'
        elif candidate.get('is_early_momentum') or candidate.get('semaphore') == 'EARLY_MOMENTUM':
            rule_code = 'EMR_EARLY_MOMENTUM'
            order_type = 'market'
        elif candidate.get('triggered_rule') and str(candidate.get('triggered_rule')).startswith('GAP_'):
            rule_code = candidate['triggered_rule']
            order_type = 'market'
        elif candidate.get('triggered_rule') and str(candidate.get('triggered_rule')).startswith('FT_'):
            rule_code = candidate['triggered_rule']
            order_type = 'market'
        elif candidate.get('triggered_rule') and str(candidate.get('triggered_rule')).startswith('VME_'):
            rule_code = candidate['triggered_rule']
            order_type = 'market'
        # Prioridad 1: Gatillo Estructural Sección B (3a, 4a, 4b, 4c, 4d)
        elif candidate.get('is_pullback_b') and candidate.get('pullback_rule_code'):
            rule_code = candidate['pullback_rule_code']
            order_type = 'market'
        # Prioridad 2: Breakout 5m override — Fast Track
        elif candidate.get('is_breakout_5m'):
            rule_code = 'Aa30_STK'
            order_type = 'market'
        elif candidate.get('triggered_rule'):
            rule_code = candidate['triggered_rule']
            order_type = 'market'
        elif rule_sig.get('has_signal'):
            best_rule  = rule_sig.get('best_rule', {})
            order_type = best_rule.get('order_type', 'market')
            rule_code  = rule_sig.get('rule_code', 'APEX_AUTO')

        sizing = calculate_position_size(
            ticker         = ticker,
            price          = price,
            composite_rank = candidate['composite_rank'],
            capital_per_op = cap_per_op,
            cfg            = cfg,
            all_ranks      = all_ranks,
            rule_code      = rule_code,
        )

        if sizing['shares'] <= 0 or price <= 0:
            continue

        log_info(MODULE,
            f'✅ COMPRANDO {ticker}: {sizing["shares"]} shares × '
            f'${price:.2f} = ${sizing["capital"]:.2f} | '
            f'Rank={candidate.get("composite_rank", 0):.1f} | '
            f'APEX={candidate.get("apex_score_4h", 0):.0f}% | '
            f'Regla={rule_code} ({order_type})'
        )

        context = candidate.get('snap', {}) or {}
        context['price'] = price
        context['rule_code'] = rule_code
        context['gap_pct'] = candidate.get('gap_pct', 0.0)
        context['is_sweet_spot'] = candidate.get('is_sweet_spot', False)

        rule_mock = {
            'rule_code':   rule_code,
            'group_name':  candidate.get('group_name', ''),
            'close_all':   False,
            'dca_enabled': False,
            'strategy':    'OPT_BEAR_ROLLOVER' if str(rule_code).startswith('OPT_BEAR_') else ('STE_BULL_EXPANSION' if str(rule_code).startswith('STE_') else ('ADUANA_GAP_RUNNER' if str(rule_code).startswith('GAP_') else ('VME_EXPANSION' if str(rule_code).startswith('VME_') else candidate.get('group_name', '')))),
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
        group_name_val = str(candidate.get('group_name', '') or '')[:50]
        entry_reason_val = str(candidate.get('entry_reason', 'apex_auto') or 'apex_auto')[:50]
        triggered_rule_val = str(candidate.get('rule_signal', {}).get('rule_code') or '')[:50]
        supabase \
            .table('stocks_priority_queue') \
            .upsert({
                'ticker':          candidate['ticker'],
                'group_name':      group_name_val,
                'price_at_rank':   candidate.get('price'),
                'apex_score_4h':   candidate.get('apex_4h'),
                'apex_score_1d':   candidate.get('apex_1d'),
                'return_expected': candidate.get('return_expected', 0),
                'confidence':      candidate['confidence'],
                'composite_rank':  candidate['composite_rank'],
                'status':          status,
                'entry_reason':    entry_reason_val,
                'triggered_rule':  triggered_rule_val,
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
# MÓDULO 8.5 — CONSUMIDOR DE COLA DE PRIORIDAD
# ════════════════════════════════════════════

async def process_priority_queue_buys(supabase=None, cfg=None) -> list:
    """
    Consume los candidatos pendientes en 'stocks_priority_queue',
    ordenados por composite_rank DESC, y ejecuta compras respetando capital y slots.
    Se invoca al final de cada ciclo de 5m en stocks_scheduler y en cada ciclo APEX de 15m.
    """
    if supabase is None:
        supabase = get_supabase()
    if cfg is None:
        cfg = await load_orchestrator_config(supabase)
    if not cfg:
        return []

    # 1. Filtro horario y cutoff 15:15 ET
    from app.core.market_hours import is_market_open, get_nyc_now
    is_open, status = is_market_open()
    allow_ah = cfg.get('allow_after_hours', False)
    if not is_open and not allow_ah:
        log_info(MODULE, f'⏸️ Priority Queue: Mercado cerrado ({status}) y After-hours desactivado.')
        return []

    nyc_now = get_nyc_now()
    if nyc_now.weekday() < 5 and (nyc_now.hour > 15 or (nyc_now.hour == 15 and nyc_now.minute >= 15)) and not allow_ah:
        log_info(MODULE, f"⏸️ Priority Queue: Cutoff EOD 15:15 ET alcanzado ({nyc_now.strftime('%H:%M:%S')} ET). Aperturas bloqueadas.")
        return []

    # 2. Capital disponible y slots
    capital = await calculate_available_capital(cfg, supabase)
    if not capital['can_buy']:
        log_info(MODULE, f"⏸️ Priority Queue: Sin slots o capital disponible: {capital['reason']}")
        return []

    # 2.1 DISYUNTOR DIARIO GENERAL (Propuesta #3)
    try:
        from app.core.circuit_breaker import get_circuit_breaker_state
        cb_state = get_circuit_breaker_state()
        if cb_state.get("tripped"):
            log_info(MODULE, f"⛔ Priority Queue: Disyuntor diario activo ({cb_state.get('trip_reason')}). Compras detenidas.")
            return []
    except Exception as e_cb_q:
        log_warning(MODULE, f"Aviso leyendo disyuntor en priority queue: {e_cb_q}")

    # 3. Macro Sentiment Engine & RS Shield (Propuesta #1)
    try:
        from app.core.macro_sentiment_engine import evaluate_macro_sentiment
        macro_eval = evaluate_macro_sentiment()
        if not macro_eval.get("allow_stock_buys", True):
            log_info(MODULE, f"⏸️ Priority Queue: Nuevas compras bloqueadas por Macro Sentiment: {macro_eval.get('label')}")
            return []
        is_macro_bearish = (macro_eval.get("regime") == "RISK_OFF")
    except Exception as e_macro_q:
        from app.stocks.stocks_adaptive_tp import fetch_macro_data
        macro = await fetch_macro_data(supabase)
        is_macro_bearish = (macro.get('sentiment') == 'bearish')

    # 4. Posiciones abiertas y blacklist/cooldown
    pos_res = supabase.table('stocks_positions').select('ticker').eq('status', 'open').execute()
    owned_tickers = {p['ticker'] for p in (pos_res.data or [])}

    blacklisted_tickers = set()
    cooling_down_tickers = set()
    try:
        now_utc = datetime.now(timezone.utc)
        start_of_day_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        journal_res = supabase.table('trades_journal') \
            .select('ticker, exit_date, pnl_pct, exit_reason') \
            .gte('exit_date', start_of_day_utc) \
            .execute()
        for jr in (journal_res.data or []):
            t = jr.get('ticker')
            if not t:
                continue
            pnl_p = float(jr.get('pnl_pct') or 0.0)
            reason = str(jr.get('exit_reason') or '').lower()
            if pnl_p <= -2.5 or 'hard_cap' in reason or 'sl_' in reason:
                blacklisted_tickers.add(t)
            exit_d_str = jr.get('exit_date')
            if exit_d_str:
                try:
                    exit_dt = datetime.fromisoformat(str(exit_d_str).replace('Z', '+00:00'))
                    if (now_utc - exit_dt).total_seconds() / 60.0 < 60.0:
                        cooling_down_tickers.add(t)
                except Exception:
                    pass
    except Exception as cd_err:
        log_warning(MODULE, f"Error verificando cooldown intradía: {cd_err}")

    # 5. Obtener candidatos pendientes de stocks_priority_queue
    q_res = supabase.table('stocks_priority_queue') \
        .select('*') \
        .eq('status', 'pending') \
        .order('composite_rank', desc=True) \
        .limit(25) \
        .execute()

    pending_items = q_res.data or []
    if not pending_items:
        return []

    candidates = []
    for item in pending_items:
        t = item['ticker']
        if t in owned_tickers:
            try:
                supabase.table('stocks_priority_queue').update({'status': 'owned'}).eq('ticker', t).execute()
            except Exception:
                pass
            continue
        if t in blacklisted_tickers:
            log_info(MODULE, f"⛔ Priority Queue: {t} bloqueada por lista negra intradía")
            continue
        if t in cooling_down_tickers:
            log_info(MODULE, f"⏳ Priority Queue: {t} en cooldown <60 min")
            continue

        price = float(item.get('price_at_rank') or item.get('price') or 0.0)
        if price <= 0:
            try:
                import yfinance as yf
                fast = yf.Ticker(t).fast_info
                price = float(fast.get('last_price') or fast.get('regular_market_previous_close') or 0.0)
            except Exception:
                price = 0.0

        if price <= 0:
            continue

        c_dict = {
            'ticker': t,
            'price': price,
            'composite_rank': float(item.get('composite_rank') or 0.0),
            'apex_score_4h': float(item.get('apex_score_4h') or 90.0),
            'apex_score_1d': float(item.get('apex_score_1d') or 90.0),
            'apex_4h': float(item.get('apex_score_4h') or 90.0),
            'return_expected': float(item.get('return_expected') or 20.0),
            'confidence': item.get('confidence', 'high'),
            'is_overbought': bool(item.get('is_overbought', False)),
            'group_name': item.get('group_name', 'HOT'),
            'entry_reason': item.get('entry_reason', ''),
            'triggered_rule': item.get('triggered_rule', ''),
            'rsi': float(item.get('rsi_at_entry') or 50.0),
            'fib_zone': int(item.get('fib_zone') or 0),
            'is_gap_runner': 'GAP' in str(item.get('group_name', '')) or 'GAP' in str(item.get('triggered_rule', '')),
            'is_vme_runner': 'VME' in str(item.get('triggered_rule', '')) or 'VOLATILITY' in str(item.get('group_name', '')),
            'is_intraday_alpha': 'ALPHA' in str(item.get('group_name', '')) or 'ALPHA' in str(item.get('triggered_rule', '')),
            'rule_signal': {'has_signal': True, 'rule_code': item.get('triggered_rule')},
            'snap': {'price': price, 'close': price, 'rvol': 2.0}
        }
        candidates.append(c_dict)

    if not candidates:
        return []

    log_info(MODULE, f"🎯 Priority Queue Consumer: Ejecutando compras para {len(candidates)} candidatos pendientes...")
    executed = await execute_priority_buys(candidates, capital, cfg, supabase, is_macro_bearish=is_macro_bearish)
    return executed


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
    from app.core.market_hours import is_market_open, get_nyc_now
    is_open, status = is_market_open()
    allow_ah = cfg.get('allow_after_hours', False)
    
    if not is_open and not allow_ah:
        log_info(MODULE, f'⏸️ Ciclo omitido: Mercado cerrado ({status}) y After-hours desactivado.')
        return

    # ── REGLA 1.5: TOPE EOD PARA NUEVAS COMPRAS (Cutoff 15:15 ET) ──
    nyc_now = get_nyc_now()
    if nyc_now.weekday() < 5 and (nyc_now.hour > 15 or (nyc_now.hour == 15 and nyc_now.minute >= 15)) and not allow_ah:
        log_info(MODULE, f"⏸️ Ciclo de compras omitido: Cutoff EOD 15:15 ET alcanzado ({nyc_now.strftime('%H:%M:%S')} ET). Cero aperturas nuevas en últimos 45 min para evitar cierres EOD en $0.00.")
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

    # ── REGLA 2: Bloqueo de Compras en Mercado Bearish (Con Exención para Alpha Runners) ──
    is_macro_bearish = (macro.get('sentiment') == 'bearish')
    if is_macro_bearish:
        log_warning(MODULE, f"⚠️ MERCADO BEARISH ({macro.get('score')}): Compras de acciones ordinarias suspendidas por seguridad. Se evaluarán y ejecutarán EXCLUSIVAMENTE Alpha Runners y Super-Runners con volumen institucional.")

    # 3.5. Primero consumir candidatos pendientes existentes en la cola de prioridad
    try:
        pending_exec = await process_priority_queue_buys(supabase, cfg)
        if pending_exec:
            log_info(MODULE, f"🎯 Prioridad ejecutada previamente desde cola: {len(pending_exec)} compras.")
            # Recalcular capital disponible tras compras pendientes
            capital = await calculate_available_capital(cfg, supabase)
            if not capital['can_buy']:
                log_info(MODULE, '⏸️ Slots o capital agotados tras ejecutar candidatos pendientes de cola.')
                return {
                    'queue_size': len(pending_exec),
                    'executed': len(pending_exec),
                    'capital': capital,
                    'top_ticker': pending_exec[0]['ticker'] if pending_exec else None,
                }
    except Exception as pq_e:
        log_warning(MODULE, f"Aviso consumiendo cola pendiente: {pq_e}")

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
    executed = await execute_priority_buys(queue, capital, cfg, supabase, is_macro_bearish=is_macro_bearish)

    return {
        'queue_size': len(queue),
        'executed':   len(executed),
        'capital':    capital,
        'top_ticker': queue[0]['ticker'] if queue else None,
    }

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_orchestrator_cycle())
