import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase
from app.stocks.stocks_orchestrator import fetch_global_config, check_system_limits

async def run_diagnostics():
    print("=== STOCKS DIAGNOSTICS ===")
    sb = get_supabase()
    cfg = fetch_global_config(sb)
    print(f"Global Config: paper_trading={cfg.get('paper_trading')}, ai_enabled={cfg.get('ai_enabled')}")
    
    limits = check_system_limits(sb, cfg)
    print(f"Limits Check: can_buy={limits['can_buy']}, reason={limits.get('reason')}")
    print(f"Active Positions: {limits.get('active_count')} / {limits.get('max_positions')}")
    
    if not limits['can_buy']:
        print("System cannot buy based on limits.")
        return

    # Check top APEX scores
    res = sb.table('apex_scores').select('*').order('apex_score_4h', desc=True).limit(5).execute()
    print("\nTop 5 APEX Scores:")
    for r in res.data:
        print(f"{r['ticker']}: 4H={r['apex_score_4h']}, 1D={r['apex_score_1d']}, Conf={r['confidence']}")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
