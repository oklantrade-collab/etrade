# eTrader APEX Options
## Addendum de Estrategias para Antigravity

**Versión:** 1.1 (revisión del addendum v1.0 del 18 de octubre de 2026)
**Fecha:** 18 de octubre de 2026
**Complementa:** `eTrader_APEX_Options_Arquitectura_Antigravity.md` v1.2 (en adelante, "el principal")
**Modo:** Simulación / Paper Trading únicamente

---

## 0. Cómo leer este documento

**Precedencia.** Para todo lo relativo a estrategias, este addendum **prevalece** sobre las secciones 9.2, 9.3 y el Sprint 8 del principal. Para todo lo demás (límites, ADUANA, Settings, adaptador de solo lectura, gates G1/G2/G3, despliegue con Options Worker local) prevalece el principal.

Etiquetas:

- **[FIJO]**: decisión de producto, no se cambia sin aprobación explícita.
- **[POR DEFECTO]**: parámetro inicial, editable en Settings y sujeto a calibración. No es una ley de mercado.
- **[VERIFICAR]**: depende de lo que Antigravity encuentre en el repositorio, en IBKR o en la cuenta.

**Prioridad absoluta [FIJO]:** corrección matemática, gestión de riesgo, trazabilidad y calidad de datos, por encima de la cantidad de estrategias o señales.

---

## 1. Qué cambió respecto al addendum v1.0

| # | Tema | v1.0 | v1.1 | Razón |
|---|---|---|---|---|
| 1 | Límites | Cifras fijas en el texto (USD 1.000, 50, 100) | Se leen de la pestaña **Opciones** de Settings (§17 del principal) | Una sola fuente de verdad, editable |
| 2 | Viabilidad | Se asume que las 14 estrategias son operables | **Matriz de viabilidad por estrategia** en el Sprint 0.5 y **gate de habilitación por estrategia** | Con USD 50 de riesgo y costes reales, varias estrategias son inviables o casi (§6) |
| 3 | Horizonte | Todo intradía | Columna "horizonte natural"; estrategias multi-día **fuera de V1** (decisión D-14) | Condor, butterflies y calendars ganan por paso del tiempo o por pin al vencimiento; el P&L intradía es mínimo frente a costes |
| 4 | Cálculo | Fórmula por estrategia | **Motor genérico por suma de patas**; fórmulas cerradas como **oráculo de pruebas** | Menos código y menos errores; las fórmulas validan al motor |
| 5 | Expectativa | Solo contexto de señal | **Vista de volatilidad** (`sigma_view`) además del sesgo direccional | Con IV como única distribución, straddle, condor y créditos tienen expectativa ≈ −costes por construcción |
| 6 | Costes | "Calcular costes" | Tabla de costes de ida y vuelta por estrategia y **ratio costes/riesgo** como filtro | El coste fijo pesa mucho más en estructuras de 4 contratos |
| 7 | Catálogo | `enabled / experimental / disabled` | Cuatro estados con **criterios de promoción** y libro **shadow** separado | Habilitar con evidencia operativa, no por decisión ad hoc |
| 8 | Patas | "Rechazar desincronizadas" | Umbral de sincronización, contratos no estándar, ex-dividendo, asignación y permisos de cuenta | Reglas concretas y verificables |
| 9 | Contexto | Etiquetas cualitativas | Definiciones numéricas editables de cada etiqueta | Reproducibilidad y calibración |
| 10 | Integración | Endpoints y tablas propios | Armonizado con el principal: prefijo `/api/options/v1`, tablas `opt_*`, patrón de jobs | Evitar dos esquemas paralelos |
| 11 | Secuencia | Sprints A–F | Hitos **E0–E6** enlazados con el plan del principal | Un solo calendario |
| 12 | Settings | No contemplado | Nuevos parámetros en la pestaña Opciones (§14) | Todo editable sin redeploy |

---

## 2. Alcance y límites que se conservan

- **Modo obligatorio:** análisis, backtesting y Paper Trading. No habilitar órdenes reales en frontend ni backend. El adaptador IBKR sigue **sin métodos de órdenes** (principal §14.2).
- **Límites de simulación:** capital, riesgo por operación, riesgo abierto, stop diario, número de operaciones diarias y horarios de entrada/salida se **leen de Settings**. Valores iniciales del principal: riesgo USD 50 por operación, USD 100 abierto, stop diario USD 50, hasta 3 operaciones al día (nunca forzadas), entradas hasta 30 minutos antes del cierre, universo de hasta 20 subyacentes.
- **Costes y precios:** bid/ask conservador; nunca fills al mid.
- **Multiplicador:** validar el de cada contrato; no asumir 100 (§7).
- **Datos:** mostrar estado `LIVE / DELAYED / FROZEN / STALE / ERROR`. No convertir datos ausentes en cero.
- **Sin opciones cortas descubiertas** ni estructuras cuyo riesgo máximo no pueda calcularse de forma fiable.

Estos valores son parámetros de prueba, no garantías de rentabilidad ni recomendaciones de inversión.

---

## 3. Catálogo de estrategias

### 3.1 Tabla maestra

| # | Estrategia | Familia (etiqueta UI) | Riesgo definido | Horizonte natural | Estado inicial | Hito |
|---|---|---|---|---|---|---|
| 1 | Long Call | single-leg | Sí | Intradía | `enabled` (principal Sprint 3) | Principal |
| 2 | Long Put | single-leg | Sí | Intradía | `enabled` | Principal |
| 3 | Bull Call Spread | vertical (débito) | Sí | Intradía | `enabled` | Principal |
| 4 | Bear Put Spread | vertical (débito) | Sí | Intradía | `enabled` | Principal |
| 5 | Bull Put Spread | vertical (crédito) | Sí | Intradía / multi-día | `disabled` | E2 |
| 6 | Bear Call Spread | vertical (crédito) | Sí | Intradía / multi-día | `disabled` | E2 |
| 7 | Long Straddle | multi-leg (débito) | Sí | Intradía condicionado | `disabled` | E3 |
| 8 | Long Strangle | multi-leg (débito) | Sí | Intradía condicionado | `disabled` | E3 |
| 9 | Iron Condor | multi-leg defined-risk (crédito) | Sí | **Multi-día** | `disabled` | E4 |
| 10 | Iron Butterfly | multi-leg defined-risk (crédito) | Sí | **Multi-día** | `disabled` | E4 |
| 11 | Long Call Butterfly | multi-leg (débito) | Sí | **Multi-día** | `experimental` | E5 |
| 12 | Long Put Butterfly | multi-leg (débito) | Sí | **Multi-día** | `experimental` | E5 |
| 13 | Calendar Spread | calendar/diagonal | Sí (débito) | **Multi-día** | `experimental` (solo análisis) | E6 |
| 14 | Diagonal Spread | calendar/diagonal | Sí (débito) | **Multi-día** | `experimental` (solo análisis) | E6 |

Reglas de etiquetado en la UI [FIJO]: `single-leg`, `vertical`, `multi-leg defined-risk` y `calendar/diagonal`. **Long Call y Long Put no son verticales.** Una vertical combina opciones del mismo subyacente, mismo tipo, mismo vencimiento y strikes distintos. Calendar y Diagonal **nunca** se tratan como verticales.

### 3.2 Extensiones futuras (fuera de este addendum)

- **Protective Put** y **Covered Call:** requieren integrar posiciones de acciones de Stocks (D-20). Se especifican aparte.
- **Ratio spreads:** excluidos hasta modelar y probar explícitamente sus riesgos (D-21). Riesgo asimétrico o no acotado: bloqueados en backend.

### 3.3 Estados del catálogo y promoción

| Estado | Qué permite |
|---|---|
| `disabled` | Visible en el catálogo, sin cálculo ni señales |
| `experimental` | Análisis manual en Strategy Lab; **sin** candidatas automáticas ni botón de simulación de entrada |
| `shadow` | Genera candidatas y se simulan en forward paper en un **libro separado** (`book = 'shadow'`) |
| `enabled` | Entra en el scanner y puede ser seleccionada para el libro principal |

Libro shadow [FIJO]: no consume operaciones diarias ni presupuesto de riesgo, nunca aparece en el "Top 3", y su rendimiento se reporta aparte. Usa las mismas tablas con `book = 'shadow'`.

**Criterios de promoción `shadow → enabled`** **[POR DEFECTO]**, por estrategia:

1. Fórmulas y pruebas del §12 en verde, incluidas las del oráculo cerrado.
2. Al menos **2 semanas** y **20 operaciones shadow** simuladas.
3. P&L de cada operación **reconcilia** con el recálculo desde los fills por pata (tolerancia USD 0,01).
4. Cero incidentes críticos: límite violado, dato inválido aceptado, pata sin cotización valorada con un precio inventado.
5. Matriz de viabilidad (§6) favorable para la estrategia.
6. Aprobación manual del responsable del producto.

La promoción acredita **corrección operativa**, no rentabilidad. Con menos de 30 operaciones por estrategia, la UI muestra "muestra insuficiente" en lugar de métricas de rendimiento. La promoción se hace desde Settings o Strategy Lab con un botón que solo se habilita cuando se cumplen los criterios; no hay anulación manual en V1. Cada cambio de estado se registra en `opt_strategy_state_history`.

---

## 4. Motor de payoff y fórmulas

### 4.1 Motor genérico [FIJO]

Una única función calcula el P&L al vencimiento sumando las patas:

```
Para cada pata i:  lado_i (+1 comprada, −1 vendida), ratio_i, M_i (multiplicador), K_i, tipo_i (C/P), prima_i
valor_intrínseco_i(S_T) = max(S_T − K_i, 0) si Call;  max(K_i − S_T, 0) si Put
P&L(S_T) = Σ_i  lado_i × ratio_i × M_i × ( valor_intrínseco_i(S_T) − prima_i )  −  costes
```

- Pérdida y ganancia máximas, y equilibrios (break-evens), se obtienen de una malla de `S_T` que incluye los strikes, un precio cercano a cero y un precio alto, y se contrastan con las fórmulas cerradas.
- **Calendar y Diagonal no usan este cálculo**: la pata larga sigue viva al vencimiento corto. Solo admiten repricing (§8).
- Para posiciones antes del vencimiento, el P&L usa precios ejecutables y/o un modelo de valoración identificado, con supuestos y timestamp visibles. **El payoff al vencimiento no es el P&L intradía.**

### 4.2 Fórmulas cerradas (oráculo de pruebas)

Convenciones: `S_T` precio del subyacente al vencimiento; `K` strike; `M` multiplicador; `D` débito neto por acción; `C` crédito neto por acción; `W` ancho entre strikes. Todas las cifras se muestran **antes y después de costes**.

| Estrategia | Pérdida máxima | Ganancia máxima | Break-even |
|---|---|---|---|
| Long Call | prima × M | Ilimitada | K + prima |
| Long Put | prima × M | (K − prima) × M | K − prima |
| Bull Call (K₁ < K₂) | D × M | (K₂ − K₁ − D) × M | K₁ + D |
| Bear Put (K₁ < K₂) | D × M | (K₂ − K₁ − D) × M | K₂ − D |
| Bull Put (vende K₂, compra K₁) | (K₂ − K₁ − C) × M | C × M | K₂ − C |
| Bear Call (vende K₁, compra K₂) | (K₂ − K₁ − C) × M | C × M | K₁ + C |
| Long Straddle | primas totales × M | Ilimitada al alza; (K − primas) × M a la baja | K ± primas totales |
| Long Strangle (K_put < K_call) | primas totales × M | Ilimitada al alza; (K_put − primas) × M a la baja | K_put − primas; K_call + primas |
| Iron Condor, alas simétricas | (W − C) × M | C × M | K_put corta − C; K_call corta + C |
| Iron Condor, alas asimétricas | (max(W_put, W_call) − C) × M | C × M | Igual que arriba |
| Iron Butterfly, alas simétricas | (W − C) × M | C × M | K central ± C |
| Long Butterfly 1:−2:1, alas iguales | D × M | (W − D) × M en el strike central | K_bajo + D; K_alto − D |

Notas:

- En el Iron Condor asimétrico solo uno de los dos lados puede perder, por eso el peor caso usa el ala más ancha.
- Cualquier cifra con multiplicador distinto de 100 debe salir de `M_i`, nunca de una constante.

### 4.3 Validación estructural por estrategia

La candidata se descarta antes de puntuar si incumple:

| Familia | Validaciones |
|---|---|
| Todas | Mismo subyacente; `conid`, tipo, strike, vencimiento, multiplicador, trading class y exchange de cada pata válidos; cotización bid/ask presente y `bid ≤ ask`; datos `LIVE`; antigüedad máxima (§9) |
| Verticales | Mismo tipo y vencimiento; strikes ordenados; ancho dentro del rango de Settings |
| Crédito | Crédito neto > 0 y `C < W` (si no, estructura inválida o arbitraje aparente: revisar datos) |
| Straddle | Mismo strike y vencimiento |
| Strangle | `K_put < precio < K_call`; mismo vencimiento |
| Iron Condor | `K₁ < K₂ < K₃ < K₄`; mismo vencimiento; crédito neto > 0 |
| Iron Butterfly | `K₁ < K₂ = K₃ < K₄`; mismo vencimiento; crédito neto > 0 |
| Butterfly | Ratios exactamente 1:−2:1; tres strikes ordenados; alas iguales (las asimétricas se rechazan en V1); `0 < D < W` |
| Calendar | Mismo strike y tipo; vencimiento corto < largo |
| Diagonal | Mismo tipo; vencimiento corto < largo; strikes distintos |

---

## 5. Contexto de mercado y selección de estrategias

### 5.1 Definiciones numéricas de las etiquetas **[POR DEFECTO, editables en Settings]**

Las etiquetas son contexto, no garantías. Son hipótesis de partida a calibrar en shadow.

| Etiqueta | Definición inicial |
|---|---|
| Alcista / bajista | Dirección APEX del subyacente (`bullish` / `bearish`) |
| Movimiento fuerte | Señal APEX de fuerza: ADX ≥ 25 o RVOL ≥ 2,0 |
| Lateral / rango | Dirección `neutral` y ADX < 20 |
| Movimiento grande esperado | RVOL ≥ 2,0 **sin** evento binario conocido dentro del DTE |
| IV alta / baja | IV/HV de referencia ≥ 1,5 / ≤ 0,9 |

### 5.2 Matriz contexto → candidatas

| Contexto | Candidatas iniciales |
|---|---|
| Alcista, movimiento fuerte, coste razonable | Long Call; Bull Call Spread |
| Alcista moderado, riesgo definido | Bull Call Spread; Bull Put Spread |
| Bajista, movimiento fuerte, coste razonable | Long Put; Bear Put Spread |
| Bajista moderado, riesgo definido | Bear Put Spread; Bear Call Spread |
| Lateral / rango | Iron Condor; Iron Butterfly (solo si están habilitadas) |
| Movimiento grande en cualquier dirección | Long Straddle; Long Strangle |
| Precio objetivo estrecho con evidencia suficiente | Butterfly (`experimental`) |
| Oportunidad temporal de IV | Calendar / Diagonal (solo análisis manual) |

### 5.3 Reglas

- La matriz genera **candidatas, no órdenes**. Solo participan estrategias en estado `shadow` o `enabled`.
- Se filtran primero contratos inválidos, liquidez insuficiente, spreads excesivos, cotizaciones obsoletas, patas incompatibles y riesgo no calculable. Después se comparan expectativa neta, riesgo máximo, liquidez, costes, escenarios y calidad de datos.
- **Straddle y Strangle no se proponen cuando hay un evento binario (earnings, FDA) dentro del DTE**, aunque haya "movimiento grande esperado": la IV ya descuenta el evento y la caída posterior (IV crush) suele superar el beneficio. Parámetro `allow_event_vol_strategies`, por defecto **No**.
- Para el mismo subyacente y dirección, si dos candidatas difieren en menos de 5 puntos de score, se prefiere la de **menos patas**.
- El score 0–100 es un ranking, no una probabilidad de éxito salvo calibración validada. Se registran razones de aceptación y rechazo y la versión del modelo. Nunca se ordena solo por ganancia máxima ni se fuerzan operaciones diarias.

---

## 6. Viabilidad económica con el presupuesto de riesgo

### 6.1 Costes de ida y vuelta de referencia

Con los valores iniciales del principal: comisión USD 0,65 y fees USD 0,05 por contrato y lado, y slippage de USD 0,01 por acción por contrato y lado. **Estos son supuestos conservadores [VERIFICAR con la tarifa de la cuenta y calibrar con fills simulados].**

Coste por contrato, ida y vuelta: `2 × 0,70 + 2 × (0,01 × 100) = USD 3,40`.

| Estructura | Contratos | Coste ida y vuelta | % del riesgo de USD 50 |
|---|---:|---:|---:|
| Long Call / Put | 1 | 3,40 | 6,8% |
| Vertical, straddle, strangle, calendar, diagonal | 2 | 6,80 | 13,6% |
| Iron Condor, Iron Butterfly | 4 | 13,60 | 27,2% |
| Butterfly 1:−2:1 | 4 | 13,60 | 27,2% |

### 6.2 Condición aproximada para que el riesgo máximo ≤ USD 50

Por acción, con costes por defecto restados (coste en dólares ÷ 100 por contrato-ida-y-vuelta):

| Estrategia | Condición aproximada |
|---|---|
| Long Call / Put | Prima ≲ 0,47 |
| Vertical de débito | Débito ≲ 0,43 |
| Vertical de crédito | `W − C ≲ 0,43`. Con `W = 1`, crédito ≳ 0,57: el strike corto debe estar casi ATM. Con strikes de 0,50 es más amplio, pero pocos subyacentes los tienen |
| Straddle / Strangle | Primas totales ≲ 0,43: solo subyacentes muy baratos o strangles muy OTM (poca probabilidad) |
| Iron Condor / Butterfly | `W − C ≲ 0,36`. Con `W = 1`, crédito ≳ 0,64: prácticamente solo con IV muy alta y strikes cortos casi ATM |

**Conclusión [FIJO como advertencia]:** con USD 50 de riesgo y estos costes, **Long Call/Put, verticales y, con suerte, algunos créditos son los candidatos realistas**; straddle/strangle son marginales; condor, iron butterfly y butterfly son casi siempre inviables. No es un defecto del diseño: es información que el Sprint 0.5 debe medir con datos reales antes de invertir esfuerzo de construcción. Si estructuras de 4 contratos son importantes para el proyecto, la decisión correcta es revisar el riesgo por operación o los supuestos de costes (D-15, D-19), no forzar la estrategia.

### 6.3 Matriz de viabilidad (entregable del Sprint 0.5)

Para cada estrategia del catálogo, sobre las mismas sesiones del gate G1:

- % de sesiones con al menos una candidata estructuralmente válida y con riesgo máximo dentro del límite.
- Mediana de `costes / riesgo máximo` y de spread relativo por pata.
- Número de subyacentes optionables que la soportan.
- Recomendación: `mantener disabled`, `pasar a experimental` o `candidata a shadow`.

El G1 del principal sigue exigiendo solo la viabilidad de las estrategias V1 (1 a 4). El resto es informativo y decide el orden de E2 a E6.

### 6.4 Filtro de costes

Una candidata se rechaza si `costes de ida y vuelta / riesgo máximo > max_cost_to_risk_ratio`, **[POR DEFECTO] 20%**. Con costes por defecto, verticales y straddle pasan (13,6%); condor, iron butterfly y butterfly no (27,2%) hasta que el riesgo por operación suba o los supuestos de costes se calibren a la baja con evidencia. El filtro es una barrera adicional: la expectativa neta ya descuenta costes.

---

## 7. Reglas de patas, contratos y riesgo específico

### 7.1 Contratos

- **Multiplicador:** leído del contrato. Los contratos con multiplicador distinto de 100 o con entregable ajustado (por acciones corporativas) se **rechazan por defecto** (`allow_nonstandard_multiplier = No`). Los mini y los ajustados no se mezclan con los estándar.
- Una pata sin cotización válida hace **no elegible** a la candidata; nunca se interpola ni se rellena.
- Mismo `trading class` y exchange coherentes en todas las patas.

### 7.2 Sincronización multi-pata

- Todas las cotizaciones de una candidata deben estar dentro de `max_leg_quote_skew_sec` entre sí, **[POR DEFECTO] 3 s**, y cada una dentro de la antigüedad máxima general (principal §17.2, 15 s).
- El snapshot guardado incluye todas las patas del mismo instante.
- Sin ejecución simultánea perfecta: el simulador aplica el slippage por pata del principal y, en el escenario adverso, el peor orden de ejecución con movimiento de una pata en contra.

### 7.3 Asignación, ejercicio y pin risk

El horizonte intradía con cierre forzado antes del cierre regular evita el ejercicio y el pin risk al vencimiento, pero no elimina el riesgo en estructuras con patas cortas:

| Regla | Valor **[POR DEFECTO]** |
|---|---|
| Cierre forzado antes del cierre regular | 15 min (principal §8) |
| Salida por protección de pata corta: delta absoluto de la pata corta ≥ | 0,70 |
| Excluir Bear Call Spread y otras estructuras con Call corta si hay **ex-dividendo dentro del DTE** y la Call corta está ITM o a un strike del ATM | Sí **[VERIFICAR fuente de dividendos]** |
| Estructuras con patas cortas en vencimientos de 0 DTE | Excluidas |

Una prima cobrada **no** es ganancia garantizada. Los créditos se muestran siempre junto a su pérdida máxima.

### 7.4 Permisos de la cuenta

Verificar en el Sprint 0.5 que la cuenta permite spreads y estructuras multi-pata (nivel de aprobación de opciones) y qué margen o poder de compra consume cada una. En defined-risk, el consumo de margen suele coincidir con la pérdida máxima; **[VERIFICAR]** con IBKR. Si la cuenta no permite una familia, esa familia permanece `disabled`.

### 7.5 Estrategias específicas

| Estrategia | Reglas adicionales |
|---|---|
| Bull Put / Bear Call | Calcular el sobrecoste de ejecución neto en natural: `(crédito_mid − crédito_natural) / crédito_mid ≤ 15%` |
| Straddle / Strangle | Evaluar el movimiento esperado frente a las primas, los costes y el IV crush. No recomendar por IV alta o baja solamente |
| Iron Condor / Iron Butterfly | Cuatro cotizaciones sincronizadas; alas simétricas por defecto; asimétricas solo con cálculo por lado |
| Butterfly | Solo `experimental` hasta contar con un modelo de precio objetivo con intervalo de confianza validado |
| Calendar / Diagonal | Solo análisis manual. Requieren repricing de ambas patas con vencimientos distintos, curva de IV por vencimiento y sensibilidad a tiempo, IV, gamma y riesgo cerca del vencimiento corto. Sin ese modelo y sus datos, no se emiten señales automáticas |

---

## 8. Motor de escenarios y expectativa

### 8.1 Dos vistas separadas [FIJO]

1. **Payoff al vencimiento**, calculado matemáticamente (§4).
2. **P&L estimado intradía**, con repricing por escenario. Se muestran los supuestos y el timestamp.

Matriz mínima: variación del subyacente (baja, estable, sube y shocks configurables), tiempo hasta la salida, cambio de IV (baja, estable, sube; escenarios del principal §10.3), bid/ask por pata, comisiones, slippage y datos obsoletos o mercado cerrado. Se muestra el P&L **por pata y total**, antes y después de costes. Cada pata se reprecia con su propio vencimiento e IV; en Calendar y Diagonal, con curva de IV por vencimiento.

### 8.2 Expectativa: sesgo direccional y vista de volatilidad

El principal define la distribución A (neutral) y la B (con sesgo APEX). **Se extiende B con una vista de volatilidad**:

```
sigma_imp   = IV_atm * sqrt(h / (252 * 6.5))                  # movimiento implícito en h horas de mercado
vol_ratio   = clip( HV_ref / IV_atm , 0.7 , 1.3 )              # HV_ref: volatilidad realizada reciente
sigma_view  = sigma_imp * ( 1 + gamma_vol * (vol_ratio − 1) )  # gamma_vol [POR DEFECTO] = 0.25
mu_view     = direccion * alpha * sigma_imp                    # alpha [POR DEFECTO] = 0.25 (principal §10.2)
Distribución B = lognormal con deriva mu_view y volatilidad sigma_view
```

- `HV_ref` **[POR DEFECTO]**: volatilidad realizada de las últimas 5 sesiones, anualizada **[VERIFICAR fuente; reutilizar el cálculo de Stocks si existe]**.
- Con `gamma_vol = 0` y `alpha = 0`, la expectativa de cualquier estrategia es ≈ −costes y no se selecciona ninguna: es el comportamiento correcto sin ventaja demostrada.
- Los créditos y condores solo muestran expectativa positiva si `HV_ref < IV`; las estrategias de débito en volatilidad, si `HV_ref > IV`.
- Ambos parámetros son **hipótesis** que se calibran con paper. Si calibrados quedan en ≤ 0, el sistema debe seleccionar pocas o ninguna operación.
- Todas las estrategias usan el mismo criterio de elegibilidad del principal: `ev_view_net > 0` y `ev_view_net / max_loss ≥ min_ev_ratio`.

---

## 9. IBKR y calidad de datos

- Reutilizar la conexión persistente del Options Worker local; el navegador nunca se conecta a IBKR (principal §5 y §14).
- Validar por pata: subyacente, tipo, strike, vencimiento, multiplicador, trading class, exchange, bid/ask, timestamp, IV, griegas y disponibilidad de volumen y open interest.
- Distinguir dato ausente de cero. Mostrar permisos, suscripciones y tipo de dato `LIVE / DELAYED / FROZEN`.
- Rechazar snapshots obsoletos o desincronizados (§7.2). No presentar datos retrasados como tiempo real.
- Si no hay cotización válida para valorar o cerrar una posición, marcarla **no valorable**, alertar y aplicar la regla `close_blocked_data` del principal. Nunca inventar un precio.
- El consumo de líneas de datos sube con las patas: una candidata de 4 patas gasta cuatro líneas. El generador de combinaciones respeta `max_concurrent_quotes` y prioriza por viabilidad previa (§6.2) para no gastar líneas en estructuras que no caben en el riesgo.

---

## 10. Riesgo y Paper Trading

- Calcular y mostrar la pérdida máxima **antes** de simular.
- Todo pasa por ADUANA con las reglas O-1 a O-11 del principal. Se añade una regla de familia:
  - **O-12:** el estado de la estrategia debe ser `enabled` para el libro principal o `shadow` para el libro shadow.
  - **O-13:** sincronización multi-pata y contratos estándar según §7.1 y §7.2.
- Bloquear operaciones que excedan el riesgo por operación o el agregado, según Settings y techos del entorno.
- Detener nuevas entradas al alcanzar el stop diario.
- Respetar el corte de entradas y las reglas de salida configuradas. Las patas cortas añaden la salida por protección (§7.3).
- Bloquear órdenes reales en backend; la UI no puede ser el único control.
- Tratar asignación, ejercicio, pin risk y riesgo de patas según §7.3.

---

## 11. Datos, endpoints y UI

### 11.1 Tablas (adiciones al principal §16)

Prefijo `opt_` y convenciones del principal. Antes de crear tablas, inspeccionar el esquema y reutilizar oportunidades, posiciones paper, fills, eventos de riesgo y logs existentes.

| Tabla | Propósito |
|---|---|
| `opt_strategy_catalog` | Una fila por estrategia: `key`, familia, nombre, `version`, `state`, `holding_horizon`, definición estructural (JSONB), parámetros por defecto |
| `opt_strategy_state_history` | Auditoría de cada cambio de estado: quién, cuándo, de y a qué estado, criterios evaluados |
| `opt_candidate_legs` | **Patas normalizadas** por candidata: `candidate_id`, `leg_index`, `conid`, lado, ratio, tipo, strike, vencimiento, multiplicador, bid, ask, timestamp, IV, griegas |
| `opt_candidates` (existente) | Se añaden `strategy_key`, `strategy_version`, `family`, `book` (`selected` / `shadow`), `costs_roundtrip`, `cost_to_risk_ratio`, `sigma_view`, `gamma_vol_used`. Las patas pasan de JSONB a `opt_candidate_legs` (el campo `legs` queda como resumen derivado, no como fuente) |
| `opt_simulations` (existente) | Se añade el resultado **por pata** y la vista (`expiry_payoff` / `intraday_repricing`) |
| `opt_paper_trades` (existente) | Se añaden `book` y `strategy_version` |

Reglas: UUID, timestamps UTC, índices e integridad referencial, RLS. Secretos solo en backend. **Toda decisión debe poder reproducirse** con su snapshot, `model_version`, `settings_version` y `strategy_version`. Migraciones aditivas y reversibles.

### 11.2 Endpoints (armonizados con el principal §15)

| Método | Endpoint | Notas |
|---|---|---|
| GET | `/api/options/v1/strategies` | Catálogo con estado, familia y viabilidad |
| GET | `/api/options/v1/strategies/{key}` | Definición, versión, historial de estado, métricas por libro |
| POST | `/api/options/v1/strategies/evaluate` | **Análisis manual**: patas dadas por el usuario, validadas en servidor, calculadas sobre snapshots/cotizaciones almacenadas. Sin TWS, sin crear operaciones |
| POST | `/api/options/v1/strategies/scenarios` | Escenarios de precio, tiempo e IV de una estructura evaluada |
| PUT | `/api/options/v1/strategies/{key}/state` | Promoción o degradación de estado; solo rol propietario; solo si se cumplen los criterios de §3.3 |
| POST | `/api/options/v1/paper-trades/open` | Reemplaza `paper-trading/simulate` del addendum v1.0; pasa por ADUANA |

Validar payloads en servidor. No exponer secretos en logs.

### 11.3 UI: Strategy Lab (V1.1 del principal)

- Filtros por familia y por estado (`disabled`, `experimental`, `shadow`, `enabled`).
- Comparación de estrategias para el mismo subyacente.
- Patas, vencimientos, strikes, débito o crédito, ganancia y pérdida máximas y break-even.
- Payoff al vencimiento y tabla de escenarios intradía **en dos vistas separadas**.
- P&L por pata y total, antes y después de costes; ratio costes/riesgo.
- Indicadores de liquidez, estado de datos, supuestos y motivos de recomendación o rechazo.
- Las estrategias `experimental` y `disabled` se ven como catálogo; **no son recomendación operable**.
- Solo acciones de simulación: ningún botón de envío real. En `experimental`, la acción "Simular entrada" aparece deshabilitada.
- Todos los cálculos se hacen en backend; el navegador no contiene lógica financiera.
- Página de catálogo con la matriz de viabilidad (§6.3) y el avance de cada estrategia hacia sus criterios de promoción.

---

## 12. Pruebas y backtesting

### Unitarias (obligatorias)

- **Oráculo cerrado:** para cada estrategia, el motor genérico (§4.1) coincide con las fórmulas del §4.2 en una malla amplia de `S_T`.
- **Propiedades:** el mínimo de la malla coincide con la pérdida máxima; el P&L cambia de signo en cada break-even; el payoff es continuo y lineal a tramos; con crédito el P&L en `S_T` extremo no excede los máximos.
- Multiplicadores distintos de 100; rechazo por defecto de contratos no estándar.
- Costes y slippage: la tabla del §6.1 se reproduce con los valores por defecto; el filtro `max_cost_to_risk_ratio` rechaza lo esperado.
- Strikes, vencimientos, tipos y ratios inválidos (§4.3); crédito con `C ≥ W`; butterfly asimétrica.
- Datos faltantes, obsoletos, spreads invertidos, patas desincronizadas por encima de `max_leg_quote_skew_sec`.
- Repricing por movimiento del subyacente, tiempo e IV; distribución A y B con `sigma_view`.
- Ex-dividendo y protección de pata corta.
- **Reconciliación:** el P&L de cada operación simulada coincide con el recálculo desde los fills por pata (tolerancia USD 0,01).
- Verificación de que ninguna ruta envía órdenes reales.

### Integración

- Datos IBKR simulados de cadenas, contratos, griegas y cotizaciones multi-pata.
- Persistencia y reproducción de snapshots.
- RLS y aislamiento por usuario.
- Reconexión del Gateway sin duplicar posiciones ni evaluaciones.
- Simulación de fills y cierres con costes.
- Cambios de estado de estrategia: solo con criterios cumplidos y rol correcto; historial auditado.
- Regresión de ADUANA y de Stocks, Crypto y Forex.

### Backtesting y evaluación

- Sin look-ahead bias; no fills al mid por defecto; incorporar spread, comisiones, slippage y latencia.
- Separar calibración y evaluación fuera de muestra.
- Reportar número de operaciones, expectativa neta, drawdown, tasa de ganancia, profit factor, distribución de pérdidas y sensibilidad a costes, **por estrategia y por libro**.
- No afirmar rentabilidad con pocos ejemplos ni con payoff teórico únicamente.
- El histórico de opciones disponible será el de los snapshots propios (principal §14.4): documentar su cobertura limitada.

---

## 13. Plan de hitos E0–E6

Cada hito entrega código, migraciones, pruebas, documentación, evidencia, limitaciones conocidas y pasos de despliegue y rollback. Los hitos se acoplan al calendario del principal.

| Hito | Se ejecuta con | Contenido | Criterio de aceptación |
|---|---|---|---|
| **E0** | Sprint 0 y 0.5 del principal | Auditoría de código y datos; registro de las 14 estrategias en `opt_strategy_catalog` con familia, versión, horizonte y estado; **matriz de viabilidad (§6.3)**; verificación de permisos multi-pata | Las no habilitadas no generan señales operables; informe de viabilidad con datos reales |
| **E1** | Sprint 3 y 4 del principal | Motor genérico de payoff, oráculo cerrado, estructurales, costes, escenarios por pata y vista de volatilidad; las 4 estrategias V1 | Ninguna simulación sin riesgo calculado; pruebas del §12 en verde; payoff al vencimiento separado del repricing intradía |
| **E2** | Tras el Sprint 7 del principal (G3) | Bull Put y Bear Call: reglas de asignación, ex-dividendo, protección de pata corta, sobrecoste de crédito | Pasan primero por `shadow`; criterios de §3.3 |
| **E3** | Tras E2 | Long Straddle y Long Strangle con vista de volatilidad y filtro de eventos | Estrategia solo `enabled` si la expectativa se sostiene en shadow; sin propuestas con evento binario en el DTE |
| **E4** | Condicionado a la matriz de viabilidad y a D-14/D-15/D-19 | Iron Condor e Iron Butterfly; cuatro cotizaciones sincronizadas | No se construye si la matriz muestra inviabilidad persistente con el riesgo por operación vigente |
| **E5** | Condicionado a modelo de precio objetivo | Long Call/Put Butterfly | Permanecen `experimental` hasta validar el modelo |
| **E6** | Condicionado a D-14 (horizonte multi-día) | Calendar y Diagonal: repricing de dos vencimientos con curva de IV | Solo análisis manual; nunca se tratan como verticales; sin señales automáticas |

Gates: G1, G2 y G3 del principal siguen vigentes. Se añade el **gate de habilitación por estrategia** (§3.3).

---

## 14. Settings: parámetros adicionales de la pestaña "Opciones"

Se añade una sección **C-bis "Estrategias adicionales"** a la pestaña Opciones de Settings (principal §17), con los mismos patrones: todo editable, valor efectivo y techos, validaciones, auditoría y `settings_version`.

| Parámetro | Valor por defecto | Rango |
|---|---:|---|
| Estado por estrategia | Según §3.1 | `disabled / experimental / shadow / enabled` (la promoción a `enabled` exige criterios cumplidos) |
| Ratio máx. costes / riesgo (`max_cost_to_risk_ratio`) | 20% | 5–50% |
| Sincronización máx. entre patas | 3 s | 1–10 |
| Sobrecoste de ejecución neto máx. en créditos | 15% | 2–30% |
| Delta absoluto de pata corta para salida por protección | 0,70 | 0,50–0,95 |
| Excluir Calls cortas con ex-dividendo en el DTE | Sí | Sí/No |
| Permitir contratos no estándar | No | Sí/No |
| `gamma_vol` | 0,25 | 0–1 |
| Ventana de `HV_ref` | 5 sesiones | 3–20 |
| ADX para "lateral" / "movimiento fuerte" | 20 / 25 | 10–40 |
| RVOL para "movimiento grande" | 2,0 | 1,2–5 |
| IV/HV para "IV alta" / "IV baja" | 1,5 / 0,9 | 0,5–3 |
| Permitir estrategias de volatilidad con evento binario (`allow_event_vol_strategies`) | No | Sí/No |
| Ancho de ala/strike: mínimo / máximo (USD) | 1 / 5 | 0,5–10 |
| Shadow: operaciones mínimas / semanas mínimas | 20 / 2 | 5–200 / 1–12 |
| Tolerancia de reconciliación de P&L | USD 0,01 | 0,001–0,10 |
| Preferir menor complejidad si los scores difieren menos de | 5 puntos | 0–15 |

Cambiar estos parámetros genera nueva `model_version` cuando afecta al score o a la elegibilidad. Los cambios aplican a nuevas candidatas; no alteran posiciones abiertas.

---

## 15. Criterios globales de aceptación

1. El catálogo distingue `single-leg`, `vertical`, `multi-leg defined-risk` y `calendar/diagonal`, y refleja los cuatro estados.
2. Las estrategias habilitadas calculan correctamente payoff, break-even, ganancia y pérdida máximas y escenarios; el oráculo cerrado coincide con el motor.
3. Costes, ratio costes/riesgo y calidad de datos participan en la evaluación.
4. Los límites de riesgo se aplican en backend, vía ADUANA, y se leen de Settings.
5. Se explica por qué se propone o rechaza cada candidata.
6. Las evaluaciones son reproducibles desde snapshots, versión del modelo, de las estrategias y de Settings.
7. Calendar y Diagonal no generan señales automáticas sin modelo validado.
8. Ninguna ruta puede enviar órdenes reales.
9. Una estrategia solo se habilita tras pasar por `shadow` con criterios cumplidos y aprobación del propietario.
10. La matriz de viabilidad existe y justifica el orden de E2 a E6.
11. El documento principal y el changelog quedan actualizados.

---

## 16. Decisiones pendientes

- **D-14:** Horizonte multi-día. Habilitarlo exige nuevas reglas de riesgo (gap nocturno, asignación, margen) y cambios en ADUANA (O-8). Condiciona E4, E5 y E6.
- **D-15:** Calibración de comisiones, fees y slippage por pata con evidencia de fills simulados.
- **D-16:** Fuente de dividendos y fechas ex-dividendo.
- **D-17:** Fuente de `HV_ref` (reutilizar la de Stocks o calcular desde barras intradía).
- **D-18:** Nivel de aprobación de opciones de la cuenta IBKR y reglas de margen para spreads y multi-pata.
- **D-19:** Si las estructuras de 4 contratos son prioritarias, evaluar un riesgo por operación mayor. Hoy son prácticamente inviables con USD 50.
- **D-20:** Integración de posiciones de acciones de Stocks para Protective Put y Covered Call.
- **D-21:** Modelo de riesgo para ratio spreads antes de siquiera considerarlos.
- **D-22:** Modelo de precio objetivo con intervalo de confianza para butterflies.
- **D-23:** Modelo de curva de IV por vencimiento para Calendar y Diagonal.

---

## 17. Instrucciones para Antigravity

1. **Inspeccionar antes de editar.** Auditar el repositorio, el documento principal, las tablas Supabase, los endpoints, el motor de riesgo, ADUANA, Settings, Strategy Lab (si existe) y la conexión IBKR. No asumir carpetas, tablas ni endpoints.
2. Reutilizar lo existente; migraciones aditivas y reversibles; entregar por hitos con pruebas.
3. **No construir una estrategia sin pasar antes por el catálogo, el motor genérico y sus pruebas con oráculo.**
4. **No habilitar una estrategia sin criterios de promoción cumplidos.** No hay atajo manual en V1.
5. No inventar cotizaciones ni datos de mercado; si faltan, bloquear y mostrar el estado.
6. Paper Trading es el único modo de ejecución; no crear rutas hacia órdenes reales.
7. Presentar con cada entrega: archivos cambiados, resultados de pruebas, limitaciones y funciones no habilitadas.
8. Cada punto **[VERIFICAR]** se resuelve con evidencia y se documenta.
9. Actualizar el principal y su changelog cuando una decisión de este addendum lo requiera.

### Prompt de arranque sugerido (E0)

> Lee `eTrader_APEX_Options_Arquitectura_Antigravity.md` (v1.2) y este addendum (v1.1) completos. Ejecuta solo el hito E0 junto con los Sprints 0 y 0.5 del principal. No modifiques código existente. Entrega: (1) inventario técnico y mapa de reutilización, incluyendo Strategy Lab si existe; (2) propuesta de migraciones para `opt_strategy_catalog`, `opt_strategy_state_history` y `opt_candidate_legs`; (3) la matriz de viabilidad por estrategia con datos reales de al menos 5 sesiones; (4) verificación de permisos multi-pata y margen en la cuenta; (5) lista de riesgos y de cada punto [VERIFICAR] resuelto. Detente y espera aprobación antes del Sprint 1.

---

## 18. Changelog

- **v1.1 (18-oct-2026):** integración con el principal v1.2; viabilidad y costes por estrategia; motor genérico y oráculo de pruebas; vista de volatilidad; estados y promoción por estrategia con libro shadow; reglas de patas, asignación y permisos; contexto numérico; armonización de tablas y endpoints; hitos E0–E6; parámetros de Settings; decisiones D-14 a D-23.
- **v1.0 (18-oct-2026):** addendum inicial con catálogo de 14 estrategias, fórmulas, motor de escenarios, riesgo, UI, pruebas y sprints A–F.
