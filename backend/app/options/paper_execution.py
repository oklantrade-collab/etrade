"""Motor de simulacion de ejecucion Paper Trading para APEX Options (Sprint 6).
Jamas envia ordenes reales al broker. Simula fills conservadores basados en
cotizaciones reales persistidas:
  - Entrada: compra al ask + slippage, venta al bid - slippage.
  - Salida: liquidacion de compra al bid - slippage, liquidacion de venta al ask + slippage.
  - Comisiones reales por contrato y trazabilidad completa de cada fill.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logger import log_info, log_warning
from app.core.market_hours import is_market_open
from app.core.time_utils import parse_iso_utc
from app.options import strategies as st

MODULE = "PAPER_EXECUTION"
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
            # Ejecución dirigida al Midpoint para no pagar el spread completo ni nacer en pérdida contable
            if bid > 0 and ask > 0:
                midpoint = round((bid + ask) / 2.0, 4)
                fill_price = round(midpoint + (slippage * 0.5), 4)
            else:
                fill_price = round(ask + slippage, 4)
            total_debit += fill_price
            closing_side = "sell"
        else:
            if bid > 0 and ask > 0:
                midpoint = round((bid + ask) / 2.0, 4)
                fill_price = round(max(0.01, midpoint - (slippage * 0.5)), 4)
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
                       now: datetime | None = None,
                       qty_override: int | None = None) -> ExitExecutionResult:
    """Simula la salida conservadora (cierre total o parcial) de una posicion.
    Invierte cada pierna:
      - Pierna abierta como 'buy' se cierra con 'sell' al bid - slippage.
      - Pierna abierta como 'sell' se cierra con 'buy' al ask + slippage.
    """
    now_dt = now or datetime.now(timezone.utc)
    entry_fills = position.get("entry_fills") or []
    pos_qty = int(position.get("qty") or 1)
    qty = qty_override if qty_override is not None else pos_qty
    total_invested_full = float(position.get("entry_total_invested") or 0.0)
    invested_portion = round(total_invested_full * (qty / max(1, pos_qty)), 2)

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
    realized_pnl = round(total_recovered - invested_portion, 2)

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

        # Valuación a precio justo Mid-Market (si use_mid_pricing está activo) o liquidación conservadora
        f_bid = float(bid)
        f_ask = float(ask)
        use_mid = bool(eff.get("use_mid_pricing", False))

        if use_mid and f_bid > 0 and f_ask > 0:
            leg_price = round((f_bid + f_ask) / 2.0, 4)
            net_proceeds += leg_price if orig_side == "buy" else -leg_price
        else:
            if orig_side == "buy":
                net_proceeds += f_bid
            else:
                net_proceeds -= f_ask

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


def _is_ib_bridge_alive_sb(sb, max_age_sec: float = 180.0) -> bool:
    """Comprueba usando el cliente Supabase dado si el bridge APOLO está activo."""
    try:
        res = sb.table("stocks_config").select("value").eq("key", "ib_bridge_heartbeat").limit(1).execute()
        rows = getattr(res, "data", None)
        if not isinstance(rows, list) or not rows:
            return False
        val = rows[0].get("value") if isinstance(rows[0], dict) else None
        if not isinstance(val, str) or not val:
            return False
        import ast, json
        try:
            data = json.loads(val)
        except Exception:
            data = ast.literal_eval(val)
        if not isinstance(data, dict) or not data.get("connected"):
            return False
        ts_str = data.get("timestamp")
        if not ts_str:
            return False
        ts = parse_iso_utc(ts_str)
        if ts is None:
            return False
        return (datetime.now(timezone.utc) - ts).total_seconds() <= max_age_sec
    except Exception:
        return False


def execute_selected_candidate_to_trade(sb, cand: dict[str, Any], eff: dict[str, Any],
                                        und: dict[str, Any] | None = None,
                                        now_dt: datetime | None = None) -> dict[str, Any] | None:
    """
    Ejecuta una candidata seleccionada creando la posición en opt_paper_trades
    y despachando las piernas de la orden a stocks_orders para que el puente
    de Interactive Brokers (ib_bridge_worker / TWS) las ejecute en el broker.
    """
    from app.options.warrior_momentum_options import is_warrior_options_golden_window, MAX_CONTRACTS_PER_SYMBOL
    from app.options.settings_defaults import get_effective_max_risk_per_trade_usd
    from app.options.order_execution_plan import snap_option_tick

    now_dt = now_dt or datetime.now(timezone.utc)
    is_open = is_market_open()
    market_open = is_open[0] if isinstance(is_open, tuple) else bool(is_open)
    if not market_open:
        log_info(MODULE, f"Mercado cerrado. No se ejecutan nuevas posiciones de opciones para candidata {cand.get('id')}")
        return None

    # 0.A Ventana de Oro Única (09:35-11:30 ET)
    if eff.get("enforce_golden_window", True):
        in_win, win_msg = is_warrior_options_golden_window(now_dt)
        if not in_win:
            log_info(MODULE, f"⏸️ [PAPER EXEC BLOCKED] Fuera de Ventana de Oro 09:35-11:30 ET: {win_msg}")
            return None

    cid = cand["id"]
    uid = cand.get("underlying_id")
    sym_check = str((und or {}).get("symbol") or cand.get("symbol") or "").upper().strip()
    cand_dir_raw = str(cand.get("direction") or cand.get("strategy_type") or "").lower()
    opt_dir = "CALL" if ("call" in cand_dir_raw or cand_dir_raw == "bullish") else "PUT"

    # 0.B Disyuntor Diario Global & Cooldown
    try:
        from app.core.circuit_breaker import can_open_new_trade
        if sym_check:
            can_open, cb_reason = can_open_new_trade(sym_check, sb=sb)
            if not can_open:
                log_warning(MODULE, f"⛔ [PAPER EXEC] Compra bloqueada por Disyuntor para {sym_check}: {cb_reason}")
                return None
    except Exception:
        pass

    try:
        from app.options.exit_engine import is_ticker_in_options_cooldown
        if sym_check:
            in_cd, cd_msg = is_ticker_in_options_cooldown(sym_check, opt_dir)
            if in_cd:
                log_info(MODULE, f"⏸️ [PAPER EXEC] Ticker {sym_check} ({opt_dir}) en cooldown: {cd_msg}")
                return None
    except Exception:
        pass

    # 0.C Veto Macro Diario SPY/QQQ 1D para CALLs
    if opt_dir == "CALL":
        try:
            from app.core.structural_regime_engine import evaluate_macro_daily_bias
            macro_bias = evaluate_macro_daily_bias()
            if macro_bias.get("veto_calls"):
                log_warning(MODULE, f"⛔ [PAPER EXEC] CALL bloqueado para {sym_check}: {macro_bias.get('reason')}")
                return None
        except Exception:
            pass

    # 0.D Filtro Anti-Clímax RSI 1H al entrar (PUT <= 20 / CALL >= 80)
    rsi_1h_raw = (
        cand.get("rsi_1h")
        or (cand.get("metrics") or {}).get("rsi_1h")
        or (cand.get("exit_plan") or {}).get("rsi_1h")
        or (und or {}).get("rsi_1h")
    )
    if rsi_1h_raw is not None:
        try:
            rsi_1h_v = float(rsi_1h_raw)
            if opt_dir == "PUT" and rsi_1h_v <= 20.0:
                log_info(MODULE, f"⛔ [PAPER EXEC] PUT bloqueado por sobreventa extrema (RSI 1H={rsi_1h_v:.1f} <= 20)")
                return None
            if opt_dir == "CALL" and rsi_1h_v >= 80.0:
                log_info(MODULE, f"⛔ [PAPER EXEC] CALL bloqueado por sobrecompra extrema (RSI 1H={rsi_1h_v:.1f} >= 80)")
                return None
        except (TypeError, ValueError):
            pass

    # 0.E Rechazar candidatas obsoletas (de días anteriores) o con vencimiento 0DTE
    today_iso = now_dt.date().isoformat()
    cand_created = str(cand.get("created_at") or "")[:10]
    cand_expiry = str(cand.get("expiry") or "")[:10]
    if (cand_created and cand_created < today_iso) or (cand_expiry and cand_expiry <= today_iso):
        try:
            sb.table("opt_candidates").update({"eligibility_status": "rejected"}).eq("id", cid).execute()
        except Exception:
            pass
        return None

    # 1. Comprobar si ya existe posición abierta para esta candidata o subyacente en la misma dirección
    try:
        if sym_check:
            existing = sb.table("opt_paper_trades").select("*").eq("symbol", sym_check).eq("direction", cand.get("direction")).eq("status", "open").execute().data
            if existing:
                return existing[0]
            # Si ya se envió una orden hoy para este símbolo en los últimos 30 minutos, evitar bucle de órdenes repetidas
            recent_ord = sb.table("stocks_orders").select("id, created_at").eq("ticker", sym_check[:10]).eq("direction", "buy").order("created_at", desc=True).limit(1).execute().data
            if recent_ord and recent_ord[0].get("created_at"):
                o_dt = parse_iso_utc(recent_ord[0]["created_at"])
                if o_dt is not None and (now_dt - o_dt).total_seconds() < 1800.0:
                    return None
        existing_cand = sb.table("opt_paper_trades").select("*").eq("candidate_id", cid).eq("status", "open").execute().data
        if existing_cand:
            return existing_cand[0]
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

    # Cargar posiciones abiertas reales para evaluar límite de capital y cupo de contratos
    open_rows = []
    try:
        open_rows = sb.table("opt_paper_trades").select("*").eq("status", "open").execute().data or []
        if not isinstance(open_rows, list):
            open_rows = []
        current_open_risk = sum(float(p.get("max_loss_total") or p.get("entry_total_invested") or 0.0) for p in open_rows)
        max_capital = float(eff.get("max_open_risk_usd", 5000.0))
        cand_max_loss = float(cand.get("max_loss_total") or 0.0)
        if current_open_risk + cand_max_loss > max_capital:
            return None

        ctx.positions = [
            aduana.OpenPosition(
                underlying_id=p.get("underlying_id") or 0,
                max_loss_total=float(p.get("max_loss_total") or p.get("entry_total_invested") or 0.0),
                direction=p.get("direction", "bullish"),
                candidate_id=p.get("candidate_id")
            )
            for p in open_rows
        ]
    except Exception:
        open_rows = []

    aduana_res = aduana.validate_entry(cand, ctx, eff)
    if not aduana_res.approved:
        return None

    sym = str(und.get("symbol") or cand.get("symbol") or "UNKNOWN").upper()
    open_sym_qty = sum(int(p.get("qty") or 1) for p in open_rows if str(p.get("symbol") or "").upper() == sym)
    if open_sym_qty >= MAX_CONTRACTS_PER_SYMBOL:
        log_info(MODULE, f"⛔ [PAPER EXEC] Límite Anti-Stacking para {sym}: {open_sym_qty}/{MAX_CONTRACTS_PER_SYMBOL} contratos ya abiertos.")
        return None

    # Evaluar Structural Regime & ADUANA Gatekeeper si está habilitado
    if eff.get("enforce_options_gatekeeper", True):
        try:
            u_px = float(und.get("price") or cand.get("underlying_price") or 0.0)
            if u_px > 0:
                from app.core.structural_regime_engine import evaluate_structural_regime
                st_reg = evaluate_structural_regime(sym, u_px)
                if opt_dir == "CALL" and not st_reg.get("can_enter_call", True):
                    log_info(MODULE, f"⛔ [PAPER EXEC] {sym} CALL bloqueado por Régimen Estructural: {st_reg.get('call_veto_reason')}")
                    return None
                if opt_dir == "PUT" and not st_reg.get("can_enter_put", True):
                    log_info(MODULE, f"⛔ [PAPER EXEC] {sym} PUT bloqueado por Régimen Estructural: {st_reg.get('put_veto_reason')}")
                    return None
        except Exception:
            pass
        try:
            u_px = float(und.get("price") or cand.get("underlying_price") or 0.0)
            if u_px > 0:
                from app.options.aduana_gap_runner_options import fetch_and_evaluate_options_gatekeeper
                gate = fetch_and_evaluate_options_gatekeeper(sym, opt_dir, u_px)
                if not gate.get("approved", True):
                    log_info(MODULE, f"⛔ [PAPER EXEC] {sym} ({opt_dir}) bloqueado por ADUANA Gatekeeper: {gate.get('reason')}")
                    return None
        except Exception:
            pass

    fill_res = simulate_entry_fill(cand, None, eff, now_dt)

    # Tope estricto de Settings ("Riesgo máximo por operación" = $800) y MAX_CONTRACTS_PER_SYMBOL = 3
    max_risk_usd = get_effective_max_risk_per_trade_usd(sb, eff)
    qty = min(MAX_CONTRACTS_PER_SYMBOL - open_sym_qty, max(1, int(cand.get("qty") or 1)))
    unit_cost = float(fill_res.entry_debit or cand.get("entry_debit") or 0.0) * 100.0
    if unit_cost > max_risk_usd + 1e-9:
        log_warning(MODULE, f"⛔ [PAPER EXEC] {sym} rechazado: 1 contrato (${unit_cost:.2f}) excede Riesgo máximo por operación (${max_risk_usd:.2f}).")
        return None
    if unit_cost > 0 and (unit_cost * qty) > max_risk_usd + 1e-9:
        qty = max(1, min(qty, int(max_risk_usd // unit_cost)))
        cand_adj = dict(cand, qty=qty)
        fill_res = simulate_entry_fill(cand_adj, None, eff, now_dt)

    # Con puente IBKR activo: protocolo Broker-First estricto (despachar BUY a TWS y crear en opt_paper_trades tras fill)
    bridge_live = _is_ib_bridge_alive_sb(sb)
    inserted = None
    if not bridge_live:
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
    expires_iso = (now_dt + timedelta(seconds=90)).isoformat()
    for f in fill_res.entry_fills:
        stk = f.get("strike")
        rgt = f.get("right")
        side = f.get("side") or "buy"
        px = float(f.get("fill_price") or 0.0)
        lmt_px = snap_option_tick(px, mode="nearest") if px > 0 else 0.05
        opt_target_band = f"OPT:{exp_compact}:{stk}:{rgt}"
        try:
            sb.table("stocks_orders").insert({
                "ticker": sym[:10],
                "target_band": opt_target_band,
                "group_name": "OPTIONS_AUTONOMOUS",
                "rule_code": "APEX_AUTO",
                "order_type": "limit",
                "direction": side,
                "shares": qty,
                "market_price": px,
                "limit_price": lmt_px,
                "status": "pending",
                "expires_at": expires_iso,
                "created_at": fill_res.entry_time,
            }).execute()
        except Exception:
            pass

    if inserted is not None:
        return inserted

    return {
        "status": "order_dispatched",
        "candidate_id": cid,
        "symbol": sym,
        "strategy_type": cand["strategy_type"],
        "direction": cand["direction"],
        "qty": qty,
        "expiry": cand["expiry"],
        "entry_debit": fill_res.entry_debit,
        "entry_total_invested": fill_res.entry_total_invested,
        "max_loss_total": float(cand.get("max_loss_total") or fill_res.entry_total_invested),
        "max_profit_total": (float(cand["max_profit_contract"]) * qty) if cand.get("max_profit_contract") else None,
    }
