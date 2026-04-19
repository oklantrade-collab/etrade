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
        self.load_rules()

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
    ) -> dict:
        """
        Construye el contexto de evaluación para un ticker.
        """
        price = float(snap.get("price", 0))
        close = float(snap.get("close", price))
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
            "intrinsic_price": intrinsic_price,
            "pool_type": pool_type or "",
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

        # ── CHECK 1: IA Score ─────────────────────────────
        ia_min = float(rule.get("ia_min") or 0)
        if ia_min > 0:
            ia_val = float(context.get("ia_score", 0))
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
            tech_val = float(context.get("tech_score", 0))
            tech_ok = tech_val >= tech_min
            checks["tech_score"] = {
                "passed": tech_ok,
                "value": tech_val,
                "required": tech_min,
            }
            if not tech_ok:
                failures.append(f"Tech {tech_val:.0f} < {tech_min}")

        # ── CHECK 2.5: Fundamental Score (Universe) ──────
        # Solo para empresas del Universe Builder (≥ 70)
        fund_min = float(rule.get("fundamental_score_min") or (70.0 if rule_code == "PRO_BUY_MKT" else 0.0))
        if fund_min > 0:
            fund_val = float(context.get("fundamental_score", 0))
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
            fib_match = context.get("fib_zone", 0) in fib_trig
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
            fib_ok = context.get("fib_zone", 0) in fib_trig
            checks["fib_zone"] = {
                "passed": fib_ok,
                "value": context.get("fib_zone"),
                "required": fib_trig,
            }
            if not fib_ok:
                failures.append(
                    f'Fib {context.get("fib_zone")} no en {fib_trig}'
                )

        # ── CHECK 5: RVOL mínimo ─────────────────────────
        rvol_min = float(rule.get("rvol_min") or 0)
        if rvol_min > 0:
            rvol_val = float(context.get("rvol", 0))
            rvol_ok = rvol_val >= rvol_min
            checks["rvol"] = {
                "passed": rvol_ok,
                "value": rvol_val,
                "required": rvol_min,
            }
            if not rvol_ok:
                failures.append(f"RVOL {rvol_val:.2f}x < {rvol_min}x")

        # ── CHECK 6: Proximidad al precio LIMIT ──────────
        if order_type == "limit":
            limit_key = (
                "limit_buy_price" if direction == "buy"
                else "limit_sell_price"
            )
            est_price = context.get(limit_key)
            price = context.get("price", 0)
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
        if rule_code == "S02" or rule_code == "PRO_BUY_LMT":
            # 1. IA Score lower threshold for discount buys
            s02_ia_ok = ia_val >= 6.0
            checks["ia_score"]["passed"] = s02_ia_ok
            checks["ia_score"]["required"] = 6.0
            if not s02_ia_ok:
                failures.append(f"IA {ia_val:.1f} < 6.0 (S02 requirement)")
            
            # 2. Bollinger Proximity Check
            bb_lower = context.get("bb_lower")
            current_price = context.get("close", 0)
            if bb_lower and current_price:
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
            if fund_min > 0:
                s02_fund_ok = fund_val >= 65.0
                checks["fundamental"]["passed"] = s02_fund_ok
                checks["fundamental"]["required"] = 65.0
                if not s02_fund_ok:
                    failures.append(f"Fundamental {fund_val:.0f} < 65.0 (S02 requirement)")

            # 4. Calculus of LIMIT Price (User Formula)
            intrinsic = context.get("intrinsic_price", 0)
            if intrinsic > 0 and bb_lower:
                limit_price = min(bb_lower, intrinsic * 0.95)
                # También aplicar el 'piso mínimo' de Price * 0.97 como seguridad adicional
                limit_price = min(limit_price, current_price * 0.97)
                result["smart_limit_price"] = round(limit_price, 2)

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
            intrinsic = context.get("intrinsic_price", 0)
            current_price = context.get("close", 0)
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
            # Nota: Esto se valida por el pool, pero re-confirmamos
            rev_growth = context.get("revenue_growth_yoy", 0) # Necesito que esto esté en context
            if rev_growth < 20:
                failures.append(f"Revenue Growth {rev_growth}% < 20%")

            # 4. Calculus of LIMIT Price (Current Price for immediate fill)
            if len(failures) == 0:
                result["smart_limit_price"] = current_price # Comprar ya si está barato

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
