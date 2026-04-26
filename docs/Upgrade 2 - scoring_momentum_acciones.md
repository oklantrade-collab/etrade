# Modelo de Scoring de Momentum Intradiario
### Propuesta técnica para identificar acciones con potencial de disparo en el día

---

## Resumen ejecutivo

Este documento propone un sistema cuantitativo de puntuación (score) del 1 al 10 para clasificar acciones según su probabilidad de experimentar un movimiento de precio significativo durante la sesión bursátil. El modelo combina datos de volumen de Interactive Brokers (IBKR), sentimiento social vía Social Market Analytics (SMA), catalizadores de noticias y estructura técnica de precio.

---

## 1. Objetivo

Diseñar una variable compuesta — **Score de Momentum** — que permita rankear automáticamente una lista de acciones al inicio de cada sesión, identificando cuáles tienen mayor probabilidad de un movimiento de precio importante en el día o en los días siguientes.

El score opera en una escala continua de **1 a 10**, donde:

| Rango | Clasificación | Acción sugerida |
|-------|--------------|-----------------|
| 7.5 – 10 | Alerta fuerte | Candidato prioritario para seguimiento activo |
| 5.0 – 7.4 | En vigilancia | Monitorear evolución cada 15 minutos |
| 1.0 – 4.9 | Bajo interés | Excluir de la sesión |

---

## 2. Fuentes de datos

Todas las variables se obtienen desde la infraestructura de Interactive Brokers o fuentes complementarias de acceso directo:

| Variable | Fuente | Tipo de dato |
|----------|--------|--------------|
| RVOL (volumen relativo) | TWS API — `reqMktData()` | Numérico en tiempo real |
| S Score (sentimiento social) | TWS — columna Social Sentiment (SMA) | Score −3 a +3, actualiza 1 min |
| SV Score (volumen de menciones) | TWS — columna Social Sentiment (SMA) | Score 0 a 10, actualiza 1 min |
| Catalizador | Feed de noticias IBKR / Benzinga pre-market | Categórico manual o NLP |
| Estructura técnica | TWS API — OHLCV, máximos históricos | Numérico calculado |

---

## 3. Las cinco variables del modelo

### V1 — RVOL: Volumen relativo · Peso: 30%

El volumen relativo compara el volumen actual de la sesión contra el promedio de los últimos 20 días para el mismo período horario.

**Normalización:**
```
V1_norm = min((RVOL − 1) / 4, 1.0)
```

| RVOL | Interpretación |
|------|---------------|
| 1x | Volumen normal — sin señal |
| 2x | Actividad elevada — inicio de interés |
| 3x | Significativo — capital institucional probable |
| 5x+ | Extremo — señal muy fuerte |

**Justificación:** Es la variable con mayor correlación empírica con movimientos sostenidos. Sin volumen extraordinario, ningún movimiento de precio es duradero. Un RVOL de 3x en los primeros 15 minutos es la señal más confiable de que hay capital no retail entrando.

---

### V2 — S Score: Sentimiento social · Peso: 20%

Score de sentimiento de Social Market Analytics, integrado nativamente en TWS. Mide el tono neto de tweets únicos y filtrados sobre la acción en una ventana de 24 horas con ponderación temporal.

**Normalización:**
```
V2_norm = (S_Score + 3) / 6      ← rango original: −3 a +3
```

**Cómo activarlo en TWS:** columna sobre cualquier Watchlist → Insert Column → grupo "Social Sentiment" → agregar `S Score`.

**Justificación:** El sentimiento retail positivo alimenta presión compradora adicional y actúa como indicador adelantado — el S Score suele subir antes de que el precio reaccione completamente.

---

### V3 — SV Score: Volumen de menciones sociales · Peso: 10%

Mide la intensidad de actividad en redes sociales comparada con el promedio histórico de esa acción, independientemente de si el sentimiento es positivo o negativo.

**Normalización:**
```
V3_norm = SV_Score / 10          ← rango original: 0 a 10
```

**Justificación:** Una explosión de menciones suele preceder al movimiento de precio por 15–30 minutos. Es una alarma temprana incluso cuando el S Score todavía es neutro.

---

### V4 — Catalizador: Tipo de noticia · Peso: 25%

El catalizador es la razón fundamental del movimiento. Sin catalizador, un volumen alto puede ser ruido, manipulación o flujo de dark pool no interpretable.

**Escala categórica:**

| Tipo de catalizador | Valor raw | Ejemplos |
|--------------------|-----------|---------|
| Sin noticia visible | 0 | Movimiento huérfano — descartar |
| Rumor / upgrade de analista | 3 | Rating upgrade, price target revision |
| Earnings beat / guidance al alza | 6 | Resultados superiores al consenso |
| Evento binario fuerte | 10 | Aprobación FDA, M&A, contrato masivo |

**Normalización:**
```
V4_norm = Cat_raw / 10
```

**Regla de oro:** si el score total es alto pero V4 = 0, descartar la señal. El catalizador es el único factor que no puede sustituirse con los demás.

---

### V5 — Estructura técnica de precio · Peso: 15%

Evalúa la posición del precio respecto a niveles clave y la calidad de la vela de apertura. Actúa como filtro de timing — confirma que el precio tiene espacio libre para subir sin resistencia significativa.

**Escala de puntuación (0–10):**

| Condición técnica | Puntos |
|-------------------|--------|
| Precio por debajo de resistencia importante | 0–2 |
| Ruptura de resistencia con volumen | 4–6 |
| Gap alcista confirmado en apertura | 5–7 |
| Vela de rango amplio sin mecha superior | +2 |
| Máximo de 52 semanas / histórico | +2 |

**Normalización:**
```
V5_norm = Tecnico_raw / 10       ← suma de condiciones, máximo 10
```

---

## 4. Fórmula del Score de Momentum

```
Score_raw = (V1_norm × 0.30)
          + (V2_norm × 0.20)
          + (V3_norm × 0.10)
          + (V4_norm × 0.25)
          + (V5_norm × 0.15)

Score_final = round(Score_raw × 10, 1)   →   escala 1.0 a 10.0
```

Todas las variables normalizadas operan en el rango [0, 1], garantizando que el score máximo sea exactamente 10.

---

## 5. Proceso de aplicación diario

```
PRE-MERCADO (4:00 AM – 9:30 AM)
│
├── 1. Revisar noticias de las empresas con mayor volumen pre-market
│       → Clasificar catalizador (V4) de cada una
│
├── 2. Verificar S Score y SV Score en TWS para la watchlist
│       → Anotar valores actuales de V2 y V3
│
└── 3. Calcular score preliminar antes de la apertura

APERTURA (9:30 AM – 9:45 AM)
│
├── 4. NO operar en los primeros 5 minutos
│       → Observar dirección y consistencia del movimiento
│
├── 5. Leer RVOL de los primeros 15 minutos (V1)
│       → Actualizar score con volumen real de apertura
│
└── 6. Evaluar estructura técnica (V5)
        → ¿Hay ruptura de resistencia con volumen?

DECISIÓN (minuto 15+)
│
├── Score ≥ 7.5  →  Candidato activo. Esperar pullback para entrar.
├── Score 5–7.4  →  Vigilar cada 15 min. Re-calcular si cambia V1 o V2.
└── Score < 5.0  →  Excluir. Pasar a siguiente acción de la lista.
```

---

## 6. Implementación técnica en Python + IBKR

El modelo puede automatizarse con la TWS API de Interactive Brokers usando `ib_insync`. El siguiente esquema muestra la estructura del script:

```python
from ib_insync import IB, Stock
import pandas as pd

# Conexión a TWS
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

def calcular_score(rvol, s_score, sv_score, catalizador_raw, tecnico_raw):
    """
    Calcula el Score de Momentum de 1 a 10.
    """
    v1 = min((rvol - 1) / 4, 1.0)
    v2 = (s_score + 3) / 6
    v3 = sv_score / 10
    v4 = catalizador_raw / 10
    v5 = tecnico_raw / 10

    score_raw = (v1 * 0.30) + (v2 * 0.20) + (v3 * 0.10) + (v4 * 0.25) + (v5 * 0.15)
    score_final = round(score_raw * 10, 1)
    return max(1.0, min(score_final, 10.0))

def clasificar(score):
    if score >= 7.5:
        return "ALERTA FUERTE"
    elif score >= 5.0:
        return "EN VIGILANCIA"
    else:
        return "BAJO INTERÉS"

# Ejemplo de uso sobre una lista de tickers
watchlist = ['NVDA', 'TSLA', 'AAPL', 'AMD', 'META']

resultados = []
for ticker in watchlist:
    # Aquí se conectan los datos reales de TWS API
    # Los valores de ejemplo deben reemplazarse con reqMktData()
    score = calcular_score(
        rvol=2.8,
        s_score=1.5,
        sv_score=6.0,
        catalizador_raw=6,
        tecnico_raw=7
    )
    resultados.append({
        'Ticker': ticker,
        'Score': score,
        'Clasificación': clasificar(score)
    })

df = pd.DataFrame(resultados).sort_values('Score', ascending=False)
print(df.to_string(index=False))
```

---

## 7. Limitaciones y consideraciones

**El modelo no predice — prioriza.** El score no garantiza que una acción suba; reduce el universo de candidatos a los que tienen mayor confluencia de señales positivas.

**El catalizador es no sustituible.** Un score de 9.0 con V4 = 0 debe descartarse. El volumen sin explicación es una trampa frecuente en acciones de baja capitalización.

**El RVOL es más confiable después del minuto 5.** Las primeras velas tienen alta volatilidad artificial — el RVOL calculado en los primeros 2 minutos no es representativo.

**El S Score de IB refleja Twitter/X filtrado.** No captura Reddit (WallStreetBets) ni Stocktwits directamente. Para mayor cobertura, complementar con la API de ApeWisdom para menciones en Reddit.

**Recalcular cada 15 minutos.** El score no es estático. El RVOL y el S Score cambian durante la sesión y pueden degradar o mejorar la señal.

---

## 8. Extensiones futuras

- **Módulo de short squeeze detector:** agregar variable de short interest (disponible en IBKR) para detectar potencial de squeeze en acciones con alto score y alto short float.
- **Integración con Reddit (ApeWisdom API):** sumar menciones en WallStreetBets como variable V6 con peso del 5%, redistribuyendo los pesos actuales.
- **Backtesting:** cruzar el score histórico calculado con retornos intradiarios reales para calibrar los pesos con datos propios.
- **Alertas automáticas:** configurar notificaciones cuando una acción de la watchlist supera el umbral de 7.5 durante la sesión.

---

## 9. Resumen de pesos del modelo

| Variable | Descripción | Peso | Fuente |
|----------|-------------|------|--------|
| V1 — RVOL | Volumen relativo vs promedio 20d | 30% | TWS API |
| V4 — Catalizador | Tipo y fuerza de la noticia | 25% | Noticias IBKR / manual |
| V2 — S Score | Sentimiento social ponderado | 20% | SMA en TWS |
| V5 — Técnico | Estructura y posición de precio | 15% | TWS API / gráfico |
| V3 — SV Score | Volumen de menciones sociales | 10% | SMA en TWS |
| **Total** | | **100%** | |

---

*Documento generado como propuesta de sistema de trading cuantitativo. No constituye asesoría financiera. Toda operación implica riesgo de pérdida de capital.*
