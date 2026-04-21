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
        
        # Initialize OpenAI (Primary)
        self.openai_client = None
        if settings.openai_api_key:
            try:
                self.openai_client = OpenAI(api_key=settings.openai_api_key)
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

    async def execute_full_analysis(self, ticker: str, watchlist_entry: dict = None, tech_data: dict | None = None, **kwargs) -> dict | None:
        """Executes consensus analysis: (QWEN + GEMINI + CLAUDE)."""
        log_info(MODULE, f"═══ AI CONSENSUS ANALYSIS START: {ticker} ═══")
        
        try:
            sb = get_supabase()
            
            # 1. Technical Score (Param or DB)
            if not tech_data:
                tech_res = sb.table("technical_scores").select("*").eq("ticker", ticker).order("timestamp", desc=True).limit(1).execute()
                if tech_res.data:
                    tech_data = tech_res.data[0]
                else:
                    log_warning(MODULE, f"No technical data provided or found for {ticker}")
                    # Create minimal tech_data if missing
                    tech_data = {"close": 0, "technical_score": 50}
            
            # 2. Layer 3 & 4: Fundamental and Context
            funda_data = await self.fundamental.analyze_ticker(ticker)
            context_data = await self.context.analyze_context(ticker, watchlist_entry)

            # --- CÁLCULO DE VALOR INTRÍNSECO S09 (Dual Method) ---
            fund_res = sb.table("watchlist_daily").select("*").eq("ticker", ticker).execute()
            # Fallback a watchlist_entry si el DB falla (útil si el registro es muy reciente)
            fundamental_universe = float(watchlist_entry.get("fundamental_score", 0))
            eps_ttm = 0
            sector = "Other"
            f_data = {}
            if fund_res.data:
                f_data = fund_res.data[0]
                fundamental_universe = float(f_data.get("fundamental_score", fundamental_universe))
                eps_ttm = float(f_data.get("eps_ttm") or 0)
                sector = f_data.get("sector", "Other")
                analyst_consensus = float(f_data.get("analyst_rating", watchlist_entry.get("analyst_rating", 0)) or 0)
            else:
                analyst_consensus = float(watchlist_entry.get("analyst_rating", 0))

            sector_pes = {
                "Technology": 28, "Healthcare": 22, "Financial Services": 14,
                "Consumer Cyclical": 22, "Consumer Defensive": 18, "Communication Services": 20,
                "Industrials": 18, "Energy": 12, "Basic Materials": 15, "Utilities": 16, "Real Estate": 18
            }
            sector_pss = {
                "Technology": 6.0, "Healthcare": 4.5, "Financial Services": 2.5,
                "Consumer Cyclical": 2.0, "Consumer Defensive": 1.5, "Communication Services": 3.0,
                "Industrials": 1.8, "Energy": 1.5, "Basic Materials": 1.2, "Utilities": 2.2, "Real Estate": 4.5
            }
            
            avg_sector_pe = sector_pes.get(sector, 18)
            avg_sector_ps = sector_pss.get(sector, 2.0)
            
            rev_growth_yoy = float(f_data.get("revenue_growth_yoy", 0)) if f_data else 0
            current_price = float(tech_data.get("close", 0))
            intrinsic_price = 0
            
            if eps_ttm > 0:
                growth_factor = 1 + (max(0, rev_growth_yoy) / 100) * 0.5
                intrinsic_price = eps_ttm * avg_sector_pe * growth_factor
            else:
                rps = float(f_data.get("revenue_per_share") or 0) if f_data else 0
                if rps > 0:
                    intrinsic_price = rps * avg_sector_ps * 0.7
                else:
                    ps_ratio = float(f_data.get("price_to_sales") or 0) if f_data else 0
                    if ps_ratio > 0:
                        intrinsic_price = current_price * (avg_sector_ps / ps_ratio) * 0.7

            is_undervalued = (current_price < intrinsic_price) and (intrinsic_price > 0)
            is_deep_value = current_price <= (intrinsic_price * 0.90)

            # 3. Layer 5: Parallel Core AI Analysis (OpenAI Primary + Fallbacks)
            results = await asyncio.gather(
                self._try_openai(ticker, tech_data, funda_data, context_data),
                self._try_gemini(ticker, tech_data, funda_data, context_data),
                self._try_claude(ticker, tech_data, funda_data, context_data),
                return_exceptions=True
            )
            
            openai_res = results[0] if not isinstance(results[0], Exception) else None
            gemini_res = results[1] if not isinstance(results[1], Exception) else None
            claude_res = results[2] if not isinstance(results[2], Exception) else None
            
            scores_ia = []
            rationales = []
            o_score = float(openai_res.get("financial_score", 0)) if openai_res else 0
            g_score = float(gemini_res.get("financial_score", 0)) if gemini_res else 0
            c_score = float(claude_res.get("financial_score", 0)) if claude_res else 0
            
            # Normalización
            if o_score > 11: o_score /= 10
            if g_score > 11: g_score /= 10
            if c_score > 11: c_score /= 10
            
            o_score = max(0.0, min(10.0, o_score))
            g_score = max(0.0, min(10.0, g_score))
            c_score = max(0.0, min(10.0, c_score))
            
            if o_score > 0: scores_ia.append(o_score)
            if g_score > 0: scores_ia.append(g_score)
            if c_score > 0: scores_ia.append(c_score)

            # --- LLM ANALISIS WITH FALLBACK ---
            if not scores_ia:
                log_info(MODULE, f"Using synth math fallback (Reason: All IAs offline or failed)")
                fb = self._math_fallback(ticker, tech_data, funda_data, context_data, fundamental_universe, analyst_consensus)
                fb["intrinsic_value"] = round(intrinsic_price, 2)
                fb["is_undervalued"] = is_undervalued
                fb["undervaluation"] = round(((intrinsic_price - current_price) / intrinsic_price * 100), 1) if is_undervalued and intrinsic_price > 0 else 0
                fb["fundamental_universe"] = fundamental_universe
                log_info(MODULE, f"Fallback result for {ticker}: ProScore={fb.get('pro_score')} (F.Score={fundamental_universe})")
                return fb

            final_ia_avg = sum(scores_ia) / len(scores_ia)
            if qwen_res: rationales.append(f"QWEB ({round(q_score,1)}/10): {qwen_res.get('analysis_summary', '')}")
            if gemini_res: rationales.append(f"GEMINI ({round(g_score,1)}/10): {gemini_res.get('analysis_summary', '')}")
            if claude_res: rationales.append(f"CLAUDE ({round(c_score,1)}/10): {claude_res.get('analysis_summary', '')}")

            m_scores = []
            if qwen_res: m_scores.append(float(qwen_res.get("meta_score", 0)))
            if gemini_res: m_scores.append(float(gemini_res.get("meta_score", 0)))
            if claude_res: m_scores.append(float(claude_res.get("meta_score", 0)))
            final_meta = sum(m_scores) / len(m_scores) if m_scores else 50

            final_decision = "ENTER" if (final_meta >= 65 and fundamental_universe >= 70) else "WAIT"

            combined = {
                "pro_score": round(final_ia_avg, 1),
                "meta_score": round(final_meta, 0),
                "decision": final_decision,
                "ai_rationale": " | ".join(rationales),
                "qwen_score": o_score, # Mantenemos key para compatibilidad frontend pero datos son de OpenAI
                "gemini_score": g_score,
                "qwen_summary": openai_res.get("analysis_summary", "") if openai_res else "",
                "gemini_summary": gemini_res.get("analysis_summary", "") if gemini_res else "",
                "claude_summary": claude_res.get("analysis_summary", "") if claude_res else "",
                "intrinsic_value": round(intrinsic_price, 2),
                "is_undervalued": is_undervalued,
                "undervaluation": round(((intrinsic_price - current_price) / intrinsic_price * 100), 1) if is_undervalued and intrinsic_price > 0 else 0,
                "quadrant": openai_res.get("quadrant") if openai_res else (claude_res.get("quadrant") if claude_res else "C"),
                "fundamental_universe": fundamental_universe
            }
            
            if final_decision == "ENTER":
                opp_id = await self._save_opportunity(ticker, combined)
                combined["opportunity_id"] = opp_id
                
            return combined

        except Exception as e:
            log_error(MODULE, f"Orchestrator failed: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    async def _try_openai(self, ticker, tech, funda, ctx):
        if not self.openai_client: return None
        try:
            prompt = self._build_prompt(ticker, tech, funda, ctx)
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini", # Usamos mini para balance velocidad/precisión
                messages=[{"role": "user", "content": prompt}]
            )
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            log_warning(MODULE, f"OpenAI error: {e}")
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

    def _math_fallback(self, ticker, tech, funda, ctx, fundamental_universe: float = 0, analyst_consensus: float = 0) -> dict:
        tech_score = tech.get("technical_score", 0)
        price = tech.get("close", 0)
        atr = tech.get("atr_14", price * 0.02)
        meta = (tech_score * 0.7) + 20
        decision = "ENTER" if meta >= 65 else "WAIT"
        
        # Ponderación del F.Score (0-100) -> Pro Score (0-10)
        # REGLA: Prevalece Consenso de Expertos (NYC) si existe (>0), de lo contrario usa F.Score
        if analyst_consensus > 0:
            synth_ia = analyst_consensus
            rationale = "Expert Consensus (NYC Analyst Rating 1-10) is primary."
        else:
            synth_ia = fundamental_universe / 10.0
            rationale = "F.Score Factor Fallback (Primary AI & Analyst Consensus unavailable)."
        
        # Mezclar un poco con el Technical Score para que no sea estático
        # (Ajuste fino: 90% Fundamental/Consenso + 10% Técnico)
        norm_tech = tech_score / 10.0
        synth_ia = (synth_ia * 0.9) + (norm_tech * 0.1)
        
        return {
            "pro_score": round(synth_ia, 1),
            "meta_score": round(meta, 1),
            "quadrant": "C", 
            "decision": decision, 
            "trade_type": "swing_trade", "trade_setup": {
                "entry_zone_low": round(price * 0.995, 2), "entry_zone_high": round(price * 1.005, 2), 
                "stop_loss": round(price - (atr * 2), 2), "target_1": round(price + (atr * 3), 2),
                "entry_rationale": "F.Score Factor Fallback (Primary AI unavailable)."
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
