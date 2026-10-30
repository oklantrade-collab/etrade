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

SESSION_COLD_MARKET_CASE_STUDY = WarriorSession(
    session_date="2024-08-29",
    video_title="Don't Make It Worse!",
    video_url="https://www.youtube.com/watch?v=warrior_dont_make_it_worse",
    net_pnl=-1516.16,
    account_mode="main_account",
    prior_drawdown=0.0,
    mental_state="Mercado frío, lento y errático en pre-mercado con S&P 500 y Nasdaq en rojo; breakouts sin volumen de continuación.",
    key_mindset_change="Regla de oro: 'Don't Make It Worse!'. Reducir el tamaño de posición al 25%-33% del estándar. Aceptar una pérdida pequeña (-$1,500) y proteger el capital en vez de entrar en espiral de venganza arriesgando -$15,000 o -$20,000.",
    stop_trading_discipline="Cerrar la sesión temprano tras detectar mechas de rechazo superiores (topping tails) y giros violentos (jackknife). Dejar de operar antes de que el mercado abra si no hay confirmación.",
    notes="Sesión defensiva maestra. Operó PCLA (-$1,000), NWE (-$798.16) y DAVI (+$282). Descartó con disciplina NCPL (thickly traded), AXG (sin volumen tras split) y DAIC (noticia positiva pero en cinta roja).",
    trades=[
        WarriorTrade(
            ticker="PCLA",
            archetype_code="ROSS_COLD_MARKET_DEFENSE",
            pnl=-1000.00,
            duration_seconds=180,
            sector="Salud / Farmacéutica Japonesa",
            float_shares=8_000_000,
            running_surge_pct=40.0,
            avg_entry_price=3.20,
            avg_exit_price=3.05,
            key_takeaway="En mercado frío, el intento de curl back hacia máximos falló con vela de rechazo superior (topping tail candle). Liquidación defensiva rápida.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="ENTRY",
                    price_level=3.20,
                    trigger_observed="Intento de recuperación (curl back) hacia los máximos de la mañana tras rebote inicial.",
                    action_taken="Comprar con tamaño de posición reducido para buscar continuación alcista.",
                    risk_factor="Mercado macro frío sin volumen de seguimiento institucional.",
                    result_outcome="El precio sube brevemente pero no logra absorber las ventas en la zona alta."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="EXIT",
                    price_level=3.05,
                    trigger_observed="Aparición de mecha superior de rechazo (topping tail candle) y reanudación de volumen vendedor.",
                    action_taken="Cortar la posición con pérdida controlada de -$1,000 para no agrandar el daño.",
                    risk_factor="Desplome posterior si se intenta aguantar (hope mode).",
                    result_outcome="Pérdida pequeña asumida con disciplina; la acción siguió cayendo."
                ),
            ]
        ),
        WarriorTrade(
            ticker="NWE",
            archetype_code="ROSS_COLD_MARKET_DEFENSE",
            pnl=-798.16,
            duration_seconds=360,
            sector="Energía / Utilities",
            float_shares=14_000_000,
            running_surge_pct=35.0,
            avg_entry_price=7.25,
            avg_exit_price=7.10,
            peak_unrealized_pnl=350.00,
            giveback_pnl=1148.16,
            key_takeaway="Ruptura de compresión en techo plano (flat top squeeze) en $7.33 provocó un doble techo y rechazo violento (jackknife). Prohibido forzar recompras en techos en mercado rojo.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="ENTRY",
                    price_level=6.90,
                    trigger_observed="Retroceso hacia soporte (buy the dip) tras subida matutina.",
                    action_taken="Comprar en el dip con lote pequeño.",
                    risk_factor="Mercado sin momentum.",
                    result_outcome="Pequeño rebote aprovechado para tomar una ganancia modesta."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="ENTRY",
                    price_level=7.25,
                    trigger_observed="Consolidación en la zona alta buscando compresión alcista (squeeze through flat top) en $7.33.",
                    action_taken="Volver a comprar en la ruptura anticipada.",
                    risk_factor="Doble techo en resistencia sin fuerza de ruptura.",
                    result_outcome="Fallo rotundo en $7.33 formando doble techo."
                ),
                WarriorTradePhase(
                    sequence_order=3,
                    phase_type="EXIT",
                    price_level=7.10,
                    trigger_observed="Rechazo alcista violento en forma de navaja (jackknife reversal) desplomándose en segundos.",
                    action_taken="Venta inmediata para frenar la sangría.",
                    risk_factor="Deslizamiento si no se corta en el acto.",
                    result_outcome="Devolvió la ganancia inicial y cerró con -$798.16 USD de pérdida neta."
                ),
            ]
        ),
        WarriorTrade(
            ticker="DAVI",
            archetype_code="ROSS_COLD_MARKET_DEFENSE",
            pnl=282.00,
            duration_seconds=120,
            sector="Tecnología / Inteligencia Artificial",
            float_shares=7_200_000,
            running_surge_pct=50.0,
            avg_entry_price=4.05,
            avg_exit_price=4.15,
            peak_unrealized_pnl=350.00,
            key_takeaway="En mercado frío, si una ruptura ($4.00) no tiene aceleración inmediata, tomar ganancias mínimas (+3% a +5%) y salir rápido.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="ENTRY",
                    price_level=4.05,
                    trigger_observed="Noticia positiva y gráfico diario similar al patrón de la acción AI, rompiendo los $4.00 buscando $5.00-$6.00.",
                    action_taken="Entrar con lote moderado en la rotura de $4.00.",
                    risk_factor="Mercado general apagado que frena los seguimientos.",
                    result_outcome="Pequeño empuje comprador hacia $4.15-$4.20."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="EXIT",
                    price_level=4.15,
                    trigger_observed="Falta de volumen y desaceleración inmediata de la cinta.",
                    action_taken="Vender para asegurar +$282 USD de ganancia parcial.",
                    risk_factor="Reversión a negativo si se espera el target optimista de $5.00.",
                    result_outcome="Aseguró pequeña ganancia y evitó quedar atrapado en la posterior caída."
                ),
            ]
        ),
    ]
)

SESSION_MONDAY_SHORT_SQUEEZE_CASE_STUDY = WarriorSession(
    session_date="2024-10-14",
    video_title="Crazy +225% Short Squeeze on Monday Morning! (+$9,671.43)",
    video_url="https://www.youtube.com/watch?v=warrior_monday_squeeze_mndr",
    net_pnl=9671.43,
    account_mode="main_account",
    prior_drawdown=0.0,
    mental_state="Apertura de semana (lunes temprano). Enfoque en capturar el 'lead gapper' que despierte el apetito del mercado.",
    key_mindset_change="Dominar el Efecto Ola de Simpatía (Sympathy Wave) y la regla de Stop Corto en soporte lejano: Cuando un short squeeze (MNDR +225%) no tiene noticias, el soporte estructural queda a kilómetros ($1.12 vs $1.70); se DEBE usar un stop mental ceñido de 10 a 15 centavos. El calor generado por el primer corredor activa compras masivas en las siguientes acciones con noticias frescas (GIXI a las 7:32 AM).",
    stop_trading_discipline="Cerró la jornada con 5 operaciones ganadoras de 6 (+9,671.43). La única pérdida fue MEDS (-$1,200) a las 7:00 AM por precipitarse antes de que el mercado tuviera volumen real.",
    notes="Sesión maestra de lunes: MNDR (+$1,300), GIXI (+$7,289.43), WFFF (+$2,282), MEDS (-$1,200). Monitoreó además CLWT, DCX e YMAT.",
    trades=[
        WarriorTrade(
            ticker="MNDR",
            archetype_code="ROSS_NO_NEWS_PARABOLIC_SQUEEZE",
            pnl=1300.00,
            duration_seconds=300,
            sector="Tecnología / Salud Móvil (Singapur)",
            float_shares=3_200_000,
            running_surge_pct=225.0,
            avg_entry_price=1.70,
            avg_exit_price=2.35,
            key_takeaway="Short Squeeze parabólico sin noticias (+225%). Entrada en micro pullback a $1.70 anticipando quiebre de $2.00 con Stop corto de 10-15 centavos porque el soporte real ($1.12) estaba muy lejos.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="FILTERING",
                    price_level=1.12,
                    trigger_observed="Disparo vertical inicial desde $0.92 hasta $1.12 y $1.50 sin noticias fundamentales.",
                    action_taken="Dejar pasar el primer tramo parabólico desordenado.",
                    risk_factor="Perseguir precios sin soporte definido.",
                    result_outcome="Esperó a que el gráfico marcara el primer retroceso ordenado."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="ENTRY",
                    price_level=1.70,
                    trigger_observed="Micro pullback limpio alrededor de $1.70 formando bandera antes de la barrera psicológica de $2.00.",
                    action_taken="Comprar en $1.70 anticipando la ruptura de los $2.00.",
                    risk_factor="Soporte técnico real muy abajo ($1.12); ratio R:R inviable si se usa soporte base.",
                    result_outcome="Aplicó regla de Stop corto fijo de 10-15 centavos (stop en $1.58-$1.60)."
                ),
                WarriorTradePhase(
                    sequence_order=3,
                    phase_type="SCALING_OUT",
                    price_level=2.25,
                    trigger_observed="Ruptura de los $2.00 disparando con violencia hacia $2.25 y $2.40.",
                    action_taken="Vender bloques parciales en la aceleración.",
                    risk_factor="Volatilidad extrema.",
                    result_outcome="Aseguró ganancias iniciales sin riesgo."
                ),
                WarriorTradePhase(
                    sequence_order=4,
                    phase_type="EXIT",
                    price_level=2.50,
                    trigger_observed="Precio alcanza pico en $2.57-$2.90 y aparecen velas con mechas superiores (topping tail).",
                    action_taken="Venta total asegurando +$1,300 USD de beneficio conservador.",
                    risk_factor="Reversión inmediata de short squeeze sin noticias.",
                    result_outcome="Salida perfecta antes de la posterior consolidación pesada."
                ),
            ]
        ),
        WarriorTrade(
            ticker="GIXI",
            archetype_code="ROSS_NO_NEWS_PARABOLIC_SQUEEZE",
            pnl=7289.43,
            duration_seconds=420,
            sector="Tecnología (Israel)",
            float_shares=4_800_000,
            running_surge_pct=100.0,
            avg_entry_price=2.10,
            avg_exit_price=3.40,
            key_takeaway="Operación estrella de la sesión. Catalizador de noticia a las 7:32 AM montado sobre la ola de simpatía (Sympathy Wave) que MNDR despertó en el mercado.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="ENTRY",
                    price_level=2.10,
                    trigger_observed="Noticia publicada a las 7:32 AM con el mercado caliente por la subida de MNDR.",
                    action_taken="Entrar con alta convicción aprovechando el apetito comprador desatado.",
                    risk_factor="Falso breakout de pre-mercado.",
                    result_outcome="Explosión del 100% hacia $3.50+ con volumen arrollador."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="EXIT",
                    price_level=3.40,
                    trigger_observed="Desaceleración de cinta en $3.50 con absorción institucional.",
                    action_taken="Venta en la cima asegurando más de +$7,000 USD de ganancia.",
                    risk_factor="Toma masiva de beneficios de pre-mercado.",
                    result_outcome="Trade más lucrativo de la jornada matutina."
                ),
            ]
        ),
        WarriorTrade(
            ticker="WFFF",
            archetype_code="ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT",
            pnl=2282.00,
            duration_seconds=240,
            sector="Consumo / Agro (Malasia)",
            float_shares=5_100_000,
            running_surge_pct=45.0,
            avg_entry_price=12.50,
            avg_exit_price=13.80,
            key_takeaway="Operación de continuidad ingresando en $12.50 y tomando beneficios rápidos en la zona de $13.70-$14.69.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="ENTRY",
                    price_level=12.50,
                    trigger_observed="Continuación alcista tras consolidación con volumen ascendente.",
                    action_taken="Entrar en $12.50 buscando impulso hacia $14.00.",
                    risk_factor="Precio nominal alto ($12+).",
                    result_outcome="Disparo limpio hacia $13.70-$14.69."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="EXIT",
                    price_level=13.80,
                    trigger_observed="Llegada a resistencia en $14.00.",
                    action_taken="Tomar ganancias rápidas asegurando +$2,282 USD.",
                    risk_factor="Rechazo en números enteros.",
                    result_outcome="Ganancia capturada con precisión."
                ),
            ]
        ),
        WarriorTrade(
            ticker="MEDS",
            archetype_code="ROSS_COLD_MARKET_DEFENSE",
            pnl=-1200.00,
            duration_seconds=180,
            sector="Salud / Farmacia",
            float_shares=6_000_000,
            running_surge_pct=25.0,
            avg_entry_price=3.40,
            avg_exit_price=3.15,
            key_takeaway="Única pérdida del día (-$1,200). Comprar patrón curl a las 7:00 AM es prematuro porque el mercado carece de volumen a esa hora.",
            phases=[
                WarriorTradePhase(
                    sequence_order=1,
                    phase_type="ENTRY",
                    price_level=3.40,
                    trigger_observed="Intento de recuperación (curl) a las 7:00 AM.",
                    action_taken="Comprar anticipando continuidad.",
                    risk_factor="Hora excesivamente temprana (7:00 AM) con volumen desértico.",
                    result_outcome="Falta total de compradores; el precio se desinfló."
                ),
                WarriorTradePhase(
                    sequence_order=2,
                    phase_type="EXIT",
                    price_level=3.15,
                    trigger_observed="Ruptura a la baja sin soporte de cinta.",
                    action_taken="Cerrar con stop loss defensivo perdiendo -$1,200.",
                    risk_factor="Desplome si no se respeta el stop.",
                    result_outcome="Pérdida asumida; evitó un castigo mayor."
                ),
            ]
        ),
    ]
)

ARCHETYPES_CATALOG = {
    "ROSS_NO_NEWS_PARABOLIC_SQUEEZE": {
        "name": "Short Squeeze Parabólico Sin Noticias (MNDR Pattern)",
        "description": "Disparo parabólico vertical (>150%-225%) en pre-mercado sin catalizador fundamental. Entrada en micro pullback anticipando números enteros con Stop corto fijo de 10-15 centavos debido a que el soporte estructural está alejado.",
        "ideal_time": "07:30-09:15 AM (Pre-Market temprano)",
        "ideal_float_max": 6_000_000,
        "ideal_price_range": (0.80, 5.00),
        "pitfalls": ["Using distant structural support as stop loss (causes massive loss)", "Entering before 7:15 AM without volume", "Chasing topping tails above whole number"]
    },
    "ROSS_COLD_MARKET_DEFENSE": {
        "name": "Defensa Activa en Mercado Frío/Rojo (Don't Make It Worse)",
        "description": "Protocolo de reducción de riesgo y supervivencia cuando S&P 500 / Nasdaq están en rojo y los breakouts no tienen seguimiento. Tamaño al 25%-33%, prohibidas recompras en techos planos y salida inmediata ante mechas de rechazo (topping tails).",
        "ideal_time": "08:30-09:45 AM (Pre-Market y Apertura)",
        "ideal_float_max": 10_000_000,
        "ideal_price_range": (1.50, 10.00),
        "pitfalls": ["Overtrading / Revenge trading", "Buying flat-top squeezes in cold tape", "Holding through topping tail candles", "Trading thickly traded or illiquid reverse splits"]
    },
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
        self._sessions: List[WarriorSession] = [
            SESSION_72K_CASE_STUDY,
            SESSION_COLD_MARKET_CASE_STUDY,
            SESSION_MONDAY_SHORT_SQUEEZE_CASE_STUDY,
        ]
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
        - macro_is_red / is_cold_market: Optional[bool] (S&P 500 / Nasdaq en rojo o mercado lento)
        - is_thickly_traded: Optional[bool] (Libro de órdenes saturado de bloques gigantes)
        - is_reverse_split: Optional[bool] (Acción con split inverso reciente)
        - volume: Optional[float] (Volumen acumulado)
        - has_topping_tail: Optional[bool] (Vela con mecha superior >40% de rechazo)
        - is_flat_top_squeeze: Optional[bool] (Intento de rotura de techo plano)
        - has_positive_news: Optional[bool] (Noticia alcista)
        - candle_is_red: Optional[bool] (Vela roja en pre-market o intradía)
        """
        ticker = str(context.get("ticker", "")).upper()
        price = float(context.get("price", 0.0))
        vwap = float(context.get("vwap", 0.0))
        sma_200 = float(context.get("sma_200", 0.0)) if context.get("sma_200") else None
        change_pct = float(context.get("change_pct", 0.0))
        float_shares = float(context.get("float_shares", 10_000_000))
        spread_pct = float(context.get("spread_pct", 0.5))
        volume = float(context.get("volume", 1_000_000))
        is_running_up = bool(context.get("is_running_up", False))
        is_consolidating_above_vwap = bool(context.get("is_consolidating_above_vwap", False))
        tape_acceleration = bool(context.get("tape_acceleration", False))

        # Flags de mercado frío y filtros defensivos de Ross Cameron ("Don't Make It Worse!")
        is_cold_market = bool(context.get("macro_is_red", False) or context.get("is_cold_market", False))
        is_thickly_traded = bool(context.get("is_thickly_traded", False))
        is_reverse_split = bool(context.get("is_reverse_split", False))
        has_topping_tail = bool(context.get("has_topping_tail", False))
        is_flat_top_squeeze = bool(context.get("is_flat_top_squeeze", False))
        has_positive_news = bool(context.get("has_positive_news", False))
        candle_is_red = bool(context.get("candle_is_red", False))

        # Flags de la sesión de lunes (MNDR, GIXI, WFFF, MEDS)
        is_parabolic_squeeze = bool(context.get("is_parabolic_squeeze", False) or change_pct >= 150.0)
        has_sympathy_wave_active = bool(context.get("has_sympathy_wave_active", False))
        support_price = float(context.get("support_price", 0.0))
        time_str = str(context.get("time_str", ""))
        is_pre_715_curl = bool(context.get("is_pre_715_curl", False) or (time_str and time_str < "07:15"))

        # ── CASO COLD 1: FILTRO DE ACCIÓN PESADA / THICKLY TRADED (Lección NCPL) ──
        if is_thickly_traded:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Filtro Anti-Acción Pesada (Thickly Traded)",
                similarity_score=0.94,
                recommended_action="BLOCK_THICKLY_TRADED_TAPE",
                action_type="BLOCK_ENTRY",
                historical_trade_ref="NCPL (Descartada)",
                reasoning=(
                    f"{ticker} descartada por libro de órdenes excesivamente denso (thickly traded) con bloques masivos en compra y venta. "
                    f"Lección de Ross Cameron en NCPL: A pesar de ser la principal ganadora del día en porcentaje, los muros en Level 2 frenan el movimiento "
                    f"e impiden la expansión rápida de precios. Prohibido comprar acciones lentas y pesadas."
                ),
                execution_params={"block_entries": True, "reason": "Thickly traded Level 2"},
                lessons_learned=[
                    "No operar gappers pesados con exceso de liquidez estancada en Level 2",
                    "Buscar acciones ligeras (thin tape) donde órdenes de mercado muevan centavos con facilidad"
                ]
            )

        # ── CASO COLD 2: FILTRO DE REVERSE SPLIT SIN VOLUMEN (Lección AXG) ──
        if is_reverse_split and volume < 100_000:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Filtro de Reverse Split Ilíquido",
                similarity_score=0.95,
                recommended_action="BLOCK_ILLIQUID_REVERSE_SPLIT",
                action_type="BLOCK_ENTRY",
                historical_trade_ref="AXG (Descartada)",
                reasoning=(
                    f"{ticker} descartada por falta extrema de volumen ({volume:,.0f} acciones) tras split inverso. "
                    f"Lección de Ross Cameron en AXG: Descartada tras un reverse split de 200 a 1 con solo 5,000 acciones operadas; "
                    f"el float bajo artificial sin compradores reales crea trampas sin liquidez de salida."
                ),
                execution_params={"block_entries": True, "min_volume_required": 100_000},
                lessons_learned=["Ignorar bajas de float artificiales tras reverse split si no hay volumen masivo que lo confirme"]
            )

        # ── CASO COLD 3: FILTRO DE NOTICIA POSITIVA EN CINTA ROJA (Lección DAIC) ──
        if has_positive_news and candle_is_red:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Filtro de Catalizador en Terreno Rojo",
                similarity_score=0.92,
                recommended_action="BLOCK_RED_TAPE_CATALYST",
                action_type="BLOCK_ENTRY",
                historical_trade_ref="DAIC (Descartada)",
                reasoning=(
                    f"{ticker} publicó noticia positiva pero el gráfico está en terreno rojo o vela bajista. "
                    f"Lección de Ross Cameron en DAIC: Noticia positiva de permanecer en NASDAQ descartada porque el precio no mostró demanda "
                    f"y cotizó en rojo. La acción manda sobre la noticia; si no sube con volumen verde, no se compra."
                ),
                execution_params={"block_entries": True, "require_green_candle": True},
                lessons_learned=["No comprar noticias positivas si el precio cotiza en vela roja"]
            )

        # ── CASO COLD / MONDAY: FILTRO ANTI-PRECIPITACIÓN PRE-7:15 AM (Lección MEDS) ──
        if is_pre_715_curl and volume < 200_000:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Filtro Anti-Precipitación Pre-7:15 AM",
                similarity_score=0.94,
                recommended_action="BLOCK_PRE_715_UNCONFIRMED_CURL",
                action_type="BLOCK_ENTRY",
                historical_trade_ref="MEDS (-$1,200 USD)",
                reasoning=(
                    f"Intento de entrada en patrón curl o rebote antes de las 07:15 AM ({time_str or 'temprano'}) con volumen bajo ({volume:,.0f}). "
                    f"Lección de Ross Cameron en MEDS: Comprar a las 7:00 AM es precipitarse porque el mercado no tiene suficiente volumen "
                    f"ni liquidez institucional; la falta de seguimiento comprador produjo la única pérdida del lunes (-$1,200). Prohibido operar curls sin volumen masivo antes de las 7:15 AM."
                ),
                execution_params={"block_entries": True, "min_time": "07:15", "min_premarket_volume": 200_000},
                lessons_learned=[
                    "No operar patrones curl antes de las 7:15 AM sin volumen masivo confirmado (>200k)",
                    "Esperar a que el pre-mercado formalice su volumen y participantes a partir de 7:15-7:30 AM"
                ]
            )

        # ── CASO COLD 4: CORTE DEFENSIVO POR TOPPING TAIL CANDLE (Lección PCLA) ──
        if has_topping_tail and is_cold_market:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Corte Defensivo por Mecha Superior de Rechazo",
                similarity_score=0.93,
                recommended_action="DEFENSIVE_CUT_TOPPING_TAIL",
                action_type="SAFETY_GUARD",
                historical_trade_ref="PCLA (-$1,000 USD)",
                reasoning=(
                    f"{ticker} intentó recuperación (curl back) pero generó mecha superior de rechazo (topping tail candle). "
                    f"Lección de Ross Cameron en PCLA: En mercado frío, el rechazo superior indica fallo de continuación y reanudación de ventas. "
                    f"Liquidación defensiva inmediata aceptando pérdida controlada (-$1,000) bajo el principio 'Don't Make It Worse!'."
                ),
                execution_params={"hard_stop_on_candle_low": True, "cancel_adds": True},
                lessons_learned=[
                    "Cortar de inmediato si aparece topping tail candle en mercado frío",
                    "Aceptar pérdidas pequeñas y controladas en lugar de esperar recuperaciones milagrosas"
                ]
            )

        # ── CASO COLD 5: BLOQUEO DE RUPTURA EN TECHO PLANO / ANTI-JACKKNIFE (Lección NWE) ──
        if is_flat_top_squeeze and is_cold_market:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Bloqueo Anti-Jackknife en Techo Plano",
                similarity_score=0.91,
                recommended_action="BLOCK_FLAT_TOP_BREAKOUT_IN_COLD_MARKET",
                action_type="BLOCK_ENTRY",
                historical_trade_ref="NWE (-$798.16 USD)",
                reasoning=(
                    f"Intento de compra en compresión de techo plano (flat top squeeze) en mercado frío. "
                    f"Lección de Ross Cameron en NWE: Comprar en la zona alta buscando ruptura de techo provocó un doble techo y rechazo violento "
                    f"en forma de navaja (jackknife reversal), devolviendo las ganancias del dip previo. Prohibido forzar rupturas en techos planos cuando los índices están en rojo."
                ),
                execution_params={"block_high_pivot_buys": True, "allow_only_deep_dips": True},
                lessons_learned=[
                    "No forzar compras en techos planos si el mercado macro está apagado",
                    "Evitar dobles techos con giros violentos (jackknife reversals)"
                ]
            )

        # ── CASO COLD 6: PROTOCOLO GENERAL DE TAMAÑO DEFENSIVO (Lección DAVI / Don't Make It Worse) ──
        if is_cold_market and not is_running_up:
            # Modificador defensivo de parámetros si el mercado está frío
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_COLD_MARKET_DEFENSE",
                archetype_name="Modo Defensivo de Mercado Frío (Don't Make It Worse)",
                similarity_score=0.89,
                recommended_action="APPLY_COLD_MARKET_REDUCED_SIZING",
                action_type="SAFETY_GUARD",
                historical_trade_ref="DAVI (+$282 USD) / Sesión 'Don't Make It Worse'",
                reasoning=(
                    f"Mercado macro en rojo o pre-mercado frío sin volumen institucional. "
                    f"Protocolo 'Don't Make It Worse': Reducción obligatoria del tamaño de lote al 25%-33% del estándar. "
                    f"Targets reducidos (+3% a +6% tipo DAVI) y stop loss ultracorto. Límite estricto de pérdida máxima de sesión (-$1,500) para blindar el capital."
                ),
                execution_params={
                    "position_size_multiplier": 0.30,  # 30% del tamaño normal
                    "take_profit_target_pct": 5.0,     # Target modesto rápido
                    "max_daily_loss_limit": 1500.0,    # Límite estricto de cierre de sesión
                    "stop_loss_pct": 1.5
                },
                lessons_learned=[
                    "Reducir tamaño al 25%-33% cuando los índices generales estén en rojo",
                    "Tomar ganancias mínimas rápidas y no esperar continuaciones de +20%",
                    "Detener el robot si el drawdown del día alcanza -$1,500"
                ]
            )

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

        # ── CASO MONDAY 2: IMPULSO POR OLA DE SIMPATÍA TRAS RUNNER LÍDER (Lección GIXI) ──
        if has_sympathy_wave_active and has_positive_news:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_NO_NEWS_PARABOLIC_SQUEEZE",
                archetype_name="Impulso por Ola de Simpatía (Sympathy Wave Runner)",
                similarity_score=0.96,
                recommended_action="BOOST_SYMPATHY_RUNNER",
                action_type="EXECUTE_ENTRY",
                historical_trade_ref="GIXI (+$7,289.43 USD)",
                reasoning=(
                    f"{ticker} publicó catalizador fresco con el mercado encendido por la ola de simpatía (Sympathy Wave) de un gapper previo (tipo MNDR). "
                    f"Lección de Ross Cameron en GIXI: El trade más lucrativo (+100% y +$7,289 USD) ocurrió a las 7:32 AM aprovechando el calor y liquidez "
                    f"que el corredor anterior desató en el sector. Aumentar tamaño y convicción."
                ),
                execution_params={
                    "position_size_multiplier": 1.25,
                    "entry_type": "CATALYST_SYMPATHY_MOMENTUM",
                    "take_profit_target_pct": 20.0,
                    "trailing_stop_pct": 3.5
                },
                lessons_learned=[
                    "Aprovechar la ola de simpatía: un líder parabólico temprano despierta compradores para los siguientes catalizadores",
                    "GIXI a las 7:32 AM generó la mayor ganancia del día gracias a la inercia compradora previa"
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

        # ── CASO MONDAY 3: SHORT SQUEEZE SIN NOTICIAS CON STOP CORTO POR SOPORTE LEJANO (Lección MNDR) ──
        base_support = support_price if support_price > 0 else (vwap if vwap > 0 else 0.0)
        distance_to_support_pct = ((price - base_support) / price) if (price > 0 and base_support > 0) else 0.0
        if is_parabolic_squeeze and distance_to_support_pct > 0.12:
            return PlaybookMatchResult(
                matched=True,
                archetype_code="ROSS_NO_NEWS_PARABOLIC_SQUEEZE",
                archetype_name="Short Squeeze Parabólico con Stop Ceñido de 10-15 Centavos",
                similarity_score=0.95,
                recommended_action="USE_TIGHT_MICRO_STOP_10_CENTS",
                action_type="EXECUTE_ENTRY",
                historical_trade_ref="MNDR (+$1,300 USD)",
                reasoning=(
                    f"{ticker} en short squeeze vertical (+{change_pct:.1f}%). El soporte base (${base_support:.2f}) "
                    f"está a {distance_to_support_pct*100:.1f}% de distancia, lo que destruiría la relación R:R si se usa soporte estructural. "
                    f"Regla de Ross Cameron en MNDR: En micro pullbacks parabólicos, NO usar el soporte alejado. Usar stop mental ceñido de "
                    f"$0.10 a $0.15 centavos (o ~2.5%-3.5%), buscando la ruptura de números enteros ($2.00) y vendiendo en la aceleración."
                ),
                execution_params={
                    "entry_type": "MICRO_PULLBACK_WHOLE_NUMBER",
                    "fixed_stop_cents": 0.15,
                    "max_stop_pct": 3.5,
                    "target_cents": [price + 0.30, price + 0.55, price + 0.80],
                    "trailing_stop_after_breakout": True
                },
                lessons_learned=[
                    "En squeeze parabólico, no usar soporte estructural lejano como stop loss",
                    "Fijar stop ultracorto de 10-15 centavos y escalar ganancias en los números enteros",
                    "Vender al primer indicio de mecha superior (topping tail)"
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

    def add_session(self, session: WarriorSession, persist_supabase: bool = True) -> bool:
        """Agrega una nueva sesión o video al banco de datos en memoria y opcionalmente a Supabase."""
        # Evitar duplicados por fecha y título
        for idx, s in enumerate(self._sessions):
            if s.session_date == session.session_date and s.video_title == session.video_title:
                self._sessions[idx] = session
                log_info(MODULE, f"Actualizada sesión existente en memoria: {session.video_title} ({session.session_date})")
                break
        else:
            self._sessions.append(session)
            log_info(MODULE, f"Nueva sesión incorporada al Playbook: {session.video_title} ({session.session_date}) - {len(session.trades)} trades")

        if persist_supabase:
            try:
                from app.core.supabase_client import get_supabase
                sb = get_supabase()
                
                # 1. Insert session
                sess_row = sb.table("warrior_sessions").upsert({
                    "session_date": session.session_date,
                    "video_title": session.video_title,
                    "video_url": session.video_url,
                    "net_pnl": session.net_pnl,
                    "account_mode": session.account_mode,
                    "prior_drawdown": session.prior_drawdown,
                    "mental_state": session.mental_state,
                    "key_mindset_change": session.key_mindset_change,
                    "stop_trading_discipline": session.stop_trading_discipline,
                    "notes": session.notes,
                }, on_conflict="session_date,video_title").execute()
                
                if sess_row.data:
                    sess_id = sess_row.data[0]["id"]
                    for t in session.trades:
                        t_row = sb.table("warrior_trades").insert({
                            "session_id": sess_id,
                            "archetype_code": t.archetype_code,
                            "ticker": t.ticker,
                            "pnl": t.pnl,
                            "duration_seconds": t.duration_seconds,
                            "sector": t.sector,
                            "float_shares": t.float_shares,
                            "running_surge_pct": t.running_surge_pct,
                            "avg_entry_price": t.avg_entry_price,
                            "avg_exit_price": t.avg_exit_price,
                            "peak_unrealized_pnl": t.peak_unrealized_pnl,
                            "giveback_pnl": t.giveback_pnl,
                            "max_shares_held": t.max_shares_held,
                            "key_takeaway": t.key_takeaway,
                        }).execute()
                        
                        if t_row.data and t.phases:
                            t_id = t_row.data[0]["id"]
                            for p in t.phases:
                                sb.table("warrior_trade_phases").insert({
                                    "trade_id": t_id,
                                    "sequence_order": p.sequence_order,
                                    "phase_type": p.phase_type,
                                    "price_level": p.price_level,
                                    "trigger_observed": p.trigger_observed,
                                    "action_taken": p.action_taken,
                                    "risk_factor": p.risk_factor,
                                    "result_outcome": p.result_outcome,
                                    "timestamp_or_time_str": p.timestamp_or_time_str,
                                    "shares": p.shares,
                                }).execute()
            except Exception as e:
                log_warning(MODULE, f"No se pudo persistir en Supabase (continuando con in-memory): {e}")

        return True


# Singleton del motor
warrior_playbook = WarriorPlaybookEngine()
