"""Modulo de Analisis de Performance y Metricas para APEX Options (Sprint 7).
Calcula indicadores de rentabilidad, riesgo y sensibilidad para la cartera paper.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

MODEL_VERSION = "v1.0-s7"


def calculate_performance(trades: list[dict[str, Any]],
                          open_trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Calcula las metricas completas de performance para una lista de operaciones cerradas."""
    open_trades = open_trades or []
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate_pct": 0.0,
            "net_pnl_usd": 0.0,
            "unrealized_pnl_usd": round(sum(float(t.get("unrealized_pnl") or 0.0) for t in open_trades), 2),
            "gross_profit_usd": 0.0,
            "gross_loss_usd": 0.0,
            "profit_factor": 0.0,
            "expectancy_usd": 0.0,
            "avg_win_usd": 0.0,
            "avg_loss_usd": 0.0,
            "win_loss_ratio": 0.0,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "equity_curve": [],
            "by_strategy": {},
            "by_symbol": {},
            "by_exit_reason": {},
            "slippage_sensitivity": {},
            "model_version": MODEL_VERSION,
        }

    # Ordenar cronologicamente por exit_time o entry_time
    sorted_trades = sorted(
        trades,
        key=lambda x: str(x.get("exit_time") or x.get("entry_time") or x.get("created_at") or "")
    )

    n_trades = len(sorted_trades)
    pnls = [float(t.get("realized_pnl") or 0.0) for t in sorted_trades]
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    bes = [p for p in pnls if p == 0]

    gross_profit = sum(wins)
    gross_loss = sum(losses)
    net_pnl = sum(pnls)

    win_rate = (len(wins) / n_trades * 100.0) if n_trades else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    expectancy = net_pnl / n_trades if n_trades else 0.0
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    # Curva de equidad y Drawdown
    equity_curve: list[dict[str, Any]] = []
    cum = 0.0
    peak = 0.0
    max_dd = 0.0

    for idx, t in enumerate(sorted_trades, start=1):
        pnl = float(t.get("realized_pnl") or 0.0)
        cum = round(cum + pnl, 2)
        if cum > peak:
            peak = cum
        dd = round(peak - cum, 2)
        if dd > max_dd:
            max_dd = dd

        equity_curve.append({
            "trade_num": idx,
            "trade_id": t.get("id"),
            "symbol": t.get("symbol"),
            "strategy": t.get("strategy_type"),
            "date": str(t.get("exit_time") or t.get("entry_time") or "")[:10],
            "pnl": pnl,
            "cumulative_pnl": cum,
            "peak": peak,
            "drawdown": dd,
        })

    # Desglose por estrategia
    by_strat: dict[str, list[float]] = defaultdict(list)
    for t in sorted_trades:
        by_strat[t.get("strategy_type") or "unknown"].append(float(t.get("realized_pnl") or 0.0))

    strat_summary = {}
    for st, p_list in by_strat.items():
        st_wins = sum(1 for p in p_list if p > 0)
        strat_summary[st] = {
            "trades": len(p_list),
            "net_pnl": round(sum(p_list), 2),
            "win_rate_pct": round(st_wins / len(p_list) * 100.0, 1),
            "expectancy": round(sum(p_list) / len(p_list), 2),
        }

    # Desglose por simbolo
    by_sym: dict[str, list[float]] = defaultdict(list)
    for t in sorted_trades:
        by_sym[t.get("symbol") or "UNKNOWN"].append(float(t.get("realized_pnl") or 0.0))

    sym_summary = {}
    for sym, p_list in by_sym.items():
        sym_wins = sum(1 for p in p_list if p > 0)
        sym_summary[sym] = {
            "trades": len(p_list),
            "net_pnl": round(sum(p_list), 2),
            "win_rate_pct": round(sym_wins / len(p_list) * 100.0, 1),
        }

    # Desglose por motivo de salida
    by_exit: dict[str, list[float]] = defaultdict(list)
    for t in sorted_trades:
        by_exit[t.get("exit_reason") or "unknown"].append(float(t.get("realized_pnl") or 0.0))

    exit_summary = {}
    for ex, p_list in by_exit.items():
        exit_summary[ex] = {
            "trades": len(p_list),
            "net_pnl": round(sum(p_list), 2),
            "avg_pnl": round(sum(p_list) / len(p_list), 2),
        }

    # Sensibilidad a slippage (1x vs 2x vs 3x)
    total_slip_cost = 0.0
    for t in sorted_trades:
        fills = (t.get("entry_fills") or []) + (t.get("exit_fills") or [])
        qty = int(t.get("qty") or 1)
        for f in fills:
            total_slip_cost += float(f.get("slippage_applied") or 0.0) * 100.0 * qty

    unrealized_open = sum(float(t.get("unrealized_pnl") or 0.0) for t in open_trades)

    return {
        "total_trades": n_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": len(bes),
        "win_rate_pct": round(win_rate, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "unrealized_pnl_usd": round(unrealized_open, 2),
        "gross_profit_usd": round(gross_profit, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_usd": round(expectancy, 2),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "max_drawdown_usd": round(max_dd, 2),
        "equity_curve": equity_curve,
        "by_strategy": strat_summary,
        "by_symbol": sym_summary,
        "by_exit_reason": exit_summary,
        "slippage_sensitivity": {
            "base_slippage_usd": round(total_slip_cost, 2),
            "pnl_with_2x_slippage": round(net_pnl - total_slip_cost, 2),
            "pnl_with_3x_slippage": round(net_pnl - 2.0 * total_slip_cost, 2),
        },
        "model_version": MODEL_VERSION,
    }
