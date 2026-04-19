"""
eTrader v5.0 — DCA Manager (Dollar Cost Averaging)
Gestiona recompras escalonadas para posiciones de Stocks.

Lógica:
  1. Verifica si existe posición abierta para el ticker
  2. Precio actual < precio promedio
  3. No se superó el máximo de recompras (dca_max_buys)
  4. Precio bajó al menos dca_min_drop_pct desde la última compra
"""
from datetime import datetime, timezone

from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase

MODULE = "DCA_MANAGER"


def check_dca_rebuy(ticker: str, price: float) -> dict:
    """
    Verifica si aplica una recompra DCA para un ticker.

    Returns:
        dict con 'eligible': True/False y detalles.
    """
    sb = get_supabase()

    # Obtener posición activa
    pos = sb.table("stocks_positions") \
        .select("*") \
        .eq("ticker", ticker) \
        .eq("status", "open") \
        .limit(1) \
        .execute()

    if not pos.data:
        return {"eligible": False, "reason": "Sin posición abierta"}

    position = pos.data[0]
    avg_price = float(position["avg_price"])
    dca_count = int(position.get("dca_count", 0))

    # Obtener regla DCA del grupo
    group_name = position.get("group_name", "inversiones_pro")
    rule_code = "S01" if group_name == "inversiones_pro" else "S05"

    rule_res = sb.table("stocks_rules") \
        .select("dca_max_buys, dca_min_drop_pct") \
        .eq("rule_code", rule_code) \
        .limit(1) \
        .execute()

    if not rule_res.data:
        return {"eligible": False, "reason": "Regla no encontrada"}

    max_buys = int(rule_res.data[0].get("dca_max_buys", 3))
    min_drop = float(rule_res.data[0].get("dca_min_drop_pct", 1.0)) / 100

    # Verificar condiciones DCA
    if dca_count >= max_buys:
        return {
            "eligible": False,
            "reason": f"Máximo DCA alcanzado ({dca_count}/{max_buys})",
        }

    if price >= avg_price:
        return {
            "eligible": False,
            "reason": f"Precio ${price:.2f} >= promedio ${avg_price:.2f}",
        }

    drop_from_avg = (avg_price - price) / avg_price
    if drop_from_avg < min_drop:
        return {
            "eligible": False,
            "reason": (
                f"Caída {drop_from_avg*100:.2f}% < mínimo {min_drop*100:.1f}%"
            ),
        }

    return {
        "eligible": True,
        "dca_count": dca_count,
        "max_buys": max_buys,
        "avg_price": avg_price,
        "current_price": price,
        "drop_pct": round(drop_from_avg * 100, 2),
        "reason": (
            f"DCA elegible: precio bajó {drop_from_avg*100:.2f}% "
            f"desde promedio ${avg_price:.2f}. "
            f"Recompra {dca_count+1}/{max_buys}"
        ),
    }


def update_position_after_buy(
    ticker: str,
    new_price: float,
    new_shares: float,
) -> dict:
    """
    Actualiza el precio promedio y shares después de una recompra DCA.
    """
    sb = get_supabase()

    pos = sb.table("stocks_positions") \
        .select("*") \
        .eq("ticker", ticker) \
        .eq("status", "open") \
        .limit(1) \
        .execute()

    if not pos.data:
        return {"error": "Posición no encontrada"}

    p = pos.data[0]
    old_shares = float(p["shares"])
    old_avg = float(p["avg_price"])
    old_count = int(p.get("dca_count", 0))

    total_shares = old_shares + new_shares
    new_avg = ((old_shares * old_avg) + (new_shares * new_price)) / total_shares

    sb.table("stocks_positions") \
        .update({
            "shares": total_shares,
            "avg_price": round(new_avg, 4),
            "total_cost": round(total_shares * new_avg, 2),
            "dca_count": old_count + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }) \
        .eq("id", p["id"]) \
        .execute()

    log_info(MODULE, f"DCA {ticker}: {old_shares}→{total_shares} shares, "
                     f"avg ${old_avg:.2f}→${new_avg:.2f}, "
                     f"recompra {old_count+1}")

    return {
        "ticker": ticker,
        "old_shares": old_shares,
        "new_shares": total_shares,
        "old_avg": old_avg,
        "new_avg": round(new_avg, 4),
        "dca_count": old_count + 1,
    }
