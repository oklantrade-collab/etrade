from datetime import datetime, timezone
import pandas as pd
from typing import List, Dict, Any

async def check_real_mode_readiness(sb) -> Dict[str, Any]:
    """
    Evaluates criteria for moving from paper trading to real mode.
    """
    # 1. Días de paper trading
    # MIN_DAYS = 14
    first_trade_res = sb.table('paper_trades') \
        .select('created_at') \
        .eq('mode', 'paper') \
        .order('created_at', desc=False) \
        .limit(1) \
        .execute()
    
    first_trade_date = None
    days_active = 0
    if first_trade_res.data:
        # Compatibility fix for different datetime formats
        dt_str = first_trade_res.data[0]['created_at']
        if 'Z' in dt_str:
            dt_str = dt_str.replace('Z', '+00:00')
        first_trade_date = datetime.fromisoformat(dt_str)
        days_active = (datetime.now(timezone.utc) - first_trade_date).days
        
    # 2. Total de trades
    # MIN_TRADES = 30
    all_paper_trades_res = sb.table('paper_trades') \
        .select('total_pnl_usd, total_pnl_pct, closed_at, created_at') \
        .eq('mode', 'paper') \
        .execute()
    
    trades = all_paper_trades_res.data or []
    total_trades = len(trades)
    
    # 3. Win rate global
    # MIN_WIN_RATE = 45.0 (%)
    wins = [t for t in trades if float(t.get('total_pnl_usd') or 0) > 0]
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    
    # 4. EV global
    # MIN_EV = 0.10
    losses = [t for t in trades if float(t.get('total_pnl_usd') or 0) <= 0]
    avg_win_pct = (sum(float(t.get('total_pnl_pct') or 0) for t in wins) / len(wins)) if wins else 0
    avg_loss_pct = abs(sum(float(t.get('total_pnl_pct') or 0) for t in losses) / len(losses)) if losses else 0
    win_rate_dec = win_rate / 100
    ev = (win_rate_dec * avg_win_pct) - ((1 - win_rate_dec) * avg_loss_pct)
    
    # 5. Sin pérdidas consecutivas excesivas
    # MAX_CONSECUTIVE_LOSSES = 4
    trades_sorted = sorted(trades, key=lambda x: x.get('closed_at') or x.get('created_at') or '')
    current_consecutive_losses = 0
    max_consecutive_losses = 0
    for t in trades_sorted:
        if float(t.get('total_pnl_usd') or 0) <= 0:
            current_consecutive_losses += 1
            if current_consecutive_losses > max_consecutive_losses:
                max_consecutive_losses = current_consecutive_losses
        else:
            current_consecutive_losses = 0
            
    # 6. Drawdown máximo
    # MAX_DRAWDOWN = 8.0 (%)
    equity = 100.0
    equity_curve = [equity]
    for t in trades_sorted:
        equity += float(t.get('total_pnl_pct') or 0)
        equity_curve.append(equity)
    
    df_equity = pd.Series(equity_curve)
    max_dd = 0
    if not df_equity.empty and len(df_equity) > 1:
        roll_max = df_equity.cummax()
        # Ensure roll_max is not zero to avoid division by zero
        drawdown_pct = ((df_equity - roll_max) / roll_max.replace(0, 1)) * 100
        max_dd = abs(drawdown_pct.min())

    criteria = {
        'days_ok':              {'met': bool(days_active >= 14), 'value': int(days_active), 'required': 14},
        'trades_ok':            {'met': bool(total_trades >= 30), 'value': int(total_trades), 'required': 30},
        'win_rate_ok':          {'met': bool(win_rate >= 45.0), 'value': float(round(win_rate, 2)), 'required': 45.0},
        'ev_ok':                {'met': bool(ev >= 0.10), 'value': float(round(ev, 4)), 'required': 0.10},
        'no_excessive_losses':  {'met': bool(max_consecutive_losses <= 4), 'value': int(max_consecutive_losses), 'required': 4},
        'drawdown_ok':          {'met': bool(max_dd <= 8.0), 'value': float(round(max_dd, 2)), 'required': 8.0},
    }
    
    pending = [k for k, v in criteria.items() if not v['met']]
    all_criteria_met = bool(len(pending) == 0)
    
    return {
        'all_criteria_met': all_criteria_met,
        'criteria': criteria,
        'pending': pending,
        'evaluated_at': datetime.now(timezone.utc).isoformat()
    }
