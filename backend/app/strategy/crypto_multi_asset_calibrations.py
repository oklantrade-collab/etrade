"""
eTrader v5.0 -- Crypto Multi-Asset Calibrations
===============================================
Módulo especializado para el mercado de Criptomonedas (Binance Futures):
1. Weekend Sniper Mode (Sáb 00:00 UTC - Dom 22:00 UTC): Prioridad de rebote en compresión de volumen.
2. Funding Rate Shield: Protección preventiva contra cobros adversos de tasas de fondeo.
3. Fast Short Hedge: Cobertura acelerada en 1 vela de 5m ante flash dumps.
4. Notional USD Sizing: Normalización de tamaño por valor nocional en dólares ($300 - $500 USD).
"""

from datetime import datetime, timezone
import pandas as pd
import numpy as np
from app.core.logger import log_info, log_warning
from app.strategy.quantum_squeeze_hedge import calculate_5m_velocity, calculate_asymmetric_hedge_lots

MODULE = 'CRYPTO_CALIBRATION'

def is_weekend_sniper_active(now_utc: datetime = None) -> bool:
    """
    Retorna True si estamos en fin de semana (Sábado o Domingo hasta las 22:00 UTC),
    donde el volumen institucional baja y el mercado oscila en rangos de alta predictibilidad.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday() # 5 = Sábado, 6 = Domingo
    if weekday == 5:
        return True
    if weekday == 6 and now_utc.hour < 22:
        return True
    return False

def check_funding_rate_shield(
    symbol: str,
    position: dict,
    current_pnl_pct: float,
    funding_rate: float,
    now_utc: datetime = None
) -> dict | None:
    """
    Funding Rate Shield:
    Si faltan <= 5 minutos para el corte de Funding Rate (00:00, 08:00, 16:00 UTC)
    y la posición está en micro-ganancia (+0.1% a +0.3%) pagando una tasa adversa (> +0.03% en LONG o < -0.03% en SHORT),
    dispara Take Profit preventivo a Breakeven para evitar pagar comisión.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # Cortes de fondeo: cada 8 horas (0, 8, 16)
    minutes_to_funding = 60 - now_utc.minute if now_utc.minute > 0 else 0
    next_hour = (now_utc.hour + 1) % 24
    is_funding_imminent = (next_hour in (0, 8, 16) and now_utc.minute >= 55)

    if not is_funding_imminent:
        return None

    side = (position.get('side') or '').lower()
    
    # LONG paga si funding_rate es positivo; SHORT paga si funding_rate es negativo
    is_paying_funding = (side in ('long', 'buy') and funding_rate >= 0.0003) or (side in ('short', 'sell') and funding_rate <= -0.0003)

    if is_paying_funding and (0.0010 <= current_pnl_pct <= 0.0035):
        log_info(MODULE, f"🛡️ [FUNDING SHIELD] {symbol} {side.upper()}: Cierre preventivo antes del corte ({funding_rate*100:.3f}%)")
        return {
            'action': 'close_funding_shield',
            'reason': f"Funding Shield activado: Corte inminente con tasa {funding_rate*100:.3f}% y PnL {current_pnl_pct*100:.2f}%",
            'symbol': symbol
        }
    return None

def evaluate_fast_short_hedge_crypto(
    df_5m: pd.DataFrame,
    position: dict
) -> dict | None:
    """
    Fast Short Hedge para Crypto (Flash Dump Protection):
    Activa la cobertura SHORT de QSHR en 1 sola vela de 5m cuando V_5m >= 2.5 y volumen institucional.
    """
    if df_5m is None or len(df_5m) < 2 or not position:
        return None

    side = (position.get('side') or '').lower()
    if side not in ('long', 'buy'):
        return None

    vel = calculate_5m_velocity(df_5m)
    last_c = df_5m.iloc[-1]
    prev_c = df_5m.iloc[-2]

    # Caída violenta en 5m con aceleración (Flash Dump)
    is_flash_dump = (vel['is_high_velocity'] or (vel['direction'] == 'BEARISH_SURGE' and vel['v_5m_score'] >= 1.5)) and (last_c['close'] < prev_c['close'])

    if is_flash_dump:
        orig_size = float(position.get('size') or position.get('lots') or 1.0)
        hedge_size = calculate_asymmetric_hedge_lots(orig_size, vel['v_5m_score'])
        return {
            'action': 'open_fast_short_hedge',
            'side': 'short',
            'size': hedge_size,
            'velocity': vel['v_5m_score'],
            'rule_code': 'Dd61_FAST_SHORT_HEDGE',
            'reason': f"Fast Short Hedge Crypto activado (V_5m={vel['v_5m_score']:.2f}, Size={hedge_size})"
        }
    return None

def calculate_notional_usd_sizing(
    symbol: str,
    current_price: float,
    target_notional_usd: float = 300.0,
    min_size_precision: int = 4
) -> float:
    """
    Calcula el tamaño del token necesario para alcanzar el valor nocional en dólares deseado.
    Size = Target_Notional_USD / Current_Price
    """
    if current_price <= 0:
        return 0.0
    raw_size = target_notional_usd / current_price
    
    if symbol.startswith('BTC'):
        return round(raw_size, 3) # e.g. 0.005 BTC
    elif symbol.startswith('ETH'):
        return round(raw_size, 3) # e.g. 0.150 ETH
    elif symbol.startswith('SOL'):
        return round(raw_size, 2) # e.g. 4.50 SOL
    else:
        return round(raw_size, min_size_precision)
