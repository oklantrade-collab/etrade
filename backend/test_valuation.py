
from app.stocks.valuation_engine import (
    calculate_composite_pro_score,
    calculate_piotroski_fscore,
    calculate_graham_number,
    calculate_dcf,
    calculate_altman_zscore
)

# Datos reales aproximados de AAPL Q4 2025
financials = {
    'roa': 0.28, 'roa_prev': 0.26,
    'ocf': 118e9, 'net_income': 97e9,
    'total_assets': 352e9,
    'current_assets': 143e9,
    'current_liabilities': 131e9,
    'long_term_debt': 85e9, 'long_term_debt_prev': 95e9,
    'total_liabilities': 299e9,
    'retained_earnings': 0e9,
    'market_cap': 3.3e12,
    'eps': 6.57, 'fcf_per_share': 7.20,
    'book_value_per_share': 4.38,
    'current_ratio': 1.07, 'current_ratio_prev': 0.95,
    'gross_margin': 0.46, 'gross_margin_prev': 0.43,
    'asset_turnover': 1.12, 'asset_turnover_prev': 1.08,
    'revenue_growth_yoy': 0.05,
    'ebit': 115e9, 'revenue': 391e9,
    'shares_outstanding': 15.4e9,
    'shares_outstanding_prev': 15.8e9,
}

# Test Piotroski
p = calculate_piotroski_fscore(financials)
print(f'Piotroski: {p["score"]}/9 ({p["interpretation"]})')

# Test Graham
g = calculate_graham_number(6.57, 4.38, 190.0)
print(f'Graham Number: ${g["graham_number"]:.2f}')
print(f'Margen seguridad: {g["margin_of_safety"]:.1f}%')

# Test DCF
d = calculate_dcf(7.20, 0.05, 'Technology')
print(f'DCF Intrínseco: ${d["intrinsic_value"]:.2f}')

# Test Composite (sin IA)
result = calculate_composite_pro_score(
    ticker='AAPL',
    current_price=190.0,
    financials=financials,
    sector='Technology',
    analyst_rating=8.5,   # IB analyst rating
    technical_score=72,   # technical score
    ia_score=None,        # sin IA
)
print(f'Pro Score (sin IA): {result["pro_score"]}/10')
print(f'Rating: {result["rating"]}')
print(f'Intrínseco: ${result["intrinsic_value"]:.2f}')
print(f'Status: {result["valuation_status"]}')
print(f'Fuente: {result["data_source"]}')
