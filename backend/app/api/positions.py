"""
eTrader v2 — Positions API endpoints
"""
from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
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
