from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
from app.core.supabase_client import get_supabase
from app.backtesting import backtest_engine

router = APIRouter()

class BacktestParams(BaseModel):
    symbol: str = 'BTC/USDT'
    start_date: str = '2024-01-01'
    end_date: str   = '2024-12-31'
    initial_capital: float = 10000.0
    spike_multiplier: float = 2.5
    mtf_signal_threshold: float = 0.65
    sl_multiplier: float = 2.0
    rr_ratio: float = 2.5
    risk_pct: float = 0.01

@router.get("")
async def list_backtests():
    supabase = get_supabase()
    result = supabase.table('backtest_runs') \
        .select('id, strategy_name, symbol, start_date, end_date, initial_capital, final_capital, total_return_pct, win_rate, profit_factor, sharpe_ratio, max_drawdown_pct, total_trades, status, created_at') \
        .order('created_at', desc=True) \
        .limit(20) \
        .execute()
    return result.data

@router.post("/run")
async def run_backtest(params: BacktestParams, background_tasks: BackgroundTasks):
    supabase = get_supabase()
    run_id = str(uuid.uuid4())
    
    # Crear registro inmediato en BD
    supabase.table('backtest_runs').insert({
        'id': run_id,
        'strategy_name': 'VolumeSpike_MTF_v1',
        'symbol': params.symbol,
        'start_date': params.start_date,
        'end_date': params.end_date,
        'initial_capital': params.initial_capital,
        'params_used': params.model_dump(),
        'status': 'running'
    }).execute()
    
    # Ejecutar en background (no bloquear la respuesta HTTP)
    background_tasks.add_task(
        backtest_engine.run_backtest,
        params.model_dump(),
        supabase,
        run_id
    )
    
    return {
        'run_id': run_id,
        'status': 'running',
        'message': 'Backtest iniciado en background'
    }

@router.delete("/{run_id}")
async def delete_backtest(run_id: str):
    supabase = get_supabase()
    supabase.table('backtest_runs').delete().eq('id', run_id).execute()
    return {"message": "Backtest eliminado"}


import pandas as pd
from typing import Optional

@router.get("/performance")
async def get_backtest_performance(
    symbol: Optional[str] = None,
    regime: Optional[str] = None,
    mode: str = "backtest"
):
    """
    Calcula métricas de performance agrupadas por regla y régimen.
    Ajuste 1: Fórmula EV = (win_rate * avg_win_pct) - (1 - win_rate)
    """
    try:
        supabase = get_supabase()
        query = supabase.table('paper_trades').select('*').eq('mode', mode)

        if symbol:
            query = query.eq('symbol', symbol)
        if regime:
            query = query.eq('regime', regime)

        result = query.execute()
        df = pd.DataFrame(result.data)

        if df.empty:
            return {"summary": {}, "rules": []}

        # Conversión numérica de columnas clave
        for col in ['total_pnl_usd', 'total_pnl_pct', 'adx_value']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Agrupación por Regla y Régimen
        group_cols = ['rule_code', 'regime']
        
        def agg_rules(x):
            trades = len(x)
            wins_mask = x['total_pnl_usd'] > 0
            wins = len(x[wins_mask])
            wr = wins / trades
            
            pos = x[wins_mask]['total_pnl_pct']
            avg_win_pct = pos.mean() if not pos.empty else 0
            
            neg = x[~wins_mask]['total_pnl_pct']
            avg_loss_pct = abs(neg.mean()) if not neg.empty else 0
            
            # Fórmula EV corregida: (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)
            ev = (wr * avg_win_pct) - ((1 - wr) * avg_loss_pct)
            
            return pd.Series({
                'trades': trades,
                'wins': wins,
                'win_rate': round(wr * 100, 2),
                'avg_win_pct': round(avg_win_pct, 4),
                'avg_loss_pct': round(avg_loss_pct, 4),
                'expected_value': round(ev, 4),
                'avg_adx': round(x['adx_value'].mean(), 2)
            })

        rules_perf = df.groupby(group_cols).apply(agg_rules).reset_index()
        rules_perf = rules_perf.sort_values('expected_value', ascending=False)

        # Resumen global simplificado
        total_trades = len(df)
        global_wins = len(df[df['total_pnl_usd'] > 0])
        
        summary = {
            "total_trades": total_trades,
            "win_rate": round((global_wins / total_trades) * 100, 2) if total_trades > 0 else 0,
            "avg_ev": round(rules_perf['expected_value'].mean(), 4) if not rules_perf.empty else 0,
            "profitable_rules": len(rules_perf[rules_perf['expected_value'] > 0])
        }

        return {
            "summary": summary,
            "rules": rules_perf.to_dict(orient='records')
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
