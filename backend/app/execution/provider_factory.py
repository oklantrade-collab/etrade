"""
eTrader — Provider Factory
============================
Factory que crea el proveedor de mercado correcto
según el tipo de mercado configurado.

Uso:
    from app.execution.provider_factory import create_provider
    provider = create_provider('forex_futures')
    await provider.connect()
"""
import os
from app.core.logger import log_info, log_error


def create_provider(market_type: str):

    if market_type in (
        'crypto_futures', 'crypto_spot'
    ):
        from app.execution.providers.binance_provider import BinanceCryptoProvider
        from app.core.config import settings
        return BinanceCryptoProvider(
            api_key=os.getenv('BINANCE_API_KEY') or settings.binance_api_key,
            api_secret=os.getenv('BINANCE_SECRET') or settings.binance_secret,
            market=market_type.replace('crypto_', ''),
            testnet=(os.getenv('BINANCE_TESTNET', 'true').lower() == 'true')
        )

    elif market_type in (
        'forex_futures', 'forex_spot'
    ):
        from app.execution.providers.ctrader_provider import CTraderProtobufProvider
        return CTraderProtobufProvider(
            client_id    = os.getenv('CTRADER_CLIENT_ID'),
            client_secret= os.getenv('CTRADER_CLIENT_SECRET'),
            account_id   = int(os.getenv('CTRADER_ACCOUNT_ID', 0)),
            access_token = os.getenv('CTRADER_ACCESS_TOKEN'),
            environment  = os.getenv('CTRADER_ENV', 'demo')
        )

    else:
        raise ValueError(
            f'Market type no soportado: {market_type}'
        )
