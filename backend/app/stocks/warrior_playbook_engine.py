"""
warrior_playbook_engine.py — Ross Cameron Trading Experiences & Playbook Knowledge Engine

Estructura de datos y motor de inferencia que almacena, lee, analiza y aplica
las experiencias y estrategias de trading de Ross Cameron (Warrior Trading) para guiar
las decisiones tácticas de los robots automatizados de eTrade:
- Micro Pullbacks Scalper (micro_pullback_engine)
- Alpha Runner Scanner (alpha_runner_scanner)
- Warrior Momentum Options (warrior_momentum_options)
- Aduana Stocks Exit Engine (aduana_stocks_exit_engine)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Dict, List, Optional, Any
from app.core.logger import log_info, log_warning, log_error

MODULE = "WARRIOR_PLAYBOOK"

# =====================================================================
# DATA STRUCTURES / MODELS
# =====================================================================

@dataclass
class WarriorTradePhase:
    sequence_order: int
    phase_type: str  # FILTERING, ENTRY, SCALING_IN, SCALING_OUT, DIP_REBUY, EXIT
    price_level: float
    trigger_observed: str
    action_taken: str
    risk_factor: str
    result_outcome: str
    timestamp_or_time_str: Optional[str] = None
    shares: Optional[int] = None

@dataclass
class WarriorTrade:
    ticker: str
    archetype_code: str
    pnl: float
    duration_seconds: int
    sector: str
    float_shares: float
    running_surge_pct: float
    avg_entry_price: float
    avg_exit_price: float
    key_takeaway: str
    phases: List[WarriorTradePhase] = field(default_factory=list)
    peak_unrealized_pnl: float = 0.0
    giveback_pnl: float = 0.0
    max_shares_held: Optional[int] = None

@dataclass
class WarriorSession:
    session_date: str
    video_title: str
    video_url: str
    net_pnl: float
    account_mode: str
    prior_drawdown: float
    mental_state: str
    key_mindset_change: str
    stop_trading_discipline: str
    notes: str
    trades: List[WarriorTrade] = field(default_factory=list)

@dataclass
class PlaybookMatchResult:
    matched: bool
    archetype_code: Optional[str]
    archetype_name: Optional[str]
    similarity_score: float  # 0.0 a 1.0
    recommended_action: str  # BUY_VWAP_SUPPORT, ANTICIPATE_BREAKOUT, PYRAMID_SCALE_IN, BLOCK_200MA_RESISTANCE, WARN_DIP_SLIPPAGE, HOLD
    action_type: str         # 'EXECUTE_ENTRY', 'BLOCK_ENTRY', 'SCALE_IN', 'SCALE_OUT', 'SAFETY_GUARD'
    historical_trade_ref: str
    reasoning: str
    execution_params: Dict[str, Any] = field(default_factory=dict)
    lessons_learned: List[str] = field(default_factory=list)


# =====================================================================
# IN-MEMORY KNOWLEDGE BASE (SEED DATA EMBEBIDO DE ALTA FIDELIDAD)
# =====================================================================

SESSION_72K_CASE_STUDY = WarriorSession(
    session_date="2024-06-28",
    video_title="+$72,872.42 on 3 Explosive Stocks",
    video_url="https://www.youtube.com/watch?v=warrior_trading_72k_recap",
    net_pnl=72872.42,
    account_mode="main_account",
    prior_drawdown=-44000.00,
    mental_state="Racha negativa previa (-$37k y -$22k); foco disperso al operar simultáneamente cuenta pequeña y principal.",
    key_mindset_change="Puso la cuenta principal en primer plano y descartó la cuenta pequeña; recuperó velocidad crítica y ejecución instantánea sin delay.",
    stop_trading_discipline="Cerró la sesión tras la explosión de GEM (+46k). Dejó pasar otros gappers de +140% (como CZ) para blindar el balance y no sobreoperar.",
    notes="Cierre mensual por encima de $500,000 en ganancias acumuladas.",
    trades=[
        WarriorTrade(
            ticker="VWave",
            archetype_code="ROSS_VWAP_BOUNCE_CLEAN",
            pnl=10000.00,
            duration_seconds=300,
            sector="Defensa / Aeroespacial",
            float_shares=12_000_000,
            running_surge_pct=80.0,
            avg_entry_price=8.00,
            avg_exit_price=9.50,
            key_takeaway="Dejar pasar el 1er micro pullback si colisiona contra la 200 MA overhead. Comprar soporte limpio en VWAP.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="FILTERING",
                    price_level=9.00,
                    trigger_observed="Precio subió de $5 a $9 pero rozaba la media móvil de 200 períodos (200 MA).",
                    action_taken="Dejó pasar el primer micro pullback.",
                    risk_factor="200 MA actuaba como techo masivo de resistencia overhead.",
                    result_outcome="Evitó quedar atrapado en el falso quiebre inicial."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="ENTRY",
                    price_level=8.00,
                    trigger_observed="El precio cayó a $8.00 testeando con exactitud la línea del VWAP.",
                    action_taken="Compró soporte en VWAP buscando rebote limpio.",
                    risk_factor="Riesgo de pérdida de VWAP con stop loss bajo $7.80.",
                    result_outcome="Rebote explosivo inmediato con fuerte volumen comprador."
                ),
                WarriorTradePhase(
                    sequence_order=3,
                    phase_type="EXIT",
                    price_level=9.50,
                    trigger_observed="Precio disparado a $9.50 mostrando primeros indicios de volumen vendedor.",
                    action_taken="Vendió la posición completa para amarrar +$10,000.",
                    risk_factor="Agotamiento del impulso comprador en resistencia previa.",
                    result_outcome="Ganancia cerrada limpia; la acción se desplomó minutos más tarde."
                ),
            ]
        ),
        WarriorTrade(
            ticker="SVRE",
            archetype_code="ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT",
            pnl=16000.00,
            duration_seconds=480,
            sector="Tecnología / Detección Conducción",
            float_shares=6_500_000,
            running_surge_pct=120.0,
            avg_entry_price=6.98,
            avg_exit_price=8.50,
            peak_unrealized_pnl=18800.00,
            giveback_pnl=2800.00,
            key_takeaway="Entrada en consolidación montada sobre VWAP anticipando número redondo $7.00. En dips tardíos con alto spread, peligro de slippage.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="FILTERING",
                    price_level=8.33,
                    trigger_observed="Impulso temprano a $3.66 luego pico a $8.33 y posterior caída por debajo del VWAP perdiendo fuerza.",
                    action_taken="Omitió operar los picos iniciales desordenados.",
                    risk_factor="Acción sobreextendida con riesgo de atrapamiento de novatos.",
                    result_outcome="Esperó a que el gráfico construyera una estructura limpia."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="ENTRY",
                    price_level=6.98,
                    trigger_observed="Acción recupera y consolida por encima del VWAP construyendo base plana.",
                    action_taken="Entró en $6.98 para anticipar el quiebre del nivel psicológico de $7.00.",
                    risk_factor="Resistencia en $7.00 con órdenes vendedoras institucionales.",
                    result_outcome="Ruptura explosiva superando $7.00 con alta aceleración."
                ),
                WarriorTradePhase(
                    sequence_order=3,
                    phase_type="SCALING_OUT",
                    price_level=8.50,
                    trigger_observed="El precio explota sucesivamente hacia $7.50, $8.00 y $8.50–$9.00.",
                    action_taken="Fue vendiendo bloques parciales en la subida.",
                    risk_factor="Sobreextensión en temporalidad corta.",
                    result_outcome="Aseguró ganancias llegando a estar en +$18,800 no realizados."
                ),
                WarriorTradePhase(
                    sequence_order=4,
                    phase_type="DIP_REBUY",
                    price_level=8.00,
                    trigger_observed="Retroceso a soporte en $8.00.",
                    action_taken="Intentó recompra en dip con 10,000 acciones a $8.00.",
                    risk_factor="Deslizamiento (slippage) por ensanchamiento del spread Bid/Ask en Level 2.",
                    result_outcome="Saltó la orden de protección con deslizamiento devolviendo ~$2,800; cerró la emisora con +$16,000 netos."
                ),
            ]
        ),
        WarriorTrade(
            ticker="GEM",
            archetype_code="ROSS_RUNNING_UP_PYRAMID",
            pnl=46000.00,
            duration_seconds=120,
            sector="Gaming / Entretenimiento",
            float_shares=4_200_000,
            running_surge_pct=230.0,
            avg_entry_price=3.88,
            avg_exit_price=5.58,
            max_shares_held=60000,
            peak_unrealized_pnl=48000.00,
            key_takeaway="Scaling In agresivo en escáner Running Up (+230%) con bajo float. Venta total en pico de clímax parabólico en 2 minutos.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="FILTERING",
                    price_level=3.57,
                    trigger_observed="Escáner de volumen alerta que GEM cotiza a $3.57 subiendo más de 230%.",
                    action_taken="Reconoce catalizador de momentum extremo con bajo float.",
                    risk_factor="Alta velocidad de cinta y spreads dinámicos.",
                    result_outcome="Alinea órdenes de compra a mercado con confirmación Level 2."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="ENTRY",
                    price_level=3.70,
                    trigger_observed="Confirmación de aceleración de cinta en velas de 5s.",
                    action_taken="Compra bloque inicial de 15,000 acciones a $3.70.",
                    risk_factor="Volatilidad extrema.",
                    result_outcome="Entrada limpia con la cinta empujando al alza."
                ),
                WarriorTradePhase(
                    sequence_order=3,
                    phase_type="SCALING_IN",
                    price_level=3.95,
                    trigger_observed="Precio rompe con fuerza $3.80, $3.95 y $4.00.",
                    action_taken="Añade sucesivamente posiciones construyendo entre 45,000 y 60,000 acciones.",
                    risk_factor="Aumento de riesgo absoluto por volumen de acciones.",
                    result_outcome="Precio promedio de posición sube a $3.88 con impulso vertical."
                ),
                WarriorTradePhase(
                    sequence_order=4,
                    phase_type="SCALING_OUT",
                    price_level=4.20,
                    trigger_observed="Superación inicial de los $4.00.",
                    action_taken="Toma beneficios parciales en $4.20 para asegurar costo.",
                    risk_factor="Retroceso intradía rápido.",
                    result_outcome="Cero riesgo residual en la operación."
                ),
                WarriorTradePhase(
                    sequence_order=5,
                    phase_type="SCALING_IN",
                    price_level=5.00,
                    trigger_observed="Ruptura monumental del número entero psicológico de $5.00.",
                    action_taken="Agrega tamaño final para el empuje terminal.",
                    risk_factor="Clímax inminente.",
                    result_outcome="La acción vuela verticalmente hacia $5.50-$5.66."
                ),
                WarriorTradePhase(
                    sequence_order=6,
                    phase_type="EXIT",
                    price_level=5.58,
                    trigger_observed="Pico máximo alcanzado en $5.58 (el HOD diario fue $5.66) con absorción de venta.",
                    action_taken="Vende el bloque principal en el clímax absoluto.",
                    risk_factor="Reversión inmediata tipo caída libre tras agotar compradores.",
                    result_outcome="+$46,000 de beneficio neto cerrado en apenas 2 minutos de duración."
                ),
            ]
        ),
    ]
)

ARCHETYPES_CATALOG = {
    "ROSS_VWAP_BOUNCE_CLEAN": {
        "name": "Rebote Limpio en Soporte VWAP",
        "description": "Entrada en el soporte de VWAP tras un primer impulso fuerte. Evita el primer micro pullback si colisiona con resistencias mayores (ej. 200 MA overhead).",
        "ideal_time": "09:30-10:15 AM",
        "ideal_float_max": 20_000_000,
        "ideal_price_range": (2.00, 15.00),
        "pitfalls": ["200 MA overhead resistance", "Falling knife through VWAP"]
    },
    "ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT": {
        "name": "Ruptura de Consolidación sobre VWAP",
        "description": "Acción que tras un pico cae por debajo del VWAP y luego recupera posicionándose firmemente ENCIMA del VWAP en una base plana. Entrada anticipada al quiebre de números enteros/medios.",
        "ideal_time": "08:45-10:30 AM",
        "ideal_float_max": 15_000_000,
        "ideal_price_range": (1.50, 12.00),
        "pitfalls": ["Dip slippage on wide Level 2 spread", "Fakeout if tape stalls"]
    },
    "ROSS_RUNNING_UP_PYRAMID": {
        "name": "Pirámide Acelerada en Escáner Running Up",
        "description": "Acción con catalizador de volumen desproporcionado (+200%) en escáner de alta velocidad. Se entra con lote inicial y se escala agresivamente (scaling in) conforme rompe niveles de $0.10, $0.25 y $0.50.",
        "ideal_time": "08:30-09:45 AM",
        "ideal_float_max": 8_000_000,
        "ideal_price_range": (1.50, 8.00),
        "pitfalls": ["Chasing exhausted tape", "Holding through parabolic breakdown"]
    }
}


# =====================================================================
# MOTOR DE INFERENCIA EN TIEMPO REAL PARA EL ROBOT
# =====================================================================

class WarriorPlaybookEngine:
    """Motor de consulta y evaluación de oportunidades en vivo contra el Playbook de Ross Cameron."""

    def __init__(self):
        self._sessions: List[WarriorSession] = [SESSION_72K_CASE_STUDY]
        self._archetypes = ARCHETYPES_CATALOG

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Retorna todas las sesiones y bitácoras cargadas en el banco de datos."""
        return [asdict(s) for s in self._sessions]

    def get_session_by_date(self, target_date: str) -> Optional[Dict[str, Any]]:
        for s in self._sessions:
            if s.session_date == target_date:
                return asdict(s)
        return None

    def get_archetypes(self) -> Dict[str, Any]:
        return self._archetypes

    def evaluate_live_opportunity(self, context: Dict[str, Any]) -> PlaybookMatchResult:
        """
        Evalúa las variables en caliente de un ticker contra el banco de experiencias de Ross Cameron.
        
        Variables esperadas en context:
        - ticker: str
        - price: float
        - change_pct: float (ej: +230%)
        - vwap: float
        - sma_200: Optional[float] (Media Móvil de 200 periodos)
        - is_running_up: bool
        - float_shares: Optional[float]
        - spread_pct: Optional[float] (Spread Bid/Ask porcentual)
        - is_consolidating_above_vwap: Optional[bool]
        - tape_acceleration: Optional[bool] (Cinta verde rápida en 5s)
        """
        ticker = str(context.get("ticker", "")).upper()
        price = float(context.get("price", 0.0))
        vwap = float(context.get("vwap", 0.0))
        sma_200 = float(context.get("sma_200", 0.0)) if context.get("sma_200") else None
        change_pct = float(context.get("change_pct", 0.0))
        float_shares = float(context.get("float_shares", 10_000_000))
        spread_pct = float(context.get("spread_pct", 0.5))
        is_running_up = bool(context.get("is_running_up", False))
        is_consolidating_above_vwap = bool(context.get("is_consolidating_above_vwap", False))
        tape_acceleration = bool(context.get("tape_acceleration", False))

        # ── CASO A: GUARDIA DE SEGURIDAD 200 MA OVERHEAD (Lección VWave) ──
        if sma_200 and sma_200 > price and ((sma_200 - price) / price) < 0.025:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_VWAP_BOUNCE_CLEAN",
                archetype_name="Filtro de Resistencia 200 MA Overhead",
                similarity_score=0.95,
                recommended_action="BLOCK_MICRO_PULLBACK_200MA_RESISTANCE",
                action_type="BLOCK_ENTRY",
                historical_trade_ref="VWave (+$10,000)",
                reasoning=(
                    f"El precio (${price:.2f}) colisiona directamente contra la 200 MA (${sma_200:.2f}) a menos de 2.5% de distancia. "
                    f"Experiencia Ross Cameron en VWave: Dejar pasar el primer micro pullback porque la 200 MA actúa como techo masivo. "
                    f"Esperar a que el precio caiga y testee soporte limpio en VWAP (${vwap:.2f})."
                ),
                execution_params={"block_entries_until_vwap_tested": True, "target_vwap": vwap},
                lessons_learned=[
                    "No comprar el primer micro pullback contra la 200 MA",
                    "Esperar absorción limpia en VWAP"
                ]
            )

        # ── CASO B: REBOTE LIMPIO EN SOPORTE VWAP (Lección VWave) ──
        if vwap > 0 and abs(price - vwap) / vwap <= 0.012 and change_pct >= 25.0:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_VWAP_BOUNCE_CLEAN",
                archetype_name="Rebote Limpio en Soporte VWAP",
                similarity_score=0.92,
                recommended_action="BUY_VWAP_SUPPORT",
                action_type="EXECUTE_ENTRY",
                historical_trade_ref="VWave (+$10,000)",
                reasoning=(
                    f"El precio (${price:.2f}) está testeando con precisión el VWAP (${vwap:.2f}) con ganancia intradía previa de +{change_pct:.1f}%. "
                    f"Configuración idéntica a la entrada de Ross en VWave a $8.00: comprar soporte en VWAP buscando rebote rápido y vender al primer clímax."
                ),
                execution_params={
                    "entry_type": "LIMIT_ON_VWAP",
                    "stop_loss_pct": 2.5,
                    "target_take_profit_pct": 12.0,
                    "max_hold_minutes": 10
                },
                lessons_learned=[
                    "Comprar soporte en VWAP con confirmación de rebote",
                    "Vender de inmediato al notar primer volumen vendedor pesado"
                ]
            )

        # ── CASO C: CORREDOR MASIVO RUNNING UP CON ESCALAMIENTO PIRAMIDAL (Lección GEM) ──
        if (change_pct >= 150.0 or is_running_up) and float_shares <= 8_000_000 and tape_acceleration:
            # Calcular proximidad a números enteros y medios
            cents_part = round(price % 1.0, 2)
            is_near_breakout = cents_part in [0.70, 0.80, 0.95, 0.00, 0.48, 0.50]
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_RUNNING_UP_PYRAMID",
                archetype_name="Pirámide Acelerada en Escáner Running Up",
                similarity_score=0.96,
                recommended_action="PYRAMID_SCALE_IN",
                action_type="SCALE_IN",
                historical_trade_ref="GEM (+$46,000 en 2 minutos)",
                reasoning=(
                    f"{ticker} subiendo +{change_pct:.1f}% con bajo float ({float_shares/1e6:.1f}M) y aceleración de cinta. "
                    f"Configuración GEM: Ross construyó posición masiva de 15k a 60k acciones añadiendo en cada ruptura ($3.70, $3.80, $3.95, $4.00, $5.00) "
                    f"y liquidando en el clímax absoluto en $5.58."
                ),
                execution_params={
                    "initial_tranche_pct": 30,
                    "scale_in_step_cents": 0.15,
                    "max_pyramid_tranches": 4,
                    "climax_exit_rule": "SELL_100_ON_FIRST_RED_5S_CANDLE",
                    "max_seconds_in_trade": 180
                },
                lessons_learned=[
                    "Añadir agresivamente a la posición ganadora mientras la cinta imprima verde sin titubear",
                    "Tomar parciales en números enteros ($4.00, $5.00)",
                    "Vender bloque completo en clímax; no intentar aguantar retrocesos en movimientos parabólicos"
                ]
            )

        # ── CASO D: CONSOLIDACIÓN POR ENCIMA DE VWAP (Lección SVRE) ──
        if is_consolidating_above_vwap and price > vwap:
            # Verificar peligro de slippage si el spread es ancho
            if spread_pct > 1.5:
                return PlaybookMatchResult(
                    matched=True,
                    archetype_code="ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT",
                    archetype_name="Alerta Anti-Slippage en Consolidación VWAP",
                    similarity_score=0.88,
                    recommended_action="WARN_DIP_SLIPPAGE_LIMIT_ONLY",
                    action_type="SAFETY_GUARD",
                    historical_trade_ref="SVRE (Devolución de -$2,800)",
                    reasoning=(
                        f"Spread Bid/Ask elevado ({spread_pct:.2f}%). Lección de Ross en SVRE: Intentó recompra en dip a $8.00, "
                        f"el spread se abrió y saltó su stop con slippage devolviendo $2,800. Prohibidas órdenes MARKET; usar LIMIT o reducir lote 60%."
                    ),
                    execution_params={"allow_market_orders": False, "size_reduction_pct": 50},
                    lessons_learned=["Evitar recompras tardías en dips si el Level 2 muestra spread abierto"]
                )

            # Consolidación sana con spread estrecho: anticipar ruptura de número entero
            cents_away = round((int(price) + 1.0) - price, 2)
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT",
                archetype_name="Ruptura de Consolidación sobre VWAP",
                similarity_score=0.90,
                recommended_action="ANTICIPATE_WHOLE_NUMBER_BREAKOUT",
                action_type="EXECUTE_ENTRY",
                historical_trade_ref="SVRE (+$16,000 netos)",
                reasoning=(
                    f"Consolidación plana por encima de VWAP (${vwap:.2f}) a ${cents_away:.2f} de romper el número entero. "
                    f"Caso SVRE: Entrada en $6.98 anticipando el quiebre de $7.00. Salida escalonada (Scaling Out) en impulsos hacia arriba."
                ),
                execution_params={
                    "entry_cents_before_whole": 0.03,
                    "scaling_out_targets": [price * 1.08, price * 1.15, price * 1.25],
                    "stop_loss_level": vwap * 0.99
                },
                lessons_learned=[
                    "Entrar en consolidación sobre VWAP anticipando el número entero",
                    "Escalar ventas (Scaling Out) para asegurar beneficios en la subida"
                ]
            )

        # ── SIN COINCIDENCIA DIRECTA ──
        return PlaybookMatchResult(
            matched=False,
            archetype_code=None,
            archetype_name=None,
            similarity_score=0.0,
            recommended_action="HOLD_OBSERVE",
            action_type="HOLD",
            historical_trade_ref="Ninguna",
            reasoning=f"Las condiciones de {ticker} (${price:.2f}, {change_pct:+.1f}%) no cumplen los criterios de alta convicción del Playbook de Ross Cameron.",
            execution_params={},
            lessons_learned=[]
        )


# Singleton del motor
warrior_playbook = WarriorPlaybookEngine()
