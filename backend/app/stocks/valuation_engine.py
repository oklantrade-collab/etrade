
"""
Motor de Valoración Matemático — eTrader v4.5

Calcula el Pro Score (1-10) y el Valor
Intrínseco usando modelos financieros clásicos
sin depender de quota de IA.

Modelos implementados:
  1. Piotroski F-Score (salud financiera)
  2. Graham Number (valor intrínseco clásico)
  3. DCF Simplificado (flujo de caja)
  4. Altman Z-Score (riesgo de quiebra)
  5. Composite Pro Score (síntesis)

Fuente de datos: Interactive Brokers (IB TWS)
"""

import math
from typing import Optional
from app.core.logger import log_info # Adjusted from memory_store to logger to match existing project structure

# ── Múltiplos PE por sector ───────────────────
SECTOR_PE_MULTIPLES = {
    'Technology':           28.0,
    'Healthcare':           22.0,
    'Financial Services':   14.0,
    'Consumer Cyclical':    20.0,
    'Consumer Defensive':   18.0,
    'Energy':               15.0,
    'Industrials':          18.0,
    'Real Estate':          35.0,
    'Utilities':            20.0,
    'Materials':            16.0,
    'Communication Services': 22.0,
    'Default':              18.0,
}

# ── WACC estimado por sector ──────────────────
SECTOR_WACC = {
    'Technology':           0.10,
    'Healthcare':           0.09,
    'Financial Services':   0.09,
    'Consumer Cyclical':    0.09,
    'Consumer Defensive':   0.08,
    'Energy':               0.10,
    'Industrials':          0.09,
    'Real Estate':          0.08,
    'Utilities':            0.07,
    'Default':              0.09,
}


# ════════════════════════════════════════════
# MODELO 1 — PIOTROSKI F-SCORE
# ════════════════════════════════════════════

def calculate_piotroski_fscore(
    financials: dict
) -> dict:
    """
    Calcula el Piotroski F-Score (0-9).

    financials debe contener:
      roa:              Return on Assets actual
      roa_prev:         ROA año anterior
      ocf:              Operating Cash Flow
      net_income:       Net Income
      total_assets:     Total Assets
      long_term_debt:   Deuda largo plazo
      long_term_debt_prev: Deuda año anterior
      current_ratio:    Current Assets/Liabilities
      current_ratio_prev: Current ratio año ant
      shares_outstanding:    Acciones actuales
      shares_outstanding_prev: Acciones año ant
      gross_margin:     Margen bruto actual
      gross_margin_prev: Margen bruto año ant
      asset_turnover:   Revenue/Total Assets
      asset_turnover_prev: Asset turnover año ant
    """
    score  = 0
    detail = {}

    # ── RENTABILIDAD ─────────────────────────
    roa = float(financials.get('roa', 0))
    f1  = roa > 0
    if f1: score += 1
    detail['F1_ROA_positive'] = {
        'passed': f1,
        'value':  round(roa * 100, 2),
        'description': 'ROA > 0 (empresa rentable)'
    }

    ocf = float(financials.get('ocf', 0))
    f2  = ocf > 0
    if f2: score += 1
    detail['F2_OCF_positive'] = {
        'passed': f2,
        'value':  ocf,
        'description': 'Flujo de caja operativo > 0'
    }

    roa_prev = float(financials.get('roa_prev', 0))
    f3 = roa > roa_prev
    if f3: score += 1
    detail['F3_ROA_improving'] = {
        'passed': f3,
        'value':  round((roa - roa_prev) * 100, 2),
        'description': 'ROA mejora vs año anterior'
    }

    net_income   = float(
        financials.get('net_income', 0)
    )
    total_assets = float(
        financials.get('total_assets', 1)
    )
    ocf_roa = ocf / total_assets \
              if total_assets > 0 else 0
    f4 = ocf_roa > roa
    if f4: score += 1
    detail['F4_OCF_vs_ROA'] = {
        'passed': f4,
        'value':  round(ocf_roa * 100, 2),
        'description':
            'OCF/Assets > ROA (ganancias reales)'
    }

    # ── APALANCAMIENTO ────────────────────────
    debt      = float(
        financials.get('long_term_debt', 0)
    )
    debt_prev = float(
        financials.get('long_term_debt_prev', 0)
    )
    assets_prev = total_assets  # simplificado
    f5 = (debt / total_assets) < \
         (debt_prev / assets_prev) \
         if total_assets > 0 and assets_prev > 0 \
         else False
    if f5: score += 1
    detail['F5_Leverage_decreasing'] = {
        'passed': f5,
        'value':  round(debt / total_assets * 100,
                        2) if total_assets else 0,
        'description': 'Ratio de deuda disminuye'
    }

    cr      = float(
        financials.get('current_ratio', 0)
    )
    cr_prev = float(
        financials.get('current_ratio_prev', 0)
    )
    f6 = cr > cr_prev
    if f6: score += 1
    detail['F6_Liquidity_improving'] = {
        'passed': f6,
        'value':  round(cr, 2),
        'description':
            'Current ratio mejora (más liquidez)'
    }

    shares      = float(
        financials.get('shares_outstanding', 1)
    )
    shares_prev = float(
        financials.get(
            'shares_outstanding_prev', 1
        )
    )
    f7 = shares <= shares_prev * 1.01
    # Tolerancia 1% para splits mínimos
    if f7: score += 1
    detail['F7_No_dilution'] = {
        'passed': f7,
        'value':  round(
            (shares - shares_prev)
            / shares_prev * 100, 2
        ) if shares_prev > 0 else 0,
        'description':
            'Sin dilución de acciones'
    }

    # ── EFICIENCIA ────────────────────────────
    gm      = float(
        financials.get('gross_margin', 0)
    )
    gm_prev = float(
        financials.get('gross_margin_prev', 0)
    )
    f8 = gm > gm_prev
    if f8: score += 1
    detail['F8_Margin_improving'] = {
        'passed': f8,
        'value':  round(gm * 100, 2),
        'description': 'Margen bruto mejora'
    }

    at      = float(
        financials.get('asset_turnover', 0)
    )
    at_prev = float(
        financials.get('asset_turnover_prev', 0)
    )
    f9 = at > at_prev
    if f9: score += 1
    detail['F9_Efficiency_improving'] = {
        'passed': f9,
        'value':  round(at, 4),
        'description': 'Asset turnover mejora'
    }

    # ── Clasificación ─────────────────────────
    if score >= 8:
        interpretation = 'Excelente'
        color          = 'green'
    elif score >= 6:
        interpretation = 'Sólida'
        color          = 'blue'
    elif score >= 4:
        interpretation = 'Aceptable'
        color          = 'yellow'
    else:
        interpretation = 'Problemática'
        color          = 'red'

    return {
        'score':          score,
        'max_score':      9,
        'normalized':     round(score / 9 * 10, 2),
        'interpretation': interpretation,
        'color':          color,
        'detail':         detail,
    }


# ════════════════════════════════════════════
# MODELO 2 — GRAHAM NUMBER
# ════════════════════════════════════════════

def calculate_graham_number(
    eps:             float,
    book_value:      float,
    current_price:   float,
    sector:          str = 'Default'
) -> dict:
    """
    Calcula el Graham Number y el margen
    de seguridad respecto al precio actual.

    Graham Number = √(22.5 × EPS × Book Value)
    """
    if eps <= 0 or book_value <= 0:
        return {
            'graham_number':   None,
            'margin_of_safety': None,
            'is_undervalued':  False,
            'applicable':      False,
            'reason': (
                'No aplica: EPS o Book Value '
                'negativos (empresa sin ganancias)'
            )
        }

    graham = math.sqrt(
        22.5 * eps * book_value
    )

    if current_price > 0:
        margin = (graham - current_price) \
                 / graham * 100
        is_undervalued = current_price < graham
    else:
        margin         = 0
        is_undervalued = False

    # Precio objetivo conservador (10% margen)
    target_conservative = graham * 0.90

    return {
        'graham_number':       round(graham, 4),
        'current_price':       current_price,
        'margin_of_safety':    round(margin, 2),
        'is_undervalued':      is_undervalued,
        'target_conservative': round(
            target_conservative, 4
        ),
        'upside_pct':          round(
            (graham - current_price)
            / current_price * 100, 2
        ) if current_price > 0 else 0,
        'applicable':          True,
    }


# ════════════════════════════════════════════
# MODELO 3 — DCF SIMPLIFICADO
# ════════════════════════════════════════════

def calculate_dcf(
    fcf_per_share:    float,
    growth_rate:      float,
    sector:           str   = 'Default',
    projection_years: int   = 5,
    terminal_multiple: float = None
) -> dict:
    """
    DCF simplificado basado en FCF por acción.

    Proyecta el FCF N años con la tasa de
    crecimiento histórica y lo descuenta
    al presente usando el WACC del sector.
    """
    if fcf_per_share <= 0:
        return {
            'intrinsic_value': None,
            'applicable':      False,
            'reason': 'FCF negativo — no aplicable'
        }

    wacc = SECTOR_WACC.get(
        sector,
        SECTOR_WACC['Default']
    )
    pe   = terminal_multiple or SECTOR_PE_MULTIPLES.get(
        sector, SECTOR_PE_MULTIPLES['Default']
    )

    # Proyectar FCF
    pv_total  = 0.0
    fcf_proj  = fcf_per_share
    projections = []

    for year in range(1, projection_years + 1):
        fcf_proj = fcf_proj * (1 + growth_rate)
        pv       = fcf_proj / (1 + wacc) ** year
        pv_total += pv
        projections.append({
            'year':  year,
            'fcf':   round(fcf_proj, 4),
            'pv':    round(pv, 4),
        })

    # Valor terminal (perpetuidad)
    terminal_fcf  = fcf_proj * pe
    terminal_pv   = terminal_fcf / (
        1 + wacc
    ) ** projection_years
    intrinsic_val = pv_total + terminal_pv

    return {
        'intrinsic_value':   round(intrinsic_val, 4),
        'terminal_value':    round(terminal_pv, 4),
        'pv_cashflows':      round(pv_total, 4),
        'wacc_used':         round(wacc * 100, 2),
        'growth_rate_used':  round(
            growth_rate * 100, 2
        ),
        'projection_years':  projection_years,
        'projections':       projections,
        'applicable':        True,
    }


# ════════════════════════════════════════════
# MODELO 4 — ALTMAN Z-SCORE
# ════════════════════════════════════════════

def calculate_altman_zscore(
    financials: dict
) -> dict:
    """
    Altman Z-Score para evaluar riesgo
    de dificultad financiera.

    Z > 2.99: Zona segura
    Z 1.81-2.99: Zona gris
    Z < 1.81: Zona de peligro
    """
    ta  = float(financials.get(
        'total_assets', 1
    ))
    if ta <= 0:
        ta = 1

    ca  = float(financials.get(
        'current_assets', 0
    ))
    cl  = float(financials.get(
        'current_liabilities', 0
    ))
    re  = float(financials.get(
        'retained_earnings', 0
    ))
    ebit = float(financials.get('ebit', 0))
    mcap = float(financials.get('market_cap', 0))
    tl  = float(financials.get(
        'total_liabilities', 1
    ))
    rev = float(financials.get('revenue', 0))

    # Componentes del Z-Score
    A = (ca - cl) / ta        # Working Capital / TA
    B = re / ta               # Retained Earnings / TA
    C = ebit / ta             # EBIT / TA
    D = mcap / tl \
        if tl > 0 else 0      # Market Cap / TL
    E = rev / ta              # Revenue / TA

    z = (1.2 * A) + (1.4 * B) + \
        (3.3 * C) + (0.6 * D) + (1.0 * E)

    if z > 2.99:
        zone        = 'safe'
        description = 'Zona Segura — bajo riesgo'
        risk_score  = 1  # 1-3 bajo riesgo
    elif z >= 1.81:
        zone        = 'grey'
        description = 'Zona Gris — riesgo moderado'
        risk_score  = 5  # 4-6 riesgo moderado
    else:
        zone        = 'danger'
        description = 'Zona Peligro — alto riesgo'
        risk_score  = 9  # 7-10 alto riesgo

    return {
        'z_score':     round(z, 4),
        'zone':        zone,
        'description': description,
        'risk_score':  risk_score,
        'components': {
            'A_working_capital': round(A, 4),
            'B_retained_earn':   round(B, 4),
            'C_ebit_ratio':      round(C, 4),
            'D_market_vs_debt':  round(D, 4),
            'E_asset_turnover':  round(E, 4),
        }
    }


# ════════════════════════════════════════════
# COMPOSITE PRO SCORE — Síntesis final
# ════════════════════════════════════════════

def calculate_composite_pro_score(
    ticker:          str,
    current_price:   float,
    financials:      dict,
    sector:          str   = 'Default',
    analyst_rating:  float = None,
    technical_score: float = None,
    ia_score:        float = None,
) -> dict:
    """
    Calcula el Pro Score final combinando
    todos los modelos matemáticos.

    Pesos sin IA:
      Piotroski:       35%
      Graham Margin:   25%
      DCF Upside:      20%
      Analyst Rating:  15% (si existe)
      Technical:        5%

    Pesos con IA:
      Matemático:      40%
      IA Score:        60%

    Retorna un score de 1-10 siempre,
    incluso sin IA y sin analyst rating.
    """

    results = {}

    # ── 1. Piotroski F-Score ─────────────────
    piotroski = calculate_piotroski_fscore(
        financials
    )
    piotroski_normalized = piotroski['normalized']
    results['piotroski'] = piotroski

    # ── 2. Graham Number ─────────────────────
    eps   = float(financials.get('eps', 0))
    bvps  = float(
        financials.get('book_value_per_share', 0)
    )
    graham = calculate_graham_number(
        eps, bvps, current_price, sector
    )
    results['graham'] = graham

    graham_score = 0.0
    if graham['applicable']:
        margin = graham.get('margin_of_safety', 0)
        # Convertir margen a score 0-10
        # +50% margen → 10 puntos
        # 0% margen   → 5 puntos
        # -50% margen → 0 puntos
        graham_score = max(0, min(10,
            5 + (margin / 10)
        ))

    # ── 3. DCF ───────────────────────────────
    fcf_per_share = float(
        financials.get('fcf_per_share', 0)
    )
    revenue_growth = float(
        financials.get('revenue_growth_yoy', 0.05)
    )
    dcf = calculate_dcf(
        fcf_per_share  = fcf_per_share,
        growth_rate    = revenue_growth,
        sector         = sector,
    )
    results['dcf'] = dcf

    dcf_score = 0.0
    if dcf.get('applicable') and \
       dcf.get('intrinsic_value') and \
       current_price > 0:
        upside = (
            dcf['intrinsic_value'] - current_price
        ) / current_price * 100
        # +100% upside → 10 pts
        # 0% upside    → 5 pts
        # -50% upside  → 0 pts
        dcf_score = max(0, min(10,
            5 + (upside / 20)
        ))

    # ── 4. Altman Z-Score ─────────────────────
    altman = calculate_altman_zscore(financials)
    results['altman'] = altman
    # Convertir risk_score (1-9) a score de calidad
    altman_quality = 10 - altman['risk_score']

    # ── 5. Valor Intrínseco consolidado ───────
    # Promedio ponderado de Graham y DCF
    intrinsic_estimates = []
    if graham.get('applicable') and \
       graham.get('graham_number'):
        intrinsic_estimates.append(
            graham['graham_number']
        )
    if dcf.get('applicable') and \
       dcf.get('intrinsic_value'):
        intrinsic_estimates.append(
            dcf['intrinsic_value']
        )

    intrinsic_value = None
    if intrinsic_estimates:
        intrinsic_value = sum(
            intrinsic_estimates
        ) / len(intrinsic_estimates)

    if current_price > 0 and intrinsic_value:
        margin_of_safety = (
            intrinsic_value - current_price
        ) / intrinsic_value * 100
        valuation_status = (
            'undervalued' if margin_of_safety > 10
            else 'overvalued' if margin_of_safety < -10
            else 'fairly_valued'
        )
    else:
        margin_of_safety = 0
        valuation_status = 'unknown'

    # ── 6. Calcular Pro Score matemático ──────
    weights_no_analyst = {
        'piotroski':   0.35,
        'graham':      0.25,
        'dcf':         0.20,
        'altman':      0.10,
        'technical':   0.10,
    }
    weights_with_analyst = {
        'piotroski':   0.30,
        'graham':      0.20,
        'dcf':         0.15,
        'altman':      0.08,
        'analyst':     0.20,
        'technical':   0.07,
    }

    tech_score_norm = float(
        technical_score or 0
    ) / 10  # normalizar a 0-10

    if analyst_rating:
        # Con Analyst Rating de IB
        weights = weights_with_analyst
        math_score = (
            piotroski_normalized * weights['piotroski']
            + graham_score       * weights['graham']
            + dcf_score          * weights['dcf']
            + altman_quality     * weights['altman']
            + float(analyst_rating) * weights['analyst']
            + tech_score_norm    * weights['technical']
        ) / sum(weights.values())
        data_source = 'math + ib_analysts'
    else:
        # Sin Analyst Rating
        weights = weights_no_analyst
        math_score = (
            piotroski_normalized * weights['piotroski']
            + graham_score       * weights['graham']
            + dcf_score          * weights['dcf']
            + altman_quality     * weights['altman']
            + tech_score_norm    * weights['technical']
        ) / sum(weights.values())
        data_source = 'math_only'

    math_score = round(
        max(1.0, min(10.0, math_score)), 2
    )

    # ── 7. Incorporar IA si está disponible ───
    if ia_score and 1 <= ia_score <= 10:
        final_score = (
            math_score * 0.40
            + ia_score  * 0.60
        )
        data_source += ' + ia'
    else:
        final_score = math_score

    # ── 7.5 Generar Justificación Detallada ────────
    # Explicación de la fórmula para el usuario
    if analyst_rating:
        formula_math = "30% Piotroski + 20% Graham + 15% DCF + 8% Altman + 20% Analysts + 7% Tech"
    else:
        formula_math = "35% Piotroski + 25% Graham + 20% DCF + 10% Altman + 10% Tech"
    
    explanation = (
        f"Puntaje de valoración: {float(final_score or 0):.1f}/10. "
        f"Sustentado en la fórmula: "
    )
    
    if ia_score:
        explanation += f"(Math Score {float(math_score or 0):.1f} * 0.4) + (IA Score {float(ia_score or 0):.1f} * 0.6). "
    else:
        explanation += f"{formula_math}. "
        
    # Safe access to component values for formatting
    val_graham = float(graham.get('graham_number') or 0)
    val_dcf = float(dcf.get('intrinsic_value') or 0)

    explanation += (
        f"Componentes: Piotroski={piotroski['score']}/9 (Salud), "
        f"Graham=${val_graham:.2f} (Valor), "
        f"DCF=${val_dcf:.2f} (Flujo). "
        f"Fuente de datos: {data_source}."
    )

    final_score = round(
        max(1.0, min(10.0, final_score)), 2
    )

    # ── 8. Clasificación del score ─────────────
    if final_score >= 8.0:
        rating = 'STRONG BUY'
        color  = '#00C896'
    elif final_score >= 7.0:
        rating = 'BUY'
        color  = '#4FC3F7'
    elif final_score >= 5.5:
        rating = 'HOLD'
        color  = '#FFB74D'
    elif final_score >= 4.0:
        rating = 'WEAK'
        color  = '#FF8A65'
    else:
        rating = 'AVOID'
        color  = '#FF4757'

    iv_display = f"${intrinsic_value:.2f}" if intrinsic_value else "N/A"
    
    log_info('VALUATION',
        f'{ticker}: Pro Score {final_score:.1f} ({rating}) | '
        f'Intrínseco: {iv_display} | '
        f'Piotroski: {piotroski["score"]}/9 | '
        f'Fuente: {data_source}'
    )

    return {
        'ticker':            ticker,
        'pro_score':         final_score,
        'math_score':        math_score,
        'ia_score':          ia_score,
        'rating':            rating,
        'color':             color,
        'data_source':       data_source,
        'ia_available':      ia_score is not None,
        'explanation':       explanation,

        # Valor intrínseco
        'intrinsic_value':   round(
            intrinsic_value, 4
        ) if intrinsic_value else None,
        'margin_of_safety':  round(
            margin_of_safety, 2
        ),
        'valuation_status':  valuation_status,

        # Componentes individuales
        'components': {
            'piotroski': {
                'score':  piotroski['score'],
                'max':    9,
                'norm':   piotroski_normalized,
                'label':  piotroski['interpretation'],
            },
            'graham': {
                'value':     graham.get(
                    'graham_number'
                ),
                'margin':    graham.get(
                    'margin_of_safety'
                ),
                'undervalued': graham.get(
                    'is_undervalued'
                ),
            },
            'dcf': {
                'value':    dcf.get(
                    'intrinsic_value'
                ),
                'upside':   round(
                    (dcf.get('intrinsic_value',
                              current_price)
                     - current_price)
                    / current_price * 100, 2
                ) if dcf.get('applicable')
                   and current_price > 0 else 0,
            },
            'altman': {
                'z_score': altman['z_score'],
                'zone':    altman['zone'],
            },
            'analyst_rating': analyst_rating,
            'technical_score': technical_score,
        },

        # Detalle Piotroski para el dashboard
        'piotroski_detail': piotroski['detail'],
        'dcf_projections':  dcf.get(
            'projections', []
        ),
    }
