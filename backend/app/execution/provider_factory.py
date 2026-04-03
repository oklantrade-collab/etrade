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
    """
    Factory que crea el proveedor correcto
    según el tipo de mercado configurado.

    Tipos soportados:
        - 'crypto_futures' / 'crypto_spot'  → BinanceCryptoProvider
        - 'forex_futures'  / 'forex_spot'   → CTraderProvider

    Args:
        market_type: Tipo de mercado a operar.

    Returns:
        Instancia del proveedor correspondiente (sin conectar).

    Raises:
        ValueError: Si el tipo de mercado no está soportado.
    """
    log_info('FACTORY', f'Creando proveedor para: {market_type}')

    if market_type in ('crypto_futures', 'crypto_spot'):
        from app.execution.providers.binance_provider import BinanceCryptoProvider
        from app.core.config import settings

        return BinanceCryptoProvider(
            api_key=os.getenv('BINANCE_API_KEY') or settings.binance_api_key,
            api_secret=os.getenv('BINANCE_SECRET') or settings.binance_secret,
            market=market_type.replace('crypto_', ''),
            testnet=(
                os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
            ),
        )

    elif market_type in ('forex_futures', 'forex_spot'):
        from app.execution.providers.ctrader_provider import CTraderProvider

        client_id     = os.getenv('CTRADER_CLIENT_ID')
        client_secret = os.getenv('CTRADER_CLIENT_SECRET')
        account_id    = os.getenv('CTRADER_ACCOUNT_ID')
        access_token  = os.getenv('CTRADER_ACCESS_TOKEN')
        environment   = os.getenv('CTRADER_ENV', 'demo')

        # Validar que las credenciales estén configuradas
        missing = []
        if not client_id:     missing.append('CTRADER_CLIENT_ID')
        if not client_secret: missing.append('CTRADER_CLIENT_SECRET')
        if not account_id:    missing.append('CTRADER_ACCOUNT_ID')
        if not access_token:  missing.append('CTRADER_ACCESS_TOKEN')

        if missing:
            msg = f'Variables de entorno faltantes: {", ".join(missing)}'
            log_error('FACTORY', msg)
            raise ValueError(msg)

        return CTraderProvider(
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
            access_token=access_token,
            environment=environment,
        )

    else:
        raise ValueError(f'Proveedor no soportado: {market_type}')
