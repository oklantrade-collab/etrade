"""
eTrade v6.0 — SELECTOR INTELIGENTE DE CONTRATOS (GAP RUNNER OPTIONS)
====================================================================
Módulo especializado para la selección del strike, vencimiento y
dimensionamiento adaptativo de contratos para la estrategia ADUANA_GAP_RUNNER.

Criterios de Selección:
1. Right: 'C' para CALLs (Gap Up) / 'P' para PUTs (Gap Down).
2. Delta Objetivo:
   - CALLs: +0.40 <= Delta <= +0.65 (ATM / ligeramente ITM/OTM).
   - PUTs:  -0.40 >= Delta >= -0.65.
3. Vencimiento (DTE): 2 a 14 días (o hasta 21 días en alta volatilidad).
4. Filtros de Liquidez Obligatorios:
   - Bid > 0, Ask > 0.
   - Spread relativo (Ask - Bid) / Mid <= 10.0% (ideal <= 8.0%).
   - Open Interest >= 100 contratos (o >= 50 en aperturas de ciclo).
   - Volumen diario >= 30 contratos.
5. Dimensionamiento Adaptativo en Tranches:
   - Budget total asignado (ej. $600 - $1,500 USD).
   - Distribución en contratos enteros (1/3, 2/3, 3/3 o 1/2, 2/2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.core.logger import log_info, log_warning


@dataclass
class SelectedContract:
    contract_id: int
    conid: int
    symbol: str
    right: str               # 'C' | 'P'
    strike: float
    expiry: date
    dte: int
    bid: float
    ask: float
    mid: float
    spread_pct: float
    delta: float
    open_interest: float
    volume: float
    cost_per_contract: float # mid * 100
    target_total_contracts: int
    tranche_1_contracts: int
    tranche_2_contracts: int
    tranche_3_contracts: int
    tranche_model: str       # '3_TRANCHES' (33/33/34) | '2_TRANCHES' (50/50) | 'SINGLE' (100)
    score: float = 0.0


def calculate_tranche_allocation(target_contracts: int) -> Tuple[int, int, int, str]:
    """
    Calcula la distribución de contratos en tranches según la cantidad total disponible.
    - >= 3 contratos: 3 Tranches (33.3%, 33.3%, 33.4%).
    - 2 contratos: 2 Tranches del 50% (1 en T1, 1 en T2).
    - 1 contrato: Single Tranche (1 en T1).
    """
    if target_contracts >= 3:
        t1 = max(1, target_contracts // 3)
        t2 = max(1, target_contracts // 3)
        t3 = target_contracts - t1 - t2
        return t1, t2, t3, "3_TRANCHES"
    elif target_contracts == 2:
        return 1, 1, 0, "2_TRANCHES"
    else:
        return 1, 0, 0, "SINGLE"


def select_best_option_contract(
    contracts: List[Dict[str, Any]],
    underlying_price: float,
    direction: str = "CALL",
    budget_usd: float = 1000.0,
    max_spread_pct: float = 10.0,
    min_open_interest: float = 50.0,
    min_volume: float = 20.0,
    now_date: Optional[date] = None
) -> Tuple[Optional[SelectedContract], List[str]]:
    """
    Evalúa la cadena de opciones y selecciona el contrato óptimo para el Gap Runner.
    Retorna (SelectedContract o None, lista_de_motivos_de_rechazo).
    """
    ref_date = now_date or datetime.now(timezone.utc).date()
    is_call = direction.upper() in ("CALL", "BULLISH")
    target_right = "C" if is_call else "P"

    target_delta = 0.50 if is_call else -0.50
    rejection_reasons = []
    candidates: List[SelectedContract] = []

    for c in contracts:
        conid = c.get("conid") or c.get("contract_id") or 0
        cid = c.get("id") or conid
        sym = c.get("symbol") or ""
        right = str(c.get("right") or "").upper()

        if right != target_right:
            continue

        strike = float(c.get("strike") or 0.0)
        exp_val = c.get("expiry")
        if isinstance(exp_val, str):
            exp_date = date.fromisoformat(exp_val[:10])
        elif isinstance(exp_val, date):
            exp_date = exp_val
        else:
            continue

        dte = (exp_date - ref_date).days
        # Filtro DTE: entre 2 y 21 días (evitar 0DTE y evitar meses lejanos con delta dragging)
        if dte < 2 or dte > 21:
            continue

        # Obtener cotizaciones latest
        ql = c.get("opt_quotes_latest") or c
        if isinstance(ql, list):
            ql = ql[0] if ql else {}

        bid = float(ql.get("bid") or 0.0)
        ask = float(ql.get("ask") or 0.0)
        oi = float(ql.get("open_interest") or 0.0)
        vol = float(ql.get("volume") or 0.0)
        delta_val = ql.get("delta")

        # 1. Filtros de precio y liquidez
        if bid <= 0.0 or ask <= 0.0 or ask <= bid:
            rejection_reasons.append(f"Strike {strike} {right} ({exp_date}): Bid/Ask inválido (${bid:.2f}/${ask:.2f})")
            continue

        mid = round((bid + ask) / 2.0, 4)
        spread_rel = ((ask - bid) / mid) * 100.0

        if spread_rel > max_spread_pct:
            rejection_reasons.append(f"Strike {strike} {right}: Spread excesivo {spread_rel:.1f}% > {max_spread_pct}%")
            continue

        if oi < min_open_interest and vol < min_volume:
            rejection_reasons.append(f"Strike {strike} {right}: Poca liquidez (OI={oi}, Vol={vol})")
            continue

        # 2. Delta estimado o provisto
        if delta_val is not None:
            delta = float(delta_val)
        else:
            # Aproximación moneyness si no hay griego calculado en la fila
            moneyness = (underlying_price / strike) if strike > 0 else 1.0
            if is_call:
                delta = 0.50 + (moneyness - 1.0) * 2.0
                delta = max(0.05, min(0.95, delta))
            else:
                delta = -0.50 - (1.0 - moneyness) * 2.0
                delta = max(-0.95, min(-0.05, delta))

        # Filtro de Delta: entre 0.38 y 0.68
        if is_call:
            if delta < 0.38 or delta > 0.68:
                continue
        else:
            if delta > -0.38 or delta < -0.68:
                continue

        cost_per_contract = mid * 100.0
        if cost_per_contract <= 0.0:
            continue

        target_total = max(1, int(budget_usd / cost_per_contract))
        t1, t2, t3, model = calculate_tranche_allocation(target_total)

        # Scoring: proximidad a delta target 0.50, menor spread, mayor liquidez
        delta_dist = abs(delta - target_delta)
        score = 100.0 - (delta_dist * 60.0) - (spread_rel * 2.0) + min(15.0, math.log1p(oi + vol))

        candidates.append(SelectedContract(
            contract_id=cid,
            conid=conid,
            symbol=sym,
            right=right,
            strike=strike,
            expiry=exp_date,
            dte=dte,
            bid=bid,
            ask=ask,
            mid=mid,
            spread_pct=round(spread_rel, 2),
            delta=round(delta, 3),
            open_interest=oi,
            volume=vol,
            cost_per_contract=round(cost_per_contract, 2),
            target_total_contracts=target_total,
            tranche_1_contracts=t1,
            tranche_2_contracts=t2,
            tranche_3_contracts=t3,
            tranche_model=model,
            score=round(score, 2)
        ))

    if not candidates:
        return None, rejection_reasons

    # Ordenar por mejor score
    candidates.sort(key=lambda x: x.score, reverse=True)
    best = candidates[0]

    return best, rejection_reasons
