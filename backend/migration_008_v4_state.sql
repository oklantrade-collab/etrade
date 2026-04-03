-- MIGRATION 008 — v4 Memory-First Position Management
-- Table to store current operational state (WARM data) for v4 bot.
-- Mirrors BOT_STATE.positions from Python memory.

CREATE TABLE IF NOT EXISTS bot_state (
    symbol              VARCHAR(30) PRIMARY KEY,
    side                VARCHAR(10),
    avg_entry_price     NUMERIC(20,8),
    total_usd           NUMERIC(20,8),
    sl_price            NUMERIC(20,8),
    tp_partial          NUMERIC(20,8), -- upper_5
    tp_full             NUMERIC(20,8), -- upper_6
    is_open             BOOLEAN DEFAULT false,
    breakeven_active    BOOLEAN DEFAULT false,
    entries             JSONB DEFAULT '[]', -- List of {trade_n, price, usd_amount, timestamp, rule_code}
    last_updated        TIMESTAMPTZ DEFAULT NOW()
);

-- Table for circuit breaker and global state
CREATE TABLE IF NOT EXISTS bot_global_state (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    circuit_triggered   BOOLEAN DEFAULT false,
    daily_pnl           NUMERIC(20,8) DEFAULT 0.0,
    last_reset          DATE DEFAULT CURRENT_DATE,
    emergency_mode      BOOLEAN DEFAULT false,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT singleton CHECK (id = 1)
);

-- Log table for closed trades (COLD data)
CREATE TABLE IF NOT EXISTS trades_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol              VARCHAR(30) NOT NULL,
    side                VARCHAR(10) NOT NULL,
    entries             JSONB NOT NULL,
    exit_price          NUMERIC(20,8),
    exit_reason         VARCHAR(30),
    realized_pnl        NUMERIC(20,8),
    roi_pct             NUMERIC(10,4),
    opened_at           TIMESTAMPTZ NOT NULL,
    closed_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Realtime for bot_state to allow dashboard updates
ALTER PUBLICATION supabase_realtime ADD TABLE bot_state;
ALTER PUBLICATION supabase_realtime ADD TABLE bot_global_state;
