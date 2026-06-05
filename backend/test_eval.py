import os
import sys
import pandas as pd
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.strategy.strategy_engine import StrategyEngine

def test_eval():
    sb = get_supabase()
    engine = StrategyEngine(sb)
    
    # Dump the context for ADAUSDT around 05:30
    res = sb.table('market_snapshot').select('*').eq('symbol', 'ADAUSDT').execute()
    snap = res.data[0]
    
    # We don't have the exact historical DFs easily, so let's just evaluate based on the snapshot
    # Or just print why Aa21 failed... 
    # Let's check rule config again
    print("Test ready")

if __name__ == "__main__":
    test_eval()
