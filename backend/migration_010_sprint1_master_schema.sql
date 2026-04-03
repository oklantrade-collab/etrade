-- ==========================================================
-- MIGRATION 010 — eTrade Sprint 1 Master Schema
-- Optimized for Supabase (Memory-First Architecture)
-- ==========================================================

-- PARTE 1: ALTER TABLE (Columnas Faltantes)
-- 1.1 Tabla: positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS avg_entry_price        NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sl_price               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp_partial_price       NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp_full_price          NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS breakeven_activated    BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS breakeven_price        NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_15m              NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_4h               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_1d               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS confluence_score       SMALLINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sizing_multiplier      NUMERIC(4,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS liquidation_price      NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage               SMALLINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS funding_rate_accrued   NUMERIC(10,6) DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS market_type            VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS rule_code              VARCHAR(10);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS entry_bar_index        BIGINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS bars_held              INT DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS max_holding_bars       INT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_closed         BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_price    NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_usd      NUMERIC(10,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_at       TIMESTAMPTZ;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS entries                JSONB DEFAULT '[]'::jsonb;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS ema20_phase_entry      VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS adx_value_entry        NUMERIC(6,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS regime_entry           VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_usd      NUMERIC(10,4);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_pct       NUMERIC(8,4);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS close_reason           VARCHAR(50);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS close_bar_index        BIGINT;

-- 1.2 Tabla: orders
ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_price         NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS execution_price      NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS slippage_pct         NUMERIC(8,4);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type           VARCHAR(10);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS timeout_bars         SMALLINT DEFAULT 2;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fill_pct             NUMERIC(5,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS step_number          SMALLINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trade_n              SMALLINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS rule_code            VARCHAR(10);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_paper             BOOLEAN DEFAULT false;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS stop_price           NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS limit_price          NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS gap_pct              NUMERIC(5,3);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS expires_at_bar       BIGINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_reason     VARCHAR(50);

-- 1.3 Tabla: trading_signals
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS signal_bar_index    BIGINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS signal_age_bars     SMALLINT DEFAULT 0;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS expires_at_bar      BIGINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS is_expired          BOOLEAN DEFAULT false;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ema20_angle_raw     NUMERIC(8,4);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS plus_di             NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS minus_di            NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS fibonacci_zone      SMALLINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS regime              VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS mtf_score           NUMERIC(4,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS rr_real             NUMERIC(6,3);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_pattern          VARCHAR(50);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_sentiment        VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_recommendation   VARCHAR(10);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_agreed           BOOLEAN;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_confidence       NUMERIC(4,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS acted_upon          BOOLEAN DEFAULT false;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS blocked_reason      VARCHAR(100);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS is_paper            BOOLEAN DEFAULT false;

-- 1.4 Tabla: technical_indicators
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_angle_raw     NUMERIC(8,4);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_angle_pct     NUMERIC(5,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_was_flat      BOOLEAN;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_exit_flat_long  BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_exit_flat_short BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS adx                 NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS plus_di             NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS minus_di            NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS di_cross_bullish    BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS di_cross_bearish    BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS adx_rising          BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_ema             NUMERIC(20,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_slope_3         NUMERIC(8,4);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_decreasing      BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_increasing      BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_entry_ok        BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS fibonacci_zone      SMALLINT;
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
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS atr                 NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS atr_percentile      NUMERIC(5,1);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_value          NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_4c_type        SMALLINT;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_buy            BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_sell           BOOLEAN DEFAULT false;

-- 1.5 Tabla: market_candles
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS timeframe       VARCHAR(5);
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS is_closed       BOOLEAN DEFAULT true;
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS hlc3            NUMERIC(20,8);
CREATE INDEX IF NOT EXISTS idx_market_candles_timeframe_ts ON market_candles(timeframe, open_time DESC);
CREATE INDEX IF NOT EXISTS idx_market_candles_symbol_tf ON market_candles(symbol, timeframe, open_time DESC);

-- 1.6 Tabla: risk_config
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS flat_pct              NUMERIC(5,2);
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS peak_pct              NUMERIC(5,2);
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS di_cross_required     BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS min_nivel_entrada     SMALLINT DEFAULT 1;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_daily_loss_pct    NUMERIC(5,2) DEFAULT 5.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_trade_loss_pct    NUMERIC(5,2) DEFAULT 2.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS post_sl_bars          SMALLINT DEFAULT 3;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS post_tp_bars          SMALLINT DEFAULT 1;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_correlation       NUMERIC(4,2) DEFAULT 0.80;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS vol_entry_min_pct     NUMERIC(5,2) DEFAULT 70.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS order_type_default    VARCHAR(10)  DEFAULT 'LIMIT';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS limit_timeout_bars    SMALLINT DEFAULT 2;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS stop_limit_gap_pct    NUMERIC(5,3) DEFAULT 0.10;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS fee_pct               NUMERIC(5,4) DEFAULT 0.001;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_enabled     BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_atr_mult    NUMERIC(4,2) DEFAULT 2.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_action      VARCHAR(20)  DEFAULT 'pause';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS signal_max_age_bars   SMALLINT DEFAULT 3;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS ai_candles_enabled    BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS ai_candles_mode       VARCHAR(15) DEFAULT 'informative';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_holding_bars      JSONB DEFAULT '{"5m":96,"15m":48,"30m":48,"45m":32,"4h":30,"1d":14,"1w":8}'::jsonb;

-- 1.7 Tabla: trading_config
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS capital_total          NUMERIC(12,2) DEFAULT 500.00;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS pct_for_trading        NUMERIC(5,2)  DEFAULT 20.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS capital_operativo      NUMERIC(12,2);
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS buffer_pct             NUMERIC(5,2)  DEFAULT 10.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS trade_distribution     JSONB DEFAULT '{"3_trades":{"t1":20,"t2":30,"t3":50},"5_trades":{"t1":10,"t2":15,"t3":20,"t4":25,"t5":30}}'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS market_type            VARCHAR(20)   DEFAULT 'futures';
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS leverage               SMALLINT      DEFAULT 5;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS active_symbols         JSONB         DEFAULT '["BTCUSDT","ETHUSDT","SOLUSDT","ADAUSDT"]'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS mode                   VARCHAR(10)   DEFAULT 'paper';
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS retention_days         JSONB DEFAULT '{"5m":20,"15m":60,"30m":90,"45m":120,"4h":365,"1d":1095,"1w":2190}'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_enabled       BOOLEAN DEFAULT true;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_bot_token     TEXT;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_chat_id       TEXT;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS warmup_bars_required   INT DEFAULT 200;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS max_trade_loss_pct     NUMERIC(5,2)  DEFAULT 2.0;

-- 1.8 Tabla: paper_trades
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);
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
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS close_reason        VARCHAR(50);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS avg_entry_price     NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS entries             JSONB DEFAULT '[]'::jsonb;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS partial_pnl_usd     NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS full_pnl_usd        NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS total_pnl_usd       NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS total_pnl_pct       NUMERIC(8,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS fibonacci_zone_entry SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS market_type         VARCHAR(20);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS leverage            SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS liquidation_price   NUMERIC(20,8);

-- 1.9 Tabla: trading_rules
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS id                  BIGINT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS name                TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS description         TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS direction           VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS market_type         JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS ema50_vs_ema200     VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS enabled             BOOLEAN DEFAULT true;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS regime_allowed      JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS priority            INT DEFAULT 99;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS confidence          VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS entry_trades        JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS conditions          JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS logic               VARCHAR(5) DEFAULT 'AND';
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS notes               TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS version             INT DEFAULT 1;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS current             BOOLEAN DEFAULT true;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_trading_rules_active ON trading_rules(direction, enabled, current) WHERE enabled = true AND current = true;

-- 1.10 Tabla: market_regime
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS atr_percentile      NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS adx_risk_score      NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS volume_ratio        NUMERIC(6,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS volume_risk_score   NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS macro_trend         VARCHAR(10);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS macro_score         NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS mtf_threshold       NUMERIC(4,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS max_trades          SMALLINT;
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS emergency_active    BOOLEAN DEFAULT false;
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS emergency_atr_ratio NUMERIC(5,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS evaluated_at        TIMESTAMPTZ DEFAULT NOW();

-- 1.11 Tabla: alert_events
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS alert_type     VARCHAR(30);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS symbol         VARCHAR(20);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS timeframe      VARCHAR(5);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS severity       VARCHAR(10);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS telegram_sent  BOOLEAN DEFAULT false;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resolved       BOOLEAN DEFAULT false;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resolved_at    TIMESTAMPTZ;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS metadata       JSONB;

-- 1.12 Tabla: bot_state
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
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS mode                   VARCHAR(10) DEFAULT 'paper';


-- ==========================================================
-- PARTE 2: TABLAS NUEVAS
-- ==========================================================

CREATE TABLE IF NOT EXISTS reconciliation_log (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    timeframe           VARCHAR(5),
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    bot_state           JSONB,
    exchange_state      JSONB,
    discrepancy_type    VARCHAR(50),
    action_taken        VARCHAR(100),
    supabase_updated    BOOLEAN DEFAULT false,
    telegram_notified   BOOLEAN DEFAULT false,
    resolved            BOOLEAN DEFAULT false,
    resolved_at         TIMESTAMPTZ,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS symbol_health_checks (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    market_type         VARCHAR(20),
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    volume_24h          NUMERIC(20,2),
    spread_pct          NUMERIC(8,4),
    best_bid            NUMERIC(20,8),
    best_ask            NUMERIC(20,8),
    volume_ok           BOOLEAN,
    spread_ok           BOOLEAN,
    symbol_active       BOOLEAN,
    healthy             BOOLEAN,
    min_volume_usd      NUMERIC(20,2),
    max_spread_pct      NUMERIC(5,3),
    blocked_entry       BOOLEAN DEFAULT false,
    block_reason        TEXT
);

CREATE TABLE IF NOT EXISTS funding_rates (
    id                      BIGSERIAL PRIMARY KEY,
    symbol                  VARCHAR(20)     NOT NULL,
    rate                    NUMERIC(12,8)   NOT NULL,
    next_funding_time       TIMESTAMPTZ,
    checked_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    projected_cost_24h_pct  NUMERIC(10,6),
    projected_cost_24h_usd  NUMERIC(10,4),
    favorable_for_long      BOOLEAN,
    favorable_for_short     BOOLEAN,
    position_id             UUID REFERENCES positions(id) ON DELETE SET NULL,
    accrued_cost_usd        NUMERIC(10,4) DEFAULT 0,
    payments_count          SMALLINT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS slippage_log (
    id                  BIGSERIAL PRIMARY KEY,
    order_id            UUID REFERENCES orders(id) ON DELETE CASCADE,
    symbol              VARCHAR(20)     NOT NULL,
    market_type         VARCHAR(20),
    order_type          VARCHAR(10),
    side                VARCHAR(10),
    signal_price        NUMERIC(20,8)   NOT NULL,
    execution_price     NUMERIC(20,8)   NOT NULL,
    slippage_pct        NUMERIC(8,4)    NOT NULL,
    slippage_usd        NUMERIC(10,4),
    is_paper            BOOLEAN DEFAULT false,
    timestamp           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

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


-- ==========================================================
-- PARTE 3: SEED (TRADING RULES)
-- ==========================================================

INSERT INTO trading_rules
  (id, rule_code, name, description, direction, market_type, ema50_vs_ema200,
   enabled, regime_allowed, priority, confidence, entry_trades, conditions, logic, notes, version, current, created_at, updated_at)
VALUES
(1001, 'Aa13', 'LONG — EMA50 cruza basis (macro bajista)', 'EMA50 supera la VWMA (basis) en mercado macro bajista. Señal de cambio de tendencia local.', 'long', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]', '[{"indicator":"ema4_cross_basis_up","operator":"==","value":true},{"indicator":"pinescript_signal","operator":"==","value":"Buy"}]', 'AND', 'Al momento del cruce, comprar al primer Buy del PineScript', 1, true, NOW(), NOW()),
(1002, 'Aa12', 'LONG — Rebote desde lower_5/6 (macro bajista)', 'Precio tocó lower_5 o lower_6 con EMA20 girando positivo. Rebote desde sobreventa extrema.', 'long', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 2, 'medium', '[1]', '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"low_crossed_lower5_or_6","operator":"==","value":true},{"indicator":"reversal_confirmed","operator":"==","value":true}]', 'AND', 'Confirmación: is_dragonfly OR low_higher_than_prev', 1, true, NOW(), NOW()),
(1003, 'Aa11', 'LONG — EMA20 flat + ADX bajo + DI cruce (macro bajista)', 'Acumulación temprana. EMA20 positivo con ADX bajo y cruce alcista del DI.', 'long', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1]', '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"adx","operator":"<","value":20},{"indicator":"ema20_phase","operator":"==","value":"nivel_1_long"},{"indicator":"di_cross_bullish","operator":"==","value":true}]', 'AND', 'Solo régimen riesgo_medio o bajo_riesgo. Solo T1.', 1, true, NOW(), NOW()),
(1004, 'Aa24', 'LONG — EMA50 cruza basis + Nivel 1 (macro alcista)', 'EMA50 supera el basis VWMA con EMA20 en fase nivel_1_long. Entrada de alta confianza.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 1, 'high', '[1,2,3]', '[{"indicator":"ema4_cross_basis_up","operator":"==","value":true},{"indicator":"ema20_phase","operator":"==","value":"nivel_1_long"},{"indicator":"pinescript_signal","operator":"==","value":"Buy"}]', 'AND', 'Habilitar T2/T3 con condición precio decreciente', 1, true, NOW(), NOW()),
(1005, 'Aa22', 'LONG — EMA50 ascendente sobre basis (macro alcista)', 'EMA50 ángulo positivo Y precio del EMA50 sobre el basis VWMA.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]', '[{"indicator":"ema50_angle","operator":">=","value":0},{"indicator":"ema4_above_basis","operator":"==","value":true}]', 'AND', NULL, 1, true, NOW(), NOW()),
(1006, 'Aa23', 'LONG — EMA9 + EMA50 ascendentes (macro alcista)', 'Ambas EMAs dinámicas apuntan hacia arriba. Momentum de corto y mediano plazo alineados.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1]', '[{"indicator":"ema9_angle","operator":">=","value":0},{"indicator":"ema50_angle","operator":">=","value":0},{"indicator":"adx","operator":">=","value":"adx_min_config"}]', 'AND', 'adx_min_config viene del régimen activo', 1, true, NOW(), NOW()),
(1007, 'Aa21', 'LONG — EMA20 flat + ADX bajo cerca del basis (macro alcista)', 'Señal temprana en lateral. Solo válida muy cerca del basis.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["bajo_riesgo"]', 4, 'low', '[1]', '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"adx","operator":"<","value":20},{"indicator":"fibonacci_zone","operator":"between","value":[-2,2]},{"indicator":"close_vs_basis","operator":"<=","value":1.005}]', 'AND', 'Solo régimen bajo_riesgo. Solo T1.', 1, true, NOW(), NOW()),
(1008, 'Bb12', 'SHORT — EMA50 cruza basis hacia abajo (macro bajista)', 'EMA50 perfora el basis VWMA en mercado macro bajista. Señal de continuación bajista.', 'short', '["crypto_spot","crypto_futures"]', 'below', true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]', '[{"indicator":"ema4_cross_basis_down","operator":"==","value":true},{"indicator":"pinescript_signal","operator":"==","value":"Sell"}]', 'AND', 'Al momento del cruce, abrir SHORT al primer Sell del PineScript', 1, true, NOW(), NOW()),
(1009, 'Bb13', 'SHORT — EMA50 bajo basis + ADX + DI cruce (macro bajista)', 'Distribución temprana en consolidación. EMA50 ya bajo el basis con cruce bajista del DI.', 'short', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]', '[{"indicator":"ema4_below_basis","operator":"==","value":true},{"indicator":"adx","operator":"<","value":20},{"indicator":"ema20_phase","operator":"in","value":["flat","nivel_1_short"]},{"indicator":"di_cross_bearish","operator":"==","value":true},{"indicator":"ema20_angle_raw","operator":"<=","value":0}]', 'AND', NULL, 1, true, NOW(), NOW()),
(1010, 'Bb11', 'SHORT — ADX fuerte + Nivel 2 bajista (macro bajista)', 'Impulso bajista fuerte confirmado con ADX > 40 y fase nivel_2_short.', 'short', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1,2]', '[{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_short"},{"indicator":"di_spread","operator":">=","value":5}]', 'AND', 'di_spread = minus_di - plus_di >= 5 puntos', 1, true, NOW(), NOW()),
(1011, 'Bb22', 'SHORT — Agotamiento extremo en upper_6 (macro alcista)', 'HIGH cruzó upper_6 con ADX fuerte y EMA50 girando negativo. Reversal técnico en extremo Fibonacci.', 'short', '["crypto_spot","crypto_futures"]', 'above', true, '["riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]', '[{"indicator":"high_crossed_upper6","operator":"==","value":true},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_long"},{"indicator":"ema50_angle","operator":"<=","value":0},{"indicator":"reversal_candle_bearish","operator":"==","value":true}]', 'AND', 'reversal_candle_bearish = is_gravestone OR (is_red_candle AND high_in_upper6) OR high_lower_than_prev. RR mínimo forzado 3.0. Solo T1.', 1, true, NOW(), NOW()),
(1012, 'Bb23', 'SHORT — EMA50 cruza basis + EMA20 negativo (macro alcista)', 'EMA50 perfora el basis con EMA20 ya negativo. Señal más limpia de cambio en macro alcista.', 'short', '["crypto_spot","crypto_futures"]', 'above', true, '["riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]', '[{"indicator":"ema4_cross_basis_down","operator":"==","value":true},{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"pinescript_signal","operator":"==","value":"Sell"}]', 'AND', 'Al momento del cruce. RR mínimo del régimen activo.', 1, true, NOW(), NOW()),
(1013, 'Bb21', 'SHORT — ADX fuerte + Nivel 2 bajista (macro alcista)', 'Impulso bajista fuerte en mercado macro alcista. Alta selectividad.', 'short', '["crypto_spot","crypto_futures"]', 'above', true, '["bajo_riesgo"]', 3, 'medium', '[1]', '[{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_short"},{"indicator":"di_spread","operator":">=","value":10}]', 'AND', 'di_spread = minus_di - plus_di >= 10 puntos. Solo bajo_riesgo. RR mínimo 3.0. Solo T1.', 1, true, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    rule_code       = EXCLUDED.rule_code,
    name            = EXCLUDED.name,
    description     = EXCLUDED.description,
    conditions      = EXCLUDED.conditions,
    regime_allowed  = EXCLUDED.regime_allowed,
    confidence      = EXCLUDED.confidence,
    notes           = EXCLUDED.notes,
    version         = trading_rules.version + 1,
    updated_at      = NOW()
WHERE trading_rules.conditions != EXCLUDED.conditions;


-- ==========================================================
-- PARTE 4: ÍNDICES DE PERFORMANCE
-- ==========================================================

CREATE INDEX IF NOT EXISTS idx_reconciliation_symbol ON reconciliation_log(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_reconciliation_unresolved ON reconciliation_log(resolved, checked_at DESC) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_health_checks_symbol ON symbol_health_checks(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_checks_cleanup ON symbol_health_checks(checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol ON funding_rates(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time ON funding_rates(symbol, next_funding_time);
CREATE INDEX IF NOT EXISTS idx_slippage_symbol ON slippage_log(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_slippage_order_type ON slippage_log(order_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_technical_indicators_symbol_tf ON technical_indicators(symbol, timeframe, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(symbol, status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_trading_signals_active ON trading_signals(symbol, is_expired, acted_upon, created_at DESC) WHERE is_expired = false AND acted_upon = false;
CREATE INDEX IF NOT EXISTS idx_cooldowns_active ON cooldowns(symbol, active, expires_at) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_orders_pending ON orders(symbol, status, created_at DESC) WHERE status IN ('pending', 'partially_filled');
CREATE INDEX IF NOT EXISTS idx_funding_rates_latest ON funding_rates(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_trades_analysis ON paper_trades(rule_code, regime, close_reason, created_at DESC);
