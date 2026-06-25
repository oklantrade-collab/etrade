"""
eTrader v5.0 — Stocks Rule Engine
Motor de evaluación de reglas para órdenes MARKET y LIMIT.

Evalúa 8 reglas (PRO/HOT × BUY/SELL × MARKET/LIMIT) contra
el contexto de mercado actual de cada ticker.

Principio:
  Python calcula indicadores → JSON → evaluación
  IA (Claude/Gemini) ya corrió en Capa 5
  Este engine aplica las reglas definidas en stocks_rules.
"""
from typing import Optional

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

MODULE = "STOCKS_ENGINE"


class StocksRuleEngine:
    """
    Motor de evaluación de reglas para Stocks.
    Evalúa las 8 reglas (PRO/HOT × BUY/SELL × MARKET/LIMIT)
    contra el contexto de mercado.
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.sb = get_supabase()
        self.rules = {}
        self.config = {}
        self.load_config()
        self.load_rules()

    def load_config(self):
        """Load global stocks configuration."""
        try:
            res = self.sb.table("stocks_config").select("key, value").execute()
            self.config = {row["key"]: row["value"] for row in (res.data or [])}
        except Exception as e:
            log_warning(MODULE, f"Error cargando stocks_config: {e}")

    def load_rules(self):
        """Load active rules from Supabase stocks_rules table."""
        res = self.sb \
            .table("stocks_rules") \
            .select("*") \
            .eq("enabled", True) \
            .order("priority") \
            .execute()
        self.rules = {
            r["rule_code"]: r
            for r in (res.data or [])
        }
        log_info(MODULE, f"Cargadas {len(self.rules)} reglas activas")

    def build_context(
        self,
        ticker: str,
        snap: dict,
        ia_score: float = 0.0,
        tech_score: float = 0.0,
        fundamental_score: float = 0.0,
        rvol: float = 1.0,
        pine_signal: str = "",
        limit_buy_price: float = None,
        limit_sell_price: float = None,
        limit_buy_band: str = None,
        limit_sell_band: str = None,
        movement_type: str = "lateral",
        fib_zone: int = 0,
        bb_lower: float = None,
        intrinsic_price: float = 0.0,
        pool_type: str = "",
        sm_score: float = 0.0,
        piotroski_score: int = 0,
        sipv_signal: str = "",
        ema_20: float = None,
        ema_3: float = None,
        ema_9: float = None,
        bb_expanding: bool = False,
        ema_exhaustion: bool = False,
        ema3_cross_age: int = 999,
    ) -> dict:
        """
        Construye el contexto de evaluación para un ticker.
        """
        price = float(snap.get("price", 0))
        close = float(snap.get("close", price))
        high = float(snap.get("high", close))
        basis = float(snap.get("basis", price))

        return {
            "ticker": ticker,
            "price": price,
            "close": close,
            "basis": basis,
            "fib_zone": fib_zone,
            "movement_type": movement_type,
            "ia_score": ia_score,
            "tech_score": tech_score,
            "fundamental_score": fundamental_score,
            "rvol": rvol,
            "pine_signal": pine_signal,
            "limit_buy_price": limit_buy_price,
            "limit_sell_price": limit_sell_price,
            "limit_buy_band": limit_buy_band,
            "limit_sell_band": limit_sell_band,
            "bb_lower": bb_lower,
            "bb_upper": snap.get("bb_upper"),
            "high": high,
            "intrinsic_price": intrinsic_price,
            "pool_type": pool_type or "",
            "sm_score": sm_score,
            "piotroski_score": piotroski_score,
            "sipv_signal": sipv_signal,
            "ema_3": ema_3 if ema_3 is not None else snap.get("ema_3"),
            "ema_9": ema_9 if ema_9 is not None else snap.get("ema_9"),
            "ema_20": ema_20 if ema_20 is not None else snap.get("ema_20"),
            "bb_expanding": bb_expanding or bool(snap.get("bb_expanding", False)),
            "ema_exhaustion": ema_exhaustion or bool(snap.get("ema_exhaustion", False)),
            "ema3_cross_age": ema3_cross_age,
            "rsi_14": float(snap.get("rsi_14", 50.0)),
            "apex_signal": str(snap.get("apex_signal", "") or ""),
            "volume": float(snap.get("volume", 0) or 0),
            "low": float(snap.get("low", 0) or 0),
        }

    def evaluate_rule(self, rule: dict, context: dict) -> dict:
        """
        Evalúa una regla contra el contexto.
        Returns dict con triggered=True/False y razón.
        """
        checks = {}
        failures = []

        rule_code = rule["rule_code"]
        direction = rule["direction"]       # buy | sell
        order_type = rule["order_type"]     # market | limit

        # ── NUEVO: Soporte para parámetros extendidos vía JSON en 'notes' ──
        if rule.get("notes") and rule["notes"].strip().startswith("{"):
            try:
                import json
                extra = json.loads(rule["notes"])
                rule = {**rule, **extra}
            except: pass

        # ── VARIABLES DE CONTROL (Safety Definitions) ─────
        ia_val = float(context.get("ia_score") or 0)
        tech_val = float(context.get("tech_score") or 0)
        fund_val = float(context.get("fundamental_score") or 0)
        sm_val = float(context.get("sm_score") or 0)
        piot_val = int(context.get("piotroski_score") or 0)
        sipv_val = context.get("sipv_signal", "")
        current_price = float(context.get("close") or 0)

        # ── CHECK 0: Daily Timeframe Macro Trend (Anti-Crash Filter) ──
        if direction == "buy":
            ema_20_1d = float(context.get("ema_20_1d") or 0.0)
            ema_50_1d = float(context.get("ema_50_1d") or 0.0)
            ema_3_1d = float(context.get("ema_3_1d") or 0.0)
            ema_9_1d = float(context.get("ema_9_1d") or 0.0)
            
            # Bloquear entradas si la tendencia macro diaria (20 vs 50) es bajista
            if ema_20_1d > 0 and ema_50_1d > 0 and ema_20_1d < ema_50_1d:
                failures.append(f"1D Macro Bearish (No Buy): EMA20 ({ema_20_1d:.2f}) < EMA50 ({ema_50_1d:.2f})")
                
            # Bloquear entradas si la tendencia local diaria (3 vs 9) es bajista
            if ema_3_1d > 0 and ema_9_1d > 0 and ema_3_1d < ema_9_1d:
                failures.append(f"1D Local Bearish (No Buy): EMA3 ({ema_3_1d:.2f}) < EMA9 ({ema_9_1d:.2f})")
                
            # Bloquear entradas si la tendencia local en 15m es bajista pura (Cascada)
            ema_3_15m = float(context.get("ema_3") or 0.0)
            ema_9_15m = float(context.get("ema_9") or 0.0)
            ema_20_15m = float(context.get("ema_20") or 0.0)
            
            if ema_3_15m > 0 and ema_9_15m > 0 and ema_20_15m > 0:
                if ema_3_15m < ema_9_15m and ema_9_15m < ema_20_15m:
                    failures.append(f"15m Bearish Waterfall (No Buy): EMA3 ({ema_3_15m:.2f}) < EMA9 ({ema_9_15m:.2f}) < EMA20 ({ema_20_15m:.2f})")


        # ── CHECK 1: IA Score ─────────────────────────────
        ia_min = float(rule.get("ia_min") or 0)
        if ia_min > 0:
            ia_ok = ia_val >= ia_min
            checks["ia_score"] = {
                "passed": ia_ok,
                "value": ia_val,
                "required": ia_min,
            }
            if not ia_ok:
                failures.append(f"IA {ia_val:.1f} < {ia_min}")

        # ── CHECK 2: Technical Score ──────────────────────
        tech_min = float(rule.get("tech_score_min") or 0)
        if tech_min > 0:
            tech_ok = tech_val >= tech_min
            checks["tech_score"] = {
                "passed": tech_ok,
                "value": tech_val,
                "required": tech_min,
            }
            if not tech_ok:
                failures.append(f"Tech {tech_val:.0f} < {tech_min}")

        # ── CHECK 2.5: Fundamental Score (Universe) ──────
        fund_min = float(rule.get("fundamental_score_min") or (70.0 if rule_code == "PRO_BUY_MKT" else 0.0))
        
        # BYPASS para Scalping/HOT
        is_hot = "HOT" in str(context.get("pool_type", "")).upper()
        if is_hot:
            fund_min = 0.0
            
        if fund_min > 0:
            fund_ok = fund_val >= fund_min
            checks["fundamental"] = {
                "passed": fund_ok,
                "value": fund_val,
                "required": fund_min,
            }
            if not fund_ok:
                failures.append(f"Fundamental {fund_val:.0f} < {fund_min}")

        # ── CHECK 3: Tipo de Movimiento ───────────────────
        movements = rule.get("movements_allowed") or []
        if movements:
            mv_ok = context.get("movement_type", "") in movements
            checks["movement"] = {
                "passed": mv_ok,
                "value": context.get("movement_type"),
                "required": movements,
            }
            if not mv_ok:
                failures.append(
                    f'Movimiento "{context.get("movement_type")}" '
                    f"no en {movements}"
                )

        # ── CHECK 4: PineScript Signal ────────────────────
        pine_req = rule.get("pine_required", False)
        pine_rule = rule.get("pine_signal")
        fib_trig = rule.get("fib_trigger") or []

        if pine_req and pine_rule:
            # Pine signal REQUIRED
            pine_ok = context.get("pine_signal") == pine_rule
            checks["pine_signal"] = {
                "passed": pine_ok,
                "value": context.get("pine_signal"),
                "required": pine_rule,
            }
            if not pine_ok:
                failures.append(
                    f'Pine "{context.get("pine_signal")}" != "{pine_rule}"'
                )

        elif pine_rule and fib_trig:
            # OR logic: Pine OR Fibonacci
            pine_match = context.get("pine_signal") == pine_rule
            fib_match = int(context.get("fib_zone") or 0) in fib_trig
            signal_ok = pine_match or fib_match
            checks["pine_or_fib"] = {
                "passed": signal_ok,
                "pine_value": context.get("pine_signal"),
                "fib_value": context.get("fib_zone"),
                "fib_required": fib_trig,
            }
            if not signal_ok:
                failures.append(
                    f'Ni Pine="{pine_rule}" ni Fib en {fib_trig}'
                )

        elif fib_trig and not pine_rule:
            fib_ok = int(context.get("fib_zone") or 0) in fib_trig
            checks["fib_zone"] = {
                "passed": fib_ok,
                "value": context.get("fib_zone"),
                "required": fib_trig,
            }
            if not fib_ok:
                failures.append(
                    f'Fib {context.get("fib_zone")} no en {fib_trig}'
                )

        # ── CHECK 4.5: SM Score (Sentiment Market) ───────
        sm_min = float(rule.get("sm_min") or 0)
        if sm_min > 0:
            sm_ok = sm_val >= sm_min
            checks["sm_score"] = {
                "passed": sm_ok,
                "value": sm_val,
                "required": sm_min,
            }
            if not sm_ok:
                failures.append(f"SM {sm_val:.1f} < {sm_min}")

        # ── CHECK 4.6: Piotroski Score (F.Score) ─────────
        f_score_min = float(rule.get("f_score_min") or 0)
        
        if is_hot:
            f_score_min = 0.0
            
        if f_score_min > 0:
            f_ok = piot_val >= f_score_min
            checks["f_score"] = {
                "passed": f_ok,
                "value": piot_val,
                "required": f_score_min,
            }
            if not f_ok:
                failures.append(f"F.Score {piot_val} < {f_score_min}")

        # ── CHECK 4.7: SIPV Signal (Candle Pattern) ──────
        sipv_req = rule.get("sipv_required", False)
        sipv_rule = rule.get("sipv_signal")
        sipv_or_pine = rule.get("sipv_or_pine", False)

        if sipv_or_pine:
            # Lógica OR: Pine OR SIPV
            pine_match = context.get("pine_signal") == pine_rule if pine_rule else False
            sipv_match = sipv_val == sipv_rule if sipv_rule else False
            signal_ok = pine_match or sipv_match
            checks["pine_or_sipv"] = {
                "passed": signal_ok,
                "pine_val": context.get("pine_signal"),
                "sipv_val": sipv_val,
                "required": f"{pine_rule} OR {sipv_rule}"
            }
            if not signal_ok:
                failures.append(f'Ni Pine="{pine_rule}" ni SIPV="{sipv_rule}" presentes')
        
        else:
            # Lógica standard (AND si ambos están activos)
            if pine_req and pine_rule:
                pine_ok = context.get("pine_signal") == pine_rule
                checks["pine_signal"] = {
                    "passed": pine_ok,
                    "value": context.get("pine_signal"),
                    "required": pine_rule,
                }
                if not pine_ok:
                    failures.append(f'Pine "{context.get("pine_signal")}" != "{pine_rule}"')

            if sipv_req and sipv_rule:
                sipv_ok = sipv_val == sipv_rule
                checks["sipv_signal"] = {
                    "passed": sipv_ok,
                    "value": sipv_val,
                    "required": sipv_rule,
                }
                if not sipv_ok:
                    failures.append(f'SIPV "{sipv_val}" != "{sipv_rule}"')

        # ── CHECK 5: RVOL mínimo ─────────────────────────
        # Usar el rvol_min de la regla, o el global de Settings como piso (V5.1)
        global_rvol_min = float(self.config.get("rvol_min", 1.0))
        rvol_min = float(rule.get("rvol_min") or 0)
        
        # Si la regla no tiene rvol_min definido (>0), usamos el global
        effective_rvol_min = rvol_min if rvol_min > 0 else global_rvol_min

        if effective_rvol_min > 0:
            rvol_val = float(context.get("rvol", 0))
            rvol_ok = rvol_val >= effective_rvol_min
            checks["rvol"] = {
                "passed": rvol_ok,
                "value": rvol_val,
                "required": effective_rvol_min,
            }
            if not rvol_ok:
                failures.append(f"RVOL {rvol_val:.2f}x < {effective_rvol_min}x")

        # ── CHECK 6: Proximidad al precio LIMIT ──────────
        if order_type == "limit":
            limit_key = (
                "limit_buy_price" if direction == "buy"
                else "limit_sell_price"
            )
            est_price = context.get(limit_key)
            price = float(context.get("price") or 0)
            trigger = float(rule.get("limit_trigger_pct") or 0.005)

            if est_price and float(est_price) > 0:
                est_price = float(est_price)
                dist = abs(price - est_price) / est_price
                near_ok = dist <= trigger
                checks["limit_proximity"] = {
                    "passed": near_ok,
                    "distance_pct": round(dist * 100, 4),
                    "trigger_pct": trigger * 100,
                    "est_price": est_price,
                    "current_price": price,
                }
                if not near_ok:
                    failures.append(
                        f"Precio ${price:.2f} no dentro del "
                        f"{trigger*100:.1f}% del estimado "
                        f"${est_price:.2f} (dist={dist*100:.2f}%)"
                    )
            else:
                checks["limit_proximity"] = {
                    "passed": False,
                    "reason": "Precio estimado no disponible",
                }
                failures.append("Precio LIMIT estimado no calculado")

        # ── CHECK 5: Discount/Value Activation (S02 Specific) ─────
        smart_limit_price = None
        if rule_code == "S02" or rule_code == "PRO_BUY_LMT":
            # 1. IA Score lower threshold for discount buys
            s02_ia_ok = ia_val >= 6.0
            checks["ia_score_s02"] = {
                "passed": s02_ia_ok,
                "value": ia_val,
                "required": 6.0
            }
            if not s02_ia_ok:
                failures.append(f"IA {ia_val:.1f} < 6.0 (S02 requirement)")
            
            # 2. Bollinger Proximity Check
            bb_lower = context.get("bb_lower")
            if bb_lower and bb_lower > 0 and current_price > 0:
                # El precio debe estar a max 2% por ENCIMA del suelo (BB Lower)
                proximity = current_price / bb_lower
                prox_ok = proximity <= 1.02 
                checks["bb_proximity"] = {
                    "passed": prox_ok,
                    "price": current_price,
                    "bb_lower": bb_lower,
                    "dist_pct": round((proximity - 1) * 100, 2)
                }
                if not prox_ok:
                    failures.append(f"Price too far from BB Lower: {proximity:.2%} > 102%")
            
            # 3. Fundamental Score lower for discount buys
            s02_fund_ok = fund_val >= 65.0
            checks["fundamental_s02"] = {
                "passed": s02_fund_ok,
                "value": fund_val,
                "required": 65.0
            }
            if not s02_fund_ok:
                failures.append(f"Fundamental {fund_val:.0f} < 65.0 (S02 requirement)")

            # 4. Calculus of LIMIT Price (User Formula)
            intrinsic = float(context.get("intrinsic_price") or 0)
            if intrinsic > 0 and bb_lower and bb_lower > 0:
                smart_limit_price = round(min(bb_lower, intrinsic * 0.95, current_price * 0.97), 2)

        # ── CHECK 6: Value Deep Discount (S09 Specific) ──────────
        if rule_code == "S09" or rule_code == "PRO_BUY_VALUE":
            # 1. Pool check (FUTURE_GIANT or GROWTH_LEADER)
            pool = context.get("pool_type", "").upper()
            is_pro_pool = "GIANT" in pool or "LEADER" in pool
            checks["pool_filter"] = {
                "passed": is_pro_pool,
                "value": pool,
                "required": "GIANT or LEADER"
            }
            if not is_pro_pool:
                failures.append(f"Ticker no pertenece a GIANT/LEADER pool (Pool: {pool})")
            
            # 2. Deep Discount Check (Price <= Intrinsic * 0.90)
            intrinsic = float(context.get("intrinsic_price") or 0)
            if intrinsic > 0:
                discount_price = intrinsic * 0.90
                val_ok = current_price <= discount_price
                checks["value_discount"] = {
                    "passed": val_ok,
                    "price": current_price,
                    "target": round(discount_price, 2),
                    "discount_pct": round(((intrinsic - current_price) / intrinsic) * 100, 1)
                }
                if not val_ok:
                    failures.append(f"Descuento insuficiente: ${current_price} > ${discount_price:.2f} (Target: 10%)")
            else:
                failures.append("Precio Intrínseco no disponible para evaluación S09")

            # 3. Revenue Growth check (>= 20%)
            rev_growth = float(context.get("revenue_growth_yoy") or 0)
            if rev_growth < 20:
                failures.append(f"Revenue Growth {rev_growth}% < 20%")

            # 4. Calculus of LIMIT Price (Current Price for immediate fill)
            if len(failures) == 0:
                smart_limit_price = current_price # Comprar ya si está barato

        # ── CHECK 7: Regla Específica HOT_CANDLE (MOMENTUM V5.3) ──
        # Normalizar rule_code para capturar variaciones con sufijos (_BUY, _SELL)
        normalized_code = rule_code.replace("_BUY", "").replace("_SELL", "")
        if normalized_code == "HOT_CANDLE":
            ema3  = context.get("ema_3")
            ema9  = context.get("ema_9")
            ema20 = context.get("ema_20")
            bb_exp = context.get("bb_expanding", False)
            fib_z = int(context.get("fib_zone", 0))
            rvol  = float(context.get("rvol") or 1.0)
            vol_24h = float(context.get("volume") or 0)
            cross_age = int(context.get("ema3_cross_age", 999))
            bb_upper = float(context.get("bb_upper") or 99999)
            high_price = float(context.get("high") or 0)
            rsi = float(context.get("rsi_14") or 50.0)

            # ── Indicadores de 5 minutos ──
            ema3_5m  = float(context.get("ema_3_5m") or 0)
            ema9_5m  = float(context.get("ema_9_5m") or 0)
            ema20_5m = float(context.get("ema_20_5m") or 0)
            bb_exp_5m = bool(context.get("bb_expanding_5m", False))
            rsi_5m = float(context.get("rsi_5m") or 50.0)
            gap_exhaustion = bool(context.get("gap_up_exhaustion", False))
            
            # Requisito 1: Volumen Mínimo (Evitar acciones sin tracción)
            if vol_24h < 1_000_000:
                failures.append(f"Low Volume: {vol_24h/1e6:.1f}M < 1.0M (No traction)")

            # Requisito 2: Proyección de Volumen (RVOL)
            dynamic_rvol_min = float(self.config.get("rvol_min", 1.0))
            if rvol < dynamic_rvol_min:
                failures.append(f"Insufficient RVOL: {rvol:.2f}x < {dynamic_rvol_min}x (No momentum projection)")

            # Requisito 3: Momentum Técnico FRESCO (15m)
            ema_ok = (ema3 and ema9 and ema3 > ema9 and high_price <= bb_upper)
            if not (ema_ok or bb_exp):
                failures.append(f"No Fresh Momentum: Need (EMA3 > EMA9 AND High {high_price} <= BB_Upper {bb_upper}) OR (BB Expanding)")
            if rsi >= 60:
                failures.append(f"RSI Exhausted: {rsi:.1f} >= 60 (Overbought)")
            
            # Requisito 4: Alineación de tendencia (EMA20 como base)
            if ema3 and ema20 and ema3 < ema20:
                failures.append(f"Price below EMA20: {ema3:.2f} < {ema20:.2f} (Bearish trend)")

            # Requisito 5: Filtro Fibonacci (-6 hasta +2)
            fib_ok = -6 <= fib_z <= 2
            if not fib_ok:
                failures.append(f"Fibonacci Zone {fib_z} is OUT of range [-6, 2]")
            
            # Requisito 6: Evitar divergencia de agotamiento evidente
            if context.get("ema_exhaustion"):
                 if not bb_exp:
                      failures.append("Trend Exhaustion Detected: EMAs are stalling/diverging")

            # ── V5.3: Requisitos de precisión en 5 minutos ──
            
            # Requisito 7: Alineación EMA en 5 minutos (EMA3 > EMA9 > EMA20)
            if ema3_5m > 0 and ema9_5m > 0 and ema20_5m > 0:
                if not (ema3_5m > ema9_5m > ema20_5m):
                    failures.append(
                        f"5m EMA Misaligned: EMA3={ema3_5m:.2f} EMA9={ema9_5m:.2f} EMA20={ema20_5m:.2f} "
                        f"(Need EMA3 > EMA9 > EMA20 on 5m)"
                    )

            # Requisito 8: Expansión de Bollinger en 5m (bandas abriéndose)
            if not bb_exp_5m and not bb_exp:
                failures.append("5m BB Not Expanding: Bands not opening on 5m chart (Momentum not fresh)")

            # Requisito 9: RSI de 5 minutos no sobrecomprado
            if rsi_5m > 70:
                failures.append(f"5m RSI Overbought: {rsi_5m:.1f} > 70 (Intraday exhaustion)")

            # Requisito 10: Bloqueo por Gap Up Exhaustion
            if gap_exhaustion:
                gap_pct = float(context.get("gap_pct") or 0)
                failures.append(
                    f"Gap Up Exhaustion: Stock gapped {gap_pct:.1f}% and momentum has faded. "
                    f"Entry too late."
                )

        # ── CHECK 8: Regla Específica BOLLINGER_EXPLOSION (V5.3) ──
        if normalized_code == "BOLLINGER_EXPLOSION":
            bb_exp = context.get("bb_expanding", False)
            ema_exh = context.get("ema_exhaustion", False)
            rvol = float(context.get("rvol") or 1.0)
            ema3 = context.get("ema_3")
            ema9 = context.get("ema_9")
            rsi = float(context.get("rsi_14") or 50.0)
            high_price = float(context.get("high") or 0)
            bb_upper = float(context.get("bb_upper") or 99999)

            # ── Indicadores de 5 minutos ──
            ema3_5m  = float(context.get("ema_3_5m") or 0)
            ema9_5m  = float(context.get("ema_9_5m") or 0)
            ema20_5m = float(context.get("ema_20_5m") or 0)
            bb_exp_5m = bool(context.get("bb_expanding_5m", False))
            rsi_5m = float(context.get("rsi_5m") or 50.0)
            gap_exhaustion = bool(context.get("gap_up_exhaustion", False))
            
            # Requisito 1: Expansión de bandas activa (15m O 5m)
            if not bb_exp and not bb_exp_5m:
                failures.append("BB Not Expanding: Bands are not opening on any timeframe")
            
            # Requisito 2: Volumen masivo (RVOL > 1.0)
            if rvol < 1.0:
                failures.append(f"Low RVOL: {rvol:.2f} < 1.0x (Needed for explosion confirmation)")
            
            # Requisito 3: Alineación mínima EMA3 > EMA9 (15m)
            if ema3 and ema9 and ema3 < ema9:
                failures.append(f"EMA Bearish: EMA3 {ema3:.2f} < EMA9 {ema9:.2f}")

            # Requisito 4: No agotamiento
            if ema_exh:
                failures.append("EMA Exhaustion: EMA3 and EMA9 are too close (Possible reversal)")

            # Requisito 5: RSI Máximo (15m)
            if rsi > 65:
                failures.append(f"RSI Exhausted (Explosion): {rsi:.1f} > 65 (Overbought)")

            # Requisito 6: Evitar perforación de banda superior
            if high_price >= bb_upper:
                failures.append(f"Price outside band: High {high_price} >= BB_Upper {bb_upper}")

            # ── V5.3: Precisión 5 minutos ──

            # Requisito 7: Alineación EMA perfecta en 5 minutos
            if ema3_5m > 0 and ema9_5m > 0 and ema20_5m > 0:
                if not (ema3_5m > ema9_5m > ema20_5m):
                    failures.append(
                        f"5m EMA Misaligned: EMA3={ema3_5m:.2f} EMA9={ema9_5m:.2f} EMA20={ema20_5m:.2f} "
                        f"(Need perfect 5m alignment for explosion entry)"
                    )

            # Requisito 8: RSI 5m no sobrecomprado
            if rsi_5m > 70:
                failures.append(f"5m RSI Overbought: {rsi_5m:.1f} > 70 (Explosion already mature)")

            # Requisito 9: Bloqueo Gap Up Exhaustion
            if gap_exhaustion:
                gap_pct = float(context.get("gap_pct") or 0)
                failures.append(
                    f"Gap Up Exhaustion: Stock gapped {gap_pct:.1f}% and explosion is stale."
                )

        # ── CHECK 9: BLUE_DEEP_PULLBACK (APEX AZUL - Retroceso a EMA20) ──
        if normalized_code == "BLUE_DEEP_PULLBACK":
            apex_signal = str(context.get("apex_signal", ""))
            ema3_5m  = float(context.get("ema_3_5m") or 0)
            ema9_5m  = float(context.get("ema_9_5m") or 0)
            ema20_5m = float(context.get("ema_20_5m") or 0)
            rsi_5m   = float(context.get("rsi_5m") or 50.0)
            low_price = float(context.get("low") or 0)
            close_price = float(context.get("close") or 0)

            # Requisito 1: Solo para acciones APEX AZUL
            if apex_signal != "STRONG_BUY_BLUE":
                failures.append(f"Not APEX BLUE: signal={apex_signal}")

            # Requisito 2: LOW tocó EMA20 en 5m (pullback profundo)
            if ema20_5m > 0 and low_price > ema20_5m:
                failures.append(f"No Deep Pullback: LOW={low_price:.2f} > EMA20_5m={ema20_5m:.2f}")

            # Requisito 3: CLOSE sigue arriba de EMA20 (rebotó, no rompió)
            if ema20_5m > 0 and close_price <= ema20_5m:
                failures.append(f"Price broke EMA20: CLOSE={close_price:.2f} <= EMA20_5m={ema20_5m:.2f}")

            # Requisito 4: RSI limpio (no sobrecomprado)
            if rsi_5m >= 60:
                failures.append(f"RSI still hot: {rsi_5m:.1f} >= 60")

        # ── CHECK 10: BLUE_MOMENTUM_RESUME (APEX AZUL - Primer Cruce EMA3>EMA9) ──
        if normalized_code == "BLUE_MOMENTUM_RESUME":
            apex_signal = str(context.get("apex_signal", ""))
            ema3_5m  = float(context.get("ema_3_5m") or 0)
            ema9_5m  = float(context.get("ema_9_5m") or 0)
            ema20_5m = float(context.get("ema_20_5m") or 0)
            rsi_5m   = float(context.get("rsi_5m") or 50.0)

            # Requisito 1: Solo para acciones APEX AZUL
            if apex_signal != "STRONG_BUY_BLUE":
                failures.append(f"Not APEX BLUE: signal={apex_signal}")

            # Requisito 2: EMA3 > EMA9 en 5m (cruce alcista activo)
            if ema3_5m > 0 and ema9_5m > 0 and ema3_5m <= ema9_5m:
                failures.append(f"No bullish cross: EMA3_5m={ema3_5m:.2f} <= EMA9_5m={ema9_5m:.2f}")

            # Requisito 3: Cruce fresco (distancia < 0.3% = recién cruzó)
            if ema3_5m > 0 and ema9_5m > 0 and ema3_5m > ema9_5m:
                cross_dist = (ema3_5m - ema9_5m) / ema9_5m
                if cross_dist > 0.003:
                    failures.append(f"Cross not fresh: distance={cross_dist*100:.2f}% > 0.3%")

            # Requisito 4: RSI no sobrecomprado
            if rsi_5m >= 70:
                failures.append(f"RSI overbought: {rsi_5m:.1f} >= 70")

        # ── CHECK 11: BLUE_MICRO_PULLBACK (APEX AZUL - Descanso bajo EMA3) ──
        if normalized_code == "BLUE_MICRO_PULLBACK":
            apex_signal = str(context.get("apex_signal", ""))
            ema3_5m  = float(context.get("ema_3_5m") or 0)
            ema9_5m  = float(context.get("ema_9_5m") or 0)
            ema20_5m = float(context.get("ema_20_5m") or 0)
            rsi_5m   = float(context.get("rsi_5m") or 50.0)
            close_price = float(context.get("close") or 0)
            bb_upper = float(context.get("bb_upper") or 99999)

            # Requisito 1: Solo para acciones APEX AZUL
            if apex_signal != "STRONG_BUY_BLUE":
                failures.append(f"Not APEX BLUE: signal={apex_signal}")

            # Requisito 2: CLOSE < EMA3 (micro retroceso)
            if ema3_5m > 0 and close_price >= ema3_5m:
                failures.append(f"No micro pullback: CLOSE={close_price:.2f} >= EMA3_5m={ema3_5m:.2f}")

            # Requisito 3: CLOSE < BB_UPPER (dentro de la banda)
            if close_price >= bb_upper:
                failures.append(f"Above BB Upper: CLOSE={close_price:.2f} >= BB_UPPER={bb_upper:.2f}")

            # Requisito 4: Tendencia intacta EMA3 > EMA9 > EMA20
            if ema3_5m > 0 and ema9_5m > 0 and ema20_5m > 0:
                if not (ema3_5m > ema9_5m > ema20_5m):
                    failures.append(
                        f"Trend broken: EMA3={ema3_5m:.2f} EMA9={ema9_5m:.2f} EMA20={ema20_5m:.2f}"
                    )

            # Requisito 5: RSI no sobrecomprado
            if rsi_5m >= 70:
                failures.append(f"RSI overbought: {rsi_5m:.1f} >= 70")

        # ── RESULTADO FINAL ───────────────────────────────
        triggered = len(failures) == 0

        order_price = None
        if triggered:
            if order_type == "market":
                order_price = context.get("price")
            else:
                order_price = context.get(
                    "limit_buy_price" if direction == "buy"
                    else "limit_sell_price"
                )
            # Override with smart limit if calculated
            if smart_limit_price:
                order_price = smart_limit_price

        return {
            "triggered": triggered,
            "rule_code": rule_code,
            "direction": direction,
            "order_type": order_type,
            "group_name": rule.get("group_name"),
            "checks": checks,
            "failures": failures,
            "order_price": order_price,
            "close_all": rule.get("close_all", False),
            "dca_enabled": rule.get("dca_enabled", False),
            "dca_max_buys": rule.get("dca_max_buys", 3),
            "reason": (
                "OK: Todas las condiciones cumplidas"
                if triggered
                else f"FAIL: {', '.join(failures)}"
            ),
        }

    def evaluate_all(
        self,
        context: dict,
        group_name: str = None,
        direction: str = None,
    ) -> list:
        """
        Evalúa todas las reglas aplicables.
        Filtra por grupo y dirección si se indica.
        """
        results = []
        for code, rule in self.rules.items():
            if group_name and rule.get("group_name") and rule["group_name"] != group_name:
                continue
            if direction and rule["direction"] != direction:
                continue

            result = self.evaluate_rule(rule, context)
            results.append(result)

        return sorted(
            results,
            key=lambda x: (
                x["triggered"],
                x["order_type"] == "market",
            ),
            reverse=True,
        )
