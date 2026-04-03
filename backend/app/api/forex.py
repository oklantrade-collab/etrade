from fastapi import APIRouter, Depends
import os
from app.core.supabase_client import get_supabase

router = APIRouter()

@router.get('/status')
async def get_forex_status(
    sb = Depends(get_supabase)
):
    """
    Verificar si Forex está configurado y conectado.
    """
    # Verificar credenciales en env
    has_credentials = all([
        os.getenv('CTRADER_CLIENT_ID'),
        os.getenv('CTRADER_CLIENT_SECRET'),
        os.getenv('CTRADER_ACCOUNT_ID'),
        os.getenv('CTRADER_ACCESS_TOKEN'),
    ])

    # Verificar capital asignado
    config = sb.table('trading_config')\
        .select('capital_forex_futures')\
        .eq('id', 1)\
        .single()\
        .execute()

    has_capital = float(
        config.data.get(
            'capital_forex_futures', 0
        ) or 0
    ) > 0

    connected = has_credentials and has_capital

    return {
        'connected':       connected,
        'has_credentials': has_credentials,
        'has_capital':     has_capital,
        'environment':     os.getenv(
            'CTRADER_ENV', 'demo'
        ),
        'pairs_configured': [
            'EURUSD','GBPUSD',
            'USDJPY','XAUUSD'
        ] if connected else [],
    }

@router.get('/snapshots')
async def get_forex_snapshots(
    sb = Depends(get_supabase)
):
    """Obtener snapshots de pares Forex."""
    res = sb.table('market_snapshot')\
        .select('*')\
        .in_('symbol', [
            'EURUSD','GBPUSD',
            'USDJPY','XAUUSD'
        ])\
        .execute()

    return {
        row['symbol']: row
        for row in (res.data or [])
    }
