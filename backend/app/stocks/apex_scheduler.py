"""
APEX Score — Scheduler Integration
Ciclo de cálculo y backtesting del APEX Score.
Se importa desde stocks_scheduler.py.
"""

import asyncio
from datetime import datetime, timezone, timedelta

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.stocks.apex_score import calculate_apex_score


MODULE = "APEX_SCHEDULER"


async def _get_snap(ticker: str, supabase) -> dict:
    """Obtiene el market_snapshot para un ticker."""
    try:
        res = supabase.table('market_snapshot') \
            .select('*') \
            .eq('symbol', ticker) \
            .limit(1) \
            .execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


async def _get_fundamental(ticker: str, supabase) -> dict:
    """Obtiene datos fundamentales del watchlist_daily."""
    try:
        today = datetime.now().date().isoformat()
        res = supabase.table('watchlist_daily') \
            .select('*') \
            .eq('ticker', ticker) \
            .eq('date', today) \
            .limit(1) \
            .execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


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


async def run_apex_cycle(supabase=None):
    """
    Calcula el APEX Score para todos los tickers
    del watchlist cada 15 minutos.
    """
    if supabase is None:
        supabase = get_supabase()

    log_info(MODULE, "═══ APEX CYCLE START ═══")
    cycle_start = datetime.now(timezone.utc)

    try:
        # Obtener macro data una sola vez
        from app.stocks.stocks_adaptive_tp import fetch_macro_data
        macro = await fetch_macro_data(supabase)

        # Obtener watchlist activa
        today = datetime.now().date().isoformat()
        tickers_res = supabase \
            .table('watchlist_daily') \
            .select('ticker') \
            .eq('date', today) \
            .eq('hard_filter_pass', True) \
            .limit(500) \
            .execute()

        tickers = list(set(
            r['ticker'] for r in (tickers_res.data or [])
        ))

        # También incluir posiciones abiertas
        pos_res = supabase.table('stocks_positions') \
            .select('ticker') \
            .eq('status', 'open') \
            .execute()
        for p in (pos_res.data or []):
            if p['ticker'] not in tickers:
                tickers.append(p['ticker'])

        if not tickers:
            log_info(MODULE, "No tickers to process")
            return

        log_info(MODULE, f"Processing APEX for {len(tickers)} tickers")

        success_count = 0
        error_count = 0

        for ticker in tickers:
            try:
                snap = await _get_snap(ticker, supabase)
                if not snap or not snap.get('price'):
                    continue

                fund = await _get_fundamental(ticker, supabase)

                # Build fundamental cache from available data
                fund_cache = {
                    'piotroski_score': fund.get('piotroski_score', 4),
                    'margin_of_safety': fund.get('margin_of_safety', 0),
                    'altman_zone': fund.get('altman_zone', 'grey'),
                    'fundamental_score': fund.get('fundamental_score', 50),
                    'analyst_rating': fund.get('analyst_rating', 5),
                    'short_interest_pct': fund.get('short_interest_pct', 5),
                    'days_to_earnings': fund.get('days_to_earnings', 30),
                    'valuation_status': fund.get('valuation_status', 'fairly_valued'),
                }

                # Get DataFrames (use try/except per tf)
                df_5m = await _get_df(ticker, '5m')
                df_15m = await _get_df(ticker, '15m')
                df_4h = await _get_df(ticker, '4h')
                df_daily = await _get_df(ticker, '1d')

                result = calculate_apex_score(
                    ticker=ticker,
                    snap=snap,
                    fundamental_cache=fund_cache,
                    macro=macro,
                    df_5m=df_5m,
                    df_15m=df_15m,
                    df_4h=df_4h,
                    df_daily=df_daily,
                )

                # Guardar en apex_scores
                supabase.table('apex_scores').insert({
                    'ticker':          ticker,
                    'price_at_calc':   result['price'],
                    'b1_momentum':     result['blocks']['b1_momentum'],
                    'b2_technical':    result['blocks']['b2_technical'],
                    'b3_fundamental':  result['blocks']['b3_fundamental'],
                    'b4_regime':       result['blocks']['b4_regime'],
                    'b5_sentiment':    result['blocks']['b5_sentiment'],
                    'apex_score_4h':   result['apex_score_4h'],
                    'apex_score_1d':   result['apex_score_1d'],
                    'return_expected_4h': result['return_expected_4h'],
                    'return_expected_1d': result['return_expected_1d'],
                    'confidence':      result['confidence'],
                    'regime_type':     result['regime_type'],
                    'edge_pct':        result['edge_4h'],
                    'scenario_bull':   result['scenarios']['bull'],
                    'scenario_base':   result['scenarios']['base'],
                    'scenario_bear':   result['scenarios']['bear'],
                    'detail':          result['detail'],
                    'valid_until_4h':  result['valid_until_4h'],
                    'valid_until_1d':  result['valid_until_1d'],
                }).execute()

                # Actualizar market_snapshot con APEX
                try:
                    supabase.table('market_snapshot').update({
                        'apex_4h':     result['apex_score_4h'],
                        'apex_1d':     result['apex_score_1d'],
                        'apex_signal': result['signal'],
                        'apex_conf':   result['confidence'],
                    }).eq('symbol', ticker).execute()
                except Exception:
                    pass  # Columnas pueden no existir aún

                success_count += 1

            except Exception as e:
                error_count += 1
                log_warning(MODULE, f'{ticker}: {e}')

        duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        log_info(MODULE,
            f"═══ APEX CYCLE END ═══ "
            f"OK={success_count} ERR={error_count} "
            f"Duration={duration:.1f}s"
        )

        # 🚀 DISPARAR EL ORCHESTRATOR PARA ACTUALIZAR LA COLA DE PRIORIDAD
        try:
            from app.stocks.stocks_orchestrator import run_orchestrator_cycle
            log_info(MODULE, "Triggering Priority Queue Orchestrator...")
            await run_orchestrator_cycle(supabase)
        except Exception as orch_e:
            log_error(MODULE, f"Failed to run orchestrator after cycle: {orch_e}")

    except Exception as e:
        log_error(MODULE, f"APEX cycle failed: {e}")


async def run_apex_backtesting(supabase=None):
    """
    Cada 4H: verifica si las predicciones
    anteriores fueron correctas.
    Esto permite medir la precisión del modelo.
    """
    if supabase is None:
        supabase = get_supabase()

    log_info(MODULE, "═══ APEX BACKTESTING START ═══")

    try:
        now = datetime.now(timezone.utc)
        cutoff_start = (now - timedelta(hours=4, minutes=30)).isoformat()
        cutoff_end = (now - timedelta(hours=3, minutes=30)).isoformat()

        old_res = supabase \
            .table('apex_scores') \
            .select('id, ticker, price_at_calc, apex_score_4h') \
            .gte('calculated_at', cutoff_start) \
            .lte('calculated_at', cutoff_end) \
            .is_('prediction_correct', 'null') \
            .limit(200) \
            .execute()

        verified = 0
        for pred in (old_res.data or []):
            ticker = pred['ticker']
            price_then = float(pred['price_at_calc'] or 0)
            apex_4h = float(pred['apex_score_4h'] or 50)

            if price_then <= 0:
                continue

            # Obtener precio actual del snapshot
            snap_res = supabase \
                .table('market_snapshot') \
                .select('price') \
                .eq('symbol', ticker) \
                .limit(1) \
                .execute()

            if not snap_res.data:
                continue

            price_now = float(snap_res.data[0].get('price', 0))
            if price_now <= 0:
                continue

            actual_return = (price_now - price_then) / price_then * 100

            predicted_up = apex_4h >= 50
            actually_up  = actual_return > 0
            correct      = predicted_up == actually_up

            supabase.table('apex_scores').update({
                'actual_return_4h':   round(actual_return, 4),
                'prediction_correct': correct,
            }).eq('id', pred['id']).execute()

            verified += 1

        log_info(MODULE,
            f"═══ APEX BACKTESTING END ═══ "
            f"Verified {verified} predictions"
        )

    except Exception as e:
        log_error(MODULE, f"APEX backtesting failed: {e}")
