import asyncio
from app.core.supabase_client import get_supabase
from app.core.safety_manager import validate_signal
from app.strategy.macro_filter import fetch_macro_context
from app.strategy.risk_controls import check_pre_filters
import pandas as pd
from datetime import datetime, timezone

async def main():
    sb = get_supabase()
    # Mock some data for the checks
    res = sb.table("strategy_evaluations").select("*").eq("symbol", "ETHUSDT").eq("triggered", True).order("created_at", desc=True).limit(1).execute()
    if not res.data:
        print("No evaluation found")
        return
    eval_data = res.data[0]
    rule_code = eval_data["rule_code"]
    direction = eval_data["direction"]
    context = eval_data["context"]
    
    print(f"Testing rule {rule_code} ({direction})")
    
    # 1. validate_signal
    snap_eval = {
        'price': context.get('price', 3000),
        'ema_3': context.get('ema3', 3000),
        'ema_9': context.get('ema9', 3000),
        'ema_20': context.get('ema20', 3000),
        'atr': context.get('atr', 10),
        'adx': context.get('adx', 40),
    }
    v_signal = validate_signal(
        symbol="ETHUSDT", price=snap_eval['price'], timestamp=datetime.now(timezone.utc).isoformat(),
        market_type='crypto_futures', direction=direction, rule_code=rule_code, snap=snap_eval
    )
    print("validate_signal:", v_signal)

    # 2. macro
    macro = await fetch_macro_context('crypto_futures', "ETHUSDT", sb)
    print("macro_filter:", macro)

    # 3. pre_filters
    pre_res = check_pre_filters(
        regime={"category": context.get("regime", "bajo_riesgo"), "active_params": {"max_trades": 15}},
        market_data={"vol_entry_ok": False}, # Let's assume false or true
        direction=direction, symbol="ETHUSDT", current_price=snap_eval['price'], basis_price=context.get('basis', 3000),
        open_trades_count=0, symbol_positions_count=0, capital_sufficient=True, warmup_complete=True,
        max_per_symbol=4, rule_code=rule_code
    )
    print("check_pre_filters:", pre_res)

if __name__ == "__main__":
    asyncio.run(main())
