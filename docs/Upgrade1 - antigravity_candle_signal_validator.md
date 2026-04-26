# ANTIGRAVITY · Candle Signal Validator

> **Sistema de Identificación y Validación de Patrones de Velas Japonesas**
> Mercados: Crypto · Forex · Stocks — Temporalidades: 4H · 1D — Polling: 5 min (Crypto/Forex) · 2 min (Stocks)

---

## Resumen Ejecutivo

| Atributo | Valor |
|---|---|
| Versión | 1.0 |
| Patrones soportados | 26 |
| Mercados | Crypto · Forex · Stocks (Acciones) |
| Polling Crypto / Forex | Cada 5 minutos |
| Polling Stocks | Cada 2 minutos |
| Temporalidades objetivo | 4H · 1D |
| Acciones posibles | BUY · SELL · HOLD |
| Condición de alerta activa | Cualquier temporalidad (4H o 1D) con señal BUY o SELL |

**Señales por tipo:** 9 × BUY · 9 × SELL · 8 × HOLD

---

## 1. Arquitectura del Sistema

```
ENTRADA OHLC         CONSTRUCCIÓN          DETECCIÓN           DECISIÓN         SALIDA
─────────────────    ──────────────────    ─────────────────   ──────────────   ──────────────
OHLC 5min            Vela 4H               26 algoritmos       BUY / SELL       🔔 ALERTA
Crypto / Forex  ───► (48 períodos)   ───► OHLC + historial ──► por temporalid  si BUY o SELL
                     Vela 1D               2-3 velas           o HOLD           en 4H o 1D
OHLC 2min            (288 períodos)
Stocks          ───► Vela 4H
                     (120 períodos)
                     Vela 1D
                     (195 períodos*)
```

> *Stocks: 195 períodos de 2min ≈ 1 sesión de 6.5h (NYSE/NASDAQ). La vela 1D se cierra al cierre del mercado (16:00 ET).

### Regla de activación de alerta

```
BUY ALERT  → si patron(4H).accion = BUY  OR patron(1D).accion = BUY
SELL ALERT → si patron(4H).accion = SELL OR patron(1D).accion = SELL
HOLD       → silencioso — ningún patrón activado o patrón es de tipo HOLD
```

---

## 2. Mercados Soportados

### 2.1 Crypto (Polling: 5 min)

| Parámetro | Detalle |
|---|---|
| Operación | 24/7 — sin interrupciones |
| Cierre vela 1D | 00:00 UTC |
| Cierre vela 4H | 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC |
| Pares de ejemplo | BTC/USDT · ETH/USDT · SOL/USDT · BNB/USDT · XRP/USDT |
| Fuentes de datos | Binance API · Bybit API · Coinbase Advanced API · OKX API |
| Periodos para vela 4H | 48 velas de 5min |
| Periodos para vela 1D | 288 velas de 5min |
| Consideración especial | Sin fines de semana — el mercado nunca cierra |

### 2.2 Forex (Polling: 5 min)

| Parámetro | Detalle |
|---|---|
| Operación | Lunes 00:00 UTC — Viernes 22:00 UTC |
| Cierre vela 1D | 17:00 ET / 22:00 UTC (cierre sesión Nueva York) |
| Cierre vela 4H | Cada 4h desde apertura de sesión Sydney |
| Pares de ejemplo | EUR/USD · GBP/USD · USD/JPY · AUD/USD · USD/CHF |
| Fuentes de datos | OANDA API · Interactive Brokers · MetaTrader 5 API · FXCM |
| Periodos para vela 4H | 48 velas de 5min |
| Periodos para vela 1D | 288 velas de 5min |
| Consideración especial | Filtrar datos de fin de semana antes de construir velas 1D |

### 2.3 Stocks — Acciones (Polling: 2 min) ⭐ Nuevo

| Parámetro | Detalle |
|---|---|
| Operación | Lunes–Viernes 09:30–16:00 ET (sesión regular NYSE/NASDAQ) |
| Pre-market | 04:00–09:30 ET (datos disponibles, señales de menor confianza) |
| After-hours | 16:00–20:00 ET (datos disponibles, señales de menor confianza) |
| Cierre vela 1D | 16:00 ET (cierre sesión regular) |
| Cierre vela 4H | 09:30, 13:30 ET (2 velas 4H por sesión regular de 6.5h) |
| Tickers de ejemplo | AAPL · MSFT · NVDA · TSLA · AMZN · GOOGL · META · SPY · QQQ |
| Fuentes de datos | Alpaca API · Polygon.io · Alpha Vantage · Yahoo Finance · IEX Cloud |
| Periodos para vela 4H | 120 velas de 2min (4h × 60min / 2min) |
| Periodos para vela 1D | 195 velas de 2min (6.5h × 60min / 2min) |
| Polling | **Cada 2 minutos** (mayor resolución para capturar movimientos intradiarios rápidos) |

#### ¿Por qué 2 minutos para Stocks?

Las acciones individuales presentan movimientos más abruptos e informativos en marcos cortos que los pares de divisas o las criptomonedas. Un polling de 2 minutos permite:

- Detectar patrones de reversión en formación con mayor anticipación
- Capturar eventos de noticias (earnings, FDA approvals, macro data) más rápido
- Reducir la latencia entre la formación completa de la vela 4H y la emisión de la alerta
- Aprovechar la mayor liquidez intradiaria de los mercados americanos

#### Construcción de velas para Stocks

```
FUNCIÓN construir_vela_stocks(datos_2m, tamaño):
  ventana = últimos datos_2m[tamaño]
  SI mercado_abierto(ventana[-1].timestamp):
    RETORNAR {
      open   : ventana[0].open,
      high   : MAX(ventana[*].high),
      low    : MIN(ventana[*].low),
      close  : ventana[-1].close,
      volume : SUMA(ventana[*].volume),
      vwap   : SUMA(precio*vol) / SUMA(vol),   // VWAP como dato extra
      cerrada: len(ventana) == tamaño
    }
  SINO:
    RETORNAR null   // fuera de sesión — no procesar
```

> **Nota importante:** Fuera del horario regular (09:30–16:00 ET), el sistema puede continuar recolectando datos de pre/after-market pero debe marcar las señales como `confianza: REDUCIDA` dado el bajo volumen característico de esas sesiones.

---

## 3. Tabla de Decisión — 26 Patrones

### Clasificación por tipo de señal

| Acción | Cantidad | Patrones |
|---|---|---|
| **BUY** | 9 | ID: 1, 5, 7, 10, 11, 13, 17, 23, 26 |
| **SELL** | 9 | ID: 4, 9, 12, 14, 18, 22, 24, 25, 2\* |
| **HOLD** | 8 | ID: 2, 3, 6, 8, 15, 16, 19, 20, 21 |

> *ID 2 Marubozu Bajista = HOLD (señal bajista pero sin confirmación de reversión)

### Tabla completa

| ID | Nombre | Señal | Velas | Fórmula de Detección | Acción |
|:--:|---|---|:---:|---|:---:|
| 1 | Marubozu Alcista | Alcista | 1 | `Open = Low · Close = High · Sin sombras` | **HOLD** |
| 2 | Marubozu Bajista | Bajista | 1 | `Open = High · Close = Low · Sin sombras` | **HOLD** |
| 3 | Doji Estándar | Neutral | 1 | `\|Close - Open\| ≈ 0 · Mechas en ambos lados` | **HOLD** |
| 4 | Doji Lápida | Rev. Bajista | 1 | `Open ≈ Close ≈ Low · Mecha superior larga (>60% rango)` | 🔴 **SELL** |
| 5 | Doji Libélula | Rev. Alcista | 1 | `Open ≈ Close ≈ High · Mecha inferior larga (>60% rango)` | 🟢 **BUY** |
| 6 | Doji Piernas Largas | Neutral | 1 | `Open ≈ Close · Mechas largas arriba y abajo (>30% c/u)` | **HOLD** |
| 7 | Hammer | Rev. Alcista | 1 | `Cuerpo pequeño arriba · Mecha inf ≥ 2× cuerpo · Sin mecha sup` | 🟢 **BUY** |
| 8 | Hanging Man | Rev. Bajista | 1 | `Cuerpo pequeño · Mecha inf ≥ 2× cuerpo · Al tope tendencia alcista` | **HOLD** |
| 9 | Shooting Star | Rev. Bajista | 1 | `Cuerpo pequeño abajo · Mecha sup ≥ 2× cuerpo · Al tope tendencia` | 🔴 **SELL** |
| 10 | Inverted Hammer | Rev. Alcista | 1 | `Cuerpo pequeño abajo · Mecha sup larga · Al fondo tendencia bajista` | 🟢 **BUY** |
| 11 | Engulfing Alcista | Rev. Alcista | 2 | `Vela alcista envuelve completamente el cuerpo bajista previo` | 🟢 **BUY** |
| 12 | Engulfing Bajista | Rev. Bajista | 2 | `Vela bajista envuelve completamente el cuerpo alcista previo` | 🔴 **SELL** |
| 13 | Morning Star | Rev. Alcista | 3 | `Grande bajista + Doji/pequeña + Grande alcista · 3 velas` | 🟢 **BUY** |
| 14 | Evening Star | Rev. Bajista | 3 | `Grande alcista + Doji/pequeña + Grande bajista · 3 velas` | 🔴 **SELL** |
| 15 | Spinning Top Alcista | Neutral | 1 | `Cuerpo pequeño · Mechas similares · Close > Open` | **HOLD** |
| 16 | Spinning Top Bajista | Neutral | 1 | `Cuerpo pequeño · Mechas similares · Close < Open` | **HOLD** |
| 17 | Piercing Line | Rev. Alcista | 2 | `Bajista + Alcista que cierra > 50% del cuerpo bajista previo` | 🟢 **BUY** |
| 18 | Dark Cloud Cover | Rev. Bajista | 2 | `Alcista + Bajista que cierra < 50% del cuerpo alcista previo` | 🔴 **SELL** |
| 19 | Three White Soldiers | Alcista | 3 | `3 alcistas consecutivas · Cada una abre dentro del cuerpo previo` | **HOLD** |
| 20 | Three Black Crows | Bajista | 3 | `3 bajistas consecutivas · Cada una abre dentro del cuerpo previo` | **HOLD** |
| 21 | Harami Alcista | Rev. Alcista | 2 | `Grande bajista + Alcista pequeña contenida dentro del cuerpo previo` | **HOLD** |
| 22 | Harami Bajista | Rev. Bajista | 2 | `Grande alcista + Bajista pequeña contenida dentro del cuerpo previo` | 🔴 **SELL** |
| 23 | Belt Hold Alcista | Rev. Alcista | 1 | `Open = Low · Cuerpo grande · Sin mecha inferior` | 🟢 **BUY** |
| 24 | Belt Hold Bajista | Rev. Bajista | 1 | `Open = High · Cuerpo grande · Sin mecha superior` | 🔴 **SELL** |
| 25 | Tweezer Top | Rev. Bajista | 2 | `2+ velas con High igual · Primero alcista, luego bajista` | 🔴 **SELL** |
| 26 | Tweezer Bottom | Rev. Alcista | 2 | `2+ velas con Low igual · Primero bajista, luego alcista` | 🟢 **BUY** |

---

## 4. Algoritmos de Detección

### Variables base (comunes a todos los patrones)

```python
O = vela.open
H = vela.high
L = vela.low
C = vela.close

cuerpo     = abs(C - O)
rango      = H - L
mecha_sup  = H - max(O, C)
mecha_inf  = min(O, C) - L
alcista    = C > O

# Tolerancias
ε          = rango * 0.05    # tolerancia general (5% del rango)
ε_doji     = rango * 0.03    # tolerancia doji    (3% del rango)

# Para Stocks: usar ATR adaptativo (ver Mejora M2)
# ε = ATR_14 * 0.10
```

### Patrones de 1 vela

```python
# ID 1 — Marubozu Alcista → HOLD
O ≈ L(±ε)  AND  C ≈ H(±ε)  AND  alcista

# ID 2 — Marubozu Bajista → HOLD
O ≈ H(±ε)  AND  C ≈ L(±ε)  AND  !alcista

# ID 3 — Doji Estándar → HOLD
cuerpo ≤ ε_doji  AND  mecha_sup > ε  AND  mecha_inf > ε

# ID 4 — Doji Lápida → SELL 🔴
cuerpo ≤ ε_doji  AND  mecha_inf ≤ ε  AND  mecha_sup > rango*0.60

# ID 5 — Doji Libélula → BUY 🟢
cuerpo ≤ ε_doji  AND  mecha_sup ≤ ε  AND  mecha_inf > rango*0.60

# ID 6 — Doji Piernas Largas → HOLD
cuerpo ≤ ε_doji  AND  mecha_sup > rango*0.30  AND  mecha_inf > rango*0.30

# ID 7 — Hammer → BUY 🟢
mecha_inf ≥ cuerpo*2  AND  mecha_sup ≤ cuerpo*0.30  AND  cuerpo < rango*0.40

# ID 8 — Hanging Man → HOLD
mecha_inf ≥ cuerpo*2  AND  mecha_sup ≤ cuerpo*0.30  AND  tendencia_alcista_previa()

# ID 9 — Shooting Star → SELL 🔴
mecha_sup ≥ cuerpo*2  AND  mecha_inf ≤ cuerpo*0.30  AND  cuerpo < rango*0.40

# ID 10 — Inverted Hammer → BUY 🟢
mecha_sup ≥ cuerpo*2  AND  mecha_inf ≤ cuerpo*0.30  AND  alcista
AND  hist[-1].close < hist[-3].close    # contexto bajista previo

# ID 15 — Spinning Top Alcista → HOLD
cuerpo < rango*0.30  AND  mecha_sup > rango*0.25  AND  mecha_inf > rango*0.25  AND  alcista

# ID 16 — Spinning Top Bajista → HOLD
cuerpo < rango*0.30  AND  mecha_sup > rango*0.25  AND  mecha_inf > rango*0.25  AND  !alcista

# ID 23 — Belt Hold Alcista → BUY 🟢
O ≈ L(±ε)  AND  alcista  AND  cuerpo > rango*0.70

# ID 24 — Belt Hold Bajista → SELL 🔴
O ≈ H(±ε)  AND  !alcista  AND  cuerpo > rango*0.70
```

### Patrones de 2 velas (`prev = hist[-1]`)

```python
# ID 11 — Engulfing Alcista → BUY 🟢
!prev.alcista  AND  alcista
AND  O < prev.close  AND  C > prev.open

# ID 12 — Engulfing Bajista → SELL 🔴
prev.alcista  AND  !alcista
AND  O > prev.close  AND  C < prev.open

# ID 17 — Piercing Line → BUY 🟢
!prev.alcista  AND  alcista
AND  O < prev.close
AND  C > (prev.open + prev.close) / 2
AND  C < prev.open

# ID 18 — Dark Cloud Cover → SELL 🔴
prev.alcista  AND  !alcista
AND  O > prev.close
AND  C < (prev.open + prev.close) / 2
AND  C > prev.open

# ID 21 — Harami Alcista → HOLD
!prev.alcista  AND  alcista
AND  O > prev.close  AND  O < prev.open
AND  C > prev.close  AND  C < prev.open

# ID 22 — Harami Bajista → SELL 🔴
prev.alcista  AND  !alcista
AND  O < prev.close  AND  O > prev.open
AND  C < prev.close  AND  C > prev.open

# ID 25 — Tweezer Top → SELL 🔴
|H - prev.high| ≤ ε  AND  prev.alcista  AND  !alcista

# ID 26 — Tweezer Bottom → BUY 🟢
|L - prev.low| ≤ ε  AND  !prev.alcista  AND  alcista
```

### Patrones de 3 velas (`prev = hist[-1]`, `prev2 = hist[-2]`)

```python
# ID 13 — Morning Star → BUY 🟢
!prev2.alcista  AND  abs(prev2.cuerpo) > rango_total*0.50   # vela 1: grande bajista
AND  abs(prev.cuerpo) < abs(prev2.cuerpo)*0.50              # vela 2: pequeña/doji
AND  alcista  AND  cuerpo > rango_total*0.50                # vela 3: grande alcista
AND  C > (prev2.open + prev2.close) / 2                     # cierra >50% vela 1

# ID 14 — Evening Star → SELL 🔴
prev2.alcista  AND  abs(prev2.cuerpo) > rango_total*0.50
AND  abs(prev.cuerpo) < abs(prev2.cuerpo)*0.50
AND  !alcista  AND  cuerpo > rango_total*0.50
AND  C < (prev2.open + prev2.close) / 2

# ID 19 — Three White Soldiers → HOLD
prev2.alcista  AND  prev.alcista  AND  alcista              # 3 alcistas consecutivas
AND  prev.open > prev2.open  AND  prev.open < prev2.close   # abre dentro del cuerpo previo
AND  O > prev.open  AND  O < prev.close
AND  C > prev.close  AND  prev.close > prev2.close          # cierres progresivos

# ID 20 — Three Black Crows → HOLD
!prev2.alcista  AND  !prev.alcista  AND  !alcista
AND  prev.open < prev2.open  AND  prev.open > prev2.close
AND  O < prev.open  AND  O > prev.close
AND  C < prev.close  AND  prev.close < prev2.close
```

---

## 5. Loop Principal — Motor de Detección

```python
# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
MERCADOS = {
    "crypto" : { "polling": 5,  "pares": ["BTCUSDT","ETHUSDT","SOLUSDT","..."] },
    "forex"  : { "polling": 5,  "pares": ["EURUSD","GBPUSD","USDJPY","..."]   },
    "stocks" : { "polling": 2,  "pares": ["AAPL","MSFT","NVDA","TSLA","..."]  },
}

TEMPORALIDADES = {
    "4H": {
        "crypto" : 48,   # 48  × 5min = 4h
        "forex"  : 48,   # 48  × 5min = 4h
        "stocks" : 120,  # 120 × 2min = 4h
    },
    "1D": {
        "crypto" : 288,  # 288 × 5min = 24h
        "forex"  : 288,  # 288 × 5min = 24h
        "stocks" : 195,  # 195 × 2min = 6.5h (sesión regular)
    },
}

# ─── LOOP PRINCIPAL ───────────────────────────────────────────────────────────
CADA polling_interval según mercado:

  PARA CADA mercado, config EN MERCADOS:
    
    # Stocks: solo procesar en horario de mercado
    SI mercado == "stocks" AND NOT mercado_abierto():
      CONTINUAR   # saltar hasta próxima apertura

    PARA CADA par EN config.pares:
      n_periodos   = max(TEMPORALIDADES["4H"][mercado], TEMPORALIDADES["1D"][mercado])
      datos        = obtener_ohlc(par, intervalo=config.polling + "m", cantidad=n_periodos + 10)

      vela_4H      = construir_vela(datos, TEMPORALIDADES["4H"][mercado])
      vela_1D      = construir_vela(datos, TEMPORALIDADES["1D"][mercado])
      hist_4H      = historial_cerrado(par, tf="4H", n=5)
      hist_1D      = historial_cerrado(par, tf="1D", n=5)

      PARA CADA tf, vela, hist EN [("4H", vela_4H, hist_4H), ("1D", vela_1D, hist_1D)]:
        resultado = evaluar_patrones(vela, hist)

        SI resultado.accion EN ["BUY", "SELL"]:
          SI NOT alerta_reciente(par, tf, cooldown=vela.duracion):  # Mejora M6
            publicar_alerta({
              par       : par,
              mercado   : mercado,
              tf        : tf,
              patron_id : resultado.id,
              nombre    : resultado.nombre,
              accion    : resultado.accion,
              señal     : resultado.señal,
              confianza : resultado.score,    # Mejora M3
              timestamp : ahora_utc(),
              ohlc      : vela,
            })
```

---

## 6. Temporalidades Detalladas

### Construcción de velas por mercado

| Mercado | Polling | Vela 4H | Vela 1D | Cierre 1D |
|---|:---:|---:|---:|---|
| Crypto | 5 min | 48 períodos | 288 períodos | 00:00 UTC diario |
| Forex | 5 min | 48 períodos | 288 períodos | 22:00 UTC (lun–vie) |
| Stocks (NYSE/NASDAQ) | **2 min** | **120 períodos** | **195 períodos** | 16:00 ET (lun–vie) |

### Sesiones de Stocks y ventanas de evaluación

```
SESIÓN REGULAR NYSE/NASDAQ: 09:30 – 16:00 ET (6.5 horas)
────────────────────────────────────────────────────────────────────────
09:30                   13:30                   16:00
  │                       │                       │
  ├── VELA 4H #1 ─────────┤── VELA 4H #2 ─────────┤  →  CIERRE VELA 1D
  │   (120 períodos 2min) │   (120 períodos 2min) │
  │                       │                       │
  │◄────────────── VELA 1D (195 períodos 2min) ──►│

PRE-MARKET:  04:00 – 09:30 ET  → datos recolectados, señal marcada CONFIANZA_REDUCIDA
AFTER-HOURS: 16:00 – 20:00 ET  → datos recolectados, señal marcada CONFIANZA_REDUCIDA
```

### Ajustes específicos para Stocks

1. **Días festivos:** El sistema debe mantener un calendario de festivos de NYSE/NASDAQ y pausar el procesamiento esos días.
2. **Circuit breakers:** Si el mercado activa un halt o trading halt en un ticker, marcar ese par como `estado: SUSPENDIDO` y no emitir alertas hasta reanudación.
3. **Earnings / eventos corporativos:** Considerar integrar un calendario de earnings (ej. Polygon.io events API). Las señales durante semanas de earnings deben marcarse con `contexto: EARNINGS` para que el operador ajuste su gestión de riesgo.
4. **Splits y dividendos:** Ajustar precios históricos por splits y dividendos usando precios ajustados (`adj_close`) para evitar patrones falsos provocados por gaps de ajuste corporativo.
5. **ETFs e índices:** SPY, QQQ, IWM, DIA se procesan idéntico a acciones individuales pero ofrecen señales de mayor liquidez y menor volatilidad específica.

---

## 7. Estructuras de Datos

### Objeto Vela — `CandleOHLC`

```typescript
interface CandleOHLC {
  timestamp  : Date;          // UTC siempre
  open       : number;
  high       : number;
  low        : number;
  close      : number;
  volume     : number;
  vwap?      : number;        // solo Stocks (calculado desde datos intradiarios)
  closed     : boolean;       // true = vela completamente cerrada
  timeframe  : "4H" | "1D";
  pair       : string;        // "BTCUSDT" | "EURUSD" | "AAPL"
  market     : "crypto" | "forex" | "stocks";
  session?   : "regular" | "premarket" | "afterhours"; // solo Stocks
}
```

### Objeto Señal — `CandleSignal`

```typescript
interface CandleSignal {
  timestamp      : Date;                 // UTC
  pair           : string;
  market         : "crypto" | "forex" | "stocks";
  timeframe      : "4H" | "1D";
  pattern_id     : number;               // 1–26
  pattern_name   : string;
  signal         : "Alcista" | "Bajista" | "Neutral" |
                   "Reversión Alcista" | "Reversión Bajista";
  action         : "BUY" | "SELL" | "HOLD";
  confidence     : number;               // 0–100 (ver Mejora M3)
  candle         : CandleOHLC;
  prev_candles   : CandleOHLC[];         // 0, 1 o 2 velas previas según patrón
  volume_conf    : boolean;              // confirmación de volumen (Mejora M1)
  trend_aligned  : boolean;             // alineación MTF (Mejora M4)
  session_conf   : "ALTA" | "REDUCIDA"; // REDUCIDA en pre/after-hours (Stocks)
  earnings_week? : boolean;             // solo Stocks — semana de earnings
}
```

---

## 8. Mejoras Propuestas

### M1 — Confirmación por Volumen
Filtro secundario de validación: un patrón de reversión tiene mayor probabilidad de éxito cuando `volumen > SMA20_vol * 1.5`. Los patrones sin confirmación de volumen se emiten como `confianza: REDUCIDA` en lugar de alerta completa.

**Aplicación especial en Stocks:** El volumen es especialmente significativo en acciones. Un Engulfing Alcista en AAPL con volumen 3× el promedio de 20 días es considerablemente más fiable que el mismo patrón con volumen bajo.

### M2 — Tolerancia Adaptativa (ATR-based)
Reemplazar `ε = 5% del rango` por tolerancia dinámica basada en ATR de 14 períodos:
```
ε = ATR_14 * factor
factor_crypto = 0.12   # mayor volatilidad
factor_forex  = 0.08
factor_stocks = 0.10   # varía por sector (tech > utilities)
```

### M3 — Score de Confianza (0–100)
Asignar un score compuesto basado en:
- Pureza de la formación OHLC (40 pts)
- Confirmación de volumen — M1 (20 pts)
- Alineación con tendencia MTF — M4 (20 pts)
- Coincidencia con nivel S/R — M5 (20 pts)

### M4 — Filtro de Tendencia Multi-TimeFrame
Verificar alineación con temporalidad superior antes de emitir alerta:
```
BUY en 4H es de mayor calidad si:  precio_actual > EMA21(1D)
SELL en 4H es de mayor calidad si: precio_actual < EMA21(1D)
```

### M5 — Niveles de Soporte/Resistencia
Integrar detección automática de S/R usando pivots de 20 períodos. Los patrones de reversión alcista que coinciden con soporte, y los bajistas que coinciden con resistencia, reciben boost de +20 en el score.

### M6 — Deduplicación de Alertas
Cooldown por par + temporalidad: una vez emitida una alerta BUY en `AAPL / 4H`, no re-emitir hasta que la vela actual se cierre y comience la siguiente. Crítico especialmente para Stocks con polling de 2 minutos (120 evaluaciones por vela 4H).

### M7 — Bus de Eventos Desacoplado
```
Motor Detección ──► Redis PubSub / Message Queue ──► Telegram Bot
                                                  ──► Discord Webhook
                                                  ──► Email / SMS
                                                  ──► REST Webhook
                                                  ──► TradingView Alert
```

### M8 — Dashboard de Monitoreo en Tiempo Real
Panel WebSocket + React mostrando: estado por par y mercado, último patrón detectado, historial de alertas 24h, score promedio por patrón y tasa de acierto estadístico.

### M9 — Módulo de Backtesting
Procesamiento de datos OHLC históricos para medir por patrón y mercado: frecuencia de aparición, porcentaje de éxito, drawdown promedio y ratio riesgo/beneficio. Los resultados retroalimentan el score de confianza (M3).

**Recomendación para Stocks:** Backtestear separando por sector (tech, financials, energy) ya que la efectividad de los patrones varía significativamente entre sectores.

### M10 — Logging Estructurado y Auditoría
```json
{
  "timestamp": "2025-04-17T14:32:00Z",
  "event":     "SIGNAL_EMITTED",
  "pair":      "NVDA",
  "market":    "stocks",
  "tf":        "4H",
  "pattern":   { "id": 11, "name": "Engulfing Alcista" },
  "action":    "BUY",
  "confidence": 82,
  "ohlc":      { "O": 875.20, "H": 891.50, "L": 872.10, "C": 889.30 },
  "volume_conf": true,
  "trend_aligned": true,
  "session":   "regular"
}
```

---

## 9. Hoja de Ruta de Implementación

| Fase | Componentes | Prioridad | Mercados |
|---|---|:---:|---|
| **Fase 1 — Fundación** | Motor OHLC + construcción de velas · 26 algoritmos base · Alertas BUY/SELL | 🔴 CRÍTICA | Crypto · Forex · Stocks |
| **Fase 2 — Calidad** | Tolerancia ATR adaptativa (M2) · Filtro de volumen (M1) · Deduplicación (M6) | 🟠 ALTA | Todos |
| **Fase 3 — Inteligencia** | Score de confianza (M3) · Filtro MTF (M4) · Niveles S/R (M5) | 🟡 MEDIA | Todos |
| **Fase 4 — Stocks Plus** | Calendario festivos NYSE · Calendario earnings · Ajuste splits/dividendos · VWAP | 🟡 MEDIA | Stocks |
| **Fase 5 — Operaciones** | Backtesting (M9) · Dashboard (M8) · Logging (M10) · Bus de eventos (M7) | 🟢 BAJA | Todos |

---

## 10. Notas de Implementación Críticas

1. **UTC obligatorio** — todos los timestamps deben manejarse en UTC sin excepción para garantizar coherencia entre los tres mercados.

2. **Stocks: velas cerradas únicamente** — para patrones multi-vela, usar solo velas de 4H o 1D completamente cerradas. Nunca comparar la vela en formación como si fuera una vela previa.

3. **Stocks: sesión regular primero** — el motor debe priorizar los datos de 09:30–16:00 ET para la construcción de velas. Los datos de pre/after-market son complementarios, nunca base.

4. **Epsilon por mercado** — el parámetro `ε = 5%` es un punto de partida; calibrar independientemente para Crypto, Forex y Stocks usando el módulo de backtesting. Los stocks de baja liquidez y los de alta volatilidad (small caps, meme stocks) pueden requerir `ε` más amplio.

5. **Float64 obligatorio** — usar precisión de 64 bits en todos los cálculos numéricos para evitar errores de redondeo, especialmente en pares Forex con 5 decimales y acciones de precio centavo.

6. **Stocks en fines de semana** — no generar velas de 4H ni 1D de Stock en sábado o domingo. Filtrar completamente los datos de esos días del historial antes de procesar patrones.

7. **Gap overnight en Stocks** — los gaps entre el cierre del viernes y la apertura del lunes (o cualquier día siguiente) pueden disparar falsos patrones (especialmente Engulfing y Marubozu). Considerar marcar la primera vela post-gap con flag `gap_apertura: true` y reducir el score de confianza en ±15 puntos.

---

*Documento generado por Claude (Anthropic) · ANTIGRAVITY Candle Signal Validator v1.0 · Versión extendida con Stocks*
