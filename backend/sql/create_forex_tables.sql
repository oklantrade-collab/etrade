-- ════════════════════════════════════════════════
-- Forex Execution Service — Tablas de Posiciones
-- ════════════════════════════════════════════════

-- Posiciones Forex abiertas/cerradas
CREATE TABLE IF NOT EXISTS forex_positions (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol           VARCHAR(10) NOT NULL,
    side             VARCHAR(10) NOT NULL,          -- 'long' | 'short'
    lots             NUMERIC NOT NULL,
    entry_price      NUMERIC NOT NULL,
    sl_price         NUMERIC,
    tp_price         NUMERIC,
    current_price    NUMERIC,
    unrealized_pnl   NUMERIC DEFAULT 0,
    pips_pnl         NUMERIC DEFAULT 0,
    rule_code        VARCHAR(20),
    ctrader_order_id BIGINT,
    ctrader_pos_id   BIGINT,
    status           VARCHAR(20) DEFAULT 'open',    -- open | closed | pending
    opened_at        TIMESTAMPTZ DEFAULT NOW(),
    closed_at        TIMESTAMPTZ,
    close_reason     VARCHAR(50),                   -- sl | tp | sar_phase_change | max_holding | manual
    pnl_usd          NUMERIC DEFAULT 0,
    pnl_pips         NUMERIC DEFAULT 0,
    market_type      VARCHAR(30) DEFAULT 'forex_futures',
    mode             VARCHAR(20) DEFAULT 'paper'    -- paper | live
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_forex_positions_symbol
    ON forex_positions(symbol, status);

CREATE INDEX IF NOT EXISTS idx_forex_positions_status
    ON forex_positions(status);

-- Órdenes Forex (LIMIT/STOP orders)
CREATE TABLE IF NOT EXISTS forex_orders (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol           VARCHAR(10) NOT NULL,
    order_type       VARCHAR(10) NOT NULL,          -- 'market' | 'limit' | 'stop'
    side             VARCHAR(10) NOT NULL,
    lots             NUMERIC NOT NULL,
    limit_price      NUMERIC,
    sl_price         NUMERIC,
    tp_price         NUMERIC,
    rule_code        VARCHAR(20),
    status           VARCHAR(20) DEFAULT 'pending', -- pending | filled | cancelled | expired
    ctrader_order_id BIGINT,
    filled_price     NUMERIC,
    filled_at        TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Verificar creación
SELECT table_name
FROM information_schema.tables
WHERE table_name IN ('forex_positions', 'forex_orders');
