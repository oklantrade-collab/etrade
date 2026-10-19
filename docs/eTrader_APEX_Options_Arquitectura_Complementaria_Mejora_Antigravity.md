# eTrader APEX Options
## Arquitectura complementaria de mejora para Antigravity

**Versión:** 1.0
**Fecha:** 18 de octubre de 2026
**Complementa:**
- `eTrader_APEX_Options_Arquitectura_Antigravity.md` v1.2 ("el principal")
- `eTrader_APEX_Options_Addendum_Estrategias_Antigravity_v1.1` ("el addendum")
- `eTrader_APEX_Options_Propuesta_Mejora_Antigravity.md` v1.0 ("la propuesta")

**Modo:** Observación y Paper Trading únicamente. No existe ruta de órdenes reales.

---

## 0. Cómo leer este documento

**Fuente de verdad.** Para todo lo ya implementado, **el código real manda sobre cualquier documento**. La propuesta describe `backend/app/options/score.py`, `valuation.py`, la ADUANA de Opciones O-1 a O-12 y las vistas TOP 3 CALL / TOP 3 PUT *a partir de una especificación*, no de una inspección del repositorio; yo tampoco he visto el código. Todo lo que aquí se afirme sobre el sistema existente es una **hipótesis que el hito M0 debe confirmar o corregir**.

**Precedencia de este documento:**
- Prevalece sobre el principal en: §6.4 regla O-7 (datos `DELAYED`), §11 (descripción de componentes del score, que se alinea con el código existente) y §16 (nombres de tablas, que siguen la convención ya existente).
- No altera el addendum, salvo la numeración de reglas (§6).
- En todo lo demás siguen vigentes los tres documentos previos.

**Etiquetas:** **[FIJO]** decisión de producto no modificable sin aprobación; **[POR DEFECTO]** parámetro inicial editable y calibrable (no es una ley de mercado); **[VERIFICAR]** se resuelve contra el código, IBKR o la cuenta.

**Principio de invarianza [FIJO]:** una puntuación alta jamás convierte una operación inválida en elegible. Primero los filtros duros de ADUANA; solo las candidatas aprobadas se puntúan y ordenan. El score es un ranking, no una probabilidad calibrada.

---

## 1. Resumen ejecutivo

La propuesta aporta una dirección sólida: calidad de datos, score explicable, control de riesgo, simulación realista, validación fuera de muestra y trazabilidad. Este documento la **adapta a lo que ya existe** y añade lo que falta para que Antigravity pueda construir sin ambigüedad:

1. Una **reconciliación** explícita de numeraciones, nombres y reglas entre los cuatro documentos y el código.
2. **Modos de operación** (`observation` / `paper`), **estados de salud** y **kill switch**, con protocolo de reanudación seguro.
3. **Data Quality Gate** con criticidad por variable, política de faltantes y cobertura medible.
4. **Catálogo de comportamientos requeridos de ADUANA** (B-01 a B-17), mapeables a las reglas O-1…O-12 existentes sin renumerar.
5. **Calendario de eventos** con cuatro estados y política fail-closed.
6. **Sensibilidad del EV, robustez y griegas netas**, sin doble conteo de costes.
7. **Score explicable y versionado**, perfiles por familia (inactivos hasta validar), análisis de poder discriminante y protocolo **champion / challenger**.
8. **Revalidación de precio al abrir**, modelo de fills con latencia, idempotencia y reconciliación.
9. **Libro contrafactual** para multiplicar los datos de validación (con 0 a 3 operaciones al día, 100 operaciones tardan semanas).
10. **Replay determinista** de evaluaciones y plan de pruebas.

---

## 2. Reconciliación entre documentos y conflictos detectados

| # | Tema | Situación | Resolución |
|---|---|---|---|
| 1 | Numeración de ADUANA | Principal: O-1…O-11; addendum: O-12 y O-13; la propuesta y el código: **O-1…O-12** | La numeración del **código** es canónica. Este documento define comportamientos B-01…B-17 (§6); Antigravity los mapea a las O-n existentes y propone O-13+ para los que falten, **sin renumerar** nada |
| 2 | Datos `DELAYED` | La propuesta describe un multiplicador de liquidez de 0,70 para `DELAYED` "en modo de prueba"; el principal exige `LIVE` en ADUANA (O-7) | `DELAYED` solo es aceptable en modo `observation` y **nunca** abre operaciones. En modo `paper` se bloquea de forma dura. El multiplicador queda como defensa en profundidad, no como vía de elegibilidad |
| 3 | Nombres de tablas | Principal: prefijo `opt_*`; propuesta: `options_*` | Si ya existe una convención en Supabase, **se sigue esa**; `opt_*` era solo el valor por defecto sin convención previa (§13) |
| 4 | Componentes del score | Principal: 6 componentes con nombres distintos; propuesta/código: expectativa, señal/catalizador, liquidez, riesgo, IV y griegas, contexto | Se adopta la definición del **código** como baseline. Pesos 30/20/20/15/10/5 coinciden |
| 5 | Planes de sprints | Principal: Sprint 0–8; addendum: E0–E6; propuesta: Sprint 0–6 | Un solo calendario con hitos **M0–M6** (§19), que declara primero qué está ya construido |
| 6 | `LIVE_TRADING_ENABLED = false` | La propuesta usa una bandera; el principal exige bloqueo por construcción | La bandera es redundante, no es el control. El control es que **no existan métodos de órdenes** en el adaptador (principal §14.2). Si la bandera llegara a `true`, el módulo **no arranca** |
| 7 | "Reconciliar con el broker" | En V1 el paper es una simulación interna y el adaptador es de solo lectura | La reconciliación es entre el libro simulado, sus fills y el recálculo; no hay posiciones de broker que reconciliar (§11.5) |
| 8 | Estados de candidata y posición | La propuesta sugiere `REJECTED … UNKNOWN`; el principal y el addendum usan otros | Una sola máquina de estados (§11.4) |
| 9 | Delta ≈ 0,50 | El baseline premia delta cercano a 0,50 en contratos comprados; con riesgo máximo de USD 50 la prima ATM suele ser inviable | Se conserva como baseline y se mide el efecto (§3.2); los perfiles por familia (§9.3) lo sustituyen **solo tras validación** |
| 10 | Doble conteo en el score | El EV pesa 30% y además entra en el componente de riesgo ("EV adverso", 30% de 15%); el sobrecoste de ejecución del componente de riesgo se solapa con el spread del de liquidez | No se cambia nada. Se **mide** la colinealidad entre componentes antes de tocar pesos (§9.5) |
| 11 | Calendar y Diagonal en perfiles | La propuesta los incluye como familia puntuable | Siguen en "solo análisis manual" (addendum §7.5); el perfil existe pero permanece inactivo |
| 12 | Eventos desconocidos | La propuesta introduce `UNKNOWN`/`STALE`; el principal solo contemplaba earnings conocidos | Política fail-closed por defecto (§7) |

---

## 3. Baseline a preservar y puntos a auditar

### 3.1 Baseline (según la propuesta; confirmar en el código)

```
Score = Σ(S_i × W_i) / Σ(W_i),   0 ≤ Score ≤ 100
```

| Componente | Peso | Parámetro |
|---|---:|---|
| Expectativa matemática neta | 30% | `w_expectancy` |
| Señal / catalizador | 20% | `w_apex_signal` |
| Liquidez / calidad de cotización | 20% | `w_liquidity` |
| Riesgo / escenarios adversos | 15% | `w_risk` |
| IV y griegas | 10% | `w_iv_greeks` |
| Contexto / eventos binarios | 5% | `w_context` |

Selección actual: `min_score = 60`; desempate por score descendente, EV ratio descendente y pérdida máxima ascendente; hasta 3 operaciones al día; TOP 3 CALL y TOP 3 PUT como vistas. Añadir como desempate final determinista el identificador de la evaluación (o el `conid` de la primera pata).

**Regla [FIJO]:** no cambiar pesos, `min_score`, `ev_anchor`, ADUANA ni límites financieros sin pruebas comparativas, validación fuera de muestra y aprobación.

### 3.2 Puntos a auditar en M0 (sin modificar comportamiento)

| Punto | Qué comprobar |
|---|---|
| Delta de PUT | Que la proximidad a 0,50 use `abs(delta)`; que el signo negativo no penalice los PUT |
| Multiplicador `DELAYED` | Que ninguna ruta permita una entrada paper con datos `DELAYED` |
| Componente "IV" | Qué mide exactamente el 50% de IV del componente IV/griegas (dirección de preferencia, fuente de IV histórica) |
| EV | Que use precios ejecutables (ask/bid + slippage) y no el midpoint; que los costes se descuenten **una sola vez** |
| Pérdida máxima | Que incorpore multiplicador de cada pata y número de contratos |
| Faltantes | Cómo trata un componente ausente (cero, renormalización, rechazo) |
| Eventos | Si "sin evento" significa "verificado" o solo "sin datos" |
| Riesgo agregado | Si el selector incluye las posiciones abiertas |
| TOP 3 | Que sea informativo y no pueda activar entradas |
| Distribución | Distribución de scores históricos; porcentaje de candidatas por encima de 60; efecto de la restricción de USD 50 sobre el delta elegible |
| Dónde viven O-1…O-12 | Documentar archivo, versión y contrato de entrada/salida de cada regla |

Entregable de M0: informe + **pruebas de regresión con fixtures** (golden files) que congelen el comportamiento actual antes de cualquier cambio.

---

## 4. Modos de operación, salud y control

### 4.1 Modos [FIJO]

| Capacidad | `observation` | `paper` |
|---|:---:|:---:|
| Escanear, valorar y puntuar | Sí | Sí |
| Grabar snapshots | Sí | Sí |
| Datos `DELAYED` | Aceptados, marcados "no operable" | **Bloqueados** |
| Selector y entradas paper | **No** | Sí |
| Libro contrafactual (§12.2) | Sí | Sí |
| Envío de órdenes reales | No existe | No existe |

- El modo se guarda en Settings; pasar a `paper` exige permisos de datos de opciones verificados en tiempo real (`LIVE`).
- Un tercer modo (real) **no se diseña en esta fase**. Su introducción requeriría un documento aparte, cambio del principio de adaptador de solo lectura y aprobación explícita.

### 4.2 Estados de salud

| Estado | Efecto | Salida |
|---|---|---|
| `NORMAL` | Operación completa | — |
| `DEGRADED` | **No hay nuevas entradas.** Las posiciones abiertas se siguen gestionando con las salidas existentes | Automática cuando se recuperan las condiciones durante un periodo de estabilidad |
| `HALTED` | Sin nuevas entradas; se activa el protocolo de reanudación (§4.4) | Solo manual, con comprobaciones superadas |

Disparadores **[POR DEFECTO, editables]**:

| Condición | Estado |
|---|---|
| IBKR desconectado más de 30 s | `DEGRADED` |
| Antigüedad de cotización p95 > 10 s durante 5 min | `DEGRADED` |
| Más del 30% de las candidatas con datos `STALE` en una corrida | `DEGRADED` |
| Scanner con retraso mayor que 2× su frecuencia | Alerta |
| Discrepancia de reconciliación superior a la tolerancia | `HALTED` |
| 3 errores consecutivos de escritura en base de datos | `HALTED` |
| Kill switch activado | `HALTED` |

**Fail closed [FIJO]:** si falla un control crítico, no se autorizan nuevas entradas.

### 4.3 Kill switch

- Interruptor manual (rol propietario), con motivo obligatorio y registro de auditoría.
- Efecto: detiene nuevas entradas. **No cierra posiciones**: las posiciones abiertas siguen bajo sus reglas de salida.
- Protocolo separado "cerrar todo en simulación": acción distinta, con confirmación explícita y con el mismo registro de auditoría.

### 4.4 Protocolo de reanudación (tras reinicio, reconexión o `HALTED`)

1. El motor arranca en `HALTED`.
2. Reconciliar el libro paper (§11.5) y verificar que no hay duplicados (restricciones únicas).
3. Verificar que existen los trabajos programados de salida forzada para cada posición abierta.
4. Verificar que hay una cotización válida y reciente (para valorar las posiciones abiertas); si no, las posiciones se marcan `NOT_VALUABLE` y se alerta.
5. Reanudar solo si todo pasa; si no, permanecer en `DEGRADED` con alerta.
6. Registrar el resultado de cada comprobación.

---

## 5. Data Quality Gate

### 5.1 Estados por variable [FIJO]

`VALID`, `MISSING`, `STALE`, `DELAYED`, `INVALID`, `NOT_APPLICABLE`. Nunca se imputan ceros. Cada cotización registra origen, timestamp, tipo de mercado y antigüedad.

| Estado | Definición |
|---|---|
| `STALE` | Antigüedad mayor que `max_quote_age_sec` |
| `DELAYED` | Tipo de dato retrasado |
| `INVALID` | `bid > ask`, valores negativos, `bid = 0` en una pata vendida, strike o vencimiento incoherentes |
| `MISSING` | Dato ausente |
| `NOT_APPLICABLE` | No procede para esa pata o estrategia |

### 5.2 Criticidad

| Nivel | Variables | Efecto si no son `VALID` |
|---|---|---|
| **Crítico** | Precio del subyacente; `conid`, tipo, strike, vencimiento, multiplicador y trading class de cada pata; `bid` y `ask`; timestamp; tipo de mercado (`LIVE` en `paper`) | **Rechazo** con código `DATA_QUALITY_FAILURE` |
| **Importante** | IV, delta y demás griegas, volumen, open interest, tamaño bid/ask | Reducen la **cobertura** del score (§5.3) |
| **Opcional** | Rho, percentil de IV histórica, tamaños adicionales | No bloquean; se muestran como ausentes |

El gate **no puntúa**: clasifica y detiene. No duplicar su lógica en otros módulos.

### 5.3 Cobertura y componentes faltantes

```
coverage = Σ W_i de los componentes calculables / Σ W_i totales
```

Política `missing_component_policy`:

| Tipo de componente | Política **[POR DEFECTO]** |
|---|---|
| Esenciales (expectativa, liquidez, riesgo) | `reject`: código `INSUFFICIENT_COVERAGE` |
| No esenciales (señal, IV/griegas) | `conservative_zero`: contribución 0 y bandera visible; el peso **no** se redistribuye |
| Contexto/eventos | Se rige por la política de eventos (§7), no por esta |
| Renormalizar pesos | **Deshabilitado**. Solo con aprobación explícita y mostrando siempre la cobertura |

Además, `min_coverage` **[POR DEFECTO] 0,80**. Una candidata con cobertura menor se rechaza. El score guarda `coverage` y la lista de componentes ausentes.

---

## 6. Catálogo de comportamientos requeridos de ADUANA

No se renumera ADUANA. Antigravity construye en M0 una **tabla de equivalencias** entre estos comportamientos y las reglas O-1…O-12 existentes. Si falta alguno, se propone una regla **O-13 o posterior**, añadida al final.

| Código | Comportamiento requerido | Equivalente en el código |
|---|---|---|
| B-01 | Modo coherente con el estado de datos: en `paper`, solo `LIVE` | [VERIFICAR] |
| B-02 | Riesgo definido y pérdida máxima calculable | [VERIFICAR] |
| B-03 | Pérdida máxima total (con costes, contratos y multiplicador) ≤ riesgo por operación | [VERIFICAR] |
| B-04 | Riesgo abierto agregado (posiciones abiertas + la nueva) ≤ límite | [VERIFICAR] |
| B-05 | Stop diario no activado | [VERIFICAR] |
| B-06 | Spread relativo por pata y sobrecoste de ejecución del paquete dentro de umbral | [VERIFICAR] |
| B-07 | Frescura de cotización y sincronización entre patas | [VERIFICAR] |
| B-08 | Ventana horaria de entrada | [VERIFICAR] |
| B-09 | Eventos: se exige `CLEAR_VERIFIED`; `EVENT_FOUND` bloquea según política; `UNKNOWN` o `STALE` bloquea | [VERIFICAR] |
| B-10 | Idempotencia: la misma evaluación no abre dos posiciones | [VERIFICAR] |
| B-11 | Concentración por ticker, sector, dirección y vencimiento | [VERIFICAR] |
| B-12 | Estrategia en estado `enabled` (libro principal) o `shadow` (libro shadow) | [VERIFICAR] |
| B-13 | Contrato estándar y multiplicador conocido | [VERIFICAR] |
| B-14 | Cobertura mínima y componentes esenciales presentes | [VERIFICAR] |
| B-15 | Salud `NORMAL` y kill switch inactivo | [VERIFICAR] |
| B-16 | Coherencia direccional señal–estrategia cuando se exige | [VERIFICAR] |
| B-17 | Revalidación de precio al abrir (§10.3) | [VERIFICAR] |

**Contrato de salida [FIJO]:** ADUANA devuelve para cada candidata el resultado **por regla**: identificador, aprobada/rechazada, código legible, detalle y versión de ADUANA. Se persiste cada resultado (§13). La decisión de elegibilidad se centraliza en un único módulo.

---

## 7. Calendario de eventos

Capa de eventos con: fuente, timestamp de consulta, símbolo, tipo, fecha/hora (ET y UTC), horizonte y estado de verificación. Reutilizar las fuentes de datos ya integradas en la plataforma **[VERIFICAR cuáles existen y su cobertura]**.

### 7.1 Estados

`CLEAR_VERIFIED`, `EVENT_FOUND`, `UNKNOWN`, `STALE`.

- "Sin eventos" solo es válido si el calendario se consultó dentro de `calendar_max_age_hours`.
- Un calendario no consultado o desactualizado **nunca** se etiqueta como ausencia confirmada.

### 7.2 Política **[POR DEFECTO, editable por estrategia y DTE]**

| Evento | Política |
|---|---|
| Earnings o guidance dentro del DTE | **Bloquea** |
| Ex-dividendo dentro del DTE | Bloquea estructuras con Call corta cerca del ATM (addendum §7.3) |
| Publicación macro de alto impacto (decisión de tasas de la Fed, inflación, empleo) | Bloquea nuevas entradas desde 30 min antes hasta 5 min después |
| Evento corporativo conocido (split, fusión, halt) | Bloquea |
| Estado `UNKNOWN` o `STALE` | **Bloquea** (`unknown_event_policy = block`) |

En modo `observation`, `unknown_event_policy` puede ser `penalize_context` para análisis; **nunca** en `paper`. Los eventos se guardan con su estado en cada evaluación.

---

## 8. Valoración, EV y griegas

### 8.1 Identidad del EV y costes sin doble conteo [FIJO]

```
ev_view_net = Σ_s  p_s × ( pnl_bruto_s − costes_ida_y_vuelta_s )
```

- Los costes de ida y vuelta (comisiones, fees y slippage) se descuentan **exactamente una vez**.
- La entrada usa precios ejecutables (ask para comprar, bid para vender), no el midpoint. El midpoint es solo informativo.
- Prueba obligatoria: `ev_view_net = ev_bruto − costes` sin términos duplicados.

### 8.2 Sensibilidad y robustez

Para cada candidata, calcular el EV en un conjunto fijo de escenarios:

| Escenario | Cambio |
|---|---|
| Base | Parámetros vigentes |
| Sesgo reducido | `alpha × 0,5` |
| Sin sesgo | `alpha = 0` |
| Ejecución adversa | Slippage y spread de salida adversos |
| IV −10% | Shock relativo de IV |
| Vol alternativa | `k_vol` en 0,8 y 1,2 |

Se guardan `ev_min` y `ev_range`. La bandera `ev_robust` es verdadera si el EV sigue siendo positivo en sesgo reducido, ejecución adversa e IV −10%. **[POR DEFECTO]** solo informativa (`require_ev_robust = No`); se muestra en la UI. Si no hay datos suficientes para un EV fiable, el EV es **no calculable** y la candidata se rechaza: nunca se le asigna un valor artificial.

### 8.3 Griegas netas

Por pata `i`, con `lado_i` (+1 comprada, −1 vendida), `ratio_i`, `qty` (contratos) y `M_i`:

```
delta_neta_acciones = Σ_i lado_i × ratio_i × qty × M_i × delta_i
delta_neta_USD      = delta_neta_acciones × precio_subyacente
gamma_neta          = Σ_i lado_i × ratio_i × qty × M_i × gamma_i
theta_neta_dia      = Σ_i lado_i × ratio_i × qty × M_i × theta_i
vega_neta_punto     = Σ_i lado_i × ratio_i × qty × M_i × vega_i      # por 1 punto de volatilidad
rho_neta            = Σ_i lado_i × ratio_i × qty × M_i × rho_i       # si está disponible
```

- Cada griega se etiqueta con su fuente: `IBKR` o `MODEL` (cálculo propio desde la IV, siempre rotulado).
- Una griega ausente reduce la cobertura; no se completa con cero.
- Para PUT, la **proximidad** del delta se evalúa con `abs(delta)`; las griegas netas conservan el signo.
- Las griegas netas de la cartera (suma de posiciones abiertas) se muestran y generan **alertas blandas**; los límites duros siguen siendo de riesgo máximo y concentración.

---

## 9. Score explicable, versionado y validado

### 9.1 Estructura del desglose

Cada evaluación guarda un desglose por componente (JSON), sin recalcular al leer:

```json
{
  "score_version": "sv-001",
  "code_version": "git:abcdef1",
  "config_version": 42,
  "score_total": 71.4,
  "coverage": 1.0,
  "components": [
    {
      "name": "liquidity",
      "weight": 0.20,
      "score": 68.0,
      "contribution": 13.6,
      "inputs": { "spread_rel": 0.06, "open_interest": 540, "data_state": "LIVE" },
      "sub_scores": { "spread": 72.0, "open_interest": 62.0 },
      "multiplier": 1.0,
      "notes": []
    }
  ],
  "missing_components": [],
  "eligibility_snapshot": { "aduana_version": "a-007", "all_passed": true }
}
```

`contribution = score_i × peso_i / Σ pesos`. La UI permite desplegar cada componente y ver qué variables lo elevaron o redujeron.

### 9.2 Versionado

Toda evaluación guarda `code_version` (hash del repositorio), `config_version` (versión de Settings), `score_version`, `aduana_version` y `model_version`. Cualquier cambio de pesos, ancla, umbral o fórmula crea una versión nueva.

### 9.3 Perfiles por familia **[inactivos hasta validar]**

La función de IV y griegas del baseline pertenece al perfil `intraday_long_premium`. Los demás perfiles son **hipótesis** y se calculan solo en libros `shadow` y contrafactual hasta validarlos.

| Perfil | Familias | Preferencias iniciales (a calibrar) | Estado |
|---|---|---|---|
| `intraday_long_premium` | Long Call/Put, Bull Call/Bear Put | Baseline actual: puntuación de IV (50%) + proximidad de `abs(delta)` a 0,50 (50%) | **Activo** |
| `credit_defined` | Bull Put, Bear Call | `abs(delta)` de la pata corta cerca de un objetivo configurable (hipótesis 0,30); theta neta positiva; IV relativa alta | Inactivo |
| `long_volatility` | Long Straddle/Strangle | Vega neta positiva; delta neta cercana a 0; IV relativa baja; penaliza evento e IV crush | Inactivo |
| `neutral_range` | Iron Condor/Butterfly | Delta neta cercana a 0; theta neta positiva; vega neta negativa; IV relativa alta | Inactivo |
| `calendar_diagonal` | Calendar/Diagonal | Vega neta positiva; theta neta positiva; estructura temporal favorable | Solo análisis |

Reglas:

- Los perfiles **no cambian la elegibilidad**, solo el ranking.
- Para activar un perfil: pruebas de regresión frente al baseline y validación fuera de muestra (§9.6).
- Una estrategia solo puede pasar a `enabled` si su perfil está activo (criterio añadido a la promoción del addendum §3.3).
- IV relativa se evalúa frente a IV histórica o percentil, volatilidad realizada, skew y estructura temporal cuando existan datos fiables; no solo con umbrales absolutos.

### 9.4 Poder discriminante del score

Informe periódico (en Options Performance) con las operaciones de los libros principal, shadow y contrafactual:

- Correlación de rangos (Spearman) entre score y P&L neto simulado.
- Tabla por quintiles/deciles de score con P&L neto medio, tasa de acierto y tamaño de muestra.
- Intervalo de confianza por *bootstrap*. Si el intervalo incluye 0 o la muestra es menor que el mínimo, la UI muestra **"no concluyente"**.
- Frecuencia de candidatas por encima de `min_score`.

Si la correlación de rangos es indistinguible de cero, el reporte lo declara. Un score que no discrimina no justifica por sí solo cambios de pesos: justifica revisar el diseño.

### 9.5 Colinealidad entre componentes

Matriz de correlación entre los seis componentes sobre el histórico de candidatas elegibles y detección del solapamiento descrito en §2 (#10). Resultado informativo en M3; **no cambia pesos**.

### 9.6 Protocolo champion / challenger [FIJO]

1. El **champion** es la versión vigente (inicialmente el baseline). Solo él determina la selección.
2. Un **challenger** (otra versión de pesos, ancla o perfil) se calcula en paralelo sobre los mismos snapshots y se guarda; **no influye** en la selección.
3. Los parámetros del challenger y la métrica de comparación se **fijan antes** de la comparación (se guarda su huella).
4. Comparación tras ≥ 4 semanas y ≥ 200 observaciones (principal + shadow + contrafactual), con la métrica "P&L neto medio del 20% superior por score cada día".
5. Se exige: intervalo de confianza de la diferencia por *bootstrap* pareado cuya cota inferior sea > 0, y mismo signo en ≥ 75% de los bloques semanales.
6. Un resultado favorable no se aplica solo: requiere aprobación del propietario; se conserva el historial y es reversible.

Los umbrales numéricos son **[POR DEFECTO]** y editables. Mejorar el periodo de entrenamiento no es criterio de aprobación.

---

## 10. Selector, concentración y vistas

### 10.1 Reglas

- El selector es global: CALL y PUT compiten por expectativa neta, calidad y riesgo. No hay mínimo por dirección. No se seleccionan tres operaciones si solo una o ninguna cumple.
- **TOP 3 CALL / TOP 3 PUT son vistas informativas** (`informational`). Solo las candidatas con estado `SELECTED_FOR_PAPER` están aprobadas. La API distingue ambos conceptos en campos distintos.
- El riesgo agregado incluye las posiciones abiertas (principal §12.2).

### 10.2 Concentración **[POR DEFECTO, editable]**

| Dimensión | Límite |
|---|---:|
| Posiciones por ticker | 1 |
| Posiciones por sector | 2 **[VERIFICAR dato de sector en Universe]** |
| Posiciones en la misma dirección | 2 |
| Posiciones con el mismo vencimiento | 2 |
| Bloqueo por correlación alta | Desactivado por defecto |

La correlación (por defecto ventana de 60 sesiones, umbral 0,80) solo se activa cuando pueda estimarse con robustez; mientras tanto, el sector actúa como aproximación.

### 10.3 Revalidación al abrir [FIJO]

Entre la evaluación y la apertura (automática o manual) los precios cambian. Antes de abrir:

1. Recapturar cotizaciones de todas las patas.
2. Repetir ADUANA y el cálculo de riesgo con el snapshot nuevo.
3. Rechazar con `PRICE_DRIFT` si el precio ejecutable del paquete empeoró más que `max_price_drift_pct`, **[POR DEFECTO] 5%**. Una mejora de precio se acepta.
4. Guardar ambos snapshots (evaluación y apertura).

---

## 11. Motor de paper trading

### 11.1 Modelo de fills **[POR DEFECTO]**

| Parámetro | Valor |
|---|---|
| Compra / venta | Ask / bid más slippage por pata (principal §10.1), nunca el midpoint |
| Latencia simulada | 1.000 ms: el fill toma la primera cotización válida **posterior** a la decisión, no la del instante de la decisión |
| Verificación de tamaño | Si el tamaño visible es menor que la cantidad: estado `UNFILLED`, sin fill parcial |
| Fills parciales | Desactivados por defecto. Si se activan: se llena `min(tamaño, cantidad)` y el resto se cancela tras `partial_timeout_s` (30 s) |
| Multi-pata | Precio neto del paquete = suma de patas ejecutables; sin ejecución simultánea perfecta (addendum §7.2) |

### 11.2 Salidas

Las reglas de salida (take profit, stop, tiempo, invalidación, protección de pata corta) son las del principal §12.3 y addendum §7.3. Cada salida pasa por ADUANA con su clasificación PASIVA / ACTIVA.

### 11.3 Registro

Órdenes simuladas, fills por pata, cancelaciones, eventos de posición y P&L bruto y neto, todo con el identificador de la evaluación que lo originó.

### 11.4 Máquina de estados

**Candidata:** `REJECTED` (con códigos) · `DISCARDED` (bajo `min_score`) · `ELIGIBLE` · `RANKED` · `SELECTED_FOR_PAPER` · `EXPIRED_UNSELECTED` · `ERROR`.

**Posición:** `PENDING_ENTRY` → `OPEN` → `CLOSING` → `CLOSED`; ramas `UNFILLED`, `NOT_VALUABLE` (sin cotización válida para valorar o cerrar), `ERROR`.

Si el sistema ya usa nombres equivalentes, se conservan y se documenta la equivalencia. Ninguna transición salta estados ni se hace fuera del motor.

### 11.5 Idempotencia y reconciliación

- **Idempotencia:** restricciones únicas sobre `evaluation_id` por apertura y sobre la clave (`evaluation_id`, acción) por evento; los reintentos tras una reconexión no duplican.
- **Reconciliación periódica** (por defecto cada 5 min en horario de mercado y siempre al reanudar):
  1. Recalcular el P&L de las posiciones abiertas y cerradas hoy desde sus fills y comparar con lo registrado (tolerancia USD 0,01).
  2. Comparar el libro con la suma de sus eventos.
  3. Detectar duplicados.
  4. Comprobar que existe la salida forzada programada de cada posición abierta.
- Una discrepancia genera evento de riesgo y `HALTED` (§4.2).
- Si en el futuro se enviaran órdenes a una cuenta paper de IBKR, la reconciliación contra el broker sería una decisión separada que modifica el principio de adaptador de solo lectura.

---

## 12. Backtesting, libro contrafactual y analítica

### 12.1 Requisitos de validación

- Sin *look-ahead bias* ni sesgo de supervivencia evitable; la decisión usa solo datos anteriores a su instante.
- División cronológica en calibración, validación y prueba; *walk-forward* cuando haya datos; separación (embargo) de 1 sesión entre bloques.
- Costes, slippage y fills conservadores; sin fills al midpoint.
- Sin bid/ask de opciones en el instante de decisión, el caso se marca `INVALID_FOR_EXECUTION_ANALYSIS` y no entra en métricas de rendimiento.
- Resultados por estrategia, subyacente, régimen, DTE, delta, IV y horario, con tamaño de muestra y intervalo de confianza.
- Métricas: expectativa neta, drawdown, profit factor, retorno sobre riesgo, distribución de resultados, rachas.
- El histórico de opciones disponible es el de los snapshots propios; se documenta su cobertura.

### 12.2 Libro contrafactual **[FIJO el mecanismo; parámetros POR DEFECTO]**

Con 0 a 3 operaciones al día, 100 operaciones tardan semanas y no bastan para calibrar el sesgo (`alpha`, `gamma_vol`), la probabilidad teórica ni el score. Se añade un libro adicional:

- Para **toda candidata elegible no seleccionada** (y las rechazadas solo por `min_score`), se calcula el resultado simulado con el mismo modelo de fills y los snapshots grabados hasta la salida forzada.
- Se guarda en `candidate_outcomes` con `book = 'counterfactual'`.
- **No consume operaciones diarias ni presupuesto de riesgo**, no genera posiciones y no aparece en el Top 3.
- Se reporta siempre **separado** de los libros principal y shadow, y se advierte el sesgo de selección: sirve para calibración y comparación de versiones, no como P&L alcanzable.
- Depende de snapshots de los contratos candidatos (principal §14.4); aplicar la política de retención.

### 12.3 Analítica

Resultados por libro; poder discriminante (§9.4); colinealidad (§9.5); comparación champion/challenger (§9.6); calibración de probabilidad teórica frente a frecuencia observada; estimación de `alpha` y `gamma_vol`.

---

## 13. Datos y trazabilidad

### 13.1 Convención de nombres

Inspeccionar Supabase. Si existe una convención (`options_*` u otra), **se usa esa**; en ausencia de ella, `opt_*`. No se duplican tablas existentes. Migraciones idempotentes, aditivas y reversibles; UUID, claves foráneas, timestamps UTC, índices y RLS.

### 13.2 Mapeo de entidades

| Entidad (propuesta) | Equivalente en documentos previos | Acción |
|---|---|---|
| Ejecuciones de evaluación | `opt_jobs` (scan) + `evaluation_id` en candidatas | Añadir `evaluation_id` único y `code_version`, `config_version`, `score_version`, `aduana_version` |
| Snapshots de mercado | `opt_snapshots`, `opt_quotes_latest` | Reutilizar; guardar tipo de mercado y antigüedad |
| Puntuaciones y componentes | `score` y `score_breakdown` en `opt_candidates` | **Normalizar en `candidate_scores`**: una fila por candidata y `score_version` (permite challengers) |
| Resultados ADUANA | Campos de motivos en la candidata | **Nueva `admission_results`**: una fila por candidata y regla (`rule_id`, `passed`, `code`, `details`, `aduana_version`) |
| Patas | `opt_candidate_legs` (addendum) | Reutilizar |
| Órdenes y fills paper | `entry_fills`/`exit_fills` JSONB en `opt_paper_trades` | **Normalizar en `paper_orders` y `paper_fills`** (por pata), necesarios para parciales y reconciliación |
| Posiciones y eventos | `opt_paper_trades`, `opt_risk_events` | Añadir `position_events` |
| Eventos de calendario | No existía | **Nueva `event_calendar`** (símbolo, tipo, fecha/hora, fuente, consultado_en, estado) |
| Resultados contrafactuales | No existía | **Nueva `candidate_outcomes`** |
| Backtests y métricas | `opt_backtest_runs` | Añadir `backtest_metrics` |
| Salud del sistema | No existía | **Nueva `system_health`** (serie temporal) |
| Control y kill switch | No existía | **Nueva `control_events`** (modo, kill switch, quién, cuándo, motivo) |

### 13.3 Reproducibilidad [FIJO]

Cada decisión debe poder **repetirse** a partir de su snapshot y de las versiones guardadas. Una función de *replay* recalcula la evaluación completa con `code_version`, `config_version` y `score_version` originales, y compara contra lo guardado (tolerancia numérica 1e-9). Un job nocturno repite una muestra aleatoria; cualquier diferencia genera alerta.

---

## 14. Endpoints (adiciones, armonizados con el principal §15)

Prefijo `/api/options/v1`. Siguen el patrón de jobs: el backend del droplet no se conecta a IBKR.

| Método | Endpoint | Propósito |
|---|---|---|
| GET | `/evaluations/{id}` | Traza completa: snapshot, resultado por regla de ADUANA, componentes, valoración, versiones |
| POST | `/evaluations/{id}/replay` | Recalcula y devuelve diferencias |
| GET | `/health` | Estado `NORMAL / DEGRADED / HALTED`, métricas y últimas alertas |
| GET/PUT | `/control/mode` | Modo `observation` / `paper` (rol propietario, auditado) |
| POST | `/control/kill-switch` | Activar o desactivar con motivo (rol propietario) |
| GET | `/events/calendar` | Eventos por símbolo y rango, con estado |
| POST | `/events/refresh` | Crea un job de actualización del calendario |
| GET | `/scores/versions` | Versiones de score y su estado (champion / challenger) |
| GET | `/analytics/score-discrimination` | Poder discriminante por libro |
| GET | `/analytics/ev-sensitivity/{candidateId}` | Tabla de sensibilidad |
| GET | `/analytics/champion-challenger` | Comparación y decisión pendiente |
| GET/POST | `/reconciliation/latest`, `/reconciliation/run` | Última reconciliación y ejecución manual |

Validar payloads y permisos en servidor; los endpoints de control exigen rol y registran auditoría. No exponer secretos en respuestas ni en logs.

---

## 15. UI

- **Banner global** en las páginas de Opciones: modo (`observation`/`paper`), estado de salud, kill switch, edad de la última cotización y de la última reconciliación.
- **Options Opportunities:** columnas de griegas netas, `ev_range` y `ev_robust`, cobertura, estado de eventos y resultado de ADUANA; el detalle incluye lista de reglas con aprobada/rechazada y código, desglose del score desplegable, tabla de sensibilidad y comparación entre los dos snapshots (evaluación y apertura). El TOP 3 por dirección se rotula **"informativo"**.
- **Options Positions:** línea de tiempo de eventos, estado según §11.4, y bandera de `NOT_VALUABLE`.
- **Options Performance:** resultados por libro (principal, shadow, contrafactual) separados; poder discriminante; colinealidad; challenger; calibración.
- **Options Data & Status:** salud, reconciliación, calendario de eventos, versiones vigentes.
- Alertas por datos obsoletos, desconexión, límites activados y discrepancias, en el banner, en System Logs y en los canales de notificación que la plataforma ya tenga **[VERIFICAR]**.
- Solo acciones de simulación; sin botones de envío real.

---

## 16. Settings: nuevas secciones de la pestaña "Opciones"

Mismo patrón que el principal §17: editable, valor efectivo y techos, validaciones, auditoría y `settings_version`.

### I. Modo y control

| Parámetro | Valor por defecto | Rango |
|---|---:|---|
| Modo | `observation` (`paper` se activa tras verificar permisos y datos `LIVE`) | `observation / paper` |
| Kill switch | Inactivo | Sí/No (auditado) |
| `LIVE_TRADING_ENABLED` | `false` | **Bloqueado**; `true` impide el arranque |

### J. Calidad de datos y salud

| Parámetro | Valor por defecto | Rango |
|---|---:|---|
| Cobertura mínima del score | 0,80 | 0,5–1,0 |
| Política de componentes faltantes (esenciales / no esenciales) | `reject` / `conservative_zero` | Lista |
| Desconexión IBKR para `DEGRADED` | 30 s | 5–300 |
| Antigüedad p95 de cotización para `DEGRADED` | 10 s | 2–60 |
| % de candidatas `STALE` para `DEGRADED` | 30% | 5–80% |
| Errores de escritura consecutivos para `HALTED` | 3 | 1–10 |
| Tolerancia de reconciliación | USD 0,01 | 0,001–0,10 |
| Frecuencia de reconciliación | 5 min | 1–60 |

### K. Eventos

| Parámetro | Valor por defecto | Rango |
|---|---:|---|
| Antigüedad máxima del calendario | 24 h | 1–72 |
| Política ante `UNKNOWN` / `STALE` | `block` | `block / penalize_context` (solo `observation`) |
| Earnings dentro del DTE | Bloquear | Sí/No |
| Macro de alto impacto: antes / después | 30 min / 5 min | 0–120 / 0–60 |

### L. Concentración y apertura

| Parámetro | Valor por defecto | Rango |
|---|---:|---|
| Máx. por sector / vencimiento | 2 / 2 | 1–3 |
| Bloqueo por correlación alta | No | Sí/No |
| Umbral de correlación / ventana | 0,80 / 60 sesiones | 0,5–0,95 / 20–250 |
| Deriva de precio máxima al abrir | 5% | 0–20% |
| Latencia simulada | 1.000 ms | 0–10.000 |
| Fills parciales | No | Sí/No |
| Tiempo máximo de fill parcial | 30 s | 5–300 |
| Exigir `ev_robust` | No | Sí/No |

### M. Validación

| Parámetro | Valor por defecto | Rango |
|---|---:|---|
| Semanas mínimas para comparar versiones | 4 | 2–26 |
| Observaciones mínimas | 200 | 50–2.000 |
| Fracción superior del ranking diario evaluada | 20% | 5–50% |
| Bloques semanales con mismo signo | 75% | 50–100% |
| Muestra mínima por quintil para mostrar resultados | 20 | 5–200 |

---

## 17. Seguridad y auditoría

- Navegador sin acceso directo a IBKR; credenciales y `service_role` solo en backend; logs sin secretos.
- Logs estructurados con **correlation ID** que une evaluación, ADUANA, paper, reconciliación y alertas.
- Control de acceso por rol en endpoints de control, promoción y Settings; RLS en todas las tablas nuevas.
- Respeto de los límites de frecuencia y *pacing* de IBKR; el Options Worker reintenta con espera creciente.
- Toda modificación de Settings, modo, kill switch y estado de estrategia queda auditada (quién, cuándo, antes, después, motivo).
- Separación estricta de modos; el paso a `paper` exige las comprobaciones de §4.1.

---

## 18. Estrategia de pruebas

### Regresión (M0, antes de tocar nada)
Fixtures (golden files) que fijan el comportamiento actual de `score.py`, `valuation.py` y ADUANA: pesos, normalización, eventos, delta de PUT, faltantes y desempates.

### Unitarias y de propiedad
- Score en [0, 100]; pesos válidos; determinismo; monotonía (menor spread no empeora la liquidez).
- **Invarianza:** para cualquier peso, una candidata rechazada por ADUANA nunca es elegible ni seleccionable.
- Identidad del EV sin doble conteo; EV no calculable ⇒ rechazo.
- Griegas netas con signo, cantidad y multiplicador; `abs(delta)` en PUT.
- Cobertura: esencial ausente ⇒ rechazo; no esencial ausente ⇒ contribución cero y bandera.
- Casos límite: bid/ask nulos o cruzados, OI cero, spread enorme, dato `STALE`, IV extrema, multiplicador desconocido, expiración intradía, evento desconocido.

### Fail-closed y operación
- Desconectar IBKR, degradar cotizaciones o forzar errores de base de datos ⇒ no hay nuevas entradas.
- Datos `DELAYED` en `paper` ⇒ rechazo; en `observation` ⇒ candidata no operable.
- Calendario `UNKNOWN`/`STALE` ⇒ bloqueo.
- Kill switch: detiene entradas y no cierra posiciones.
- `LIVE_TRADING_ENABLED = true` ⇒ el módulo no arranca.
- Ninguna ruta de código envía órdenes reales (prueba estática y de integración).
- TOP 3 no puede abrir posiciones sin pasar por selector y ADUANA.

### Paper y reconciliación
- Revalidación al abrir: deriva por encima del umbral ⇒ `PRICE_DRIFT`.
- Latencia simulada sin *look-ahead*.
- Idempotencia tras reconexión: sin duplicados.
- Discrepancia inyectada ⇒ `HALTED`.
- Protocolo de reanudación completo.

### Reproducibilidad
Replay de una muestra de evaluaciones coincide con lo guardado; cambia de versión si cambia el código o la configuración.

### Validación
Pruebas del pipeline temporal sin *look-ahead*; intervalos de confianza; contrafactual separado de los demás libros.

### Integración
IBKR simulado y Supabase de pruebas; tiempos de espera, respuestas parciales, desconexión y recuperación; RLS; regresión de Stocks, Crypto y Forex tras cualquier extensión de ADUANA.

---

## 19. Hitos M0–M6

El primer paso es averiguar **qué parte del principal y del addendum ya está construida**; los hitos se acoplan a ese estado.

| Hito | Contenido | Aceptación |
|---|---|---|
| **M0 — Reconciliación y baseline** | Auditoría del código, tablas de equivalencia (§6, §13.2), estado de sprints del principal y del addendum ya construidos, respuestas del §21, fixtures de regresión | Informe aprobado; el comportamiento actual queda congelado en pruebas; ningún cambio de lógica sin aprobación |
| **M1 — Datos, eventos, modos y control** | Data Quality Gate, estados y cobertura; calendario de eventos; modos `observation`/`paper`; salud, kill switch y protocolo de reanudación; resultados de ADUANA por regla | Ninguna candidata con dato crítico defectuoso llega al selector; cada rechazo es auditable; fail-closed probado |
| **M2 — Valoración** | Identidad del EV, sensibilidad y `ev_robust`, griegas netas, costes sin doble conteo | Casos conocidos correctos; valor teórico distinguido del ejecutable |
| **M3 — Score explicable** | Desglose, versionado, cobertura, perfiles inactivos, poder discriminante y colinealidad | Score reproducible; elegibilidad invariante; replay determinista |
| **M4 — Selector y paper** | Concentración, revalidación al abrir, modelo de fills, idempotencia, reconciliación, estados | Límites respetados; sin duplicados tras reconexión; discrepancia ⇒ `HALTED` |
| **M5 — Validación** | Libro contrafactual, backtesting temporal, champion/challenger, analítica | Informes reproducibles con costes y resultados fuera de muestra |
| **M6 — UX y endurecimiento** | Banner, paneles, alertas, pruebas de fallo de IBKR y Supabase, documentación operativa | Una señal puede rastrearse desde sus datos hasta su resultado |

Dependencias: M1 antes que M3 y M4; M2 coordinado con E1 del addendum; M5 requiere snapshots (principal §14.4). Los gates G1, G2, G3 y el gate de habilitación por estrategia siguen vigentes; M5 aporta datos adicionales a G3 (los datos contrafactuales **no sustituyen** a las operaciones simuladas exigidas).

---

## 20. Criterios globales de aceptación

1. ADUANA tiene precedencia absoluta sobre el score y devuelve resultado por regla, persistido.
2. El score es reproducible, está en [0, 100] y guarda desglose, cobertura y versiones.
3. Datos críticos ausentes, obsoletos o inválidos no generan candidatas operables; `DELAYED` nunca abre operaciones.
4. Eventos desconocidos o desactualizados bloquean; "sin eventos" solo si fue verificado.
5. EV y riesgo muestran costes y supuestos; los costes se descuentan una vez; el EV incluye sensibilidad.
6. Estrategias multi-pata calculan exposición por pata, griegas netas y riesgo total.
7. El selector no fuerza operaciones, incluye las posiciones abiertas en el riesgo y respeta concentración.
8. Paper trading no usa el midpoint, revalida al abrir y es idempotente.
9. El sistema falla cerrado, con kill switch y protocolo de reanudación.
10. Parámetros, versiones y resultados son auditables; el replay reproduce las evaluaciones.
11. Cambios al score se aprueban con validación fuera de muestra (champion/challenger) y aprobación del propietario.
12. Trading real no existe ni puede habilitarse accidentalmente.

---

## 21. Respuestas de diseño al Apéndice A de la propuesta

Cada respuesta es el **comportamiento objetivo**; Antigravity verifica en M0 si el código ya lo cumple.

| Pregunta | Comportamiento objetivo |
|---|---|
| ¿El EV usa ejecutables o midpoints? | Precios ejecutables más slippage; el midpoint es informativo |
| ¿Los costes se descuentan una sola vez? | Sí; prueba de identidad (§8.1) |
| ¿La pérdida máxima incorpora multiplicador y contratos? | Sí: `max_loss_total = max_loss_por_contrato × qty`, con `M_i` de cada pata |
| ¿Hay griegas de IBKR para todas las patas y son actuales? | Si falta, se usa el cálculo propio rotulado `MODEL`; si falta también la IV, la pata queda sin griegas y baja la cobertura |
| ¿Delta firmado o absoluto en PUT? | `abs(delta)` para la proximidad; griegas netas con signo |
| ¿Cómo se trata un componente faltante? | Esencial ⇒ rechazo; no esencial ⇒ cero con bandera; sin renormalizar (§5.3) |
| ¿La ausencia de evento está verificada? | Solo `CLEAR_VERIFIED`; el resto bloquea (§7) |
| ¿El selector incluye posiciones abiertas? | Sí |
| ¿TOP 3 CALL/PUT puede activar entradas? | No; es informativo (§10.1) |
| ¿La reconexión reconcilia antes de reanudar? | Sí; protocolo del §4.4 |
| ¿El backtest incluye bid/ask, comisiones y slippage? | Sí; sin bid/ask el caso se marca inválido para análisis de ejecución |
| ¿Dónde están implementadas O-1…O-12? | Lo documenta M0 con archivo, versión y contrato |

---

## 22. Decisiones pendientes

Continúan la numeración del addendum (D-14 a D-23).

- **D-24:** Contenido canónico de O-1…O-12 y tabla de equivalencias con B-01…B-17.
- **D-25:** Confirmar que `DELAYED` queda bloqueado en `paper` (recomendado) y revisar el multiplicador de 0,70.
- **D-26:** Fuente del calendario de eventos, cobertura y frecuencia de actualización.
- **D-27:** Política ante `UNKNOWN`/`STALE` (por defecto `block`; revisar si la fuente es poco fiable).
- **D-28:** Fuente de sector y metodología de correlación.
- **D-29:** Coste de almacenamiento y retención del libro contrafactual y de los snapshots asociados.
- **D-30:** Umbrales definitivos de champion/challenger tras observar la dispersión real de los datos.
- **D-31:** Umbrales de degradación y salud tras observar la latencia real de IBKR.
- **D-32:** Canales de alerta (UI, System Logs y los de notificación ya existentes).
- **D-33:** Si se decidiera algún día enviar órdenes a una cuenta paper de IBKR, un documento aparte que revise el adaptador de solo lectura.

---

## 23. Instrucciones para Antigravity

1. **Comenzar por M0.** No modificar código antes de entregar el mapa de arquitectura, la tabla de equivalencias y las pruebas de regresión que congelan el comportamiento actual.
2. **Leer el código y las pruebas reales.** Este documento y la propuesta parten de especificaciones, no de una inspección del repositorio.
3. Reutilizar funciones, tablas, endpoints y controles existentes; no duplicar reglas de ADUANA en módulos divergentes.
4. Migraciones por archivo y tabla con riesgos y *rollback*; mantener compatibilidad o documentar los cambios incompatibles.
5. No cambiar pesos, `min_score`, `ev_anchor`, reglas de ADUANA ni límites financieros sin pruebas comparativas y aprobación.
6. No convertir candidatas rechazadas en elegibles mediante renormalización o valores por defecto.
7. Paper trading y observación son los únicos modos; no crear rutas hacia órdenes reales.
8. Cada hito entrega código, migraciones, pruebas, evidencias, limitaciones de datos y decisiones pendientes.
9. Resolver cada punto **[VERIFICAR]** con evidencia y documentarlo.

### Prompt de arranque sugerido (M0)

> Lee `eTrader_APEX_Options_Arquitectura_Complementaria_Mejora_Antigravity.md` junto con el principal (v1.2), el addendum (v1.1) y la propuesta de mejora (v1.0). Ejecuta solo el hito M0. No modifiques lógica de producción. Entrega: (1) mapa de arquitectura del módulo de Opciones real, con `score.py`, `valuation.py`, ADUANA O-1…O-12, selector, endpoints, tablas y pruebas existentes; (2) estado de construcción de los sprints del principal y de los hitos del addendum; (3) tabla de equivalencias entre B-01…B-17 y las reglas O-n, con las que faltan; (4) mapeo de entidades del §13.2 a tablas existentes; (5) respuestas verificadas del §21 y resultados de la auditoría del §3.2; (6) pruebas de regresión con fixtures que congelen el comportamiento actual; (7) riesgos y plan de migración con *rollback*. Detente y espera aprobación antes de M1.

---

## 24. Changelog

- **v1.0 (18-oct-2026):** primera versión. Adapta la propuesta de mejora v1.0 al sistema existente y a los documentos principal v1.2 y addendum v1.1; añade modos, salud y kill switch, Data Quality Gate, catálogo de comportamientos de ADUANA, calendario de eventos, sensibilidad del EV, perfiles, champion/challenger, libro contrafactual, revalidación al abrir, replay determinista, ajustes de Settings, hitos M0–M6 y decisiones D-24 a D-33.
