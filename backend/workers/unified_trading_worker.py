"""
eTrader v2 — Worker entry point (used by Render cron and run_bot.py).
Delegates to app.workers.unified_trading_worker.run_pipeline().
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.workers.unified_trading_worker import run_pipeline

if __name__ == "__main__":
    run_pipeline()
    sys.exit(0)
