"""
eTrader v4.5 — Decision Engine (Resilient Orchestrator with QWEN)
Master logic with QWEN (Alibaba) as Primary AI engine.

Fallback chain: QWEN (Primary) -> Claude -> Gemini -> Math.
"""
import json
import os
import sys
import asyncio
from typing import Optional
from datetime import datetime, date, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import anthropic
    import google.generativeai as genai
    from openai import OpenAI
    AI_LIBS_AVAILABLE = True
except ImportError:
    AI_LIBS_AVAILABLE = False

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.core.config import settings

from app.stocks.fundamental_analyzer import FundamentalAnalyzer
from app.stocks.context_analyzer import ContextAnalyzer

MODULE = "decision_engine"

class DecisionEngine:
    def __init__(self):
        self.fundamental = FundamentalAnalyzer()
        self.context = ContextAnalyzer()
        
        # Initialize QWEN (Primary) via OpenAI compatibility
        self.qwen_client = None
        if settings.qwen_api_key:
            try:
                self.qwen_client = OpenAI(
                    api_key=settings.qwen_api_key,
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                )
            except: pass

        # Initialize Anthropic
        self.claude = None
        if settings.anthropic_api_key:
            try:
                self.claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            except: pass
            
        # Initialize Gemini
        self.gemini = None
        if settings.gemini_api_key:
            try:
                genai.configure(api_key=settings.gemini_api_key)
                self.gemini = genai.GenerativeModel('gemini-1.5-flash-latest')
            except: pass

    async def execute_full_analysis(self, ticker: str, watchlist_entry: dict) -> dict | None:
        """Executes full multi-layer analysis with fallback."""
        log_info(MODULE, f"═══ QWEN-POWERED ANALYSIS START: {ticker} ═══")
        
        try:
            sb = get_supabase()
            
            # 1. Fetch Technical Score
            tech_res = sb.table("technical_scores").select("*").eq("ticker", ticker).order("timestamp", desc=True).limit(1).execute()
            if not tech_res.data:
                log_warning(MODULE, f"No technical score found for {ticker}")
                return None
            tech_data = tech_res.data[0]
            
            # 2. Layer 3 & 4
            funda_data = await self.fundamental.analyze_ticker(ticker)
            context_data = await self.context.analyze_context(ticker, watchlist_entry)
            
            # 3. Layer 5: Primary (Qwen) -> Claude -> Gemini -> Math
            decision = await self._try_qwen(ticker, tech_data, funda_data, context_data)
            
            if not decision:
                log_warning(MODULE, "QWEN failed, trying Claude fallback...")
                decision = await self._try_claude(ticker, tech_data, funda_data, context_data)
            
            if not decision:
                log_warning(MODULE, "AI failed, using Math fallback.")
                decision = self._math_fallback(ticker, tech_data, funda_data, context_data)
            
            # 4. Save if ENTER
            if decision and decision.get("decision") == "ENTER":
                opp_id = await self._save_opportunity(ticker, decision)
                decision["opportunity_id"] = opp_id
                
            return decision

        except Exception as e:
            log_error(MODULE, f"Orchestrator failed: {e}")
            return None

    async def _try_qwen(self, ticker, tech, funda, ctx):
        """Attempts decision with Qwen Plus."""
        if not self.qwen_client: return None
        try:
            prompt = self._build_prompt(ticker, tech, funda, ctx)
            response = self.qwen_client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "user", "content": prompt}]
            )
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            log_warning(MODULE, f"QWEN error: {e}")
            return None

    async def _try_claude(self, ticker, tech, funda, ctx):
        if not self.claude: return None
        try:
            prompt = self._build_prompt(ticker, tech, funda, ctx)
            response = self.claude.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return self._parse_json(response.content[0].text)
        except: return None

    async def _try_gemini(self, ticker, tech, funda, ctx):
        if not self.gemini: return None
        try:
            prompt = self._build_prompt(ticker, tech, funda, ctx)
            response = self.gemini.generate_content(prompt)
            return self._parse_json(response.text)
        except: return None

    def _math_fallback(self, ticker, tech, funda, ctx) -> dict:
        tech_score = tech.get("technical_score", 0)
        price = tech.get("close", 0)
        atr = tech.get("atr_14", price * 0.02)
        meta = (tech_score * 0.7) + 20
        decision = "ENTER" if meta >= 65 else "WAIT"
        return {
            "meta_score": round(meta, 1), "quadrant": "C", "decision": decision, 
            "trade_type": "swing_trade", "trade_setup": {
                "entry_zone_low": round(price * 0.995, 2), "entry_zone_high": round(price * 1.005, 2), 
                "stop_loss": round(price - (atr * 2), 2), "target_1": round(price + (atr * 3), 2),
                "entry_rationale": "Mathematical Decision Layer (Primary AI unavailable)."
            }
        }

    def _build_prompt(self, ticker, tech, funda, ctx) -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "capa5_decision.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read().replace("{{TICKER}}", ticker).replace("{{TECHNICAL_JSON}}", json.dumps(tech)).replace("{{FUNDAMENTAL_JSON}}", json.dumps(funda)).replace("{{CONTEXT_JSON}}", json.dumps(ctx)).replace("{{RISK_JSON}}", "{'max':1%}") .replace("{{CAPITAL_JSON}}", "{'total':5000}")
        except: return "Decision Prompt Error"

    def _parse_json(self, text):
        try:
            if "{" in text and "}" in text:
                return json.loads(text[text.find("{"):text.rfind("}")+1])
            return None
        except: return None

    async def _save_opportunity(self, ticker: str, data: dict) -> str | None:
        sb = get_supabase()
        try:
            setup = data.get("trade_setup", {})
            row = {
                "ticker": ticker, "meta_score": data.get("meta_score", 0), "risk_score": data.get("risk_score", 5),
                "trade_type": data.get("trade_type", "swing_trade"), "quadrant": data.get("quadrant", "D"),
                "entry_zone_low": setup.get("entry_zone_low"), "entry_zone_high": setup.get("entry_zone_high"),
                "stop_loss": setup.get("stop_loss"), "target_1": setup.get("target_1"), "rr_ratio": 2.0, "status": "pending"
            }
            res = sb.table("trade_opportunities").insert(row).execute()
            return res.data[0]["id"] if res.data else None
        except: return None
