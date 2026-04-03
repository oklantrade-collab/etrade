from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.supabase_client import get_supabase
from app.strategy.strategy_engine import StrategyEngine
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from pydantic import BaseModel
import pandas as pd

router = APIRouter()

class RuleCreate(BaseModel):
    name: str
    rule_code: str
    strategy_type: str
    direction: str
    cycle: str
    condition_ids: List[int]
    min_score: float
    weights: dict
    priority: int = 50
    enabled: bool = False

@router.get("/rules")
async def get_strategy_rules():
    """
    Lista de reglas activas con estadísticas de las últimas 24h.
    """
    sb = get_supabase()
    
    rules_res = sb.table('strategy_rules_v2').select('*').order('priority').execute()
    rules = rules_res.data or []
    
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    evals_res = sb.table('strategy_evaluations').select('rule_code, score, triggered').gte('created_at', yesterday).execute()
    evals = evals_res.data or []
    
    stats = {}
    for e in evals:
        rc = e['rule_code']
        if rc not in stats:
            stats[rc] = {'evaluaciones': 0, 'activaciones': 0, 'total_score': 0}
        stats[rc]['evaluaciones'] += 1
        if e['triggered']:
            stats[rc]['activaciones'] += 1
        stats[rc]['total_score'] += e['score']
    
    result = []
    for r in rules:
        rc = r['rule_code']
        r_stats = stats.get(rc, {'evaluaciones': 0, 'activaciones': 0, 'total_score': 0})
        
        avg_score = 0
        if r_stats['evaluaciones'] > 0:
            avg_score = round(float(r_stats['total_score'] / r_stats['evaluaciones']), 3)
            
        result.append({
            **r,
            'evaluaciones_24h': r_stats['evaluaciones'],
            'activaciones_24h': r_stats['activaciones'],
            'score_promedio_24h': avg_score
        })
        
    return result

@router.get("/reload")
async def reload_engine(sb = Depends(get_supabase)):
    """
    Forzar recarga global del motor de estrategias desde Supabase.
    """
    engine = StrategyEngine.get_instance(sb)
    await engine.reload()
    return {"success": True, "message": "Motor de estrategias recargado correctamente."}

@router.get("/live/{symbol}")
async def get_live_evaluation(
    symbol:    str,
    timeframe: str = Query('15m'),
    sb = Depends(get_supabase)
):
    """
    Evaluación exhaustiva desde Supabase (API no comparte MEMORY_STORE con el worker).
    """
    import traceback
    try:
        # ── 1. Obtener snapshot desde Supabase ──
        snap_res = sb.table('market_snapshot').select('*').eq('symbol', symbol).maybe_single().execute()
        if not snap_res.data:
            return {'error': f'Sin datos para {symbol}'}
        snap = snap_res.data

        # ── 2. Helper para obtener velas desde Supabase ──
        def get_candles_df(sym, tf, limit=100):
            res = sb.table('market_candles').select(
                'open_time,open,high,low,close,volume,basis,upper_1,upper_2,upper_3,upper_4,upper_5,upper_6,lower_1,lower_2,lower_3,lower_4,lower_5,lower_6,sar,sar_trend,pinescript_signal'
            ).eq('symbol', sym).eq('timeframe', tf).order('open_time', desc=True).limit(limit).execute()

            if not res.data:
                return pd.DataFrame()

            # Invertir para tener orden temporal ascendente para indicadores
            df = pd.DataFrame(res.data[::-1])
            df['open_time'] = pd.to_datetime(df['open_time'])
            df = df.set_index('open_time')

            numeric_cols = [
                'open','high','low','close','volume','basis','upper_1','upper_2',
                'upper_3','upper_4','upper_5','upper_6','lower_1','lower_2',
                'lower_3','lower_4','lower_5','lower_6','sar','sar_trend'
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df

        # Cargar datasets
        df_15m = get_candles_df(symbol, '15m', 150)
        df_4h  = get_candles_df(symbol, '4h',  80)
        df_5m  = get_candles_df(symbol, '5m',  50)

        # ── 3. Inicializar engine ──
        engine = StrategyEngine.get_instance(sb)
        if not engine.loaded:
            await engine.load()

        # ── 4. Construir contexto ──
        context = engine.build_context(
            snap   = snap,
            df_15m = df_15m if not df_15m.empty else None,
            df_4h  = df_4h  if not df_4h.empty else None,
            df_5m  = df_5m  if not df_5m.empty else None,
        )

        # ── 5. Evaluar todas las reglas (ignorar si están habilitadas) ──
        import math
        all_rules = []

        for code, rule in engine.rules.items():
            if rule.get('cycle') == timeframe:
                # 5.1 Evaluar la regla forzosamente
                res = engine.evaluate_rule(rule, context)
                
                # 5.2 INYECTAR METADATA CLAVE PARA LA UI
                res['strategy_type'] = rule.get('strategy_type')
                res['direction'] = rule.get('direction')

                # 5.3 Enriquecer condiciones con current_value y target_value
                for cid_str, cond_detail in res.get('conditions', {}).items():
                    cid = int(cid_str)
                    cond = engine.conditions.get(cid, {})
                    var = cond.get('variable') or {}
                    source = var.get('source_field', '')

                    cond_detail['source_field'] = source
                    val = context.get(source)
                    # Limpiar NaN o Infinity para no romper el JSON del frontend
                    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                        val = 0.0
                    cond_detail['current_value'] = val

                    # Valor objetivo (target)
                    val_lit = cond.get('value_literal')
                    val_var = cond.get('value_variable')
                    val_lst = cond.get('value_list', [])

                    if val_lit is not None:
                        cond_detail['target_value'] = float(val_lit)
                    elif val_var:
                        cond_detail['target_value'] = context.get(val_var)
                    elif val_lst:
                        cond_detail['target_value'] = ', '.join(str(x) for x in val_lst)
                    else:
                        cond_detail['target_value'] = None

                all_rules.append(res)

        # ── 6. Serialización segura del contexto ──
        # Convertir valores no serializables y limpiar NaNs 
        safe_context = {}
        for k, v in context.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                safe_context[k] = 0.0
            elif isinstance(v, (int, float, str, bool, type(None))):
                safe_context[k] = v
            else:
                safe_context[k] = str(v)

        return {
            'symbol':    symbol,
            'timeframe': timeframe,
            'context':   safe_context,
            'rules':     all_rules
        }

    except Exception as e:
        import traceback as tb
        error_detail = tb.format_exc()
        print(f"[STRATEGIES API ERROR] {error_detail}")
        return {
            'error':     'CRASH_DETECTED',
            'message':   str(e),
            'traceback': error_detail
        }

@router.post("/rules")
async def create_strategy_rule(rule: RuleCreate):
    """
    Crea una nueva regla en Supabase.
    """
    sb = get_supabase()
    data = rule.dict()
    res = sb.table('strategy_rules_v2').insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to create rule")
    return res.data[0]

@router.put("/rules/{rule_code}")
async def update_rule(
    rule_code: str,
    payload:   dict,
):
    """
    Actualiza una regla existente.
    """
    sb = get_supabase()
    allowed_fields = {
        'name', 'condition_ids',
        'condition_weights', 'min_score',
        'enabled', 'priority', 'notes',
        'market_types', 'confidence'
    }
    update_data = {
        k: v for k, v in payload.items()
        if k in allowed_fields
    }
    update_data['updated_at'] = \
        datetime.now(timezone.utc).isoformat()

    result = sb\
        .table('strategy_rules_v2')\
        .update(update_data)\
        .eq('rule_code', rule_code)\
        .execute()

    # Recargar el engine en memoria
    engine = StrategyEngine.get_instance(sb)
    await engine.reload()

    return {
        'success': True,
        'rule_code': rule_code,
        'updated': update_data
    }

@router.get("/rules/{rule_code}")
async def get_rule_detail(
    rule_code: str
):
    """
    Retorna el detalle completo de una regla
    incluyendo todas sus condiciones y pesos.
    """
    sb = get_supabase()
    rule = sb\
        .table('strategy_rules_v2')\
        .select('*')\
        .eq('rule_code', rule_code)\
        .single()\
        .execute()

    # Agregar detalle de condiciones
    if rule.data:
        cond_ids = rule.data.get(
            'condition_ids', []
        )
        conditions = sb\
            .table('strategy_conditions')\
            .select(
                '*, variable:strategy_variables(*)'
            )\
            .in_('id', cond_ids)\
            .execute()
        rule.data['conditions_detail'] = \
            conditions.data

    return rule.data

@router.get("/conditions")
async def get_strategy_conditions():
    """
    Lista de todas las condiciones disponibles.
    """
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').eq('enabled', True).execute()
    return res.data
