import pandas as pd
import numpy as np

router = APIRouter()

def calculate_forex_indicators(candles):
    if not candles: return []
    try:
        df = pd.DataFrame(candles)
        # Ensure numeric and sort chronologically
        for col in ['open','high','low','close']: 
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Calculate EMA20 (Standard for our Forex model)
        df['basis'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # Calculate ATR14
        df['tr'] = np.maximum(df['high'] - df['low'], 
                             np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                        abs(df['low'] - df['close'].shift(1))))
        df['atr'] = df['tr'].rolling(window=14).mean()
        
        # Fill ATR gaps at start with SMA of TR
        df.loc[df.index[:14], 'atr'] = df['tr'].rolling(window=14, min_periods=1).mean()

        multipliers = [1.618, 2.618, 3.618, 4.236, 5.618, 6.618]
        for i, m in enumerate(multipliers, 1):
            df[f'upper_{i}'] = df['basis'] + (df['atr'] * m)
            df[f'lower_{i}'] = df['basis'] - (df['atr'] * m)
        
        # SAR calculation fallback
        from app.analysis.parabolic_sar import calculate_parabolic_sar
        calculate_parabolic_sar(df)

        return df.fillna(0).to_dict('records')
    except Exception as e:
        print(f"Error calculating API indicators: {e}")
        return candles

@router.get('/candles')
async def get_forex_candles(
    symbol: str = 'EURUSD',
    timeframe: str = '15m',
    sb = Depends(get_supabase)
):
    """Obtener velas históricas con indicadores técnicos."""
    try:
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
        
        # Inyectar indicadores calculados al vuelo para evitar huecos en el frontend
        full_candles = calculate_forex_indicators(candles)
        return full_candles
    except Exception as e:
        print(f"Candles API Error: {e}")
        return []
    
@router.get('/positions')
async def get_forex_positions(
    status: str = 'open',
    sb = Depends(get_supabase)
):
    """Obtener posiciones de Forex (abiertas o cerradas)."""
    try:
        res = sb.table('forex_positions')\
            .select('*')\
            .eq('status', status)\
            .order('opened_at', desc=True)\
            .execute()
        return res.data or []
    except:
        return []
