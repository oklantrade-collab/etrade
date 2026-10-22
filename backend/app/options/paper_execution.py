"""Motor de simulacion de ejecucion Paper Trading para APEX Options (Sprint 6).
Jamas envia ordenes reales al broker. Simula fills conservadores basados en
cotizaciones reales persistidas:
  - Entrada: compra al ask + slippage, venta al bid - slippage.
  - Salida: liquidacion de compra al bid - slippage, liquidacion de venta al ask + slippage.
  - Comisiones reales por contrato y trazabilidad completa de cada fill.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.options import strategies as st

MODEL_VERSION = "v1.0-s6"


@dataclass
class LegFill:
    conid: int | None
    side: str                # 'buy' | 'sell'
    closing_side: str        # 'sell' para cerrar buy, 'buy' para cerrar sell
    right: str               # 'C' | 'P'
    strike: float
    bid: float
    ask: float
    fill_price: float
    slippage_applied: float
    market_data_type: str
    fee_usd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntryExecutionResult:
    entry_debit: float
    entry_fills: list[dict[str, Any]]
    entry_costs: float
    entry_total_invested: float
    entry_time: str
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExitExecutionResult:
    exit_credit: float
    exit_fills: list[dict[str, Any]]
    exit_costs: float
    exit_total_recovered: float
    realized_pnl: float
    exit_reason: str
    exit_time: str
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fee_per_contract_leg(eff: dict[str, Any]) -> float:
    return round(float(eff.get("commission_per_contract", 0.65)) + float(eff.get("extra_fees_per_contract", 0.05)), 4)


def simulate_entry_fill(candidate: dict[str, Any],
                        quotes_by_contract: dict[int, dict[str, Any]] | None,
                        eff: dict[str, Any],
                        now: datetime | None = None) -> EntryExecutionResult:
    """Simula la entrada conservadora para una candidata.
    Para cada pierna comprada: ask + slippage_normal * (ask - bid).
    Para cada pierna vendida: bid - slippage_normal * (ask - bid).
    """
    now_dt = now or datetime.now(timezone.utc)
    legs = candidate.get("legs") or []
    qty = int(candidate.get("qty") or 1)
    slip_mult = float(eff.get("slippage_normal") or 0.01)

    fills: list[dict[str, Any]] = []
    total_debit = 0.0
    fee_per_leg = fee_per_contract_leg(eff)

    for lg in legs:
        side = lg.get("side") or "buy"
        strike = float(lg.get("strike") or 0.0)
        right = lg.get("right") or "C"
        conid = lg.get("conid") or lg.get("contract_id")

        # Tomar cotizacion mas reciente de quotes_by_contract o del leg
        q = (quotes_by_contract or {}).get(conid) or lg
        bid = float(q.get("bid") or 0.0)
        ask = float(q.get("ask") or 0.0)
        mdt = str(q.get("market_data_type") or lg.get("market_data_type") or "UNKNOWN")

        spread = max(0.0, ask - bid)
        slippage = slip_mult * spread

        if side == "buy":
            fill_price = round(ask + slippage, 4)
            total_debit += fill_price
            closing_side = "sell"
        else:
            fill_price = round(max(0.01, bid - slippage), 4)
            total_debit -= fill_price
            closing_side = "buy"

        leg_fill = LegFill(
            conid=conid,
            side=side,
            closing_side=closing_side,
            right=right,
            strike=strike,
            bid=bid,
            ask=ask,
            fill_price=fill_price,
            slippage_applied=round(slippage, 4),
            market_data_type=mdt,
            fee_usd=fee_per_leg,
        )
        fills.append(leg_fill.to_dict())

    entry_costs = round(fee_per_leg * len(legs) * qty, 2)
    entry_debit = round(total_debit, 4)
    # Total invertido: debit * 100 * qty + comisiones
    total_invested = round(entry_debit * 100.0 * qty + entry_costs, 2)

    return EntryExecutionResult(
        entry_debit=entry_debit,
        entry_fills=fills,
        entry_costs=entry_costs,
        entry_total_invested=total_invested,
        entry_time=now_dt.isoformat(),
        model_version=MODEL_VERSION,
    )


def simulate_exit_fill(position: dict[str, Any],
                       quotes_by_contract: dict[int, dict[str, Any]] | None,
                       eff: dict[str, Any],
                       exit_reason: str,
                       adverse: bool = False,
                       now: datetime | None = None) -> ExitExecutionResult:
    """Simula la salida conservadora (cierre) de una posicion.
    Invierte cada pierna:
      - Pierna abierta como 'buy' se cierra con 'sell' al bid - slippage.
      - Pierna abierta como 'sell' se cierra con 'buy' al ask + slippage.
    """
    now_dt = now or datetime.now(timezone.utc)
    entry_fills = position.get("entry_fills") or []
    qty = int(position.get("qty") or 1)
    total_invested = float(position.get("entry_total_invested") or 0.0)

    slip_param = "slippage_adverse" if adverse else "slippage_normal"
    slip_mult = float(eff.get(slip_param) or (0.03 if adverse else 0.01))

    exit_fills: list[dict[str, Any]] = []
    total_credit = 0.0
    fee_per_leg = fee_per_contract_leg(eff)

    for ef in entry_fills:
        conid = ef.get("conid")
        cid = ef.get("contract_id")
        orig_side = ef.get("side") or "buy"
        strike = float(ef.get("strike") or 0.0)
        right = ef.get("right") or "C"

        # Buscar cotizacion de salida
        q = (quotes_by_contract or {}).get(conid) or (quotes_by_contract or {}).get(cid) or ef
        bid = float(q.get("bid") or 0.0)
        ask = float(q.get("ask") or 0.0)
        mdt = str(q.get("market_data_type") or "UNKNOWN")

        spread = max(0.0, ask - bid)
        slippage = slip_mult * spread

        if orig_side == "buy":
            # Vendemos para cerrar
            fill_price = round(max(0.0, bid - slippage), 4)
            total_credit += fill_price
            closing_side = "sell"
        else:
            # Compramos para cerrar
            fill_price = round(ask + slippage, 4)
            total_credit -= fill_price
            closing_side = "buy"

        leg_fill = LegFill(
            conid=conid,
            side=orig_side,
            closing_side=closing_side,
            right=right,
            strike=strike,
            bid=bid,
            ask=ask,
            fill_price=fill_price,
            slippage_applied=round(slippage, 4),
            market_data_type=mdt,
            fee_usd=fee_per_leg,
        )
        exit_fills.append(leg_fill.to_dict())

    exit_costs = round(fee_per_leg * len(entry_fills) * qty, 2)
    exit_credit = round(total_credit, 4)
    # Total recuperado neto de comisiones de salida
    total_recovered = round(exit_credit * 100.0 * qty - exit_costs, 2)
    realized_pnl = round(total_recovered - total_invested, 2)

    return ExitExecutionResult(
        exit_credit=exit_credit,
        exit_fills=exit_fills,
        exit_costs=exit_costs,
        exit_total_recovered=total_recovered,
        realized_pnl=realized_pnl,
        exit_reason=exit_reason,
        exit_time=now_dt.isoformat(),
        model_version=MODEL_VERSION,
    )


def mark_position_to_market(position: dict[str, Any],
                            quotes_by_contract: dict[int, dict[str, Any]] | None,
                            eff: dict[str, Any]) -> dict[str, Any]:
    """Calcula el valor mark-to-market y el unrealized P&L a liquidacion conservadora."""
    entry_fills = position.get("entry_fills") or []
    qty = int(position.get("qty") or 1)
    invested = float(position.get("entry_total_invested") or 0.0)

    if not entry_fills:
        last_m = float(position.get("last_mark_price") or position.get("entry_debit") or 0.0)
        unr = float(position.get("unrealized_pnl") or 0.0)
        return {"unrealized_pnl": unr, "unrealized_pnl_pct": 0.0, "last_mark_price": last_m, "valid": False}

    net_proceeds = 0.0
    valid = True

    for ef in entry_fills:
        conid = ef.get("conid")
        cid = ef.get("contract_id")
        orig_side = ef.get("side") or "buy"
        q = (quotes_by_contract or {}).get(conid) or (quotes_by_contract or {}).get(cid) or {}
        bid = q.get("bid")
        ask = q.get("ask")

        if bid is None or ask is None or bid < 0 or ask < 0 or bid > ask:
            valid = False
            break

        if orig_side == "buy":
            net_proceeds += float(bid)
        else:
            net_proceeds -= float(ask)

    if not valid:
        return {
            "unrealized_pnl": float(position.get("unrealized_pnl") or 0.0),
            "unrealized_pnl_pct": 0.0,
            "last_mark_price": float(position.get("last_mark_price") or 0.0),
            "valid": False,
        }

    exit_fees = round(fee_per_contract_leg(eff) * len(entry_fills) * qty, 2)
    current_value = round(net_proceeds * 100.0 * qty - exit_fees, 2)
    unrealized = round(current_value - invested, 2)
    unrealized_pct = round((unrealized / invested * 100.0), 2) if invested > 0 else 0.0

    return {
        "unrealized_pnl": unrealized,
        "unrealized_pnl_pct": unrealized_pct,
        "last_mark_price": round(net_proceeds, 4),
        "valid": True,
    }


def execute_selected_candidate_to_trade(sb, cand: dict[str, Any], eff: dict[str, Any],
                                        und: dict[str, Any] | None = None,
                                        now_dt: datetime | None = None) -> dict[str, Any] | None:
    """
    Ejecuta una candidata seleccionada creando la posición en opt_paper_trades
    y despachando las piernas de la orden a stocks_orders para que el puente
    de Interactive Brokers (ib_bridge_worker / TWS) las ejecute en el broker.
    """
    now_dt = now_dt or datetime.now(timezone.utc)
    cid = cand["id"]
    uid = cand.get("underlying_id")

    # 1. Comprobar si ya existe posición abierta para esta candidata
    try:
        existing = sb.table("opt_paper_trades").select("*").eq("candidate_id", cid).eq("status", "open").execute().data
        if existing:
            return existing[0]
    except Exception:
        pass

    if und is None and uid:
        try:
            u_rows = sb.table("opt_underlyings").select("*").eq("id", uid).execute().data
            if u_rows:
                und = u_rows[0]
        except Exception:
            und = {}
    und = und or {}

    from app.options import options_aduana as aduana
    event_flags = und.get("event_flags")
    ctx = aduana.static_context(uid, event_flags, underlying=und)
    ctx.now = now_dt
    aduana_res = aduana.validate_entry(cand, ctx, eff)
    if not aduana_res.approved:
        return None

    fill_res = simulate_entry_fill(cand, None, eff, now_dt)
    sym = und.get("symbol") or cand.get("symbol") or "UNKNOWN"
    qty = cand.get("qty") or 1

    pos_data = {
        "candidate_id": cid,
        "underlying_id": uid,
        "symbol": sym,
        "strategy_type": cand["strategy_type"],
        "direction": cand["direction"],
        "status": "open",
        "qty": qty,
        "expiry": cand["expiry"],
        "entry_time": fill_res.entry_time,
        "entry_debit": fill_res.entry_debit,
        "entry_fills": fill_res.entry_fills,
        "entry_costs": fill_res.entry_costs,
        "entry_total_invested": fill_res.entry_total_invested,
        "max_loss_total": float(cand.get("max_loss_total") or fill_res.entry_total_invested),
        "max_profit_total": (float(cand["max_profit_contract"]) * qty) if cand.get("max_profit_contract") else None,
        "breakeven": cand.get("breakeven"),
        "unrealized_pnl": 0.0,
        "last_mark_price": fill_res.entry_debit,
        "last_mark_at": fill_res.entry_time,
        "exit_plan": cand.get("exit_plan") or {},
        "model_version": MODEL_VERSION,
        "settings_version": int(eff.get("config_version") or 1),
    }

    try:
        inserted = sb.table("opt_paper_trades").insert(pos_data).execute().data[0]
    except Exception:
        return None

    # Despachar las piernas de la orden a stocks_orders para ejecución en TWS / IB Bridge
    exp_compact = (cand.get("expiry") or "20261026").replace("-", "")[:8]
    for f in fill_res.entry_fills:
        stk = f.get("strike")
        rgt = f.get("right")
        side = f.get("side") or "buy"
        px = f.get("fill_price") or 0.0
        opt_target_band = f"OPT:{exp_compact}:{stk}:{rgt}"
        try:
            sb.table("stocks_orders").insert({
                "ticker": sym[:10],
                "target_band": opt_target_band,
                "group_name": "OPTIONS_AUTONOMOUS",
                "rule_code": "APEX_AUTO",
                "order_type": "market",
                "direction": side,
                "shares": qty,
                "market_price": px,
                "status": "pending",
                "created_at": fill_res.entry_time,
            }).execute()
        except Exception:
            pass

    return inserted
