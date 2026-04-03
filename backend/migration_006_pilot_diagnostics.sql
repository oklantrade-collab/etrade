-- MIGRATION 006 — Pilot Diagnostics
-- Table to store high-detail logs for the first 48 hours of pilot run.

CREATE TABLE IF NOT EXISTS pilot_diagnostics (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp           TIMESTAMPTZ DEFAULT NOW(),
    symbol              VARCHAR(30) NOT NULL,
    regime_category     VARCHAR(20),
    risk_score          NUMERIC(6,2),
    ema20_phase         VARCHAR(30),
    adx                 NUMERIC(8,4),
    basis_15m           NUMERIC(20,8),
    basis_4h            NUMERIC(20,8),
    signal_pinescript   VARCHAR(10),
    rule_evaluated      VARCHAR(50),
    rule_triggered      VARCHAR(50),
    entry_blocked_by    TEXT,
    ai_recommendation   VARCHAR(20),
    full_market_data    JSONB,
    observe_only        BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_pilot_diag_ts ON pilot_diagnostics(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pilot_diag_sym ON pilot_diagnostics(symbol);

-- Enable realtime for the monitor dashboard
ALTER PUBLICATION supabase_realtime ADD TABLE pilot_diagnostics;
