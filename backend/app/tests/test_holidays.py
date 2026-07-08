import sys
import os
import pandas as pd
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.market_hours import is_market_open

def test_today():
    is_open, reason = is_market_open()
    print(f"Resultado real actual: {is_open} - {reason}")

if __name__ == "__main__":
    test_today()
