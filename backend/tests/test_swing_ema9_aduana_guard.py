import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch

from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult
from app.strategy.swing_orders import process_swing_ema_strategy


def create_df(prices, upper=None, lower=None):
    n = len(prices)
    df = pd.DataFrame({
        'open': [p - 0.0001 for p in prices],
        'high': [p + 0.0005 for p in prices],
        'low': [p - 0.0005 for p in prices],
        'close': list(prices),
        'volume': [1000.0] * n
    })
    if upper is not None:
        df['upper_2'] = upper
    if lower is not None:
        df['lower_2'] = lower
    return df


class TestAduanaEMA20AndFlatBollingerGuards:
    def setup_method(self):
        self.validator = AduanaValidator()

    def test_aduana_rejects_long_when_5m_ema20_declining(self):
        """
        Caso EURUSD: En 5m la EMA20 está perdiendo pendiente / retrocediendo.
        ADUANA debe rechazar la orden LONG con REJECT_5M_EMA20_RETROCESO.
        """
        # 15m expanding bands
        prices_15m = [1.1200 + i * 0.0002 for i in range(25)]
        upper_15m = [1.1210 + i * 0.0003 for i in range(25)]
        lower_15m = [1.1190 - i * 0.0003 for i in range(25)]
        df_15m = create_df(prices_15m, upper=upper_15m, lower=lower_15m)

        # 5m declining prices where EMA20 is sloping downwards
        prices_5m = [1.1240 - i * 0.0002 for i in range(25)]
        df_5m = create_df(prices_5m)

        res = self.validator.validate(
            symbol="EURUSD",
            side="LONG",
            order_type="LIMIT",
            market_data={
                "df_15m": df_15m,
                "df_5m": df_5m,
                "price": 1.1230,
                "rsi_15m": 30.0,
                "require_bb_extreme": False
            },
            strategy="AaApexEma"
        )
        assert not res.approved
        assert res.rule_triggered in ("REJECT_5M_EMA20_RETROCESO", "REJECT_5M_BEARISH_CASCADE", "REJECT_5M_RED_MOMENTUM")

    def test_aduana_rejects_short_when_5m_ema20_rising(self):
        """
        Caso inverso SHORT: En 5m la EMA20 está subiendo (retroceso alcista).
        ADUANA debe rechazar la orden SHORT.
        """
        # 15m expanding bands
        prices_15m = [1.1250 - i * 0.0002 for i in range(25)]
        upper_15m = [1.1260 + i * 0.0003 for i in range(25)]
        lower_15m = [1.1240 - i * 0.0003 for i in range(25)]
        df_15m = create_df(prices_15m, upper=upper_15m, lower=lower_15m)

        # 5m rising prices where EMA20 is sloping upwards
        prices_5m = [1.1200 + i * 0.0002 for i in range(25)]
        df_5m = create_df(prices_5m)

        res = self.validator.validate(
            symbol="EURUSD",
            side="SHORT",
            order_type="LIMIT",
            market_data={
                "df_15m": df_15m,
                "df_5m": df_5m,
                "price": 1.1220,
                "rsi_15m": 70.0,
                "require_bb_extreme": False
            },
            strategy="BbApexEma"
        )
        assert not res.approved
        assert res.rule_triggered in ("REJECT_5M_EMA20_RETROCESO", "REJECT_5M_BULLISH_CASCADE", "REJECT_5M_GREEN_MOMENTUM")

    def test_aduana_rejects_flat_bollinger_without_extreme_long(self):
        """
        En mercado horizontal con bandas planas (upper_slope <= 0 o lower_slope >= 0),
        compras en el medio (cerca de EMA9/Basis) deben ser rechazadas con BB_HORIZONTAL_RANGE_NOT_EXTREME.
        """
        # Bandas planas: upper y lower son horizontales
        prices_15m = [1.1230 for _ in range(25)]
        upper_15m = [1.1240 for _ in range(25)]
        lower_15m = [1.1220 for _ in range(25)]
        df_15m = create_df(prices_15m, upper=upper_15m, lower=lower_15m)

        # Precio en 1.1230 (en el centro, no abajo del lower_bb 1.1220)
        res = self.validator.validate(
            symbol="EURUSD",
            side="LONG",
            order_type="LIMIT",
            market_data={
                "df_15m": df_15m,
                "price": 1.1230
            },
            strategy="AaApexEma"
        )
        assert not res.approved
        assert res.rule_triggered == "BB_HORIZONTAL_RANGE_NOT_EXTREME"

    def test_aduana_rejects_flat_bollinger_without_extreme_short(self):
        """
        En mercado horizontal con bandas planas, ventas SHORT en el medio deben ser rechazadas.
        """
        prices_15m = [1.1230 for _ in range(25)]
        upper_15m = [1.1240 for _ in range(25)]
        lower_15m = [1.1220 for _ in range(25)]
        df_15m = create_df(prices_15m, upper=upper_15m, lower=lower_15m)

        # Precio en 1.1230 (en el centro, no arriba del upper_bb 1.1240)
        res = self.validator.validate(
            symbol="EURUSD",
            side="SHORT",
            order_type="LIMIT",
            market_data={
                "df_15m": df_15m,
                "price": 1.1230
            },
            strategy="BbApexEma"
        )
        assert not res.approved
        assert res.rule_triggered == "BB_HORIZONTAL_RANGE_NOT_EXTREME"

    def test_aduana_approves_flat_bollinger_when_piercing_lower_bb_long(self):
        """
        En mercado horizontal, si el precio perfora por debajo de lower_bb,
        la regla de bandas planas NO debe rechazarlo por ese motivo.
        """
        prices_15m = [1.1230 for _ in range(24)] + [1.1215] # Perforación por debajo de 1.1220
        upper_15m = [1.1240 for _ in range(25)]
        lower_15m = [1.1220 for _ in range(25)]
        df_15m = create_df(prices_15m, upper=upper_15m, lower=lower_15m)
        df_15m.iloc[-1, df_15m.columns.get_loc('low')] = 1.1210 # Low < lower_bb

        res = self.validator.validate(
            symbol="EURUSD",
            side="LONG",
            order_type="LIMIT",
            market_data={
                "df_15m": df_15m,
                "price": 1.1215
            },
            strategy="AaApexEma"
        )
        # No debe ser rechazada por BB_HORIZONTAL_RANGE_NOT_EXTREME
        assert res.rule_triggered != "BB_HORIZONTAL_RANGE_NOT_EXTREME"


class TestSwingOrdersStrictEMA9Conditions:
    def test_ema9_blocked_when_5m_cascade_missing_or_flat_bands(self):
        """
        Verifica que process_swing_ema_strategy no coloque la orden en EMA9 si:
        - Las bandas de 15m son planas (is_bb_expanding = False)
        - O la cascada de 5m no está activa
        """
        import asyncio

        async def _test():
            # 15m flat
            prices_15m = [1.1230 for _ in range(250)]
            df_15m = create_df(prices_15m)
            df_15m['upper_2'] = 1.1240
            df_15m['lower_2'] = 1.1220

            # Mock supabase
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.in_.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
            mock_sb.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value.data = []
            mock_sb.table.return_value.insert.return_value.execute.return_value.data = []

            with patch('app.core.memory_store.get_memory_df') as mock_mem:
                # 5m memory has non-cascade data
                mock_mem.return_value = create_df([1.1230 for _ in range(25)])

                await process_swing_ema_strategy('EURUSD', df_15m, snap={}, sb=mock_sb)

                # Verificar que si se intentó insertar alguna orden, NINGUNA sea 'Order EMA9 Pullback'
                inserted_orders = []
                for call in mock_sb.table.return_value.insert.call_args_list:
                    args, _ = call
                    inserted_orders.append(args[0])

                for o in inserted_orders:
                    assert o.get('band_name') != 'Order EMA9 Pullback', "Order EMA9 Pullback NO debe emitirse en mercado plano sin cascada 5m"

        asyncio.run(_test())
