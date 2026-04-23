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
    """Move a position to 'closed' status without deleting the record."""
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    
    if market.lower() == "crypto":
        from app.execution.order_manager import close_position
        success = close_position(position_id, reason="MANUAL_CLOSE")
        return {"status": "ok" if success else "error"}

    table_map = {
        "forex": "forex_positions",
        "stocks": "stocks_positions"
    }
    
    table_name = table_map.get(market.lower())
    if not table_name:
        return JSONResponse(status_code=400, content={"error": "Invalid market"})

    try:
        update_data = {
            "status": "closed",
            "closed_at": now,
            "close_reason": "MANUAL_CLOSE"
        }
        
        # Only add updated_at if the market is stocks (since forex doesn't have it)
        if market.lower() == "stocks":
            update_data["updated_at"] = now

        res = sb.table(table_name).update(update_data).eq("id", position_id).execute()
        
        return {"status": "closed", "data": res.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
