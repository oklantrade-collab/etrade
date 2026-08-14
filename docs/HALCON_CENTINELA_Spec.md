# HALCÓN / CENTINELA — Gestor de Cierre Proactivo Multi-Timeframe
### Especificación técnica para implementación — eTrade v5.0

---

## 1. Resumen ejecutivo

**HALCÓN** es el motor de decisión que evalúa el panorama completo del mercado en 5 temporalidades (1D, 4H, 15m, 5m, 1m) y produce un **score de cierre ponderado** por posición abierta.

**CENTINELA** es el proceso que corre continuamente sobre todas las posiciones abiertas, consulta a HALCÓN por cada una, arbitra contra los módulos reactivos existentes (SLV/SLVM, Trailing Stop) y ejecuta la orden de cierre (total o parcial) cuando corresponde.

**Objetivo dual:**
1. Maximizar ganancias cerrando de forma anticipada cuando el mercado da señales de reversión, antes de que se necesite un stop.
2. Resguardar capital evitando llegar al Stop Loss, sin sacrificar movimientos grandes a favor.

**Naturaleza del sistema:** proactivo (a diferencia de SLV/SLVM y Trailing Stop, que son reactivos). CENTINELA **nunca abre posiciones**, únicamente decide el cierre (total o parcial) de posiciones ya abiertas por otras estrategias del sistema.

---

## 2. Arquitectura general

```
                         ┌─────────────────────────┐
                         │        CENTINELA         │
                         │  (proceso ejecutor 24/7) │
                         └────────────┬─────────────┘
                                      │ consulta cada posición abierta
                                      ▼
                         ┌─────────────────────────┐
                         │          HALCÓN          │
                         │   (motor de decisión)    │
                         ├─────────────────────────┤
                         │  Capa Macro (sesgo)       │
                         │   - 1D: EMA3/9/20+Boll+SIPV│
                         │   - 4H: pendiente EMA3     │
                         ├─────────────────────────┤
                         │  Capa Micro (timing)       │
                         │   - 15m: cruces EMA        │
                         │   - 5m: EMA stack + squeeze│
                         │   - 1m: confirmación breakout│
                         ├─────────────────────────┤
                         │  Filtro de régimen (ADX)   │
                         │  Índice de compresión EMA  │
                         │  Confirmación por volumen  │
                         └────────────┬─────────────┘
                                      │ score final (-100 a +100)
                                      ▼
                         ┌─────────────────────────┐
                         │   Motor de arbitraje       │
                         │  (vs SLV/SLVM, Trailing)   │
                         └────────────┬─────────────┘
                                      ▼
                         CIERRE_TOTAL / CIERRE_PARCIAL / MANTENER
```

---

## 3. Inputs requeridos por posición

| Campo | Descripción |
|---|---|
| `symbol` | Instrumento (XAUUSD, USDJPY, BTCUSD, etc.) |
| `direction` | LONG / SHORT |
| `entry_price` | Precio de entrada |
| `current_pnl` | PNL flotante actual en USD |
| `position_size` | Tamaño de la posición |
| `opened_at` | Timestamp de apertura |
| `last_close_action_at` | Timestamp del último cierre parcial/total (para cooldown) |
| `partial_closed_pct` | % ya cerrado si hubo cierre parcial previo |
| `entry_profile` | `ALTA_VOLATILIDAD` / `TENDENCIA_SOSTENIDA` — ver sección 14 |

### Datos de mercado requeridos por temporalidad (1D, 4H, 15m, 5m, 1m)

- OHLC de las últimas N velas (mínimo 30 velas por temporalidad para cálculo de EMA20 estable)
- EMA3, EMA9, EMA20
- Bandas de Bollinger (BASIS, UPPER, LOWER) — periodo estándar 20, desviación 2
- Bandas de Fibonacci existentes en la plataforma: LOWER_1 a LOWER_6, UPPER_1 a UPPER_6, BASIS
- RSI(14) por temporalidad (1D, 4H, 15m, 5m)
- ADX(14) + DI+ + DI-
- Volumen (o tick volume en forex) de cada vela
- ATR(14) de 1D para clasificación de volatilidad del instrumento

---

## 4. Motor de scoring por nivel

Cada temporalidad devuelve un **score individual de -100 a +100**:
- **Negativo** → presión hacia SHORT / señal de cierre para LONGs
- **Positivo** → presión hacia LONG / señal de cierre para SHORTs
- **Cercano a 0** → neutral (Ámbar)

### 4.1 Nivel 1D (peso: 30%)
- Sobrecompra/sobreventa: precio por encima/debajo de banda Bollinger → ±40 puntos base
- Precio cerca del BASIS + EMA3 con pendiente en contra de la posición (últimas 3 velas cerradas) → ±30 puntos
- Patrón de vela SIPV desfavorable en formación (revisado cada 5 min) → ±20 puntos
- Score 1D = suma acotada a [-100, 100]

### 4.2 Nivel 4H (peso: 25%)
- Pendiente de EMA3 en las últimas 3 velas cerradas:
  - Ascendente sostenida → +60 (favorable a LONG)
  - Descendente sostenida → -60 (favorable a SHORT)
  - Mixta/lateral → 0 a ±20

### 4.3 Nivel 15m (peso: 20%)
- Cruce EMA3/EMA9 en curso o inminente, evaluado con estructura de HH/LL de las últimas 3 velas cerradas (excluye vela vigente):
  - LOWs ascendentes + cruce EMA3>EMA9 confirmado o en curso → +50 (mantener/reforzar LONG)
  - HIGHs decrecientes + cruce no logrado → -50 (cerrar LONG)
- Misma lógica espejada para cruce EMA9/EMA20 → ±30 adicionales (mayor jerarquía de tendencia)

### 4.4 Nivel 5m (peso: 15%)
- Escenario a (EMA3>EMA9>EMA20, sobre BASIS, 9 velas sin cruzar banda superior, EMA3 empieza a descender) → -40 para LONG
- Escenario b (EMA3>EMA9>EMA20, sobre banda superior, squeeze activo) → +40 a favor de mantener LONG mientras continúe el squeeze; invertir si HIGHs de 1m dejan de expandirse (ver 4.5)

### 4.5 Nivel 1m — confirmación de squeeze (peso: 10%)
- Solo se activa cuando 5m está en escenario b (squeeze)
- HIGHs de las últimas 3 velas cerradas de 1m: si la vela vigente no supera o queda por debajo de las anteriores → señal de agotamiento → ±40
- Requiere EMA3 cercano a EMA9 (dentro de un umbral parametrizable en % de ATR)

### 4.6 Componente RSI multi-timeframe (capa transversal)

El RSI(14) se calcula sobre 1D, 4H, 15m y 5m, y aporta puntos adicionales a cada nivel correspondiente (4.1 a 4.4), acotados por el mismo rango [-100, 100] del nivel:

- **Nivel extremo**: RSI < 20 (sobreventa, favorable a cierre de SHORT / mantener LONG) o RSI > 80 (sobrecompra, favorable a cierre de LONG / mantener SHORT) → ±25 puntos al score del nivel correspondiente
- **Divergencia** (comparando precio vs RSI en las últimas 3 velas cerradas, sin la vela vigente — misma metodología que la estructura HH/LL de 4.3): precio hace nuevo máximo/mínimo pero el RSI no lo confirma → ±35 puntos (más peso que el nivel extremo simple, por ser señal más confiable)

**Interacción con el régimen ADX (sección 5):** en régimen de tendencia fuerte (ADX>30), el componente de nivel extremo se reduce en 50% (el RSI puede mantenerse en zona extrema por periodos largos sin que eso implique reversión inminente). La divergencia mantiene su peso completo en cualquier régimen, porque es una señal de agotamiento del momentum, no solo de nivel.

### 4.7 Score final combinado

```
score_final = (score_1D * 0.30) + (score_4H * 0.25) + (score_15m * 0.20)
            + (score_5m * 0.15) + (score_1m * 0.10)
```

Los pesos son parámetros configurables por instrumento y por `entry_profile` (ver sección 14) — ver también sección 11.

### 4.8 Tabla de decisión (semáforo con intensidad)

| Score final | Semáforo | Acción sugerida |
|---|---|---|
| -100 a -60 | Rojo fuerte | Cierre total inmediato |
| -60 a -25 | Rojo débil | Cierre parcial (si aplica squeeze) o vigilancia reforzada |
| -25 a +25 | Ámbar | Mantener, solo logging |
| +25 a +60 | Verde débil | Mantener, vigilancia normal |
| +60 a +100 | Verde fuerte | Mantener con confianza, sin intervención |

*(Para posición SHORT, invertir la lectura del signo.)*

---

## 5. Filtro de régimen de volatilidad (ADX + DI)

Calculado sobre la temporalidad relevante (ver sección 6 para selección dinámica):

| ADX | Régimen | Efecto en el motor |
|---|---|---|
| < 15 | Rango / choppy | Se prioriza lógica de SQUEEZE (4.5). Se reduce el peso de cruces EMA de 15m en 50% (alta tasa de falsos positivos en lateral) |
| 15–30 | Tendencia moderada | Cruces EMA con peso normal, requieren confirmación por volumen (sección 7) |
| > 30 | Tendencia fuerte | Se incrementa el peso del macro (1D/4H) en 20%; se exige score micro más extremo (umbral -60 en vez de -25) para disparar cierre por señales de corto plazo |

DI+ y DI- se usan para confirmar la dirección de la fuerza medida por ADX antes de aplicar el ajuste — un ADX alto con DI- dominante confirma tendencia bajista, no solo "tendencia fuerte" sin dirección.

Complementario: clasificación por variación % de precio/volumen sobre ventana móvil (ej. 20 periodos) en bajo/medio/alto, usada como segunda señal de contexto junto al ADX (parametrizable, ver sección 8).

---

## 6. Índice de compresión EMA + proximidad Fibonacci

### 6.1 Cálculo

```
D1 = |EMA20 - EMA9|
D2 = |EMA3 - EMA9|
Indice_Compresion = D2 / D1   (normalizado por ATR del instrumento)
```

- `Indice_Compresion` bajo (por debajo de umbral parametrizable, ej. < 0.15) → EMAs "apretadas" → alta probabilidad de reversión o de rebote en EMA9
- Se evalúa junto con la dirección del precio: si el precio cae desde EMA3 hacia EMA9 con índice bajo, el rebote en EMA9 es más probable que la continuación de la caída

### 6.2 Multiplicador por Fibonacci

Si la compresión de EMAs ocurre simultáneamente con el precio en una banda Fibonacci (LOWER_1-6, UPPER_1-6, BASIS ya existentes en la plataforma), el score de reversión de esa capa se multiplica:

| Zona Fibonacci | Multiplicador |
|---|---|
| BASIS | x1.0 (neutral) |
| LOWER_1 / UPPER_1 | x1.2 |
| LOWER_2 / UPPER_2 | x1.4 |
| LOWER_3+ / UPPER_3+ | x1.6 (zona extrema) |

### 6.3 Selección dinámica de temporalidad para el índice de compresión

En vez de una lista fija por símbolo, se clasifica el instrumento dinámicamente por su **ATR% diario** (ATR14 / precio actual), recalculado periódicamente (ej. cada 24h):

| ATR% diario | Clasificación | Temporalidad usada para D1/D2 y cooldown |
|---|---|---|
| > 0.8% | Alta volatilidad (típico XAUUSD, USDJPY en sesiones activas) | 4H |
| ≤ 0.8% | Volatilidad normal | 15m |

Esto reemplaza el hardcodeo por símbolo — si otro instrumento sube o baja de volatilidad, el sistema reclasifica solo automáticamente.

---

## 7. Confirmación por volumen

Aplicado como filtro de confianza sobre los cruces EMA de 15m y el análisis de squeeze en 5m/1m, **no** como bloqueo total (para no perder cierres válidos en instrumentos de bajo volumen natural):

- **Cripto / Acciones**: volumen de la vela del cruce > 1.3x el promedio de volumen de las últimas 10 velas de esa temporalidad
- **Forex**: mismo umbral 1.3x sobre tick volume; si no está disponible, usar expansión del rango (high-low) de la vela como proxy

**Efecto en el score:** si el cruce ocurre pero el volumen no confirma, el score de esa capa se reduce en 50% (ej. de -60 pasa a -30) en vez de anularse.

---

## 8. Reglas de cierre y umbral de ganancia mínima

- **Ganancia mínima:** $1 USD de PNL flotante como condición necesaria (no suficiente) para ejecutar cualquier cierre. Si el score indica cierre pero `current_pnl < $1`, CENTINELA no ejecuta y solo registra la señal (log) — se espera a que el precio recupere el umbral o a que el stop reactivo (SLV/SLVM) actúe.
- **Cierre total:** score en rango Rojo fuerte (o Verde fuerte para SHORT).
- **Cierre parcial (scale-out):** score en rango Rojo débil **y** escenario de squeeze detectado (5m/1m). Porcentaje parametrizable, default 50%.
  - La porción remanente queda bajo el Trailing Stop existente (SLVM) — **CENTINELA no calcula un stop nuevo para el remanente**, evita doble cálculo de stops sobre la misma posición.

---

## 9. Jerarquía y arbitraje con módulos existentes

| Módulo | Naturaleza | Rol |
|---|---|---|
| SLV/SLVM | Reactivo | Última línea de defensa. Siempre activo, nunca desactivado por CENTINELA |
| CENTINELA | Proactivo | Intenta cerrar antes de necesitar el stop, con ganancia mínima asegurada |
| Trailing Stop (3 fases) | Reactivo | Protege ganancia ya generada cuando CENTINELA no actuó a tiempo |

**Regla de arbitraje:** al recibir señal de cierre de CENTINELA, se coloca un flag `closing_in_progress = true` sobre la posición antes de enviar la orden. Si SLV/SLVM o Trailing Stop se disparan mientras el flag está activo, se descarta su ejecución (la posición ya está en proceso de cierre) para evitar orden duplicada o error de "posición no encontrada".

---

## 10. Máquina de estados por posición

```
NEUTRAL ──(score cruza ±25)──> VIGILANCIA
VIGILANCIA ──(score cruza ±60, sin squeeze)──> CIERRE_TOTAL
VIGILANCIA ──(score cruza ±25 a ±60, con squeeze)──> CIERRE_PARCIAL
CIERRE_PARCIAL ──(remanente bajo Trailing Stop)──> MONITOREADO_POR_TRAILING
CIERRE_TOTAL ──(orden ejecutada)──> CERRADA
```

Cooldown: tras cualquier cierre (total o parcial) sobre una posición, no se reevalúa esa posición por un periodo mínimo parametrizable (default 5 min en 15m, 15 min en 4H) para evitar whipsaw.

---

## 11. Parámetros configurables (resumen)

| Parámetro | Default | Notas |
|---|---|---|
| Pesos por timeframe (1D/4H/15m/5m/1m) | Depende de `entry_profile` — ver sección 14 | Ajustable también por instrumento |
| Umbral cierre total | ±60 (TENDENCIA_SOSTENIDA) / ±45 (ALTA_VOLATILIDAD) | Ver sección 14 |
| Umbral cierre parcial | ±25 a ±60 | Requiere squeeze activo |
| % de cierre parcial | 50% | — |
| Ganancia mínima | $1 USD | Evaluar si migrar a % nocional si tamaños de posición dejan de ser uniformes |
| Umbral ADX rango/tendencia | 15 / 30 | — |
| Umbral índice de compresión | 0.15 | Normalizado por ATR |
| Umbral confirmación de volumen | 1.3x promedio 10 velas | — |
| Umbral ATR% para clasificar volatilidad | 0.8% diario | Determina 4H vs 15m para compresión/cooldown |
| Umbral RSI extremo | <20 / >80 | Reducido 50% en régimen de tendencia fuerte |
| Peso divergencia RSI | ±35 puntos por nivel | Sin reducción por régimen |
| Cooldown post-cierre | Depende de `entry_profile` — ver sección 14 | — |
| Frecuencia de monitoreo | Depende de `entry_profile` — ver sección 14 | — |

---

## 12. Modo de despliegue (rollout)

1. **Shadow mode (3–5 días):** HALCÓN calcula y loguea el score y la decisión sugerida por cada posición abierta, sin enviar ninguna orden real. Objetivo: detectar bugs de lógica (cierres duplicados, señales contradictorias no resueltas, errores de cálculo) antes de arriesgar capital real.
2. **Producción:** una vez validado el log de shadow mode sin inconsistencias, activar ejecución real. Criterio de aceptación en producción: mientras el PNL de las posiciones cerradas por CENTINELA se mantenga por encima de $1 en promedio, el modelo se considera aceptable y sigue en operación.
3. **Logging continuo:** cada decisión (cierre o no cierre) debe quedar registrada con el detalle de scores por capa, para poder auditar y recalibrar pesos/umbrales con datos reales en el futuro.

---

## 14. Perfiles de compra (`entry_profile`)

Cada posición se etiqueta al momento de apertura con un perfil que determina cómo HALCÓN/CENTINELA la va a monitorear. El perfil se asigna **automáticamente** (por la estrategia origen que generó la orden, o por las condiciones de mercado — ADX/ATR% — en el momento de la compra), no manualmente, para mantener trazabilidad.

### 14.1 ALTA_VOLATILIDAD
Ejemplo: LONG en 15m con EMA3>EMA9>EMA20 y expansión rápida de volumen/precio. Se espera rentabilidad rápida y una reversión también rápida y poco anunciada.

| Parámetro | Valor |
|---|---|
| Pesos (1D/4H/15m/5m/1m) | 10/15/25/25/25 |
| Umbral cierre total | ±45 |
| Frecuencia de monitoreo | 1m y 5m casi en tiempo real (cada 15-30s) |
| Cooldown post-cierre | 2 min |
| RSI extremo | Peso completo, sin reducción por régimen (la reversión rápida es justamente el escenario que se busca capturar) |

### 14.2 TENDENCIA_SOSTENIDA (default)
El diseño base descrito en las secciones 4 a 10 de este documento.

| Parámetro | Valor |
|---|---|
| Pesos (1D/4H/15m/5m/1m) | 30/25/20/15/10 |
| Umbral cierre total | ±60 |
| Frecuencia de monitoreo | Estándar (1D cada 5 min, resto según cierre de vela) |
| Cooldown post-cierre | 5 min (15m) / 15 min (4H) |

### 14.3 Consideraciones futuras (no bloquean la v1)

- **Correlación entre posiciones simultáneas**: instrumentos correlacionados (ej. varios pares USD) pueden disparar señales de cierre en cascada por la misma causa sistémica — no es un bug, pero conviene monitorearlo.
- **Liquidez por sesión** (forex): sensibilidad de ADX/RSI ajustable entre sesión asiática (baja liquidez) y Londres/NY (alta liquidez).

---

## 15. ORÁCULO — Módulo de pausa por calendario económico

Componente independiente de HALCÓN, con permiso para **forzar** cierres en CENTINELA (bypass del score normal y del umbral de ganancia mínima) cuando se acerca un evento económico de alto impacto.

### 15.1 Fuente de datos
Feed de calendario económico con impacto clasificado (Alto/Medio/Bajo) y hora exacta de publicación (ej. Trading Economics API, Finnhub `/calendar/economic`, FMP Economic Calendar — a elección de Antigravity según API keys ya disponibles en la plataforma). Se requiere como mínimo: `evento`, `moneda`, `impacto`, `hora_publicación`.

Sincronización: se refresca el calendario de las próximas 24-48h al menos una vez por hora; los eventos ya evaluados no se recalculan hasta su ventana de pausa.

### 15.2 Mapeo instrumento → monedas afectadas

| Instrumento | Monedas relevantes |
|---|---|
| USDJPY | USD, JPY |
| XAUUSD | USD (principalmente; reacciona fuerte a NFP, CPI, FOMC) |
| EURUSD | EUR, USD |
| BTCUSD | USD (indirectamente, vía apetito de riesgo) |

Tabla configurable y extensible por cada par de divisas presente en el símbolo.

### 15.3 Eventos globales ("mega")
Lista corta de eventos que pausan **todos** los instrumentos abiertos, sin importar la moneda del símbolo, por su impacto transversal en el mercado: FOMC, NFP, CPI de EE.UU., decisiones de tasas de BOJ/ECB/BOE. El resto de eventos de alto impacto solo pausan los instrumentos que contienen la moneda afectada (según 15.2).

### 15.4 Lógica de pausa

```
T-60min antes del evento de Alto Impacto (específico o global):
  → ORÁCULO marca trading_paused[symbol] = true
  → Se bloquean nuevas aperturas LONG/SHORT en ese símbolo mientras el flag esté activo
  → Para cada posición abierta en el símbolo, evaluar PNL actual:

      SI PNL > -$5 (pérdida pequeña o ganancia):
        → CENTINELA ejecuta CIERRE_TOTAL en mercado de inmediato,
          ignorando el score de HALCÓN

      SI PNL <= -$5 (pérdida ya significativa):
        → No se cierra en mercado. En su lugar, se coloca un bracket
          SL/TP nativo del broker (OCO) directamente sobre la posición:
            - SL: piso de -$8 en total (es decir, hasta $3 adicionales
              de pérdida más allá del PNL actual en el peor caso)
            - TP: dinámico según estado de squeeze (ver 15.4.1)
        → El bracket queda a nivel del broker, no depende de que
          CENTINELA siga monitoreando en tiempo real durante el evento

T+60min después de publicado el evento:
  → ORÁCULO libera trading_paused[symbol] = false
  → Si el bracket no se activó (posición sigue abierta), se cancela
    el bracket y la posición vuelve a evaluación normal de HALCÓN/CENTINELA
  → Si el bracket ya se ejecutó (SL o TP tocado), la posición queda cerrada
```

### 15.4.1 Definición del TP dinámico (squeeze)

El TP del bracket no es un valor fijo — se define según si hay squeeze activo en la posición al momento de activarse el flag `trading_paused` (misma detección de squeeze de las secciones 4.4/4.5):

| Estado | TP |
|---|---|
| Squeeze activo | Banda de Fibonacci más externa a favor del movimiento (UPPER_3+ / LOWER_3+) — captura el máximo posible del squeeze antes de la pausa |
| Sin squeeze | Banda de Fibonacci más cercana a favor del movimiento (UPPER_1 / LOWER_1) — captura ganancia mínima rápido, sin exponerse de más antes del evento |

### 15.5 Fail-safe
Si la fuente de calendario no responde o falla la sincronización, ORÁCULO debe asumir el escenario más conservador: mantener la última pausa conocida activa y generar una alerta — nunca interpretar "sin datos" como "sin riesgo". Si no hay forma de confirmar que no hay eventos próximos, no se debe levantar una pausa activa automáticamente.

### 15.6 Parámetros configurables

| Parámetro | Default |
|---|---|
| Ventana de pausa pre-evento | 60 min |
| Ventana de pausa post-evento | 60 min |
| Impacto mínimo que activa pausa | Alto |
| Umbral de cierre en mercado | PNL > -$5 |
| Piso del SL en bracket | -$8 en total |
| TP en bracket | Dinámico según squeeze (ver 15.4.1) |
| Frecuencia de sincronización del calendario | Cada 60 min |
| Fuente de datos del calendario | FRED / Finnhub / FMP (APIs ya disponibles en la plataforma — ver 15.1) |

### 15.7 Fuente de datos disponible

Ya existen 3 API keys activas en la plataforma que cubren esta necesidad: `FRED_API_KEY`, `FINNHUB_API_KEY`, `FMP_API_KEY`. Recomendación de uso:

- **Finnhub** (`/calendar/economic`) o **FMP** (Economic Calendar) son los más directos para esto — ambos devuelven evento, país/moneda, impacto y hora de publicación en un solo endpoint, ideal para el sincronizador de ORÁCULO.
- **FRED** es más útil como fuente complementaria de series históricas (para, por ejemplo, calibrar más adelante qué tanto se mueve un instrumento en eventos pasados), pero no está pensado como calendario de eventos futuros con hora exacta — no es la fuente principal para el trigger de pausa.

Antigravity puede usar Finnhub o FMP como fuente primaria (lo que ya esté integrado en otro módulo de la plataforma para evitar duplicar la conexión) y dejar FRED como fuente secundaria/histórica si más adelante se quiere calibrar el modelo con datos reales de movimientos pasados.

---

## 16. Notas para Antigravity

- HALCÓN debe implementarse como un módulo de cálculo puro (dado un set de datos de mercado + posición + `entry_profile`, devuelve `score_final` y `decision`), sin efectos secundarios — facilita testing unitario y el modo shadow.
- CENTINELA es el único componente con permiso de enviar órdenes; consume la salida de HALCÓN y aplica las reglas de arbitraje (sección 9) y cooldown (sección 10), con los parámetros específicos del `entry_profile` de cada posición (sección 14).
- Reutilizar el cálculo de EMA3/9/20, Bollinger, RSI y bandas Fibonacci ya existentes en la plataforma eTrade v5.0 — no reimplementar.
- El flag `closing_in_progress` debe vivir a nivel de la posición en el store central, accesible tanto por CENTINELA como por SLV/SLVM y Trailing Stop, para que el arbitraje funcione correctamente entre los tres módulos.
- La asignación de `entry_profile` debe quedar registrada junto con la estrategia origen que generó la orden, para poder auditar más adelante si el perfil predijo correctamente el comportamiento real de la posición.
- ORÁCULO (sección 15) debe implementarse como servicio independiente con permiso de forzar cierres directamente sobre CENTINELA, con prioridad sobre HALCÓN y sobre SLV/SLVM/Trailing Stop — su ejecución no espera el ciclo normal de evaluación de score.
- **Advertencia sobre el bracket SL/TP de ORÁCULO (15.4):** durante un evento de alto impacto el precio puede saltar (gap) el nivel del SL, ejecutándose con slippage más allá del piso definido (-$8), a menos que el broker ofrezca *guaranteed stop-loss*. Confirmar con el broker si esa opción existe y su costo; si no existe, documentar el SL como "mejor esfuerzo" y no como piso absoluto garantizado.
