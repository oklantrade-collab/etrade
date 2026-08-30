import pytest
import pandas as pd
from app.strategy.capital_protection import evaluate_range_bollinger_exit, ProtectionState
from app.rebote_aduana.aduana_validator import AduanaValidator


def _create_compressed_15m_df(price: float = 1.35900, bw: float = 0.0008, adx: float = 14.0) -> pd.DataFrame:
    basis = price + 0.0004
    half_w = (basis * bw) / 2.0
    upper_2 = basis + half_w
    lower_2 = basis - half_w
    
    data = []
    for _ in range(15):
        data.append({
            'open': price,
            'high': price + 0.0002,
            'low': price - 0.0002,
            'close': price,
            'upper_2': upper_2,
            'lower_2': lower_2,
            'basis': basis,
            'adx': adx,
            'volume': 200
        })
    return pd.DataFrame(data)


class TestRangeBandAndAntiChop:

    def test_aduana_anti_chop_blocks_trend_strategy_in_compression_forex(self):
        """Aduana: Bloquea BbHot en Forex si BandWidth < 12 pips y ADX < 18."""
        val = AduanaValidator()
        df_15m = _create_compressed_15m_df(bw=0.0007, adx=13.0) # ~7 pips, ADX 13
        
        market_data = {
            'df_15m': df_15m,
            'df_5m': df_15m,
            'adx_15m': 13.0,
            'rsi_15m': 50.0
        }
        
        res = val.validate(
            symbol='GBPUSD',
            side='short',
            order_type='MARKET',
            market_data=market_data,
            strategy='BbHot',
            market_type='forex_futures'
        )
        
        assert res.approved is False
        assert res.rule_triggered == 'ANTI_CHOP_BLOCKED'
        assert 'mercado lateral en compresión' in res.reason

    def test_aduana_anti_chop_allows_rebote_strategy_in_compression(self):
        """Aduana: Permite Dd11 (Rebote) en mercado comprimido porque opera en el extremo."""
        val = AduanaValidator()
        df_15m = _create_compressed_15m_df(bw=0.0007, adx=13.0)
        
        market_data = {
            'df_15m': df_15m,
            'df_5m': df_15m,
            'fib_zone': -5
        }
        
        res = val.validate(
            symbol='GBPUSD',
            side='long',
            order_type='LIMIT',
            market_data=market_data,
            strategy='Dd11',
            market_type='forex_futures'
        )
        
        # Rebote no se bloquea por Anti-Chop
        assert res.rule_triggered != 'ANTI_CHOP_BLOCKED'

    def test_range_band_exit_short_at_lower_band_with_profit_forex(self):
        """Forex: SHORT con ganancia (+2.7 pips) tocando Lower_2 se cierra asegurando piso."""
        entry = 1.35927
        current_price = 1.35890 # Lower band level (+3.7 pips ganancia)
        
        state = ProtectionState(
            position_id='pos_range_short_1',
            symbol='GBPUSD',
            side='short',
            entry_price=entry,
            current_sl=1.35950,
            original_sl=1.35950,
            market_type='forex_futures',
            rule_code='BbHot',
            lots=0.01
        )
        
        snap = {
            'upper_2': 1.35985,
            'basis': 1.35938,
            'lower_2': 1.35890, # ~9.5 pips BW
            'adx': 14.0
        }
        
        res = evaluate_range_bollinger_exit(state, current_price, snap=snap)
        
        assert res['action'] == 'close_market'
        assert 'range_bollinger_lower_exit' in res['reason']
        assert res['pips'] >= 2.0
        assert res['pnl_usd'] > 0

    def test_range_band_exit_long_at_upper_band_with_profit_crypto(self):
        """Crypto: LONG con ganancia (+1.5%) tocando Upper_2 se cierra asegurando techo."""
        entry = 50000.0
        current_price = 50750.0 # +1.5% ganancia
        
        state = ProtectionState(
            position_id='pos_range_crypto_long',
            symbol='BTCUSDT',
            side='long',
            entry_price=entry,
            current_sl=49500.0,
            original_sl=49500.0,
            market_type='crypto',
            rule_code='Trend_15m',
            lots=0.01
        )
        
        snap = {
            'upper_2': 50750.0,
            'basis': 50350.0,
            'lower_2': 49950.0, # ~1.5% BW
            'adx': 15.0
        }
        
        res = evaluate_range_bollinger_exit(state, current_price, snap=snap)
        
        assert res['action'] == 'close_market'
        assert 'range_bollinger_upper_exit' in res['reason']
        assert res['pnl_usd'] > 0

    def test_range_band_exit_strictly_blocks_if_pnl_is_negative(self):
        """🛡️ Candado Inviolable: NUNCA cerrar por toque de banda si la posición está en pérdida."""
        entry = 1.35880
        current_price = 1.35890 # SHORT en pérdida (-1.0 pip)
        
        state = ProtectionState(
            position_id='pos_range_loss',
            symbol='GBPUSD',
            side='short',
            entry_price=entry,
            current_sl=1.35950,
            original_sl=1.35950,
            market_type='forex_futures',
            rule_code='BbHot',
            lots=0.01
        )
        
        snap = {
            'upper_2': 1.35985,
            'basis': 1.35938,
            'lower_2': 1.35890,
            'adx': 14.0
        }
        
        res = evaluate_range_bollinger_exit(state, current_price, snap=snap)
        
        # En pérdida, action debe ser 'none'
        assert res['action'] == 'none'
