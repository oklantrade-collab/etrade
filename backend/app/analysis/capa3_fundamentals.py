from datetime import datetime
import asyncio
from app.core.logger import log_info, log_error, log_warning
from app.stocks.valuation_engine import calculate_composite_pro_score
from app.stocks.fundamental_analyzer import FundamentalAnalyzer

async def analyze_fundamentals(
    ticker:         str,
    current_price:  float,
    ib_data:        dict,
    sector:         str,
    analyst_rating: float = None,
    technical_score: float = None,
    supabase        = None
) -> dict:
    """
    Orquestador de Capa 3: Valoración Matemática + Enriquecimiento IA (opcional).
    """

    # 1. ¿Data insuficiente de IB? Enriquecer vía FundamentalAnalyzer (YFinance Deep)
    # Definimos insuficiente si no hay MCAP o ROA (indicadores de datos vacíos)
    is_sparse = not ib_data or ib_data.get('marketCap', 0) == 0 or ib_data.get('returnOnAssets', 0) == 0
    
    financials = {}
    if is_sparse:
        log_info('VALUATION', f"{ticker}: Datos de IB insuficientes, enriqueciendo...")
        analyzer = FundamentalAnalyzer()
        enriched_data = await analyzer.analyze_ticker(ticker)
        if enriched_data:
            financials = enriched_data
            # Actualizar rating y sector si el enriquecimiento los obtuvo
            analyst_rating = enriched_data.get('analyst_rating', analyst_rating)
            sector = enriched_data.get('sector', sector)
    
    # Si no es sparse o el enriquecimiento falló, usar lo que tenemos de IB
    if not financials:
        financials = {
            'roa':              ib_data.get('returnOnAssets', 0),
            'roa_prev':         ib_data.get('returnOnAssets_prev', 0),
            'ocf':              ib_data.get('operatingCashFlow', 0),
            'net_income':       ib_data.get('netIncome', 0),
            'total_assets':     ib_data.get('totalAssets', 1),
            'current_assets':   ib_data.get('totalCurrentAssets', 0),
            'current_liabilities': ib_data.get('totalCurrentLiabilities', 0),
            'long_term_debt':   ib_data.get('longTermDebt', 0),
            'long_term_debt_prev': ib_data.get('longTermDebt_prev', 0),
            'total_liabilities': ib_data.get('totalLiabilities', 1),
            'retained_earnings': ib_data.get('retainedEarnings', 0),
            'market_cap':        ib_data.get('marketCap', 0),
            'eps':              ib_data.get('eps', 0),
            'fcf_per_share':    ib_data.get('freeCashFlowPerShare', 0),
            'book_value_per_share': ib_data.get('bookValue', 0),
            'current_ratio':    ib_data.get('currentRatio', 0),
            'current_ratio_prev': ib_data.get('currentRatio_prev', 0),
            'gross_margin':     ib_data.get('grossMargin', 0),
            'gross_margin_prev': ib_data.get('grossMargin_prev', 0),
            'asset_turnover':   ib_data.get('assetTurnover', 0),
            'asset_turnover_prev': ib_data.get('assetTurnover_prev', 0),
            'revenue_growth_yoy': ib_data.get('revenueGrowth', 0.05),
            'ebit':             ib_data.get('ebit', 0),
            'revenue':          ib_data.get('revenue', 0),
            'shares_outstanding': ib_data.get('sharesOutstanding', 1),
            'shares_outstanding_prev': ib_data.get('sharesOutstanding_prev', 1),
        }

    # 2. Calcular score matemático inicial
    math_result = calculate_composite_pro_score(
        ticker         = ticker,
        current_price  = current_price,
        financials     = financials,
        sector         = sector,
        analyst_rating = analyst_rating,
        technical_score= technical_score,
        ia_score       = None,
    )

    # 3. ¿Llamar a la IA? Solo si el score técnico o matemático lo amerita
    # O si es explícitamente requerido (miembro PRO)
    should_call_ia = math_result['pro_score'] >= 7.0 or (technical_score or 0) >= 75
    
    ia_res = None
    if should_call_ia:
        try:
            from app.stocks.decision_engine import DecisionEngine
            engine = DecisionEngine()
            
            # Verificamos cooldown de quota antes de llamar
            import time
            if engine.openai_quota_hit_until and time.time() < engine.openai_quota_hit_until:
                log_info('VALUATION', f"{ticker}: Saltando IA por cooldown de quota.")
            else:
                # Simulamos watchlist y tech data para el motor
                wl_entry = {"ticker": ticker, "fundamental_score": math_result['pro_score'] * 10}
                tech_data = {"close": current_price, "technical_score": technical_score}
                ia_res = await engine.execute_full_analysis(ticker, wl_entry, tech_data)
        except Exception as e:
            log_warning('VALUATION', f"{ticker}: Error en enriquecimiento IA: {e}")

    # 4. Resultado Final (Unificado)
    if ia_res and ia_res.get('pro_score'):
        # Recalcular score compuesto con el peso de la IA
        final_result = calculate_composite_pro_score(
            ticker         = ticker,
            current_price  = current_price,
            financials     = financials,
            sector         = sector,
            analyst_rating = analyst_rating,
            technical_score= technical_score,
            ia_score       = float(ia_res['pro_score']),
        )
        # Inyectar resúmenes de la IA para persistencia
        final_result['qwen_summary'] = ia_res.get('qwen_summary')
        final_result['gemini_summary'] = ia_res.get('gemini_summary')
        final_result['ia_score'] = float(ia_res['pro_score'])
    else:
        final_result = math_result
        final_result['ia_score'] = None
    
    # Inyectar la explicación para el UI (Capa 4)
    final_result['ai_rationale'] = final_result.get('explanation', "Cálculo matemático puro.")

    # 5. Guardar en Supabase (Capa 3 Persistencia)
    if supabase:
        try:
            _save_to_cache(supabase, ticker, current_price, final_result)
        except Exception as e:
            log_error('VALUATION', f"Error en persistencia Capa 3: {e}")

    return final_result

def _save_to_cache(sb, ticker, price, res):
    """Persiste los resultados detallados en fundamental_cache."""
    data = {
        'ticker':            ticker,
        'current_price':     price,
        'fundamental_score': res['pro_score'] * 10,
        'intrinsic_value':   res['intrinsic_value'],
        'valuation_status':  res['valuation_status'],
        'margin_of_safety':  res['margin_of_safety'],
        'piotroski_score':   res['components']['piotroski']['score'],
        'piotroski_detail':  res['piotroski_detail'],
        'graham_number':     res['components']['graham']['value'],
        'graham_margin':     res['components']['graham']['margin'],
        'dcf_intrinsic':     res['components']['dcf']['value'],
        'dcf_upside_pct':    res['components']['dcf']['upside'],
        'altman_z_score':    res['components']['altman']['z_score'],
        'altman_zone':       res['components']['altman']['zone'],
        'math_score':        res['math_score'],
        'ia_score':          res.get('ia_score'),
        'data_source':       res['data_source'],
        'composite_intrinsic': res['intrinsic_value'],
        'math_rationale':    res.get('explanation'),
        'qwen_summary':      res.get('qwen_summary'),
        'gemini_summary':    res.get('gemini_summary'),
        'refreshed_at':      'now()',
    }
    sb.table('fundamental_cache').upsert(data, on_conflict='ticker').execute()
