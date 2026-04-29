"""
eTrade v4 — Central Memory Store
Implements the Memory-First Architecture.
HOT Data (Volatility/Indicators) lives only here.
WARM Data (Operational State) is mirrored with Supabase.
"""
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd

# ─── HOT DATA (Volatility / Indicators) ───
# Structure: MEMORY_STORE[symbol][timeframe] = { 'df': pd.DataFrame, ... }
MEMORY_STORE: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(dict))
MARKET_SNAPSHOT_CACHE: Dict[str, dict] = {}

# ─── WARM DATA (Operational Business State) ───
@dataclass
class BotState:
    positions: Dict[str, Any] = field(default_factory=dict)       # {pos_id: Position}
    cooldowns: Dict[str, Any] = field(default_factory=dict)       # {symbol: expiry_dt}
    circuit_breaker: Dict[str, Any] = field(default_factory=lambda: {
        'triggered': False, 
        'daily_pnl': 0.0,
        'last_reset': datetime.utcnow().date()
    })
    emergency: Dict[str, bool] = field(default_factory=dict)      # {symbol: bool}
    regime_cache: Dict[str, Any] = field(default_factory=dict)    # {symbol: last_regime}
    rules_cache: list[dict] = field(default_factory=list)         # Loaded rules
    config_cache: dict = field(default_factory=dict)              # Global settings
    cycle_count_15m: int = 0                                       # Cycle counter for 15m interval
    sl_alerts: Dict[str, Any] = field(default_factory=dict)       # {symbol: alert_state}
    order_lock: asyncio.Lock = field(default_factory=asyncio.Lock) # Lock for atomic order placement
    opening_locks: Dict[str, bool] = field(default_factory=dict)  # Symbols currently in the process of opening
    last_close_cycles: Dict[str, int] = field(default_factory=dict) # {symbol: cycle_index}
    current_cycle: int = 0                                          # Global cycle counter

    def get_positions_by_symbol(self, symbol: str) -> list[dict]:
        """Helper to get all open positions for a specific symbol."""
        return [p for p in self.positions.values() if p.get('symbol') == symbol]

    def get_first_position_by_symbol(self, symbol: str) -> Optional[dict]:
        """Helper for backward compatibility (gets the first/oldest position)."""
        pos_list = self.get_positions_by_symbol(symbol)
        return pos_list[0] if pos_list else None

BOT_STATE = BotState()

def get_memory_df(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    return MEMORY_STORE.get(symbol, {}).get(timeframe, {}).get('df')

def update_memory_df(symbol: str, timeframe: str, df: pd.DataFrame):
    MEMORY_STORE[symbol][timeframe]['df'] = df
    MEMORY_STORE[symbol][timeframe]['last_updated'] = datetime.utcnow()

def clear_symbol_memory(symbol: str):
    if symbol in MEMORY_STORE:
        del MEMORY_STORE[symbol]

def reset_daily_pnl():
    """Reset the circuit breaker counter at 00:00 UTC"""
    BOT_STATE.circuit_breaker['daily_pnl'] = 0.0
    BOT_STATE.circuit_breaker['triggered'] = False
    BOT_STATE.circuit_breaker['last_reset'] = datetime.utcnow().date()

def update_current_candle_close(
    symbol:        str,
    current_price: float,
    current_volume: float = 0.0
) -> None:
    """
    Actualiza el precio de cierre de la vela en curso para todos los timeframes en memoria.
    Se llama en cada ciclo de 5m con el precio actual de mercado.
    No descarga nada de Binance. Solo modifica la última fila del DataFrame en MEMORY_STORE.
    """
    from app.core.logger import log_warning
    timeframes = ['5m', '15m', '30m', '1h', '4h', '1d']

    for tf in timeframes:
        try:
            df = MEMORY_STORE.get(symbol, {}).get(tf, {}).get('df', None)

            if df is None or df.empty:
                continue

            # Obtener tiempo actual y tiempo de la última vela
            now = datetime.utcnow()
            last_idx = df.index[-1]
            
            # Determinar duración del TF en minutos
            tf_mins = {
                '5m': 5, '15m': 15, '30m': 30, 
                '1h': 60, '4h': 240, '1d': 1440
            }.get(tf, 15)
            
            # Verificar si ya debió empezar una nueva vela
            # last_idx suele ser un datetime (open_time)
            if isinstance(last_idx, datetime):
                # Si han pasado más de tf_mins desde la apertura de la última, CREAR NUEVA
                from datetime import timedelta
                if now >= (last_idx + timedelta(minutes=tf_mins)):
                    new_idx = last_idx + timedelta(minutes=tf_mins)
                    # Solo crear si no existe ya (doble check)
                    if new_idx not in df.index:
                        prev_close = float(df.at[last_idx, 'close'])
                        new_row = {
                            'open': prev_close,
                            'high': prev_close,
                            'low': prev_close,
                            'close': current_price,
                            'volume': 0.0,
                            'is_closed': False
                        }
                        # Copiar otros indicadores si existen (nan por defecto)
                        for col in df.columns:
                            if col not in new_row:
                                new_row[col] = float('nan')
                        
                        df.loc[new_idx] = new_row
                        last_idx = new_idx # Actualizar puntero para el update de abajo

            # Actualizar (o seguir actualizando) la última fila con precio actual
            # close = precio actual de mercado
            df.at[last_idx, 'close'] = current_price

            # high = máximo entre high actual y precio
            df.at[last_idx, 'high'] = max(
                float(df.at[last_idx, 'high']),
                current_price
            )

            # low = mínimo entre low actual y precio
            df.at[last_idx, 'low'] = min(
                float(df.at[last_idx, 'low']),
                current_price
            )

            # volume = acumular si se proporciona
            if current_volume > 0:
                current_vol_val = df.at[last_idx, 'volume']
                df.at[last_idx, 'volume'] = (
                    float(current_vol_val if pd.notna(current_vol_val) else 0)
                    + current_volume
                )

            # Actualizar hlc3 (usado en Fibonacci BB)
            df.at[last_idx, 'hlc3'] = (
                float(df.at[last_idx, 'high'])  +
                float(df.at[last_idx, 'low'])   +
                float(df.at[last_idx, 'close'])
            ) / 3

            MEMORY_STORE[symbol][tf]['df'] = df

        except Exception as e:
            # No interrumpir el ciclo si falla un timeframe específico
            log_warning('MEMORY_STORE', f'update_current_candle_close {symbol}/{tf}: {e}')
