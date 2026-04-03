CREATE TABLE IF NOT EXISTS market_snapshot (
    symbol           VARCHAR(20)  PRIMARY KEY,
    price            NUMERIC(20,8),
    fibonacci_zone   SMALLINT,
    basis            NUMERIC(20,8),
    upper_5          NUMERIC(20,8),
    upper_6          NUMERIC(20,8),
    lower_5          NUMERIC(20,8),
    lower_6          NUMERIC(20,8),
    dist_basis_pct   NUMERIC(8,4),
    mtf_score        NUMERIC(5,4),
    ema20_phase      VARCHAR(20),
    adx              NUMERIC(8,4),
    regime           VARCHAR(20),
    risk_score       NUMERIC(5,1),
    spike_detected   BOOLEAN      DEFAULT false,
    spike_ratio      NUMERIC(8,4),
    spike_direction  VARCHAR(15),
    updated_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- Habilitar Realtime para que el frontend reciba
-- actualizaciones instantáneas cada ciclo de 15m
ALTER PUBLICATION supabase_realtime
    ADD TABLE market_snapshot;
