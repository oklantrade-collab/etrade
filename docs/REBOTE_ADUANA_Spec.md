# REBOTE / ADUANA — Motor de Entradas en Extremos y Validador Centralizado de Órdenes
### Especificación técnica para implementación — eTrade v5.0 (complementa a HALCÓN/CENTINELA/ORÁCULO)

---

## 1. Resumen ejecutivo

**REBOTE** es el motor que detecta oportunidades de entrada (LONG/SHORT) en extremos de reversión del mercado — zonas de sobreventa/sobrecompra cerca de bandas de Bollinger extremas y niveles Fibonacci (LOWER_4/5/6, UPPER_4/5/6) — donde el margen de rentabilidad esperado es mayor.

**ADUANA** es la capa centralizada que valida o rechaza toda orden LIMIT y MARKET generada por cualquier estrategia del sistema (incluyendo REBOTE), antes de que se envíe al broker/exchange. Ninguna orden se ejecuta sin pasar por ADUANA.

**Relación con HALCÓN/CENTINELA/ORÁCULO:** REBOTE y ADUANA cubren el lado de **apertura** de posiciones; HALCÓN/CENTINELA cubren el **cierre**; ORÁCULO cubre la **pausa por calendario económico**. Los cinco módulos comparten los mismos indicadores base (EMA3/9/20, Bollinger, Fibonacci, RSI, ADX) ya calculados en la plataforma — ninguno duplica cálculo.

---

## 2. REBOTE — Motor de entradas en extremos

### 2.1 Principio de diseño: scoring, no OR binario

Al igual que en HALCÓN, cada señal de entrada aporta un score ponderado en vez de disparar la compra por sí sola. Un solo criterio aislado no es suficiente evidencia de un rebote real — puede ser el inicio de una ruptura que continúa (precio que sigue cayendo, "cuchillo cayendo").

| Señal | Descripción | Peso |
|---|---|---|
| Toque de LOWER_6 / UPPER_6 (Fibonacci, 15m) | Señal más extrema y objetiva | Alto (40) |
| Doble suelo/techo en 5m + confirmación de 2 velas de 15m | Estructura de precio clara | Alto (35) |
| EMA3>EMA9 en 5m tras squeeze + banda Bollinger extrema lateral/ascendente (o descendente para techo) | Cambio de momentum confirmado | Medio (25) |
| RSI<15 (o >85) en 15m + LOWs/HIGHs ascendentes/descendentes en 5m | Sobreventa/sobrecompra extrema con estructura de confirmación | Medio (25) |
| Zona LOWER_3-5 / UPPER_3-5 + cruce EMA3>EMA9 en 5m o señal Pinescript (MACD BUY/SELL) o SAR ascendente/descendente o EMA3 de 15m con pendiente a favor | Confirmación técnica adicional en zona de interés, sin haber tocado el extremo máximo | Medio-bajo (15) |

**Score mínimo para ejecutar entrada:** 50 (parametrizable). Esto permite que una señal Alta por sí sola sea suficiente (ej. solo tocar LOWER_6 ya da 40, necesita un poco más de confluencia), o que dos señales Medias se combinen para alcanzar el umbral.

### 2.2 Filtro de régimen ADX (mismo mecanismo que HALCÓN, sección 5)

- **ADX < 15 (rango):** el score de REBOTE se multiplica x1.2 — las entradas en extremos funcionan mejor en mercado lateral.
- **ADX 15-30 (tendencia moderada):** score sin ajuste.
- **ADX > 30 (tendencia fuerte):** el score de REBOTE se multiplica x0.5 — en tendencia fuerte, los extremos tienden a romperse y continuar (el escenario de "precio sigue cayendo" descrito originalmente), no a rebotar.

### 2.3 Filtro de régimen de tendencia local (EMA20/50/200 en 15m)

Cálculo adicional sobre la misma serie de 15m ya utilizada por HALCÓN/REBOTE (EMA50 y EMA200 se agregan al cálculo existente de EMA3/9/20, mismo timeframe, sin pipeline nuevo):

| Régimen local (15m) | Condición | Efecto |
|---|---|---|
| Alcista | EMA20 > EMA50 > EMA200 | Entradas SHORT (contra-tendencia) requieren confirmación reforzada (ver 2.3.1). Entradas LONG (a favor) usan el score estándar de REBOTE |
| Bajista | EMA20 < EMA50 < EMA200 | Entradas LONG (contra-tendencia) requieren confirmación reforzada (ver 2.3.1). Entradas SHORT (a favor) usan el score estándar de REBOTE |
| Neutral | EMAs entrelazadas, sin orden claro | Sin ajuste adicional — aplica solo el filtro ADX (2.2) |

#### 2.3.1 Confirmación reforzada para entradas contra-tendencia (AND obligatorio, no OR)

Cuando el régimen local es bajista (EMA20<EMA50<EMA200 en 15m) y REBOTE detecta una señal de entrada LONG, se exige que **las tres condiciones siguientes se cumplan simultáneamente**, además del score normal de la sección 2.1:

1. Banda inferior de Bollinger (15m) en ascenso (no lateral, no descendente)
2. EMA3 > EMA9 (15m)
3. EMA20 (15m) — la misma usada en la clasificación de régimen — empieza a girar al alza (deja de tener pendiente negativa)

La condición 3 es la más importante: es la señal de que el régimen bajista local podría estar terminando, no solo un rebote de corto plazo dentro de una tendencia bajista intacta. Sin las tres condiciones a la vez, la entrada contra-tendencia se descarta aunque el score de la sección 2.1 supere el umbral.

Lógica espejada para entradas SHORT contra-tendencia cuando el régimen local es alcista.

### 2.4 Punto de quiebre compartido con HALCÓN/CENTINELA

Cuando el mercado está en ambiente SHORT en 15m (EMA3<EMA9<EMA20) y el precio cruza por encima de EMA9 o EMA20, ese es el momento decisivo — el mismo evento alimenta dos decisiones en paralelo:

- **HALCÓN/CENTINELA** evalúa si corresponde cerrar un LONG existente en ese instrumento
- **REBOTE** evalúa si corresponde abrir un SHORT nuevo

Ambos evalúan: estructura de las últimas 3 velas cerradas (HH/LL, sin la vela vigente) + régimen local (2.3). Es el mismo trigger, pero cada módulo aplica sus propias reglas — no se debe duplicar la lógica, sino que ambos consultan el mismo evento de cruce.

Lógica espejada para ambiente LONG (EMA3>EMA9>EMA20) cruzando por debajo de EMA9/EMA20 → HALCÓN/CENTINELA evalúa cierre de SHORT, REBOTE evalúa apertura de LONG.

### 2.5 Confirmación por volumen

Igual que en HALCÓN: la vela de reversión en el extremo debe idealmente venir con expansión de volumen (>1.3x promedio de las últimas 10 velas de esa temporalidad). Se aplica como multiplicador de confianza sobre el score (no como bloqueo total).

### 2.6 Posiciones adicionales sobre el mismo instrumento

Cuando ya existe una posición abierta en el mismo instrumento y REBOTE detecta una nueva señal de entrada:

- Se exige un score mínimo **más alto** que para la primera entrada (default: 70 en vez de 50) — una segunda entrada implica promediar sobre una posición que probablemente va en contra, y requiere mayor certeza.
- Se respeta el límite configurado en Settings (`Cant. Operación x Par` para Forex, `Cant. Operación x Cripto` para Cripto) como tope duro de número de entradas acumuladas por instrumento — independiente del score.

---

## 3. ADUANA — Validador centralizado de órdenes

Toda orden LIMIT o MARKET generada por cualquier estrategia del sistema (REBOTE u otra) pasa por ADUANA antes de ejecutarse. ADUANA no genera señales de entrada — solo aprueba o rechaza.

### 3.1 Reglas de rechazo (direccionales, no absolutas)

| Regla | Condición de rechazo | Nota |
|---|---|---|
| Extremo en contra | LONG cerca de UPPER_4/5/6 o banda superior de Bollinger | Rechazar. Comprar a favor de una sobre-extensión da poco margen y alto riesgo |
| Extremo en contra (espejo) | SHORT cerca de LOWER_4/5/6 o banda inferior de Bollinger | Rechazar, mismo motivo en dirección opuesta |
| Contra-tendencia sin reforzar | LONG/SHORT contra el sesgo macro de HALCÓN (`score_1D`/`score_4H`) sin cumplir la confirmación reforzada de la sección 2.3.1 | Consulta directa al score ya calculado por HALCÓN — no se duplica el cálculo |
| Vela de impulso grande | Vela de 15m con rango (high-low) > 1.8x ATR(14) de 15m, en dirección contraria a la orden | Estas velas generan movimiento fuerte en contra del mercado reciente; se rechaza la orden que va en la misma dirección de la vela de impulso |

**Importante — regla direccional, no absoluta:** ADUANA **debe permitir explícitamente** SHORT cerca de UPPER_4/5/6 y LONG cerca de LOWER_4/5/6 — esas son exactamente las entradas que REBOTE está diseñado para generar (reversión en el extremo). El rechazo aplica solo cuando la dirección de la orden coincide con una sobre-extensión ya ocurrida en esa misma dirección (comprar más arriba en la zona alta, vender más abajo en la zona baja).

### 3.2 Regla de aprobación explícita — régimen de rango

Cuando el régimen local (2.3, EMA20/50/200 en 15m) es neutral **y** la banda de Bollinger está estrecha con EMA20 desplazándose de forma horizontal en 15m, ADUANA aprueba explícitamente:

- LONG en el extremo inferior del rango
- SHORT en el extremo superior del rango

Esta es la misma condición de "régimen de rango" usada como multiplicador en REBOTE (sección 2.2, ADX<15) — se documenta una sola definición compartida entre ambos módulos para evitar reglas duplicadas o inconsistentes.

### 3.3 Orden de evaluación

```
Orden recibida (LIMIT o MARKET, de cualquier estrategia)
  │
  ├─ 1. ¿trading_paused[symbol] activo (ORÁCULO)? → RECHAZAR
  ├─ 2. ¿Cerca de extremo en la misma dirección de la sobre-extensión (3.1)? → RECHAZAR
  ├─ 3. ¿Contra el sesgo macro de HALCÓN sin confirmación reforzada (3.1)? → RECHAZAR
  ├─ 4. ¿Vela de impulso grande en contra (3.1)? → RECHAZAR
  ├─ 5. ¿Régimen de rango + extremo correspondiente (3.2)? → APROBAR directo
  └─ 6. Ninguna regla de rechazo aplica → APROBAR
```

---

## 4. Parámetros configurables

| Parámetro | Default |
|---|---|
| Score mínimo de entrada (primera posición) | 50 |
| Score mínimo de entrada (posición adicional) | 70 |
| Multiplicador ADX rango (<15) | x1.2 |
| Multiplicador ADX tendencia fuerte (>30) | x0.5 |
| Umbral confirmación de volumen | 1.3x promedio 10 velas |
| Timeframe régimen EMA20/50/200 | 15m |
| Umbral vela de impulso (ADUANA 3.1) | >1.8x ATR(14) de 15m |
| Límite de entradas por instrumento | Según Settings (`Cant. Operación x Par` / `x Cripto`) |

---

## 5. Notas para Antigravity

- REBOTE, igual que HALCÓN, debe implementarse como módulo de cálculo puro (dado un set de datos de mercado, devuelve `score_final` y `decision`), separado del componente que envía la orden.
- ADUANA es un middleware: se ejecuta como paso obligatorio antes de cualquier envío de orden al broker/exchange, sin importar qué estrategia la originó — no solo REBOTE.
- El régimen EMA20/50/200 (15m, sección 2.3) reutiliza la misma serie de velas de 15m que ya usan HALCÓN y REBOTE para EMA3/9/20 — solo se agregan dos periodos adicionales de EMA, sin nueva fuente de datos.
- ADUANA debe consultar directamente `score_1D`/`score_4H` ya calculados por HALCÓN (sección 4 del documento HALCÓN/CENTINELA) para la regla 3.1 de contra-tendencia — no se debe reimplementar ese cálculo dentro de ADUANA.
- El punto de quiebre compartido (2.4) implica que HALCÓN/CENTINELA y REBOTE deben poder consultar el mismo evento de cruce EMA9/EMA20 en 15m sin recalcularlo cada uno por su lado — conviene centralizar ese cálculo en un solo lugar (ej. el mismo store de indicadores de 15m) y que ambos módulos lo lean.
- Dado que el timeframe de 15m concentra ahora el trigger del régimen local, el punto de quiebre y buena parte del scoring de HALCÓN, se recomienda un chequeo de salud del feed de datos de 15m (última vela recibida, gaps) — una falla en ese feed afectaría simultáneamente a varios módulos.
