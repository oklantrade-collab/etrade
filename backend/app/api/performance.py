from fastapi import APIRouter, Query
from app.core.supabase_client import get_supabase
from datetime import datetime, timezone, timedelta
from typing import Optional, List

router = APIRouter()

@router.get("/by-rule")
async def get_performance_by_rule(
    symbol: Optional[str] = None,
    mode: Optional[str] = None,
    days: Optional[int] = Query(None, description="Ultimos N dias")
):
    supabase = get_supabase()
    
    query = supabase.table('paper_trades').select('*')
    
    if symbol:
        query = query.eq('symbol', symbol)
    if mode:
        query = query.eq('mode', mode)
    if days:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query = query.gte('closed_at', since)
        
    result = query.execute()
    trades = result.data or []
    
    if not trades:
        return []
        
    # Agrupar por (rule_code, regime)
    groups = {}
    for t in trades:
        key = (t.get('rule_code', 'unknown'), t.get('regime', 'unknown'))
        if key not in groups:
            groups[key] = []
        groups[key].append(t)
        
    performance = []
    for (rule_code, regime), group_trades in groups.items():
        total_trades = len(group_trades)
        wins = [t for t in group_trades if float(t.get('total_pnl_usd') or 0) > 0]
        losses = [t for t in group_trades if float(t.get('total_pnl_usd') or 0) <= 0]
        
        win_count = len(wins)
        win_rate = win_count / total_trades if total_trades > 0 else 0
        
        avg_win_pct = sum(float(t.get('total_pnl_pct') or 0) for t in wins) / len(wins) if wins else 0
        avg_loss_pct = abs(sum(float(t.get('total_pnl_pct') or 0) for t in losses) / len(losses)) if losses else 0
        
        # ev = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)
        ev = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)
        
        total_pnl_usd = sum(float(t.get('total_pnl_usd') or 0) for t in group_trades)
        
        # ultimo_trade: MAX(closed_at)
        closed_dates = [t.get('closed_at') for t in group_trades if t.get('closed_at')]
        ultimo_trade = max(closed_dates) if closed_dates else None
        
        paper_trades_count = len([t for t in group_trades if t.get('mode') == 'paper'])
        backtest_trades_count = len([t for t in group_trades if t.get('mode') == 'backtest'])
        
        performance.append({
            "rule_code": rule_code,
            "regime": regime,
            "total_trades": total_trades,
            "wins": win_count,
            "win_rate_pct": round(win_rate * 100, 2),
            "avg_win_pct": round(avg_win_pct, 4),
            "avg_loss_pct": round(avg_loss_pct, 4),
            "ev": round(ev, 4),
            "total_pnl_usd": round(total_pnl_usd, 2),
            "ultimo_trade": ultimo_trade,
            "paper_trades": paper_trades_count,
            "backtest_trades": backtest_trades_count
        })
        
    return performance

@router.get("/ai-stats")
async def get_ai_stats():
    """
    Entregable 4 - Fase 2: Endpoint de estadísticas de IA
    """
    supabase = get_supabase()
    
    # Consulta paper_trades agrupando por ai_recommendation
    # SELECT
    #   ai_recommendation,
    #   COUNT(*)                                         AS total,
    #   SUM(CASE WHEN total_pnl_usd > 0 THEN 1 ELSE 0 END) AS acertos,
    #   ROUND(AVG(total_pnl_usd), 2)                    AS avg_pnl_usd,
    #   ROUND(SUM(total_pnl_usd), 2)                    AS total_pnl_usd
    # FROM paper_trades
    # WHERE ai_recommendation IS NOT NULL
    #   AND closed_at >= NOW() - INTERVAL '30 days'
    # GROUP BY ai_recommendation
    # ORDER BY ai_recommendation;
    
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    
    result = supabase.table('paper_trades') \
        .select('*') \
        .not_.is_('ai_recommendation', 'null') \
        .gte('closed_at', since) \
        .execute()
        
    trades = result.data or []
    
    if not trades:
        return []
        
    ai_groups = {}
    for t in trades:
        rec = t.get('ai_recommendation')
        if rec not in ai_groups:
            ai_groups[rec] = []
        ai_groups[rec].append(t)
        
    stats = []
    for rec, group_trades in ai_groups.items():
        total = len(group_trades)
        acertos = len([t for t in group_trades if float(t.get('total_pnl_usd') or 0) > 0])
        total_pnl_usd = sum(float(t.get('total_pnl_usd') or 0) for t in group_trades)
        avg_pnl_usd = total_pnl_usd / total if total > 0 else 0
        
        stats.append({
            "ai_recommendation": rec,
            "total": total,
            "acertos": acertos,
            "avg_pnl_usd": round(avg_pnl_usd, 2),
            "total_pnl_usd": round(total_pnl_usd, 2)
        })
        
    # Ordenar por ai_recommendation
    stats.sort(key=lambda x: x['ai_recommendation'])
    
    return stats

@router.get("/real-mode-readiness")
async def get_real_mode_readiness():
    """
    Entregable 2 - Fase 3: Endpoint de readiness
    """
    from app.core.readiness import check_real_mode_readiness
    supabase = get_supabase()
    result = await check_real_mode_readiness(supabase)
    return result
