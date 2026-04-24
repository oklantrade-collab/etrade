"""
ANTIGRAVITY · Capital Manager v1.0
==================================
Maneja el interés compuesto y el profit acumulado por mercado.
"""

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error

MODULE = "CAPITAL_MANAGER"

def get_total_operating_capital(market: str) -> float:
    """
    Retorna el Capital Base + Ganancia Acumulada para un mercado.
    market: 'crypto', 'forex', 'stocks'
    """
    try:
        sb = get_supabase()
        res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
        cfg = res.data or {}

        if market == 'crypto':
            base = float(cfg.get('capital_crypto_futures') or 500)
            profit = float(cfg.get('accumulated_profit_crypto') or 0)
        elif market == 'forex':
            base = float(cfg.get('capital_forex_futures') or 1000)
            profit = float(cfg.get('accumulated_profit_forex') or 0)
        elif market == 'stocks':
            base = float(cfg.get('capital_stocks_spot') or 2000)
            profit = float(cfg.get('accumulated_profit_stocks') or 0)
        else:
            base = float(cfg.get('capital_total') or 500)
            profit = 0

        total = base + profit
        return max(total, 0.1) # Nunca retornar 0 para evitar divisiones
    except Exception as e:
        log_error(MODULE, f"Error obteniendo capital operativo para {market}: {e}")
        return 500.0 # Fallback seguro

def register_realized_pnl(market: str, pnl_usd: float):
    """
    Suma o resta el PnL de una posición cerrada al profit acumulado.
    """
    try:
        sb = get_supabase()
        
        # Mapeo de columnas
        col_map = {
            'crypto': 'accumulated_profit_crypto',
            'forex':  'accumulated_profit_forex',
            'stocks': 'accumulated_profit_stocks'
        }
        column = col_map.get(market.lower())
        if not column: return

        # Obtener valor actual
        res = sb.table('trading_config').select(column).eq('id', 1).maybe_single().execute()
        current_profit = float((res.data or {}).get(column) or 0)
        
        new_profit = current_profit + pnl_usd
        
        # Actualizar
        sb.table('trading_config').update({
            column: round(new_profit, 4)
        }).eq('id', 1).execute()
        
        log_info(MODULE, f"💰 CAPITAL UPDATE ({market}): Profit anterior ${current_profit:.2f} -> Nuevo ${new_profit:.2f} (PnL: ${pnl_usd:+.2f})")
        
    except Exception as e:
        log_error(MODULE, f"Error registrando PnL en capital acumulado ({market}): {e}")
