# 🗄️ PROMPT ANTIGRAVITY — Migraciones de Base de Datos eTrade v3
## Tarea: Completar schema Supabase para Sprint 1
**Proyecto:** eTrade | **Fecha:** Marzo 2026  
**Prioridad:** CRÍTICA — ejecutar antes de iniciar el pipeline de trading

---

## CONTEXTO

El proyecto eTrade ya tiene las siguientes tablas en Supabase:
`api_connections`, `system_config`, `market_candles`, `technical_indicators`,
`candle_patterns`, `volume_spikes`, `risk_config`, `news_sentiment`,
`backtest_runs`, `alert_events`, `cron_cycles`, `system_logs`, `orders`,
`positions`, `trading_signals`, `trading_rules`, `market_regime`,
`trading_rules_history`, `paper_trades`, `cooldowns`, `config_snapshots`,
`trading_config`, `bot_state`, `market_regime_history`, `pilot_diagnostics`,
`trades_history`, `bot_global_state`

Esta tarea tiene **dos partes**:
1. Agregar columnas faltantes a tablas existentes (`ALTER TABLE`)
2. Crear 4 tablas nuevas (`CREATE TABLE`)

**REGLA IMPORTANTE:** No recrear tablas existentes. Usar solo `ALTER TABLE ADD COLUMN IF NOT EXISTS` para no perder datos ya existentes.

---

## PARTE 1 — COLUMNAS FALTANTES EN TABLAS EXISTENTES

### 1.1 Tabla: `positions`

```sql
-- Precio promedio ponderado (CRÍTICO — el SL se calcula sobre este valor, no sobre T1)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS avg_entry_price        NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sl_price               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp_partial_price       NUMERIC(20,8);   -- upper_5 o lower_5
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp_full_price          NUMERIC(20,8);   -- upper_6 o lower_6
ALTER TABLE positions ADD COLUMN IF NOT EXISTS breakeven_activated    BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS breakeven_price        NUMERIC(20,8);

-- Multi-timeframe basis (soporte/resistencia por TF)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_15m              NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_4h               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_1d               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS confluence_score       SMALLINT;        -- 1, 2 o 3 TFs alineados
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sizing_multiplier      NUMERIC(4,2);    -- 0.70 | 0.85 | 1.00

-- Futuros
ALTER TABLE positions ADD COLUMN IF NOT EXISTS liquidation_price      NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage               SMALLINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS funding_rate_accrued   NUMERIC(10,6) DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS market_type            VARCHAR(20);     -- 'spot' | 'futures'

-- Gestión de posición
ALTER TABLE positions ADD COLUMN IF NOT EXISTS rule_code              VARCHAR(10);     -- Aa13, Bb22, etc.
ALTER TABLE positions ADD COLUMN IF NOT EXISTS entry_bar_index        BIGINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS bars_held              INT DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS max_holding_bars       INT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_closed         BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_price    NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_usd      NUMERIC(10,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_at       TIMESTAMPTZ;

-- Entradas escalonadas (T1, T2, T3 — JSON array de entradas)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS entries                JSONB DEFAULT '[]'::jsonb;
-- Formato entries:
-- [
--   { "trade_n": 1, "price": 65000, "usd": 18.00, "timestamp": "...", "rule_code": "Aa22" },
--   { "trade_n": 2, "price": 63400, "usd": 27.00, "timestamp": "...", "rule_code": "Aa22" }
-- ]

-- EMA20 y ADX en el momento de la entrada
ALTER TABLE positions ADD COLUMN IF NOT EXISTS ema20_phase_entry      VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS adx_value_entry        NUMERIC(6,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS regime_entry           VARCHAR(20);     -- 'alto_riesgo' | 'riesgo_medio' | 'bajo_riesgo'

-- Resultado final
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_usd      NUMERIC(10,4);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_pct       NUMERIC(8,4);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS close_reason           VARCHAR(50);     -- 'tp_partial' | 'tp_full' | 'sl' | 'timeout' | 'manual' | 'emergency' | 'circuit_breaker'
ALTER TABLE positions ADD COLUMN IF NOT EXISTS close_bar_index        BIGINT;
```

---

### 1.2 Tabla: `orders`

```sql
ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_price         NUMERIC(20,8);   -- precio cuando se generó la señal
ALTER TABLE orders ADD COLUMN IF NOT EXISTS execution_price      NUMERIC(20,8);   -- precio real de fill
ALTER TABLE orders ADD COLUMN IF NOT EXISTS slippage_pct         NUMERIC(8,4);    -- (execution - signal) / signal * 100
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type           VARCHAR(10);     -- 'LIMIT' | 'MARKET' | 'STOP_LIMIT'
ALTER TABLE orders ADD COLUMN IF NOT EXISTS timeout_bars         SMALLINT DEFAULT 2;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fill_pct             NUMERIC(5,2) DEFAULT 0;   -- % llenado (para órdenes parciales)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS step_number          SMALLINT;        -- 1 (cerrar) o 2 (abrir) del flujo 2 pasos
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trade_n              SMALLINT;        -- T1, T2, T3, T4, T5
ALTER TABLE orders ADD COLUMN IF NOT EXISTS rule_code            VARCHAR(10);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_paper             BOOLEAN DEFAULT false;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS stop_price           NUMERIC(20,8);   -- para STOP_LIMIT
ALTER TABLE orders ADD COLUMN IF NOT EXISTS limit_price          NUMERIC(20,8);   -- para STOP_LIMIT
ALTER TABLE orders ADD COLUMN IF NOT EXISTS gap_pct              NUMERIC(5,3);    -- gap entre stop y limit price
ALTER TABLE orders ADD COLUMN IF NOT EXISTS expires_at_bar       BIGINT;          -- bar_index de expiración de orden límite
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_reason     VARCHAR(50);
```

---

### 1.3 Tabla: `trading_signals`

```sql
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);     -- Aa11, Aa22, Bb12, etc.
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS signal_bar_index    BIGINT;          -- bar en que se generó
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS signal_age_bars     SMALLINT DEFAULT 0;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS expires_at_bar      BIGINT;          -- signal_bar_index + MAX_SIGNAL_AGE_BARS
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS is_expired          BOOLEAN DEFAULT false;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ema20_angle_raw     NUMERIC(8,4);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS plus_di             NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS minus_di            NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;        -- 1, 2, 3
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS fibonacci_zone      SMALLINT;        -- -6 a +6
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS regime              VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS mtf_score           NUMERIC(4,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS rr_real             NUMERIC(6,3);    -- RR ajustado por fees
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_pattern          VARCHAR(50);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_sentiment        VARCHAR(20);     -- bullish|bearish|indecision|reversal
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_recommendation   VARCHAR(10);     -- enter|wait|caution
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_agreed           BOOLEAN;         -- IA coincide con señal
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_confidence       NUMERIC(4,2);    -- 0.0 a 1.0
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS acted_upon          BOOLEAN DEFAULT false;  -- se generó orden
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS blocked_reason      VARCHAR(100);    -- por qué no se actuó
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS is_paper            BOOLEAN DEFAULT false;
```

---

### 1.4 Tabla: `technical_indicators`

```sql
-- EMA20 phases (percentiles adaptativos — NO umbrales fijos)
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
-- Valores: 'flat' | 'nivel_1_long' | 'nivel_2_long' | 'nivel_3_long'
--          'nivel_1_short' | 'nivel_2_short' | 'nivel_3_short'

ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_angle_raw     NUMERIC(8,4);    -- ángulo normalizado por ATR
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_angle_pct     NUMERIC(5,2);    -- percentil rolling (0-100)
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_was_flat      BOOLEAN;         -- venía de fase plana
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_exit_flat_long  BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_exit_flat_short BOOLEAN DEFAULT false;

-- ADX + DI (si no existen ya)
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS adx                 NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS plus_di             NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS minus_di            NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS di_cross_bullish    BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS di_cross_bearish    BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS adx_rising          BOOLEAN DEFAULT false;  -- ADX subiendo vs 3 barras atrás

-- Basis multi-timeframe
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;        -- 1, 2, 3

-- Volumen
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_ema             NUMERIC(20,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_slope_3         NUMERIC(8,4);    -- pendiente 3 barras
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_decreasing      BOOLEAN DEFAULT false;  -- confirma LONG TP
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_increasing      BOOLEAN DEFAULT false;  -- confirma SHORT TP
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_entry_ok        BOOLEAN DEFAULT false;  -- >= 70% vol_ema

-- Fibonacci BB
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS fibonacci_zone      SMALLINT;        -- -6 a +6
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_vwma          NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_1             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_2             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_3             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_4             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_5             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_6             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_1             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_2             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_3             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_4             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_5             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_6             NUMERIC(20,8);

-- ATR para clasificador de régimen
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS atr                 NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS atr_percentile      NUMERIC(5,1);    -- percentil vs últimas 50 barras

-- MACD 4C
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_value          NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_4c_type        SMALLINT;        -- 1, 2, 3, 4
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_buy            BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_sell           BOOLEAN DEFAULT false;
```

---

### 1.5 Tabla: `market_candles`

```sql
-- Verificar que existan estos campos. Si no, agregarlos:
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS timeframe       VARCHAR(5);      -- '5m'|'15m'|'30m'|'45m'|'4h'|'1d'|'1w'
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS is_closed       BOOLEAN DEFAULT true;  -- false = vela en formación
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS hlc3            NUMERIC(20,8);   -- (high+low+close)/3

-- Índice compuesto para el cleanup por timeframe (performance crítica)
CREATE INDEX IF NOT EXISTS idx_market_candles_timeframe_ts
    ON market_candles(timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_candles_symbol_tf
    ON market_candles(symbol, timeframe, timestamp DESC);
```

---

### 1.6 Tabla: `risk_config`

```sql
-- Parámetros del clasificador automático de régimen
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS flat_pct              NUMERIC(5,2);   -- percentil para zona "plana" EMA20
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS peak_pct              NUMERIC(5,2);   -- percentil para zona "cima" EMA20
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS di_cross_required     BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS min_nivel_entrada     SMALLINT DEFAULT 1;  -- nivel mínimo EMA20 para entrar
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_daily_loss_pct    NUMERIC(5,2) DEFAULT 5.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_trade_loss_pct    NUMERIC(5,2) DEFAULT 2.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS post_sl_bars          SMALLINT DEFAULT 3;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS post_tp_bars          SMALLINT DEFAULT 1;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_correlation       NUMERIC(4,2) DEFAULT 0.80;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS vol_entry_min_pct     NUMERIC(5,2) DEFAULT 70.0;  -- % del vol_ema
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS order_type_default    VARCHAR(10)  DEFAULT 'LIMIT';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS limit_timeout_bars    SMALLINT DEFAULT 2;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS stop_limit_gap_pct    NUMERIC(5,3) DEFAULT 0.10;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS fee_pct               NUMERIC(5,4) DEFAULT 0.001;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_enabled     BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_atr_mult    NUMERIC(4,2) DEFAULT 2.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_action      VARCHAR(20)  DEFAULT 'pause'; -- 'pause'|'close_all'|'alert_only'
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS signal_max_age_bars   SMALLINT DEFAULT 3;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS ai_candles_enabled    BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS ai_candles_mode       VARCHAR(15) DEFAULT 'informative'; -- 'informative'|'binding'

-- Max holding bars por timeframe (JSON)
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_holding_bars      JSONB DEFAULT '{
    "5m": 96,
    "15m": 48,
    "30m": 48,
    "45m": 32,
    "4h": 30,
    "1d": 14,
    "1w": 8
}'::jsonb;
```

---

### 1.7 Tabla: `trading_config`

```sql
-- Capital y sizing
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS capital_total          NUMERIC(12,2) DEFAULT 500.00;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS pct_for_trading        NUMERIC(5,2)  DEFAULT 20.0;   -- % del capital total
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS capital_operativo      NUMERIC(12,2);                -- calculado: capital_total * pct * 0.90
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS buffer_pct             NUMERIC(5,2)  DEFAULT 10.0;   -- % de buffer de seguridad

-- Distribución de trades (JSON editable desde configuración)
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS trade_distribution     JSONB DEFAULT '{
    "3_trades": {"t1": 20, "t2": 30, "t3": 50},
    "5_trades": {"t1": 10, "t2": 15, "t3": 20, "t4": 25, "t5": 30}
}'::jsonb;

-- Mercado activo
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS market_type            VARCHAR(20)   DEFAULT 'futures';  -- 'spot'|'futures'
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS leverage               SMALLINT      DEFAULT 5;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS active_symbols         JSONB         DEFAULT '["BTCUSDT","ETHUSDT","SOLUSDT","ADAUSDT"]'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS mode                   VARCHAR(10)   DEFAULT 'paper';    -- 'paper'|'real'

-- Retención de datos
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS retention_days         JSONB DEFAULT '{
    "5m": 20,
    "15m": 60,
    "30m": 90,
    "45m": 120,
    "4h": 365,
    "1d": 1095,
    "1w": 2190
}'::jsonb;

-- Telegram
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_enabled       BOOLEAN DEFAULT true;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_bot_token     TEXT;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_chat_id       TEXT;

-- Warm-up
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS warmup_bars_required   INT DEFAULT 200;
```

---

### 1.8 Tabla: `paper_trades`

```sql
-- Campos críticos para el dashboard de performance (Sprint 2)
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);     -- Aa13, Bb22, etc.
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS regime              VARCHAR(20);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS signal_price        NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS execution_price     NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS slippage_pct        NUMERIC(8,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ai_recommendation   VARCHAR(10);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ai_agreed           BOOLEAN;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ai_pattern          VARCHAR(50);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS bars_held           INT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS close_reason        VARCHAR(50);     -- 'tp_partial'|'tp_full'|'sl'|'timeout'|'manual'
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS avg_entry_price     NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS entries             JSONB DEFAULT '[]'::jsonb;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS partial_pnl_usd     NUMERIC(10,4);   -- ganancia del cierre parcial en upper_5
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS full_pnl_usd        NUMERIC(10,4);   -- ganancia del cierre total en upper_6/Nivel3
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS total_pnl_usd       NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS total_pnl_pct       NUMERIC(8,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS fibonacci_zone_entry SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS market_type         VARCHAR(20);     -- 'spot'|'futures'
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS leverage            SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS liquidation_price   NUMERIC(20,8);
```

---

### 1.9 Tabla: `trading_rules`

```sql
-- Verificar que tenga estos campos. Si no, agregarlos:
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS id                  BIGINT;          -- numérico único e irrepetible
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);     -- Aa11, Aa12, Bb21, etc.
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS name                TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS description         TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS direction           VARCHAR(10);     -- 'long'|'short'
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS market_type         JSONB;           -- ['crypto_spot','crypto_futures']
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS ema50_vs_ema200     VARCHAR(10);     -- 'above'|'below'|'any'
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS enabled             BOOLEAN DEFAULT true;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS regime_allowed      JSONB;           -- ['riesgo_medio','bajo_riesgo']
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS priority            INT DEFAULT 99;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS confidence          VARCHAR(10);     -- 'high'|'medium'|'low'
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS entry_trades        JSONB;           -- [1] o [1,2] etc.
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS conditions          JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS logic               VARCHAR(5) DEFAULT 'AND';  -- 'AND'|'OR'
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS notes               TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS version             INT DEFAULT 1;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS current             BOOLEAN DEFAULT true;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ DEFAULT NOW();

-- Índice para consultas rápidas del Rule Engine
CREATE INDEX IF NOT EXISTS idx_trading_rules_active
    ON trading_rules(direction, enabled, current)
    WHERE enabled = true AND current = true;
```

---

### 1.10 Tabla: `market_regime`

```sql
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS atr_percentile      NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS adx_risk_score      NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS volume_ratio        NUMERIC(6,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS volume_risk_score   NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS macro_trend         VARCHAR(10);     -- 'bullish'|'bearish'
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS macro_score         NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS mtf_threshold       NUMERIC(4,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS max_trades          SMALLINT;
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS emergency_active    BOOLEAN DEFAULT false;
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS emergency_atr_ratio NUMERIC(5,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS evaluated_at        TIMESTAMPTZ DEFAULT NOW();
```

---

### 1.11 Tabla: `alert_events`

```sql
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS alert_type     VARCHAR(30);
-- Valores: 'emergency_atr' | 'circuit_breaker' | 'reconciliation' |
--          'sl_hit' | 'tp_partial' | 'tp_full' | 'trade_opened' |
--          'cooldown_active' | 'warmup_progress' | 'symbol_health_fail'

ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS symbol         VARCHAR(20);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS timeframe      VARCHAR(5);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS severity       VARCHAR(10);     -- 'info'|'warning'|'critical'
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS telegram_sent  BOOLEAN DEFAULT false;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resolved       BOOLEAN DEFAULT false;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resolved_at    TIMESTAMPTZ;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS metadata       JSONB;           -- datos adicionales del evento
```

---

### 1.12 Tabla: `bot_state`

```sql
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS warmup_completed       BOOLEAN DEFAULT false;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS warmup_bars_loaded     INT DEFAULT 0;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS warmup_bars_required   INT DEFAULT 200;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_15m_cycle_at      TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_5m_cycle_at       TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_reconcile_at      TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_cleanup_at        TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS circuit_breaker_active BOOLEAN DEFAULT false;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS circuit_breaker_since  TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS daily_pnl_usd          NUMERIC(10,4) DEFAULT 0;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS daily_pnl_reset_at     TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS emergency_active       BOOLEAN DEFAULT false;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS emergency_since        TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS mode                   VARCHAR(10) DEFAULT 'paper';  -- 'paper'|'real'
```

---

## PARTE 2 — TABLAS NUEVAS A CREAR

### 2.1 `reconciliation_log` — Reconciliación bot vs Binance

```sql
CREATE TABLE IF NOT EXISTS reconciliation_log (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    timeframe           VARCHAR(5),
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    bot_state           JSONB,          -- estado que tenía el bot en Supabase
    exchange_state      JSONB,          -- estado real en Binance
    discrepancy_type    VARCHAR(50),
    -- Valores: 'position_not_found' | 'price_mismatch' | 'size_mismatch' |
    --          'order_partially_filled' | 'liquidated_externally' | 'no_discrepancy'
    action_taken        VARCHAR(100),
    supabase_updated    BOOLEAN DEFAULT false,
    telegram_notified   BOOLEAN DEFAULT false,
    resolved            BOOLEAN DEFAULT false,
    resolved_at         TIMESTAMPTZ,
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_symbol
    ON reconciliation_log(symbol, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_reconciliation_unresolved
    ON reconciliation_log(resolved, checked_at DESC)
    WHERE resolved = false;
```

---

### 2.2 `symbol_health_checks` — Health check antes de operar

```sql
CREATE TABLE IF NOT EXISTS symbol_health_checks (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    market_type         VARCHAR(20),    -- 'spot'|'futures'
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Métricas del check
    volume_24h          NUMERIC(20,2),
    spread_pct          NUMERIC(8,4),
    best_bid            NUMERIC(20,8),
    best_ask            NUMERIC(20,8),

    -- Resultados por criterio
    volume_ok           BOOLEAN,        -- vol_24h > umbral mínimo
    spread_ok           BOOLEAN,        -- spread < 0.15%
    symbol_active       BOOLEAN,        -- no en modo "only reduce"
    healthy             BOOLEAN,        -- todos los criterios OK

    -- Umbrales usados en este check
    min_volume_usd      NUMERIC(20,2),
    max_spread_pct      NUMERIC(5,3),

    blocked_entry       BOOLEAN DEFAULT false,
    block_reason        TEXT
);

CREATE INDEX IF NOT EXISTS idx_health_checks_symbol
    ON symbol_health_checks(symbol, checked_at DESC);

-- Solo mantener los últimos 7 días de health checks
CREATE INDEX IF NOT EXISTS idx_health_checks_cleanup
    ON symbol_health_checks(checked_at DESC);
```

---

### 2.3 `funding_rates` — Historial de funding rates (Futuros)

```sql
CREATE TABLE IF NOT EXISTS funding_rates (
    id                      BIGSERIAL PRIMARY KEY,
    symbol                  VARCHAR(20)     NOT NULL,
    rate                    NUMERIC(12,8)   NOT NULL,   -- tasa por período (8h)
    next_funding_time       TIMESTAMPTZ,
    checked_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Proyecciones
    projected_cost_24h_pct  NUMERIC(10,6),  -- costo proyectado 24h en %
    projected_cost_24h_usd  NUMERIC(10,4),  -- costo proyectado en USD (sobre nocional)

    -- Señales para la decisión de entrada
    favorable_for_long      BOOLEAN,        -- rate < 0 → compradores reciben
    favorable_for_short     BOOLEAN,        -- rate > 0 → vendedores reciben

    -- Acumulado de la posición abierta (actualizar en ciclo 5m)
    position_id             BIGINT REFERENCES positions(id) ON DELETE SET NULL,
    accrued_cost_usd        NUMERIC(10,4) DEFAULT 0,
    payments_count          SMALLINT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol
    ON funding_rates(symbol, checked_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_funding_rates_symbol_time
    ON funding_rates(symbol, next_funding_time);
```

---

### 2.4 `slippage_log` — Tracking de slippage real

```sql
CREATE TABLE IF NOT EXISTS slippage_log (
    id                  BIGSERIAL PRIMARY KEY,
    order_id            BIGINT REFERENCES orders(id) ON DELETE CASCADE,
    symbol              VARCHAR(20)     NOT NULL,
    market_type         VARCHAR(20),
    order_type          VARCHAR(10),    -- 'LIMIT'|'MARKET'
    side                VARCHAR(10),    -- 'buy'|'sell'

    signal_price        NUMERIC(20,8)   NOT NULL,
    execution_price     NUMERIC(20,8)   NOT NULL,
    slippage_pct        NUMERIC(8,4)    NOT NULL,
    slippage_usd        NUMERIC(10,4),

    is_paper            BOOLEAN DEFAULT false,
    timestamp           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slippage_symbol
    ON slippage_log(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_slippage_order_type
    ON slippage_log(order_type, timestamp DESC);

-- Vista resumen para el dashboard de performance
CREATE OR REPLACE VIEW slippage_summary AS
SELECT
    symbol,
    order_type,
    COUNT(*)                        AS total_orders,
    ROUND(AVG(slippage_pct), 4)    AS avg_slippage_pct,
    ROUND(MAX(slippage_pct), 4)    AS max_slippage_pct,
    ROUND(SUM(slippage_usd), 2)    AS total_slippage_usd
FROM slippage_log
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY symbol, order_type
ORDER BY avg_slippage_pct DESC;
```

---

## PARTE 3 — DATOS INICIALES (SEED)

### 3.1 Seed: `trading_rules` — Las 13 reglas del v3

```sql
-- Limpiar reglas existentes si las hay (solo en desarrollo)
-- DELETE FROM trading_rules; -- DESCOMENTАР SOLO EN DEV

INSERT INTO trading_rules
  (id, rule_code, name, description, direction, market_type, ema50_vs_ema200,
   enabled, regime_allowed, priority, confidence, entry_trades, conditions, logic, notes)
VALUES
-- ═══ LONG RULES — EMA50 < EMA200 (macro bajista) ═══
(1001, 'Aa13', 'LONG — EMA50 cruza basis (macro bajista)',
 'EMA50 supera la VWMA (basis) en mercado macro bajista. Señal de cambio de tendencia local.',
 'long', '["crypto_spot","crypto_futures"]', 'below',
 true, '["riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]',
 '[{"indicator":"ema4_cross_basis_up","operator":"==","value":true},{"indicator":"pinescript_signal","operator":"==","value":"Buy"}]',
 'AND', 'Al momento del cruce, comprar al primer Buy del PineScript'),

(1002, 'Aa12', 'LONG — Rebote desde lower_5/6 (macro bajista)',
 'Precio tocó lower_5 o lower_6 con EMA20 girando positivo. Rebote desde sobreventa extrema.',
 'long', '["crypto_spot","crypto_futures"]', 'below',
 true, '["riesgo_medio","bajo_riesgo"]', 2, 'medium', '[1]',
 '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"low_crossed_lower5_or_6","operator":"==","value":true},{"indicator":"reversal_confirmed","operator":"==","value":true}]',
 'AND', 'Confirmación: is_dragonfly OR low_higher_than_prev'),

(1003, 'Aa11', 'LONG — EMA20 flat + ADX bajo + DI cruce (macro bajista)',
 'Acumulación temprana. EMA20 positivo con ADX bajo y cruce alcista del DI.',
 'long', '["crypto_spot","crypto_futures"]', 'below',
 true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1]',
 '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"adx","operator":"<","value":20},{"indicator":"ema20_phase","operator":"==","value":"nivel_1_long"},{"indicator":"di_cross_bullish","operator":"==","value":true}]',
 'AND', 'Solo régimen riesgo_medio o bajo_riesgo. Solo T1.'),

-- ═══ LONG RULES — EMA50 > EMA200 (macro alcista) ═══
(1004, 'Aa24', 'LONG — EMA50 cruza basis + Nivel 1 (macro alcista)',
 'EMA50 supera el basis VWMA con EMA20 en fase nivel_1_long. Entrada de alta confianza.',
 'long', '["crypto_spot","crypto_futures"]', 'above',
 true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 1, 'high', '[1,2,3]',
 '[{"indicator":"ema4_cross_basis_up","operator":"==","value":true},{"indicator":"ema20_phase","operator":"==","value":"nivel_1_long"},{"indicator":"pinescript_signal","operator":"==","value":"Buy"}]',
 'AND', 'Habilitar T2/T3 con condición precio decreciente'),

(1005, 'Aa22', 'LONG — EMA50 ascendente sobre basis (macro alcista)',
 'EMA50 ángulo positivo Y precio del EMA50 sobre el basis VWMA.',
 'long', '["crypto_spot","crypto_futures"]', 'above',
 true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]',
 '[{"indicator":"ema50_angle","operator":">=","value":0},{"indicator":"ema4_above_basis","operator":"==","value":true}]',
 'AND', NULL),

(1006, 'Aa23', 'LONG — EMA9 + EMA50 ascendentes (macro alcista)',
 'Ambas EMAs dinámicas apuntan hacia arriba. Momentum de corto y mediano plazo alineados.',
 'long', '["crypto_spot","crypto_futures"]', 'above',
 true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1]',
 '[{"indicator":"ema9_angle","operator":">=","value":0},{"indicator":"ema50_angle","operator":">=","value":0},{"indicator":"adx","operator":">=","value":"adx_min_config"}]',
 'AND', 'adx_min_config viene del régimen activo'),

(1007, 'Aa21', 'LONG — EMA20 flat + ADX bajo cerca del basis (macro alcista)',
 'Señal temprana en lateral. Solo válida muy cerca del basis.',
 'long', '["crypto_spot","crypto_futures"]', 'above',
 true, '["bajo_riesgo"]', 4, 'low', '[1]',
 '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"adx","operator":"<","value":20},{"indicator":"fibonacci_zone","operator":"between","value":[-2,2]},{"indicator":"close_vs_basis","operator":"<=","value":1.005}]',
 'AND', 'Solo régimen bajo_riesgo. Solo T1.'),

-- ═══ SHORT RULES — EMA50 < EMA200 (macro bajista) ═══
(1008, 'Bb12', 'SHORT — EMA50 cruza basis hacia abajo (macro bajista)',
 'EMA50 perfora el basis VWMA en mercado macro bajista. Señal de continuación bajista.',
 'short', '["crypto_spot","crypto_futures"]', 'below',
 true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]',
 '[{"indicator":"ema4_cross_basis_down","operator":"==","value":true},{"indicator":"pinescript_signal","operator":"==","value":"Sell"}]',
 'AND', 'Al momento del cruce, abrir SHORT al primer Sell del PineScript'),

(1009, 'Bb13', 'SHORT — EMA50 bajo basis + ADX + DI cruce (macro bajista)',
 'Distribución temprana en consolidación. EMA50 ya bajo el basis con cruce bajista del DI.',
 'short', '["crypto_spot","crypto_futures"]', 'below',
 true, '["riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]',
 '[{"indicator":"ema4_below_basis","operator":"==","value":true},{"indicator":"adx","operator":"<","value":20},{"indicator":"ema20_phase","operator":"in","value":["flat","nivel_1_short"]},{"indicator":"di_cross_bearish","operator":"==","value":true},{"indicator":"ema20_angle_raw","operator":"<=","value":0}]',
 'AND', NULL),

(1010, 'Bb11', 'SHORT — ADX fuerte + Nivel 2 bajista (macro bajista)',
 'Impulso bajista fuerte confirmado con ADX > 40 y fase nivel_2_short.',
 'short', '["crypto_spot","crypto_futures"]', 'below',
 true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1,2]',
 '[{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_short"},{"indicator":"di_spread","operator":">=","value":5}]',
 'AND', 'di_spread = minus_di - plus_di >= 5 puntos'),

-- ═══ SHORT RULES — EMA50 > EMA200 (macro alcista — contra-tendencia) ═══
(1011, 'Bb22', 'SHORT — Agotamiento extremo en upper_6 (macro alcista)',
 'HIGH cruzó upper_6 con ADX fuerte y EMA50 girando negativo. Reversal técnico en extremo Fibonacci.',
 'short', '["crypto_spot","crypto_futures"]', 'above',
 true, '["riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]',
 '[{"indicator":"high_crossed_upper6","operator":"==","value":true},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_long"},{"indicator":"ema50_angle","operator":"<=","value":0},{"indicator":"reversal_candle_bearish","operator":"==","value":true}]',
 'AND', 'reversal_candle_bearish = is_gravestone OR (is_red_candle AND high_in_upper6) OR high_lower_than_prev. RR mínimo forzado 3.0. Solo T1.'),

(1012, 'Bb23', 'SHORT — EMA50 cruza basis + EMA20 negativo (macro alcista)',
 'EMA50 perfora el basis con EMA20 ya negativo. Señal más limpia de cambio en macro alcista.',
 'short', '["crypto_spot","crypto_futures"]', 'above',
 true, '["riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]',
 '[{"indicator":"ema4_cross_basis_down","operator":"==","value":true},{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"pinescript_signal","operator":"==","value":"Sell"}]',
 'AND', 'Al momento del cruce. RR mínimo del régimen activo.'),

(1013, 'Bb21', 'SHORT — ADX fuerte + Nivel 2 bajista (macro alcista)',
 'Impulso bajista fuerte en mercado macro alcista. Alta selectividad.',
 'short', '["crypto_spot","crypto_futures"]', 'above',
 true, '["bajo_riesgo"]', 3, 'medium', '[1]',
 '[{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_short"},{"indicator":"di_spread","operator":">=","value":10}]',
 'AND', 'di_spread = minus_di - plus_di >= 10 puntos. Solo bajo_riesgo. RR mínimo 3.0. Solo T1.')

ON CONFLICT (id) DO NOTHING;
```

---

## PARTE 4 — ÍNDICES DE PERFORMANCE CRÍTICOS

```sql
-- Consultas más frecuentes del pipeline (cada 15m × 4 símbolos)
CREATE INDEX IF NOT EXISTS idx_technical_indicators_symbol_tf
    ON technical_indicators(symbol, timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_positions_open
    ON positions(symbol, is_open)
    WHERE is_open = true;   -- partial index — solo posiciones abiertas

CREATE INDEX IF NOT EXISTS idx_trading_signals_active
    ON trading_signals(symbol, is_expired, acted_upon, created_at DESC)
    WHERE is_expired = false AND acted_upon = false;

CREATE INDEX IF NOT EXISTS idx_cooldowns_active
    ON cooldowns(symbol, active, expires_at)
    WHERE active = true;

CREATE INDEX IF NOT EXISTS idx_orders_pending
    ON orders(symbol, status, created_at DESC)
    WHERE status IN ('pending', 'partially_filled');

CREATE INDEX IF NOT EXISTS idx_funding_rates_latest
    ON funding_rates(symbol, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_trades_analysis
    ON paper_trades(rule_code, regime, close_reason, created_at DESC);
```

---

## PARTE 5 — VERIFICACIÓN POST-MIGRACIÓN

```sql
-- Ejecutar después de las migraciones para verificar que todo está correcto:

-- 1. Verificar tablas nuevas creadas
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'reconciliation_log', 'symbol_health_checks',
    'funding_rates', 'slippage_log'
  );
-- Debe retornar 4 filas

-- 2. Verificar columnas críticas en positions
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'positions'
  AND column_name IN (
    'avg_entry_price', 'sl_price', 'tp_partial_price', 'tp_full_price',
    'breakeven_activated', 'confluence_score', 'basis_15m', 'basis_4h',
    'basis_1d', 'liquidation_price', 'rule_code', 'entries', 'bars_held'
  );
-- Debe retornar 13 filas

-- 3. Verificar columnas críticas en technical_indicators
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'technical_indicators'
  AND column_name IN (
    'ema20_phase', 'ema20_angle_raw', 'ema20_angle_pct',
    'adx', 'plus_di', 'minus_di', 'di_cross_bullish', 'di_cross_bearish',
    'basis_15m', 'basis_4h', 'basis_1d', 'confluence_score',
    'vol_decreasing', 'vol_increasing', 'vol_entry_ok',
    'upper_5', 'upper_6', 'lower_5', 'lower_6', 'fibonacci_zone',
    'macd_4c_type', 'macd_buy', 'macd_sell', 'atr_percentile'
  );
-- Debe retornar 24 filas

-- 4. Verificar seed de reglas
SELECT rule_code, name, direction, enabled
FROM trading_rules
WHERE current = true
ORDER BY direction, priority;
-- Debe retornar 13 reglas (Aa11-Aa24 y Bb11-Bb23)

-- 5. Verificar índices creados
SELECT indexname
FROM pg_indexes
WHERE tablename IN (
  'market_candles', 'technical_indicators', 'positions',
  'trading_signals', 'cooldowns', 'orders', 'funding_rates',
  'paper_trades', 'trading_rules'
);
```

---

## NOTAS FINALES PARA ANTIGRAVITY

```
1. ORDEN DE EJECUCIÓN:
   Parte 1 → Parte 2 → Parte 3 → Parte 4 → Parte 5 (verificación)
   NO ejecutar en orden inverso.

2. EN PRODUCCIÓN:
   Ejecutar cada bloque ALTER TABLE / CREATE TABLE en una transacción.
   Si algún bloque falla, hacer ROLLBACK y reportar el error.

3. DATOS EXISTENTES:
   Todos los ALTER TABLE usan IF NOT EXISTS.
   No se perderán datos de tablas existentes.

4. ENVIRONMENT:
   Ejecutar primero en el entorno de desarrollo/staging.
   Verificar con las queries de la Parte 5.
   Solo entonces ejecutar en producción.

5. BACKUP:
   Hacer backup de Supabase antes de ejecutar las migraciones
   aunque sean solo ADD COLUMN (por precaución).
```

---

*Prompt de migraciones SQL — eTrade v3*
*Antigravity Dev Team — Marzo 2026*
