from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase

router = APIRouter()

@router.get('/dashboard/summary')
async def get_crypto_dashboard(
    sb = Depends(get_supabase)
):
    """
    Retorna todos los datos del dashboard
    desde Supabase (lectura local, sin Binance).
    Tiempo de respuesta: < 50ms
    """
    # Snapshots actuales
    snaps_res = sb.table('market_snapshot')\
        .select('*')\
        .in_('symbol', [
            'BTCUSDT','ETHUSDT',
            'SOLUSDT','ADAUSDT'
        ])\
        .execute()
    snapshots = {
        s['symbol']: s
        for s in (snaps_res.data or [])
    }

    # Posiciones abiertas
    pos_res = sb.table('positions')\
        .select('*')\
        .eq('status', 'open')\
        .execute()
    positions = pos_res.data or []

    # P&L del día
    today = datetime.now(timezone.utc)\
        .replace(hour=0, minute=0, second=0, microsecond=0)\
        .isoformat()
    pnl_res = sb.table('positions')\
        .select('realized_pnl,symbol')\
        .gte('closed_at', today)\
        .eq('status', 'closed')\
        .execute()
    daily_pnl = sum(
        float(r.get('realized_pnl', 0) or 0)
        for r in (pnl_res.data or [])
    )

    # Estado del worker (último heartbeat)
    diag_res = sb.table('pilot_diagnostics')\
        .select('timestamp,cycle_type')\
        .gte('timestamp', (
            datetime.now(timezone.utc)
            - timedelta(minutes=10)
        ).isoformat())\
        .limit(1)\
        .execute()
    worker_active = bool(diag_res.data)

    # Señales recientes
    signals_res = sb.table('strategy_evaluations')\
        .select('*')\
        .gte('created_at', (
            datetime.now(timezone.utc)
            - timedelta(hours=1)
        ).isoformat())\
        .eq('triggered', True)\
        .order('created_at', desc=True)\
        .limit(10)\
        .execute()

    return {
        'snapshots':      snapshots,
        'positions':      positions,
        'daily_pnl':      round(daily_pnl, 2),
        'worker_active':  worker_active,
        'signals':        signals_res.data or [],
        'timestamp':      datetime.now(
            timezone.utc
        ).isoformat(),
    }

@router.get('/dashboard/positions')
async def get_positions_live_crypto(
    sb = Depends(get_supabase)
):
    """
    Posiciones con P&L calculado desde Supabase.
    Usa el precio de market_snapshot (actualizado
    por el worker cada 5m).
    """
    pos_res = sb.table('positions')\
        .select('*')\
        .eq('status', 'open')\
        .order('opened_at', desc=True)\
        .execute()
    positions = pos_res.data or []

    # Enriquecer con precio actual
    snaps_res = sb.table('market_snapshot')\
        .select('symbol,price,fibonacci_zone')\
        .execute()
    price_map = {
        s['symbol']: s
        for s in (snaps_res.data or [])
    }

    for pos in positions:
        symbol = pos.get('symbol', '')
        snap   = price_map.get(symbol, {})
        price  = float(snap.get('price', 0))
        entry  = float(pos.get(
            'avg_entry_price', 0
        ) or pos.get('entry_price', 0) or 0)
        side   = str(pos.get('side', 'long'))

        if price > 0 and entry > 0:
            if side in ('long', 'buy'):
                pnl_pct = (
                    price - entry
                ) / entry * 100
            else:
                pnl_pct = (
                    entry - price
                ) / entry * 100

            pos['current_price'] = price
            pos['unrealized_pnl_pct'] = round(
                pnl_pct, 4
            )
            pos['fib_zone'] = snap.get(
                'fibonacci_zone', 0
            )

    return {
        'positions':  positions,
        'count':      len(positions),
        'timestamp':  datetime.now(
            timezone.utc
        ).isoformat(),
    }
