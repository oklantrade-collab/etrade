-- ============================================================
-- eTrader v4.5 — STOCKS MODULE — Sprint 5 Migration
-- Creates all 10 tables required for the Stocks module
-- ============================================================

-- 1. WATCHLIST DIARIO (Capa 0: Universe Builder output)
CREATE TABLE IF NOT EXISTS watchlist_daily (
  id               SERIAL PRIMARY KEY,
  ticker           VARCHAR(10) NOT NULL,
  pool_type        VARCHAR(20),           -- core | tactical
  catalyst_score   INTEGER,
  catalyst_type    VARCHAR(50),
  market_regime    VARCHAR(20),
  hard_filter_pass BOOLEAN DEFAULT true,
  date             DATE DEFAULT CURRENT_DATE,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_watchlist_date ON watchlist_daily(date DESC, catalyst_score DESC);

-- 2. MARKET DATA 5M (OHLCV from yfinance / IB)
CREATE TABLE IF NOT EXISTS market_data_5m (
  id               SERIAL PRIMARY KEY,
  ticker           VARCHAR(10),
  timestamp        TIMESTAMPTZ,
  open             NUMERIC,
  high             NUMERIC,
  low              NUMERIC,
  close            NUMERIC,
  volume           BIGINT,
  rvol             NUMERIC,
  spread_pct       NUMERIC,
  slippage_est     NUMERIC,
  liquidity_score  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_mkt5m_ticker_ts ON market_data_5m(ticker, timestamp DESC);
-- Unique constraint for upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_mkt5m_upsert ON market_data_5m(ticker, timestamp);

-- 3. TECHNICAL SCORES (Capa 2 output)
CREATE TABLE IF NOT EXISTS technical_scores (
  id                SERIAL PRIMARY KEY,
  ticker            VARCHAR(10),
  timestamp         TIMESTAMPTZ,
  rsi_14            NUMERIC,
  atr_14            NUMERIC,
  bollinger_squeeze BOOLEAN,
  macd_signal       VARCHAR(20),
  ema_alignment     VARCHAR(20),
  rvol              NUMERIC,
  fib_level         VARCHAR(20),
  mtf_confirmed     BOOLEAN,
  technical_score   NUMERIC,
  signals_json      JSONB
);
CREATE INDEX IF NOT EXISTS idx_techscores_ticker_ts ON technical_scores(ticker, timestamp DESC);

-- 4. FUNDAMENTAL CACHE (Capa 3 output — refreshed periodically)
CREATE TABLE IF NOT EXISTS fundamental_cache (
  id                   SERIAL PRIMARY KEY,
  ticker               VARCHAR(10) UNIQUE,
  valuation_mode       VARCHAR(5),          -- A (value) | B (growth)
  intrinsic_value      NUMERIC,
  current_price        NUMERIC,
  margin_of_safety     NUMERIC,
  valuation_status     VARCHAR(30),
  fundamental_score    NUMERIC,
  mode_b_metrics_json  JSONB,
  confidence           VARCHAR(20),
  refreshed_at         TIMESTAMPTZ DEFAULT NOW()
);

-- 5. CONTEXT SCORES (Capa 4 output — Gemini + Grok)
CREATE TABLE IF NOT EXISTS context_scores (
  id                SERIAL PRIMARY KEY,
  ticker            VARCHAR(10),
  date              DATE DEFAULT CURRENT_DATE,
  catalyst_score    INTEGER,
  catalyst_type     VARCHAR(50),
  sentiment_score   NUMERIC,
  narrative         TEXT,
  context_score     NUMERIC,
  regime_adjustment NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_ctx_ticker_date ON context_scores(ticker, date DESC);

-- 6. TRADE OPPORTUNITIES (Capa 5 output — Claude decisions)
CREATE TABLE IF NOT EXISTS trade_opportunities (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker           VARCHAR(10) NOT NULL,
  meta_score       NUMERIC,
  risk_score       NUMERIC,
  trade_type       VARCHAR(20),          -- swing_trade | scalping | wait | no_trade
  quadrant         VARCHAR(5),           -- A | B | C | D
  entry_zone_low   NUMERIC,
  entry_zone_high  NUMERIC,
  stop_loss        NUMERIC,
  target_1         NUMERIC,
  target_2         NUMERIC,
  capital_usd      NUMERIC,
  shares           INTEGER,
  rr_ratio         NUMERIC,
  status           VARCHAR(20) DEFAULT 'pending',  -- pending | confirmed | rejected
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opp_status ON trade_opportunities(status, created_at DESC);

-- 7. TRADES ACTIVE (positions currently open)
CREATE TABLE IF NOT EXISTS trades_active (
  id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  opportunity_id        UUID REFERENCES trade_opportunities(id),
  ticker                VARCHAR(10),
  entry_price           NUMERIC,
  entry_time            TIMESTAMPTZ,
  shares                INTEGER,
  stop_loss             NUMERIC,
  target_1              NUMERIC,
  target_2              NUMERIC,
  trailing_stop_active  BOOLEAN DEFAULT false,
  current_price         NUMERIC,
  unrealized_pnl        NUMERIC,
  status                VARCHAR(20) DEFAULT 'active'
);

-- 8. TRADES JOURNAL (Capa 7 — closed trades history)
CREATE TABLE IF NOT EXISTS trades_journal (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker           VARCHAR(10),
  entry_date       TIMESTAMPTZ,
  exit_date        TIMESTAMPTZ,
  trade_type       VARCHAR(20),
  valuation_mode   VARCHAR(5),
  entry_price      NUMERIC,
  exit_price       NUMERIC,
  shares           INTEGER,
  slippage_actual  NUMERIC,
  meta_score       NUMERIC,
  risk_score       NUMERIC,
  pnl_usd          NUMERIC,
  pnl_pct          NUMERIC,
  result           VARCHAR(20),         -- win | loss | breakeven
  exit_reason      VARCHAR(50),
  market_regime    VARCHAR(20),
  catalyst_type    VARCHAR(50)
);
CREATE INDEX IF NOT EXISTS idx_journal_exit ON trades_journal(exit_date DESC);

-- 9. PERFORMANCE METRICS (rolling daily aggregation)
CREATE TABLE IF NOT EXISTS performance_metrics (
  id                    SERIAL PRIMARY KEY,
  date                  DATE DEFAULT CURRENT_DATE,
  win_rate_overall      NUMERIC,
  win_rate_swing_a      NUMERIC,
  win_rate_scalping_c   NUMERIC,
  avg_rr_achieved       NUMERIC,
  avg_slippage_actual   NUMERIC,
  sharpe_rolling_20     NUMERIC,
  regime                VARCHAR(20),
  trades_count          INTEGER
);

-- 10. STOCKS CONFIG (system parameters — editable via UI)
CREATE TABLE IF NOT EXISTS stocks_config (
  id          SERIAL PRIMARY KEY,
  key         VARCHAR(100) UNIQUE,
  value       TEXT,
  description TEXT,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Default Configuration ──
INSERT INTO stocks_config (key, value, description) VALUES
  ('total_capital_usd',           '5000',    'Capital total asignado al módulo Stocks'),
  ('max_pct_per_trade',           '20',      'Max % del capital por trade'),
  ('min_pct_per_trade',           '10',      'Min % del capital por trade'),
  ('max_simultaneous_positions',  '3',       'Max posiciones abiertas simultáneamente'),
  ('max_stock_price',             '50',      'Precio máximo de acción (hard filter)'),
  ('min_daily_volume',            '500000',  'Volumen mínimo diario en acciones'),
  ('min_market_cap_usd',          '300000000','Market cap mínimo ($300M)'),
  ('meta_score_threshold',        '70',      'Meta-Score mínimo para llamar Claude'),
  ('technical_score_threshold',   '60',      'Technical Score mínimo para Capas 3+4'),
  ('mtf_confirmation_required',   '4',       'Timeframes confirmando (de 5)'),
  ('risk_score_max_trade',        '8',       'Risk Score max — 9-10 = no trade'),
  ('scalping_max_capital_pct',    '10',      'Max % capital para Quad C (scalping)'),
  ('swing_atr_multiplier',        '2.0',     'Multiplicador ATR para SL swing'),
  ('scalping_atr_multiplier',     '1.0',     'Multiplicador ATR para SL scalping'),
  ('rvol_spike_threshold',        '2.5',     'RVOL multiplicador para Volume Spike'),
  ('slippage_max_reject',         '0.5',     'Max slippage % — rechazar si mayor'),
  ('paper_mode_active',           'true',    'Modo paper trading activo'),
  ('kill_switch_active',          'false',   'Emergency stop — detiene todo'),
  ('bear_capital_reduction_pct',  '30',      '% reducción capital en Bear'),
  ('vix_bear_threshold',          '25',      'VIX > 25 → Bear Market'),
  ('vix_bull_threshold',          '18',      'VIX < 18 → Bull Market'),
  ('watchlist_core_count',        '30',      'Tickers core estables'),
  ('scan_interval_minutes',       '5',       'Frecuencia worker en mercado'),
  ('premarket_scan_start',        '09:00',   'Inicio scan pre-market (ET)'),
  ('market_open',                 '09:30',   'Apertura mercado (ET)'),
  ('market_close',                '16:00',   'Cierre mercado (ET)')
ON CONFLICT (key) DO NOTHING;

-- ── Verification ──
SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public'
  AND table_name IN (
    'watchlist_daily', 'market_data_5m', 'technical_scores',
    'fundamental_cache', 'context_scores', 'trade_opportunities',
    'trades_active', 'trades_journal', 'performance_metrics',
    'stocks_config'
  )
ORDER BY table_name;
-- Expected: 10 rows
