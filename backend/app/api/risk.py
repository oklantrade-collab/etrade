"""
eTrader v2 — Risk API endpoints
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.core.supabase_client import get_supabase
from app.core.parameter_guard import validate_parameter_change

router = APIRouter()


class RiskConfigUpdate(BaseModel):
    max_risk_per_trade_pct: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_open_trades: Optional[int] = None
    max_positions_per_symbol: Optional[int] = None # Nuevo campo
    sl_multiplier: Optional[float] = None
    rr_ratio: Optional[float] = None
    kill_switch_enabled: Optional[bool] = None
    kill_switch_loss_pct: Optional[float] = None
    slippage_estimate_pct: Optional[float] = None
    bot_active: Optional[bool] = None


@router.get("/config")
def get_risk_config():
    """Get current risk configuration."""
    sb = get_supabase()
    result = sb.table("risk_config").select("*").limit(1).execute()
    if result.data:
        return {"risk_config": result.data[0]}
    return {"risk_config": {}}


@router.put("/config")
def update_risk_config(config: RiskConfigUpdate):
    """Update risk configuration."""
    sb = get_supabase()
    update_data = {k: v for k, v in config.model_dump().items() if v is not None}
    if not update_data:
        return {"status": "no_changes"}

    # Get the single risk_config row id
    existing = sb.table("risk_config").select("id").limit(1).execute()
    if not existing.data:
        return {"error": "No risk_config row found"}

    row_id = existing.data[0]["id"]
    sb.table("risk_config").update(update_data).eq("id", row_id).execute()
    return {"status": "updated", "updated_fields": list(update_data.keys())}


class ParameterUpdate(BaseModel):
    parameter_name: str
    new_value: float
    changed_by: str = "jhon"
    change_reason: str
    backtest_result: Optional[dict] = None

@router.post("/validate-param")
async def api_validate_parameter_change(update: ParameterUpdate):
    """Validate and apply a parameter change using guardrails (Fase 1)."""
    sb = get_supabase()
    result = await validate_parameter_change(
        parameter_name=update.parameter_name,
        new_value=update.new_value,
        changed_by=update.changed_by,
        change_reason=update.change_reason,
        backtest_result=update.backtest_result,
        supabase_client=sb
    )
    return {
        "accepted": result.accepted,
        "reason": result.reason,
        "ev": result.expected_value,
        "within_bounds": result.within_bounds
    }

@router.post("/kill-switch")
def activate_kill_switch():
    """Manually activate the kill switch."""
    sb = get_supabase()
    existing = sb.table("risk_config").select("id").limit(1).execute()
    if not existing.data:
        return {"error": "No risk_config row found"}

    row_id = existing.data[0]["id"]
    sb.table("risk_config").update({"bot_active": False}).eq("id", row_id).execute()

    from app.workers.alerts_worker import send_kill_switch_alert
    send_kill_switch_alert("Manual kill switch activation via API")

    return {"status": "kill_switch_activated", "bot_active": False}
