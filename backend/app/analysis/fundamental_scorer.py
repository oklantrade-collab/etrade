import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.core.logger import log_info, log_error, log_warning

MODULE = "fundamental_scorer"

class FundamentalScorer:
    def __init__(self):
        self.spy_data = None

    async def get_spy_performance_6m(self):
        """Calcula el rendimiento del S&P 500 (SPY) en los últimos 6 meses."""
        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="7mo") # Un poco más para asegurar 6m de trading
            if len(hist) < 20: return 0
            
            start_price = hist['Close'].iloc[0]
            end_price = hist['Close'].iloc[-1]
            return (end_price - start_price) / start_price * 100
        except Exception as e:
            log_error(MODULE, f"Error obteniendo SPY performance: {e}")
            return 0

    async def calculate_score(self, ticker: str, spy_perf_6m: float, current_price: float = 0, settings: dict = None, rvol: float = 1.0) -> dict:
        """
        Obtiene datos fundamentales y calcula el FUNDAMENTAL_SCORE (0-100).
        """
        # SIEMPRE empezar con defaults completos, luego sobrescribir con lo que el usuario haya configurado.
        # Esto previene KeyError cuando el JSON/DB tiene campos parciales.
        defaults = {
            "fg_mcap_min": 300, "fg_mcap_max": 10000, "fg_rev_growth_min": 25, "fg_price_max": 50, "fg_rs_min": 70,
            "gl_mcap_min": 5000, "gl_rev_growth_min": 12, "gl_margin_min": 30, "gl_rs_min": 75, "gl_inst_min": 40, "gl_price_max": 200,
            "ex_vol_min": 200000, "ex_debt_equity_max": 3.0, "ex_eps_neg_quarters_max": 4,
            "w_rev_growth": 20, "w_gross_margin": 15, "w_eps_growth": 15, "w_rs_score": 20, "w_inst_ownership": 10, "w_analyst_score": 20
        }
        if settings:
            defaults.update(settings)
        settings = defaults
        try:
            t = yf.Ticker(ticker)
            info = t.info
            
            # 1. Obtener métricas básicas con fallbacks robustos
            rev_growth_yoy = (info.get('revenueGrowth') or info.get('earningsGrowth') or 0) * 100
            gross_margins = (info.get('grossMargins') or info.get('profitMargins') or 0) * 100
            eps_growth_qoq = (info.get('earningsQuarterlyGrowth') or 0) * 100
            mcap = (info.get('marketCap') or info.get('enterpriseValue') or 0) / 1_000_000
            inst_ownership = (info.get('heldPercentInstitutions') or 0) * 100
            
            # --- NUEVO: CALIFICACIÓN DE EXPERTOS (Consenso Analistas) ---
            # recommendationMean: 1.0 (Strong Buy) -> 5.0 (Strong Sell)
            rec_mean = info.get('recommendationMean')
            analyst_rating_10 = 0
            if rec_mean:
                # Mapeo lineal: 1.0 (Best) -> 10 pts, 5.0 (Worst) -> 1 pt
                analyst_rating_10 = max(1, min(10, round(-2.25 * rec_mean + 12.25, 1)))
            
            
            # Si mcap es 0, intentar obtenerlo de otra forma
            if mcap == 0 and current_price > 0:
                shares = info.get('sharesOutstanding', 0)
                if shares > 0: mcap = (shares * current_price) / 1_000_000

            # 2. RS Score (Fuerza Relativa vs SPY)
            rs_score = await self.get_rs_score(ticker)

            # 3. Trend Institucional (Simulado por ahora con heldPercentInstitutions)
            # Nota: yfinance no da el trend directo, usamos el porcentaje actual como base
            inst_trend_points = 15 if inst_ownership > 50 else (inst_ownership / 50 * 15)

            # Revenue Growth YoY
            s_rev = np.clip(rev_growth_yoy, 0, float(settings.get("w_rev_growth", 25))) 
            
            # Gross Margin
            s_margin = np.clip(gross_margins / (100 / float(settings.get("w_gross_margin", 20))), 0, float(settings.get("w_gross_margin", 20)))
            
            # EPS Growth QoQ
            s_eps = np.clip(eps_growth_qoq, 0, float(settings.get("w_eps_growth", 20)))
            
            # RS Score
            s_rs = (rs_score / 100) * float(settings.get("w_rs_score", 20))
            
            # Inst Ownership
            s_inst = (inst_ownership / 100) * float(settings.get("w_inst_ownership", 10))

            # Analyst Score (Consenso de Expertos)
            s_analyst = (analyst_rating_10 / 10) * float(settings.get("w_analyst_score", 20))

            total_score = s_rev + s_margin + s_eps + s_rs + s_inst + s_analyst

            # --- VALUACIÓN (GRAHAM NUMBER / INTRINSIC VALUE) ---
            eps_ttm = info.get('trailingEps', 0)
            book_value = info.get('bookValue', 0)
            intrinsic_value = 0
            is_overvalued = False
            
            if eps_ttm > 0 and book_value > 0:
                # Fórmula de Graham Simplificada: sqrt(22.5 * EPS * BVPS)
                val_base = 22.5 * eps_ttm * book_value
                if val_base > 0:
                    intrinsic_value = np.sqrt(val_base)
            
            # Margen de seguridad del 10% sobre el valor intrínseco
            if intrinsic_value > 0:
                is_overvalued = current_price > (intrinsic_value * 1.1)

            # --- LÓGICA DE CLASIFICACIÓN DE POOLS ---
            pools = []
            
            # A. FUTURE_GIANT (Solo si NO está sobrevalorada)
            if (settings.get("fg_mcap_min", 100) <= mcap <= settings.get("fg_mcap_max", 10000) and 
                rev_growth_yoy > settings.get("fg_rev_growth_min", 20) and 
                1 <= current_price <= settings.get("fg_price_max", 50) and 
                rs_score > settings.get("fg_rs_min", 70) and 
                (eps_growth_qoq > 0 or gross_margins > 20) and
                not is_overvalued):
                pools.append("GIANT")
                
            # B. GROWTH_LEADER (Solo si NO está sobrevalorada)
            if (mcap >= settings.get("gl_mcap_min", 5000) and 
                rev_growth_yoy > settings.get("gl_rev_growth_min", 12) and 
                gross_margins > settings.get("gl_margin_min", 30) and 
                rs_score > settings.get("gl_rs_min", 75) and 
                inst_ownership > settings.get("gl_inst_min", 40) and 
                1 <= current_price <= settings.get("gl_price_max", 500) and
                not is_overvalued):
                pools.append("LEADER")

            # C. SCALPING (HOT) - Momentum Puro
            # Si tiene un RS Score brutal (>85) o un Spike de Volumen (>2.0), es HOT
            if rs_score > 85 or rvol > 2.0:
                pools.append("HOT")

            # --- LÓGICA DE CALIDAD Y EXCLUSIÓN (REQUERIMIENTO) ---
            quality_flag = "PASS"
            exclusion_reason = ""
            
            # ... (Lógica de exclusión existente) ...
            avg_vol_30d = info.get('averageDailyVolume3Month', 0)
            debt_equity = info.get('debtToEquity', 0) / 100 
            sector = info.get('sector', '')
            revenue_ttm = info.get('totalRevenue', 0)
            
            if avg_vol_30d < settings["ex_vol_min"]:
                quality_flag = "EXCLUDED"
                exclusion_reason = "Low Liquidity"
            
            if debt_equity > settings["ex_debt_equity_max"] and rev_growth_yoy < 10:
                quality_flag = "✗ EXCLUDED"
                exclusion_reason = "Zombie (Debt/Low Growth)"
            
            if "bankruptcy" in str(info.get('financialStatus', '')).lower():
                quality_flag = "✗ EXCLUDED"
                exclusion_reason = "Bankruptcy/Restructuring"
            
            if eps_growth_qoq < 0 and rev_growth_yoy < 30:
                if info.get('trailingEps', 0) < 0:
                    quality_flag = "✗ EXCLUDED"
                    exclusion_reason = "Chronic Losses w/o Growth"
            
            if "biotechnology" in sector.lower() and revenue_ttm < 10_000_000:
                quality_flag = "✗ EXCLUDED"
                exclusion_reason = "Biotech Pre-Revenue Trap"

            # Marcar como sobrevalorada si aplica
            if is_overvalued and quality_flag == "PASS":
                quality_flag = "OVERVALUED"
                exclusion_reason = f"Price (${current_price}) > Intrinsic (${intrinsic_value:.2f})"

            return {
                "ticker": ticker,
                "fundamental_score": round(total_score, 2),
                "pool_type": ", ".join(pools) if pools else "",
                "quality_flag": quality_flag,
                "revenue_growth_yoy": round(rev_growth_yoy, 2),
                "gross_margin": round(gross_margins, 2),
                "eps_growth_qoq": round(eps_growth_qoq, 2),
                "rs_score_6m": round(rs_score, 2),
                "inst_ownership_pct": round(inst_ownership, 2),
                "market_cap_mln": round(mcap, 2),
                "analyst_rating": analyst_rating_10,
                "exclusion_reason": exclusion_reason,
                "intrinsic_value": round(intrinsic_value, 2),
                "is_overvalued": is_overvalued,
                "last_update": datetime.now().isoformat()
            }

        except Exception as e:
            log_warning(MODULE, f"Error calculando fundamentales para {ticker}: {e}")
            return None

    async def get_rs_score(self, ticker: str) -> float:
        """
        Calcula el Relative Strength vs S&P 500 (SPY).
        Fórmula: (retorno_accion / retorno_spy) * 50 + 50
        Fallback: 3 meses si falla 6 meses.
        """
        try:
            # Periodos a intentar: 6 meses y luego 3 meses
            for period in ["6mo", "3mo"]:
                t = yf.Ticker(ticker)
                hist = t.history(period=period)
                if len(hist) < 15: continue
                
                start_p = hist['Close'].iloc[0]
                end_p = hist['Close'].iloc[-1]
                if start_p <= 0: continue
                stock_ret = (end_p - start_p) / start_p
                
                # Fetch SPY for same period
                spy = yf.Ticker("SPY")
                spy_hist = spy.history(period=period)
                spy_start = spy_hist['Close'].iloc[0]
                spy_end = spy_hist['Close'].iloc[-1]
                spy_ret = (spy_end - spy_start) / spy_start
                
                if spy_ret == 0: spy_ret = 0.001
                
                # Formula: (Retorno / SPY_Retorno) * 50 + 50
                rs = (stock_ret / spy_ret) * 50 + 50
                return max(0, min(100, rs))
                
            return -1 # Flag: RS_UNAVAILABLE
        except Exception as e:
            log_warning(MODULE, f"RS Error for {ticker}: {e}")
            return -1
