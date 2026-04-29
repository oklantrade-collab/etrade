"""
eTrader v4.5 — Context Analyzer (Resilient QWEN)
"""
import json, os, sys, asyncio
from datetime import date
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.logger import log_info, log_error
from app.core.supabase_client import get_supabase
from app.core.config import settings

class ContextAnalyzer:
    def __init__(self):
        self.qwen = None
        if settings.qwen_api_key:
            try:
                self.qwen = OpenAI(api_key=settings.qwen_api_key, base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
            except: pass

    async def analyze_context(self, ticker: str, watchlist_entry: dict) -> dict:
        log_info("context_analyzer", f"Analyzing sentiment for {ticker}...")
        catalyst = watchlist_entry.get("catalyst_type", "General News")
        if self.qwen:
            try:
                prompt = f"Analyze sentiment for {ticker} (catalyst: {catalyst}). JSON: {{'sentiment_score':0-100, 'narrative':'1 sentence', 'context_score':0-100}}"
                resp = self.qwen.chat.completions.create(model="qwen-plus", messages=[{"role": "user", "content": prompt}])
                text = resp.choices[0].message.content
                data = json.loads(text[text.find("{"):text.rfind("}")+1])
                data.update({"ticker": ticker, "date": date.today().isoformat(), "catalyst_type": catalyst, "catalyst_score": watchlist_entry.get("catalyst_score", 5)})
                await self._save_context(data)
                return data
            except Exception as e:
                log_error("context_analyzer", f"QWEN Fallback: {e}")
        
        # MATH FALLBACK
        log_info("context_analyzer", f"Using neutral sentiment fallback for {ticker}.")
        fallback = {"ticker": ticker, "date": date.today().isoformat(), "catalyst_type": catalyst, "catalyst_score": 5, "sentiment_score": 50, "narrative": "Neutral sentiment (AI fallback)", "context_score": 50}
        await self._save_context(fallback)
        return fallback

    async def _save_context(self, data: dict):
        sb = get_supabase()
        try:
            row = {"ticker": data["ticker"], "date": data["date"], "catalyst_score": data["catalyst_score"], "catalyst_type": data["catalyst_type"], "sentiment_score": data.get("sentiment_score", 50), "narrative": data.get("narrative", ""), "context_score": data["context_score"], "regime_adjustment": 0}
            sb.table("context_scores").insert(row).execute()
        except: pass
