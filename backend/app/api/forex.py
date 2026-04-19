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
        .select('capital_forex_futures, regime_params')\
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
        'pairs_configured': (
            config.data.get('regime_params', {}) or {}
        ).get('forex_assets', [
            'EURUSD','GBPUSD','USDJPY','XAUUSD'
        ]) if connected else [],
    }

@router.get('/snapshots')
async def get_forex_snapshots(
    sb = Depends(get_supabase)
):
    """Obtener snapshots de pares Forex."""
    config = sb.table('trading_config')\
        .select('regime_params')\
        .eq('id', 1)\
        .single()\
        .execute()
        
    pairs = (
        config.data.get('regime_params', {}) or {}
    ).get('forex_assets', [
        'EURUSD','GBPUSD','USDJPY','XAUUSD'
    ])

    res = sb.table('market_snapshot')\
        .select('*')\
        .in_('symbol', pairs)\
        .execute()

    return {
        row['symbol']: row
        for row in (res.data or [])
    }
@router.get('/candles')
async def get_forex_candles(
    symbol: str = 'EURUSD',
    timeframe: str = '15m',
    sb = Depends(get_supabase)
):
    """Obtener velas históricas con indicadores técnicos."""
    res = sb.table('market_candles')\
        .select('*')\
        .eq('symbol', symbol)\
        .eq('timeframe', timeframe)\
        .eq('exchange', 'icmarkets')\
        .order('open_time', desc=True)\
        .limit(300)\
        .execute()
    
    # Revertir para que estén en orden ascendente (cronológico)
    candles = res.data or []
    candles.reverse()
    return candles
    
@router.get('/positions')
async def get_forex_positions(
    status: str = 'open',
    sb = Depends(get_supabase)
):
    """Obtener posiciones de Forex (abiertas o cerradas)."""
    res = sb.table('forex_positions')\
        .select('*')\
        .eq('status', status)\
        .order('opened_at', desc=True)\
        .execute()
    return res.data or []
