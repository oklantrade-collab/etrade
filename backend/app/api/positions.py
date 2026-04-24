"""
eTrader v2 — Positions API endpoints
"""
from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase

router = APIRouter()


@router.get("")
def get_positions(
    status: str = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """Get positions (open and closed)."""
    sb = get_supabase()
    query = sb.table("positions").select("*").order("opened_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"positions": result.data}


@router.delete("/{position_id}/close")
def close_position_endpoint(position_id: str):
    """Close a position manually."""
    from app.execution.order_manager import close_position
    success = close_position(position_id, reason="MANUAL")
    if success:
        return {"status": "closed", "position_id": position_id}
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"status": "error", "message": "Failed to close position. Check system_logs for details."}
    )


@router.get("/orders")
def get_orders(
    status: str = Query(default=None),
    symbol: str = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """Get order history."""
    sb = get_supabase()
    query = sb.table("orders").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if symbol:
        query = query.eq("symbol", symbol)
    result = query.execute()
    return {"orders": result.data}
@router.delete("/{market}/{position_id}")
def delete_position_record(market: str, position_id: str):
    """Hard delete a position record from the database."""
    sb = get_supabase()
    
    table_map = {
        "crypto": "positions",
        "forex": "forex_positions",
        "stocks": "stocks_positions"
    }
    
    table_name = table_map.get(market.lower())
    if not table_name:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "message": f"Invalid market type: {market}"}
        )
    
    try:
        res = sb.table(table_name).delete().eq("id", position_id).execute()
        if res.data:
            return {"status": "deleted", "market": market, "id": position_id}
        else:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"status": "error", "message": "Position not found or already deleted."}
            )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": str(e)}
        )

@router.post("/{market}/{position_id}/close")
def manual_close_position(market: str, position_id: str):
    """Fetch current price, calculate PnL, and close position."""
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    market_l = market.lower()
    
    if market_l == "crypto":
        from app.execution.order_manager import close_position
        success = close_position(position_id, reason="MANUAL_CLOSE")
        return {"status": "ok" if success else "error"}

    table_map = {
        "forex": "forex_positions",
        "stocks": "stocks_positions"
    }
    
    table_name = table_map.get(market_l)
    if not table_name:
        return JSONResponse(status_code=400, content={"error": "Invalid market"})

    try:
        # 1. Get position details
        pos_res = sb.table(table_name).select("*").eq("id", position_id).single().execute()
        if not pos_res.data:
            return JSONResponse(status_code=404, content={"error": "Position not found"})
        
        pos = pos_res.data
        symbol = pos.get("symbol") or pos.get("ticker")
        side = (pos.get("side") or pos.get("direction") or "buy").lower()
        entry_price = float(pos.get("entry_price") or pos.get("avg_price") or 0)
        size = float(pos.get("lots") or pos.get("shares") or 0)

        # 2. Get current price from snapshot
        snap_res = sb.table("market_snapshot").select("price").eq("symbol", symbol).execute()
        current_price = float(snap_res.data[0]["price"]) if snap_res.data else entry_price

        # 3. Calculate PnL
        pnl_usd = 0.0
        pips = 0.0
        
        if market_l == "forex":
            from app.strategy.capital_protection import PIP_SIZES
            pip = PIP_SIZES.get(symbol, 0.0001)
            diff = (current_price - entry_price) if side in ("long", "buy") else (entry_price - current_price)
            pips = diff / pip
            
            # Pip Value logic (Standard 1.0 lot = $10/pip approx)
            pip_value = 10.0
            if "JPY" in symbol: pip_value = 6.5
            if "XAU" in symbol: pip_value = 1.0
            
            pnl_usd = pips * pip_value * abs(size)
        else: # stocks
            diff = (current_price - entry_price) if side in ("long", "buy") else (entry_price - current_price)
            pnl_usd = diff * size

        # 4. Update with real data
        update_data = {
            "status": "closed",
            "closed_at": now,
            "close_reason": "MANUAL_CLOSE",
            "current_price": current_price,
            "pnl_usd": round(pnl_usd, 2)
        }
        
        if market_l == "forex":
            update_data["pnl_pips"] = round(pips, 1)
        if market_l == "stocks":
            update_data["updated_at"] = now
            update_data["unrealized_pnl"] = round(pnl_usd, 2) # used in stocks history

        sb.table(table_name).update(update_data).eq("id", position_id).execute()
        
        # ── REGISTRAR PN EN CAPITAL ACUMULADO (Interés Compuesto) ──
        try:
            from app.core.capital_manager import register_realized_pnl
            register_realized_pnl(market_l, pnl_usd)
        except Exception as cap_e:
            print(f"Error updating accumulated capital: {cap_e}")

        return {"status": "closed", "pnl_usd": pnl_usd, "exit_price": current_price}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
