# RADAR / CASCADA — Especificación e Integración sobre el Sistema Ya Implementado
### Documento único para Antigravity — eTrade v5.0 (mercados **Crypto y Forex**)

**Contexto:** HALCÓN/CENTINELA/ORÁCULO y REBOTE/ADUANA ya están construidos e implementados. Este documento **no reemplaza esos módulos** — especifica dos componentes nuevos (RADAR y CASCADA) y los cambios puntuales de integración que hay que aplicar sobre el código ya existente para que los consuman. No hace falta releer los documentos originales de esos módulos; todo lo necesario para la integración está en la sección 4 de este documento.

---

## 1. Resumen ejecutivo

**RADAR** es el bus de señales compartido de la plataforma: calcula cada indicador y evento de mercado **una sola vez** por instrumento/timeframe y lo publica para que HALCÓN, REBOTE, ADUANA y CASCADA lo consuman — ninguno de los cuatro vuelve a calcularlo por su cuenta.

**CASCADA** es el gestor de posiciones que se originaron en un extremo (vía REBOTE) y corrieron más allá de lo esperado — decide, nivel por nivel, si conviene asegurar la ganancia (rebote) o dejar correr la posición (continuación confirmada), y absorbe parte de la lógica de SLV/SLVM para evitar que dos módulos reaccionen de forma contradictoria al mismo evento.

**Alcance:** Crypto (Binance Futures) y Forex (IC Markets/cTrader) únicamente. Ambos workers corren sobre el mismo droplet con baja latencia, condición necesaria para el modelo de eventos casi en tiempo real que requiere CASCADA. El worker de Stocks (IB TWS, local) queda fuera por ahora.

---

## 2. RADAR — Bus de señales compartido

### 2.1 Principio de diseño

Cada señal de mercado se calcula en un único punto de la plataforma y se publica en dos formas:
- **Snapshot de estado** (consulta puntual: "¿cuál es el régimen ADX ahora mismo?")
- **Cola de eventos discretos** (para señales tipo cruce, donde el momento exacto importa: "el cruce EMA3<EMA9 ocurrió a las 14:32:07")

Los eventos discretos son obligatorios para cualquier señal que CASCADA consuma — si un módulo solo lee el estado actual por polling, puede perderse el instante exacto del cruce entre dos ciclos de lectura, y para CASCADA cada nivel es una decisión de una sola vez.

### 2.2 Catálogo de señales

| Señal | Tipo | Cálculo | Consumido por |
|---|---|---|---|
| `pendiente_EMA3` / `pendiente_EMA9` / `pendiente_EMA20` | Estado | Normalizada por ATR (ver 3.5) — ascendente/lateral/descendente | HALCÓN, CASCADA, REBOTE, SLV/SLVM |
| `cruce_EMA3_EMA9`, `cruce_EMA9_EMA20`, `cruce_EMA20_EMA50`, `cruce_EMA50_EMA200` | Evento | Detección de cruce en 15m | CASCADA, HALCÓN, SLV/SLVM |
| `cruce_fibonacci_LOWER_x` / `UPPER_x` | Evento | Precio cruza de una banda Fibonacci a la siguiente | CASCADA, REBOTE |
| `regimen_ADX` + dirección (DI+/DI-) | Estado | ADX(14) + DI | HALCÓN, REBOTE |
| `regimen_local_15m` (alcista/bajista/neutral) | Estado | EMA20/50/200 en 15m | REBOTE, ADUANA |
| `indice_compresion` + `proximidad_fibonacci` | Estado | D2/D1 normalizado por ATR | HALCÓN |
| `rsi_extremo` / `rsi_divergencia` (por timeframe) | Estado/Evento | RSI(14) | HALCÓN, REBOTE |
| `squeeze_activo` | Estado | Bollinger bandwidth | HALCÓN, REBOTE |
| `confirmacion_volumen` | Estado | Volumen vs promedio 10 velas | HALCÓN, REBOTE |
| `vela_impulso` | Evento | Rango > 1.8x ATR | ADUANA |
| `trading_paused[symbol]` | Estado | Calendario económico (ORÁCULO) | ADUANA, CENTINELA, REBOTE |
| `nivel_cascada[position_id]` | Estado (por posición) | Nivel actual alcanzado en CASCADA | HALCÓN, REBOTE, ADUANA |
| `cascade_hold[position_id]` | Estado (por posición) | Bloqueo activo de cierre discrecional | CENTINELA, Trailing Stop, SLV/SLVM (parcial, ver 3.6) |
| `pnl_pico[position_id]` | Estado (por posición) | Máximo PNL histórico alcanzado | CASCADA (giveback) |

### 2.3 Señales de instrumento vs señales de posición

- **De instrumento** (aplican a todas las posiciones abiertas de ese símbolo): régimen ADX, régimen local, squeeze, RSI, cruces EMA, `trading_paused`.
- **De posición** (específicas de cada posición individual): `nivel_cascada`, `cascade_hold`, `pnl_pico`, `entry_profile`. Viven en el store de la posición, no en el store del instrumento.

### 2.4 Fail-safe

Si RADAR no puede calcular una señal (dato faltante, gap en el feed), debe publicar un estado explícito de `sin_datos` en vez de omitir la señal silenciosamente — cualquier módulo consumidor debe tratar `sin_datos` como "no actuar" en las decisiones que dependan de esa señal, nunca asumir un valor neutral por defecto.

---

## 3. CASCADA — Gestor de posiciones en extensión

### 3.1 Alcance

Se activa únicamente sobre posiciones marcadas con `origen = REBOTE` que ya superaron el nivel N0 (entrada en extremo) y se encuentran en ganancia. Posiciones abiertas por otras estrategias del sistema no entran en CASCADA — siguen bajo HALCÓN/CENTINELA y SLV/SLVM tal como están implementados hoy.

### 3.2 Niveles de cascada (SHORT — espejado para LONG)

```
N0: Entrada en extremo (REBOTE/ADUANA), precio sobre banda Bollinger superior
N1: cruce_EMA3_EMA9   (15m)
N2: cruce_EMA9_EMA20  (15m)
N3: cruce_EMA20_EMA50 (15m)
N4: cruce_EMA50_EMA200 (15m)
N5: cruce_fibonacci_LOWER_1 → LOWER_2 → ... → LOWER_6 (sucesivo)
```

### 3.3 Chequeo en cada nivel alcanzado

```
a. CHEQUEO DE REBOTE: ¿el componente rápido del par que acaba de cruzar
   empieza a girar de vuelta en contra de la caída, antes de confirmarse
   el siguiente nivel, Y el PNL de la posición sigue siendo positivo?
   → SI → CERRAR (asegurar ganancia)

b. CHEQUEO DE CONTINUACIÓN: ¿las señales de apoyo (3.4) confirman que
   la caída sigue?
   → SI → MANTENER, activar cascade_hold=true (ver 3.6)
```

El chequeo de rebote (a) se refina con la clasificación de pendiente de EMA20 (sección 3.5): un giro del componente rápido **no** se considera rebote válido si EMA20 permanece en su pendiente original — eso es ruido de corto plazo dentro de la tendencia de fondo, no reversión real.

### 3.4 Señales de apoyo (confirman continuación)

- **(i)** Banda superior de Bollinger (15m) aplanándose o descendiendo — en todos los niveles.
- **(ii)** HIGHs de las últimas 3 velas cerradas descendiendo — **15m en N1**, **30m en N2 a N5** (escalamiento intencional: a mayor profundidad de la cascada, se exige confirmación en una temporalidad más amplia para reducir ruido).

### 3.5 Clasificación de pendiente compartida (EMA3 / EMA9 / EMA20)

```
pendiente_normalizada = (EMA_actual - EMA_hace_N_velas) / ATR(14)
  (N = 3-5 velas cerradas, sin la vela vigente)

Ascendente:  pendiente > +0.15
Lateral:     -0.15 <= pendiente <= +0.15
Descendente: pendiente < -0.15
```

Publicado por RADAR para EMA3, EMA9 y EMA20 — reutilizable por cualquier módulo, no solo CASCADA.

**Tabla de combinación EMA3 (velocidad) × EMA20 (proyección de tendencia):**

| EMA3 | EMA20 | Interpretación |
|---|---|---|
| Ascendente | Ascendente | Tendencia fuerte confirmada |
| Ascendente | Lateral / Descendente | Tendencia débil o en transición — precaución |
| Descendente | Ascendente | Ruido de corto plazo (pullback) dentro de tendencia de fondo intacta — **no** es reversión real |
| Descendente | Descendente / Lateral | Reversión real probable |

EMA9 actúa como puente de confirmación intermedia: si EMA3 y EMA9 ya están alineados en la nueva dirección pero EMA20 todavía no, es una señal de fuerza intermedia — mayor que solo EMA3 girando, menor que la confirmación completa de la tabla. Se usa como matiz adicional en el score de CASCADA, no como condición binaria propia.

### 3.6 Interacción con SLV/SLVM

SLV/SLVM se arma cuando EMA3 (15m) pasa de ascendente a descendente (para un LONG; espejado para SHORT), y ejecuta el cierre cuando ocurre cualquiera de estos dos eventos: cruce EMA3<EMA9, o PNL <= $1.

El cruce EMA3<EMA9 es exactamente el nivel N1 de CASCADA — si SLV/SLVM ejecutara el cierre automático ahí para una posición en modo CASCADA, nunca le daría tiempo a CASCADA de evaluar rebote vs continuación. Se resuelve así:

| Trigger de SLV/SLVM | Posición normal (no-CASCADA) | Posición en modo CASCADA |
|---|---|---|
| EMA3 pasa a descendente (armado) | Igual que hoy — sin cambios | Igual — además marca la entrada al nivel N1 |
| Cruce EMA3<EMA9 (ejecución) | Cierra tal cual hoy — sin cambios | Delegado a CASCADA: evalúa 3.3 (a/b) en vez de cierre automático |
| PNL <= $1 (ejecución) | Igual que hoy — sin cambios | Sustituido por el giveback dinámico (3.7) |

A partir de N2 en adelante no hay overlap con SLV/SLVM (solo reacciona a EMA3/EMA9) — CASCADA opera sin conflicto en esos niveles, con el giveback como único backstop.

### 3.7 Giveback dinámico (piso de seguridad permanente)

Reemplaza el piso fijo de PNL<=$1 únicamente para posiciones en modo CASCADA. Se aplica **siempre**, independientemente del valor de `cascade_hold` — es la válvula de seguridad que evita que el bloqueo de cierres se convierta en una pérdida:

```
SI pnl_actual < (pnl_pico * 0.5):   [umbral 50%, parametrizable]
  → forzar CIERRE_TOTAL, ignorando cascade_hold
```

`pnl_pico` se actualiza en cada evaluación mientras la posición sigue abierta (máximo histórico de PNL flotante alcanzado por esa posición).

### 3.8 Interacción con REBOTE (entradas adicionales)

Antes de generar una señal de entrada adicional en un instrumento con una posición ya en modo CASCADA, REBOTE debe consultar `nivel_cascada` y `regimen_local_15m` — si CASCADA determinó que el movimiento actual es ruido de corto plazo (tabla 3.5, fila "Descendente/Ascendente"), REBOTE no debe proponer una entrada adicional en la dirección contraria a la tendencia de fondo que CASCADA ya identificó como intacta.

### 3.9 Interacción con ADUANA

ADUANA consulta `cascade_hold` de cualquier posición existente en el instrumento al validar una nueva orden (LIMIT o MARKET, de cualquier estrategia) sobre ese mismo símbolo — una orden que reforzaría una CASCADA activa se evalúa con criterio distinto a una que la contradice (mayor escrutinio en el segundo caso).

---

## 4. Cambios de integración sobre el sistema ya implementado

Estos son los únicos cambios que hay que aplicar al código ya construido de HALCÓN/CENTINELA/ORÁCULO y REBOTE/ADUANA. No requieren rehacer nada de lo ya implementado, solo conectar los puntos indicados a RADAR/CASCADA.

### 4.1 Sobre HALCÓN/CENTINELA (ya implementado)

1. **Inputs de mercado:** el módulo de HALCÓN que hoy calcula EMA3/9/20, Bollinger, Fibonacci, RSI, ADX y volumen por timeframe debe reemplazar ese cálculo propio por una lectura del snapshot que publica RADAR. Ningún dato de mercado se recalcula dentro de HALCÓN a partir de este cambio.
2. **Arbitraje (antes de ejecutar cierre):** CENTINELA debe consultar `cascade_hold[position_id]` (publicado por RADAR) antes de ejecutar cualquier cierre por score. Si está en `true`, CENTINELA no ejecuta — solo registra la señal en log. El único mecanismo que puede forzar el cierre de una posición con `cascade_hold=true` es el giveback dinámico de CASCADA (3.7) o el stop duro ATR de SLV/SLVM, que nunca se bloquea.
3. **SLV/SLVM — delegación de ejecución:** para posiciones marcadas `origen=REBOTE` en modo CASCADA, el trigger de ejecución por cruce EMA3<EMA9 deja de cerrar automáticamente y en su lugar dispara la evaluación de CASCADA (3.3). El armado por pendiente de EMA3 y el trigger de PNL<=$1 se mantienen sin cambios para posiciones normales; para posiciones en CASCADA, el trigger de PNL<=$1 se sustituye por el giveback dinámico (3.7). Ver tabla completa en 3.6.
4. **Campo nuevo en la posición:** agregar `origen` (estrategia que generó la posición) al modelo de datos de la posición, si no existe ya — es la condición que determina si una posición entra o no en modo CASCADA.

### 4.2 Sobre REBOTE/ADUANA (ya implementado)

1. **Inputs de mercado:** igual que en 4.1.1 — REBOTE y ADUANA deben leer de RADAR en vez de calcular por su cuenta `regimen_local_15m`, `regimen_ADX`, `squeeze_activo`, `rsi_extremo`, `vela_impulso`, etc.
2. **REBOTE — posiciones adicionales (regla ya existente en el módulo):** antes de proponer una entrada adicional sobre un instrumento con una posición ya en modo CASCADA, consultar `nivel_cascada` y `regimen_local_15m`. Si CASCADA determinó que el movimiento es ruido de corto plazo (tabla 3.5), REBOTE no debe proponer la entrada adicional en la dirección contraria a la tendencia de fondo identificada.
3. **ADUANA — orden de evaluación:** agregar un paso de consulta a `cascade_hold` de cualquier posición existente en el instrumento antes de aprobar una nueva orden. Una orden que refuerza una CASCADA activa se evalúa con el criterio estándar ya implementado; una orden que la contradice pasa por evaluación reforzada (mismo criterio que la regla de contra-tendencia ya existente en ADUANA).

---

## 5. Parámetros configurables

| Parámetro | Default |
|---|---|
| Umbral pendiente ascendente/descendente | ±0.15 (normalizado por ATR) |
| Temporalidad señal (i) — Bollinger superior | 15m, todos los niveles |
| Temporalidad señal (ii) — HH descendentes | 15m en N1, 30m en N2-N5 |
| Umbral giveback dinámico | 50% del `pnl_pico` |
| Alcance de mercados | Crypto y Forex únicamente |

---

## 6. Notas para Antigravity

- RADAR debe implementarse como servicio independiente con dos interfaces: consulta de snapshot (síncrona) y suscripción a eventos discretos (para cruces EMA y Fibonacci) — HALCÓN, REBOTE, ADUANA y CASCADA se conectan como consumidores, ninguno recalcula.
- CASCADA es un módulo de estado por posición (no un cálculo puro como HALCÓN/REBOTE) — necesita persistir `nivel_cascada`, `cascade_hold` y `pnl_pico` en el store de la posición entre evaluaciones.
- Los cambios de la sección 4 son puntuales y no requieren reescribir HALCÓN, CENTINELA, REBOTE o ADUANA — son puntos de conexión (lectura de RADAR, consulta de `cascade_hold`/`nivel_cascada`) sobre la lógica ya construida.
- Priorizar la implementación de RADAR sobre Crypto y Forex primero (mismo droplet, baja latencia) antes de evaluar extender a Stocks, dado que ese worker corre local por la dependencia de IB TWS y tiene características de latencia distintas.
- El fail-safe de `sin_datos` (2.4) es crítico para CASCADA en particular — una posición en modo CASCADA con datos faltantes no debe interpretarse como "mantener por defecto", debe alertar y aplicar el giveback dinámico como único criterio de seguridad hasta que RADAR vuelva a tener datos confiables.
