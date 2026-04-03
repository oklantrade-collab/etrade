"""
eTrader v2 — Logs & Cycles API endpoints
"""
from fastapi import APIRouter, Query
from app.core.supabase_client import get_supabase

router = APIRouter()


@router.get("/logs")
def get_logs(
    module: str = Query(default=None),
    level: str = Query(default=None),
    cycle_id: str = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    """Get system logs with filters."""
    sb = get_supabase()
    query = sb.table("system_logs").select("*").order("created_at", desc=True).limit(limit)
    if module:
        query = query.eq("module", module)
    if level:
        query = query.eq("level", level)
    if cycle_id:
        query = query.eq("cycle_id", cycle_id)
    result = query.execute()
    return {"logs": result.data}


@router.get("/cycles")
def get_cycles(
    limit: int = Query(default=20, le=100),
):
    """Get cron job cycle history."""
    sb = get_supabase()
    result = (
        sb.table("cron_cycles")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"cycles": result.data}
