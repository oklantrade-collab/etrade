-- MIGRATION 014: signals_log — Auditoría de señales detectadas (Ejecutadas y Bloqueadas)
-- eTrade v4 | Marzo 2026

CREATE TABLE IF NOT EXISTS signals_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(10) NOT NULL,
    rule_code       VARCHAR(10),
    price           NUMERIC(20,8),
    score_final     NUMERIC(8,4),
    acted_on        BOOLEAN DEFAULT false,
    reason_skip     TEXT,
    metadata        JSONB,
    detected_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_log_symbol_ts ON signals_log(symbol, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_log_acted_on ON signals_log(acted_on, detected_at DESC);

-- Habilitar tiempo real
ALTER PUBLICATION supabase_realtime ADD TABLE signals_log;
