import pytest
from app.stocks.stocks_rule_engine import StocksRuleEngine

def test_aduana_long_impulse_guard_blocks_weak_trend_and_sellers():
    re = StocksRuleEngine.get_instance()

    base_ctx = {
        'ticker': 'TEST_STOCK',
        'price': 10.0,
        'rvol': 2.0,
        'macro_1d_aligned': True,
        'buying_force_score': 85,
        'adr_14_pct': 4.0,
        'entry_route_1h': 'PULLBACK',
        'entry_support_1h': 'EMA9',
        'pool_type': 'HOT',
        'is_ema3_1h_ascending': True,
        'ema3_slope_1h': 0.10,
        'is_ema3_above_ema9': True,
        'adx_5m': 25.0,
        'plus_di_5m': 28.0,
        'minus_di_5m': 14.0,
        'is_red_candle_1h': False,
        'is_last_candle_green': True,
        'lower_wick_ratio': 0.35,
    }

    rule_obj = {
        'rule_code': 'LONG_PULLBACK_1H',
        'direction': 'buy',
        'order_type': 'market',
        'enabled': True
    }

    # 1. Caso Aprobado: ADX fuerte (25) y +DI > -DI
    res_ok = re.evaluate_rule(rule_obj, base_ctx)
    assert res_ok['triggered'] is True, f"Debió disparar pero falló: {res_ok.get('failures')}"

    # 2. Caso Bloqueado: -DI > +DI (Vendedores dominando, caso CANG)
    ctx_sellers = {**base_ctx, 'plus_di_5m': 20.0, 'minus_di_5m': 25.0}
    res_sellers = re.evaluate_rule(rule_obj, ctx_sellers)
    assert res_sellers['triggered'] is False
    assert any("Aduana -DI > +DI" in f for f in res_sellers['failures'])

    # 3. Caso Bloqueado: ADX débil < 18 (Mercado aletargado, caso CANG ADX 11.1)
    ctx_weak_adx = {**base_ctx, 'adx_5m': 11.1}
    res_weak_adx = re.evaluate_rule(rule_obj, ctx_weak_adx)
    assert res_weak_adx['triggered'] is False
    assert any("Aduana ADX Débil" in f for f in res_weak_adx['failures'])

    # 4. Caso Bloqueado: Cuchillo Cayendo (1H Roja + 5m Roja sin mecha de absorción)
    ctx_knife = {
        **base_ctx,
        'is_red_candle_1h': True,
        'is_last_candle_green': False,
        'lower_wick_ratio': 0.10,  # Solo 10% de mecha (sin absorción)
    }
    res_knife = re.evaluate_rule(rule_obj, ctx_knife)
    assert res_knife['triggered'] is False
    assert any("Aduana Falling Knife" in f for f in res_knife['failures'])


def test_dip_buy_rebound_confirmation():
    re = StocksRuleEngine.get_instance()

    base_dip = {
        'ticker': 'TEST_DIP',
        'price': 10.0,
        'close': 10.0,
        'open': 9.90,       # Vela 15m verde
        'high': 10.20,
        'low': 9.75,
        'rvol': 1.5,
        'rsi_14': 45.0,
        'bb_upper': 11.0,
        'ema_9_1d': 10.50,
        'ema_20_1d': 9.80,   # Low (9.75) <= EMA20_1D (9.80) -> Dip tocado
        'ema_3_1d': 10.60,
        'ema_20_4h': 9.70,
        'ema_20': 9.90,
        'ema_9': 10.00,
        'ema_3': 10.10,
        'is_ema3_1h_ascending': True,
        'ema3_slope_1h': 0.05,
        'is_ema3_above_ema9': True,
        'adx_5m': 22.0,
        'plus_di_5m': 26.0,
        'minus_di_5m': 15.0,
        'is_red_candle_1h': False,
        'is_last_candle_green': True,
        'lower_wick_ratio': 0.40,
    }

    rule_dip = {
        'rule_code': 'PRO_DIP_BUY',
        'direction': 'buy',
        'order_type': 'market',
        'enabled': True
    }

    # 1. Caso Aprobado: Vela 15m verde rebotando en EMA20
    res_ok = re.evaluate_rule(rule_dip, base_dip)
    assert res_ok['triggered'] is True, f"Fallo inesperado: {res_ok.get('failures')}"

    # 2. Caso Bloqueado: Vela 15m roja en caída sin absorción (cuchillo cayendo en soporte)
    ctx_knife_dip = {
        **base_dip,
        'open': 10.15,
        'close': 9.76,      # Cierre rojo cerca del mínimo (9.75)
        'high': 10.15,
        'low': 9.75,
    }
    res_knife = re.evaluate_rule(rule_dip, ctx_knife_dip)
    assert res_knife['triggered'] is False
    assert any("Rebote no confirmado en EMA20" in f for f in res_knife['failures'])
