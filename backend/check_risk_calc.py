import sys
sys.path.append('c:/Fuentes/eTrade/backend')
from app.config.forex_config import PIP_SIZES, LOT_CONFIG

def calculate_forex_lot_size_fixed(
    symbol: str,
    capital_usd: float,
    risk_pct: float,
    sl_pips: float,
    price: float = 1.0,
) -> dict:
    pip_size = PIP_SIZES.get(symbol, 0.0001)
    risk_usd = capital_usd * (risk_pct / 100.0)

    CONTRACT_SIZES = {
        'XAUUSD': 100,
        'XAGUSD': 5000,
        'US30':   1,
        'US500':  1,
        'NAS100': 1,
    }
    contract_size = CONTRACT_SIZES.get(symbol, 100_000)

    pip_value = pip_size * contract_size
    
    # Si la moneda de cotización es JPY (ej. USDJPY, EURJPY), convertir el pip value de JPY a USD dividiendo por el precio
    if 'JPY' in symbol and price > 0:
        pip_value_usd = pip_value / price
    else:
        pip_value_usd = pip_value

    if sl_pips > 0 and pip_value_usd > 0:
        lots = risk_usd / (sl_pips * pip_value_usd)
    else:
        lots = LOT_CONFIG['micro_lot']

    step = LOT_CONFIG['lot_step']
    lots = max(LOT_CONFIG['min_lot'], round(lots / step) * step)

    return {
        'lotes': round(lots, 2),
        'risk_usd': round(risk_usd, 2),
        'pip_value_usd': round(pip_value_usd, 4),
        'pip_size': pip_size,
    }

test_cases = [
    ('EURUSD', 50, 1.1556),
    ('GBPUSD', 40, 1.3466),
    ('USDJPY', 60, 157.73),
    ('XAUUSD', 40, 4278.0),
    ('USDJPY', 100, 157.73),
]

print("=== CALCULOS CORREGIDOS (CON CONVERSION JPY -> USD) ===")
print(f"Capital: $200 USD | Riesgo: 2% ($4.00 USD)")
print("-" * 80)
print(f"{'Simbolo':<10} {'Precio':<10} {'SL (pips)':<10} {'Lotes':<8} {'PipVal USD/Lot':<16} {'Riesgo Real USD':<15}")
print("-" * 80)

for sym, sl_pips, price in test_cases:
    res = calculate_forex_lot_size_fixed(sym, 200.0, 2.0, sl_pips, price)
    lots = res['lotes']
    pip_val_usd = res['pip_value_usd']
    real_risk = sl_pips * pip_val_usd * lots
    print(f"{sym:<10} {price:<10.2f} {sl_pips:<10} {lots:<8.2f} ${pip_val_usd:<15.4f} ${real_risk:<14.2f}")
