# ANCLA — Gestión Dinámica de Stop Loss y Take Profit por Fibonacci/Bollinger
### Especificación técnica para implementación — eTrade v5.0 (complementa a HALCÓN/CENTINELA/ORÁCULO, REBOTE/ADUANA, RADAR/CASCADA)

---

## 1. Resumen ejecutivo

**ANCLA** ancla el Stop Loss y el Take Profit a niveles estructurales del mercado (bandas de Fibonacci y Bollinger ya calculadas en la plataforma) en vez de a una distancia fija en pips/porcentaje. Objetivo: evitar que el SL se ejecute por ruido normal de vela ("cuchillos") y asegurar ganancia parcial de forma escalonada sin cortar tendencias fuertes de forma prematura.

**Dos componentes independientes:**
- **SL dinámico** (15m): se arma/desarma según la posición del precio dentro de su zona Fibonacci actual y la pendiente de EMA3.
- **TP en dos etapas**: primera mitad de la posición condicionada a agotamiento de momentum en EMA3 de **4H**, con nivel calculado sobre la zona Fibonacci de **1D**; segunda mitad (1D) como objetivo de resguardo puro por nivel de Bollinger, sin condición de momentum.

**Depende de:** RADAR (datos de mercado), y se arbitra junto con SLV/SLVM y CASCADA (sección 4).

**Alcance de mercados:** Crypto y Forex únicamente — mismo alcance que RADAR/CASCADA, del cual ANCLA depende para todos sus datos. El worker de Stocks queda fuera por ahora.

**Modelo de coordinación de salidas (SL/TP):** ADUANA se extiende para ser el único punto de envío y cancelación de todas las órdenes del sistema — entradas (como ya hace) y salidas (SLV/SLVM, Trailing Stop, ANCLA, CASCADA). Cada solicitud llega clasificada como PASIVA (aseguramiento continuo de bajo mantenimiento) o ACTIVA (gestión por estructura de mercado en tiempo real) — ver sección 4.

---

## 2. Stop Loss dinámico (15m)

### 2.1 Condición de armado

Cada 15 minutos se recalcula la zona Fibonacci donde está el precio actualmente (ej. para un LONG, entre UPPER_1 y UPPER_2). Se divide esa zona en dos mitades. El SL se arma cuando **ambas** condiciones se cumplen:

1. El precio está en la **mitad inferior** de su zona Fibonacci actual
2. EMA3 (15m) tiene pendiente **descendente**

Lógica espejada para SHORT (mitad superior de la zona, EMA3 ascendente).

### 2.2 Cálculo del nivel de SL

```
ancho_zona = banda_superior_zona - banda_inferior_zona
buffer_pct = 10% * ancho_zona
buffer_atr = 0.5 * ATR(14, 15m)

SL = banda_inferior_zona - max(buffer_pct, buffer_atr)
```

El piso mínimo en ATR evita que el buffer sea insuficiente cuando la zona Fibonacci actual es angosta (el 10% de una zona muy estrecha podría quedar dentro del ruido normal de una vela).

### 2.3 Recalculo y desarmado

- El valor del SL se recalcula cada 15 minutos mientras esté armado.
- **Desarmado (cancelación):** solo cuando EMA3 (15m) sostiene pendiente ascendente durante **2 velas cerradas consecutivas** (no 1 sola vela) — evita flicker de armado/desarmado en mercados oscilantes, y evita dejar la posición sin protección por un giro momentáneo de EMA3.
- **Re-armado:** cuando vuelven a cumplirse las condiciones de 2.1 (precio en mitad inferior de zona + EMA3 descendente), se recalcula y coloca de nuevo con el mismo cálculo de 2.2.

### 2.4 Ejecución

- Antes de solicitar la orden, verificar que la posición sigue abierta (otras estrategias — SQUEEZE, CASCADA, CENTINELA — pueden haberla cerrado antes).
- El SL se solicita a **ADUANA** (clasificación `ACTIVA`) como una orden **STOP (o STOP-LIMIT si el broker lo soporta)** en el nivel calculado — no se ejecuta a mercado de forma anticipada, se dispara solo cuando el precio toca ese nivel. ADUANA es quien la coloca, reemplaza y cancela en el broker (ver sección 4).
- Todas las órdenes de SL de ANCLA se colocan como **reduce-only** — nunca pueden abrir una posición nueva por error.
- La cancelación cruzada frente a otros módulos y frente a las propias órdenes de TP de ANCLA la resuelve ADUANA de forma centralizada (sección 4.2) — ANCLA no necesita implementar esta lógica por su cuenta.
- El cierre es por el **100%** de la posición activa en ese momento (no del tamaño original de entrada, si ya hubo cierres parciales previos).
- **Sincronización de tamaño:** cualquier ejecución parcial sobre la posición (TP1 de ANCLA, o un cierre parcial de cualquier otro módulo) debe disparar de inmediato una solicitud de recálculo/reemplazo de la orden de SL a ADUANA, sin esperar al próximo ciclo de 15 minutos — evita que la cantidad de la orden de SL en el broker quede desincronizada del tamaño real remanente.

---

## 3. Take Profit en dos etapas (1D)

### 3.1 Primera etapa — 50% de la posición (condicionado a Fibonacci 1D + EMA3 4H)

**Condición de disparo:** EMA3 en temporalidad de **4 horas** con pendiente lateral o descendente (LONG; inverso ascendente/lateral para SHORT). La zona Fibonacci de referencia para el cálculo del nivel sigue siendo la de **1D** — solo la condición de momentum cambia de timeframe, para reaccionar más rápido a un agotamiento sin esperar a que se confirme en la vela diaria completa.

**Cálculo del nivel:**

```
ancho_zona_1D = banda_superior_zona_1D - banda_inferior_zona_1D
TP_1 = banda_superior_zona_1D - (10% * ancho_zona_1D)
```

(Ejemplo LONG: zona UPPER_1-UPPER_2 → TP_1 = UPPER_2 - 10%*(UPPER_2-UPPER_1))

**Recalculo:** la zona Fibonacci (1D) se recalcula cada día; la condición de EMA3 (4H) se recalcula cada 4 horas. Mientras la condición de EMA3 no se cumpla y la primera etapa siga sin ejecutarse, ambos recalculos continúan de forma independiente.

**Tipo de orden:** al cumplirse la condición de EMA3(4H), se coloca una orden **LIMIT** en el nivel `TP_1` calculado — no se ejecuta a mercado. La orden queda esperando a que el precio la alcance.

**Cancelación por pérdida de la condición (histéresis, mejora 2):** si la orden LIMIT de TP1 está pendiente (colocada pero no ejecutada) y EMA3(4H) vuelve a pendiente ascendente sostenida durante **2 velas de 4H consecutivas** antes de que el precio alcance el nivel, la orden se cancela — la señal de agotamiento que la motivó ya no es válida, y no tiene sentido tomar ganancia parcial si la tendencia retomó fuerza. Misma lógica de histéresis que la usada para desarmar el SL (2.3), aplicada aquí en sentido inverso.

**Ejecución:** cierra el 50% del tamaño **actual** de la posición (no del tamaño original si hubo reducciones previas de otros módulos).

### 3.2 Segunda etapa — 50% restante (nivel Bollinger, sin condición de momentum)

Se coloca **únicamente después de que se ejecuta la primera etapa** (secuencial, no simultánea).

**Cálculo del nivel:**

```
TP_2 = banda_superior_Bollinger_1D - (10% * (banda_superior_Bollinger_1D - BASIS_1D))
```

(Inverso para SHORT: TP_2 = banda_inferior_Bollinger_1D + 10%*(BASIS_1D - banda_inferior_Bollinger_1D))

**Sin condición de EMA3** — se ejecuta apenas el precio toca ese nivel, sin esperar señal de agotamiento de momentum.

**Recalculo:** se recalcula cada día mientras la segunda etapa siga sin ejecutarse.

**Ejecución:** cierra el 100% del remanente de la posición (que a esta altura ya es el 50% original).

### 3.3 Control de disparo único

Cada etapa se ejecuta **una sola vez por posición**. Flags requeridos en el store de la posición:

- `ancla_tp1_fired[position_id]` — se activa al ejecutar la primera etapa; bloquea reevaluación futura de la condición 3.1
- `ancla_tp2_fired[position_id]` — se activa al ejecutar la segunda etapa; bloquea reevaluación futura de la condición 3.2

Sin este control, si el precio permanece varios días dentro del rango de disparo de una etapa ya ejecutada, ANCLA intentaría cerrar "50%" de nuevo sobre lo que ya quedó reducido.

### 3.4 Verificación de tamaño mínimo del broker (mejora 5)

Antes de enviar la orden de TP1 (el cierre del 50%), verificar el tamaño mínimo de operación que acepta el broker/exchange para ese instrumento:

```
SI tamaño_50% < minimo_broker[symbol]:
  → cerrar el 100% de la posición directamente en TP1
  → no colocar la etapa 2 (no queda remanente)
```

Esto evita que el sistema intente enviar una orden por debajo del mínimo permitido (que el broker rechazaría) y garantiza que, cuando la posición es demasiado pequeña para dividirse en dos mitades operables, se toma la ganancia completa en un solo movimiento en vez de fallar silenciosamente o dejar un remanente que no se puede gestionar.

### 3.5 Ejecución — verificación previa y solicitud a ADUANA

Antes de solicitar cualquiera de las dos órdenes, verificar que la posición sigue abierta (otras estrategias pueden haberla cerrado o reducido antes). Igual que el SL, las órdenes de TP se solicitan a **ADUANA** (clasificación `ACTIVA`) como reduce-only — ANCLA no envía nada directo al broker, ni implementa su propia lógica de cancelación cruzada: ADUANA la resuelve de forma centralizada (sección 4.2), incluyendo el recálculo del SL cuando TP1 ejecuta, y la cancelación de TPs pendientes si el SL ejecuta primero.

---

## 4. Gatekeeper centralizado — ADUANA extendida a órdenes de salida

Se reconsideró la decisión anterior: en vez de que cada módulo de salida (SLV/SLVM, Trailing Stop, ANCLA) envíe sus órdenes directo al broker coordinándose solo por una tabla declarativa, **ADUANA se extiende para ser el único punto de envío y cancelación de todas las órdenes del sistema — entradas y salidas.**

### 4.1 Clasificación de órdenes

| Clasificación | Módulos | Comportamiento |
|---|---|---|
| **PASIVA** | SLV/SLVM, Trailing Stop (3 fases) | Aseguramiento continuo de bajo mantenimiento — se ajustan de forma gradual y automática (ej. trailing por ATR), sin reevaluar estructura de mercado en cada ciclo |
| **ACTIVA** | ANCLA (SL y ambas etapas de TP), CASCADA (giveback dinámico) | Evalúan estructura de mercado en tiempo real (Fibonacci, EMA, régimen) y arman/desarman/cancelan con mayor frecuencia, siguiendo la histéresis propia de cada módulo |

La clasificación no cambia el comportamiento interno de cada módulo (ANCLA sigue recalculando cada 15m/4H/1D como está diseñado, SLV/SLVM sigue su propia cadencia) — solo determina cómo ADUANA gestiona la orden una vez recibida: una orden PASIVA se actualiza en ADUANA solo cuando su módulo de origen recalcula; una orden ACTIVA se espera que cambie con más frecuencia y ADUANA no la trata como anómala si se reemplaza varias veces en el día.

### 4.2 Flujo de una solicitud de orden de salida

```
Módulo origen (SLV/SLVM, Trailing Stop, ANCLA, CASCADA)
  → envía solicitud a ADUANA: {position_id, tipo (SL/TP), clasificación (PASIVA/ACTIVA), nivel, origen_modulo}
  → ADUANA:
      1. Consulta el registro de órdenes pendientes de esa posición
      2. Aplica la tabla de prioridad (4.3) para decidir si la nueva solicitud
         reemplaza, coexiste con, o es rechazada frente a las órdenes ya registradas
      3. Envía/cancela la orden real en el broker
      4. Actualiza el registro único de la posición
  → Cuando cualquier orden se ejecuta (fill en el broker):
      → ADUANA cancela automáticamente cualquier otra orden pendiente
        sobre esa misma posición, sin depender de que cada módulo
        implemente su propia lógica de cancelación cruzada
```

### 4.3 Tabla de prioridad (aplicada por ADUANA)

| Módulo | Clasificación | Prioridad |
|---|---|---|
| SLV/SLVM (stop ATR) | Pasiva | Máxima — nunca cancelado por ninguna otra orden |
| ANCLA (SL) | Activa | Coexiste con SLV/SLVM — el nivel más cercano al precio protege primero |
| ANCLA (TP, ambas etapas) | Activa | Independiente — no compite por cierre total, solo reduce tamaño |
| CASCADA (giveback dinámico) | Activa | Puede forzar cierre incluso con `cascade_hold=true` — es la válvula de seguridad de CASCADA |
| Trailing Stop | Pasiva | Actúa cuando CENTINELA no cerró a tiempo; ADUANA lo cancela si SLV/SLVM o ANCLA ejecutan primero |

### 4.4 Beneficio de centralizar vs. mantener la tabla declarativa

- **Un único registro de verdad** de qué órdenes están pendientes sobre cada posición, en vez de que cada módulo mantenga su propio estado y deba recordar consultar a los demás (el riesgo de olvido que señalamos en la respuesta anterior).
- La cancelación cruzada (si SL ejecuta, cancelar TPs pendientes; si TP1 ejecuta, recalcular tamaño del SL) vive en un solo lugar — ADUANA — en vez de estar repartida en la lógica de cada módulo.
- La distinción PASIVA/ACTIVA preserva el comportamiento real de cada tipo de orden — no se pierde la diferencia entre "aseguramiento continuo de bajo mantenimiento" y "gestión activa por estructura de mercado" que señalaste.

### 4.5 Cambios de integración sobre módulos ya implementados

| Módulo | Estado | Cambio requerido |
|---|---|---|
| ADUANA | Ya implementado (gatekeeper de entradas) | Agregar canal de recepción de solicitudes de salida (SL/TP) con el flujo de 4.2, y el registro de órdenes pendientes por posición |
| SLV/SLVM | Ya implementado | En vez de enviar la orden directo al broker, enviar la solicitud a ADUANA con clasificación `PASIVA` |
| Trailing Stop | Ya implementado | Mismo cambio — solicitud a ADUANA con clasificación `PASIVA` |
| ANCLA | Nuevo (este documento) | Envía sus solicitudes de SL/TP a ADUANA con clasificación `ACTIVA`, siguiendo el diseño ya descrito en las secciones 2 y 3 |
| CASCADA | Nuevo (documento RADAR/CASCADA) | El giveback dinámico (3.7 de ese documento) envía su solicitud de cierre a ADUANA con clasificación `ACTIVA` |

---

## 5. Parámetros configurables

| Parámetro | Default |
|---|---|
| Timeframe SL | 15m |
| Timeframe TP etapa 1 — zona Fibonacci | 1D |
| Timeframe TP etapa 1 — condición EMA3 | 4H |
| Timeframe TP etapa 2 (Bollinger) | 1D |
| Buffer SL (% del ancho de zona) | 10% |
| Buffer SL (piso ATR) | 0.5 x ATR(14, 15m) |
| Velas de confirmación para desarmar SL | 2 (cerradas, consecutivas) |
| % de posición en TP etapa 1 | 50% |
| Buffer TP etapa 1 (% del ancho de zona Fibonacci 1D) | 10% |
| Buffer TP etapa 2 (% del ancho Bollinger 1D) | 10% |
| Orden de ejecución TP | Secuencial (etapa 2 se coloca solo tras ejecutarse etapa 1) |
| Tipo de orden SL | STOP / STOP-LIMIT |
| Tipo de orden TP (ambas etapas) | LIMIT |
| Velas de confirmación para cancelar TP1 por pérdida de condición | 2 (4H, consecutivas) |
| Verificación de mínimo del broker antes de TP1 | Sí — si 50% < mínimo, cierra 100% en TP1 |

---

## 6. Notas para Antigravity

- ANCLA consume datos de RADAR (bandas de Fibonacci, Bollinger, EMA3, ATR) — no calcula estos indicadores de forma independiente, igual que HALCÓN, REBOTE, ADUANA y CASCADA.
- El componente de SL y el de TP son independientes entre sí — pueden coexistir simultáneamente sobre la misma posición sin conflicto (uno protege a la baja, el otro toma ganancia al alza).
- Todas las órdenes de ANCLA (SL y ambas etapas de TP) deben colocarse como **reduce-only** en el broker/exchange, para evitar que un error de sincronización abra una posición nueva no deseada.
- Persistir en el store de la posición: `ancla_sl_armado` (bool), `ancla_tp1_fired`, `ancla_tp2_fired` — necesarios para el control de disparo único y la lógica de armado/desarmado con histéresis de 2 velas.
- Con el gatekeeper centralizado (sección 4), ANCLA **no envía órdenes directo al broker** — envía sus solicitudes de SL/TP a ADUANA (clasificación `ACTIVA`), y es ADUANA quien las coloca, reemplaza y cancela en el broker, incluyendo la cancelación cruzada entre las propias órdenes de ANCLA y frente a SLV/SLVM y Trailing Stop.
- Las órdenes de SL son STOP/STOP-LIMIT y las de TP son LIMIT — ninguna de las órdenes de ANCLA se ejecuta a mercado directamente; todas quedan colocadas en el broker (vía ADUANA) esperando a que el precio alcance el nivel calculado.
- TP1 tiene histéresis de cancelación (2 velas de 4H) simétrica a la del SL (2 velas de 15m) — si la condición de EMA3 que motivó la orden deja de cumplirse antes de que se ejecute, ANCLA solicita la cancelación a ADUANA.
- Antes de enviar la solicitud de TP1 a ADUANA, consultar el tamaño mínimo de operación del broker/exchange para ese instrumento — si el 50% calculado queda por debajo del mínimo, cerrar el 100% directamente en esa orden y omitir la etapa 2.
- Ver sección 4.5 para los cambios de integración requeridos sobre ADUANA, SLV/SLVM y Trailing Stop (todos ya implementados) — son cambios de enrutamiento de las órdenes existentes hacia el gatekeeper, no una reescritura de su lógica de decisión.
