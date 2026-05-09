-- ═══════════════════════════════════════════════════════
-- APEX Orchestrator — Priority Queue & Config
-- eTrader v5.0 — Migration 007
-- ═══════════════════════════════════════════════════════

-- Cola de Alta Prioridad (dinámica)
CREATE TABLE IF NOT EXISTS stocks_priority_queue (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker          VARCHAR(10) NOT NULL,
    group_name      VARCHAR(30),

    -- APEX Score
    apex_score_4h   NUMERIC NOT NULL,
    apex_score_1d   NUMERIC NOT NULL,
    return_expected NUMERIC,
    confidence      VARCHAR(10),

    -- Composite Rank (métrica de orden única)
    composite_rank  NUMERIC NOT NULL,

    -- Estado en la cola
    status          VARCHAR(20) DEFAULT 'pending',
    -- pending | buying | owned | blocked | watching

    -- Razón de entrada a la cola
    entry_reason    VARCHAR(50),
    triggered_rule  VARCHAR(30),

    -- Anti-sobrecompra
    is_overbought   BOOLEAN DEFAULT false,
    rsi_at_entry    NUMERIC,
    fib_zone        INTEGER,

    -- Capital asignado
    capital_assigned NUMERIC DEFAULT 0,
    shares_target    INTEGER DEFAULT 0,
    price_at_rank    NUMERIC,

    -- Timestamps
    entered_at      TIMESTAMPTZ DEFAULT NOW(),
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    bought_at       TIMESTAMPTZ,
    exited_at       TIMESTAMPTZ,

    -- Solo 1 entrada activa por ticker
    UNIQUE(ticker, status)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_pq_rank
    ON stocks_priority_queue(composite_rank DESC, status);

-- Agregar a stocks_config los nuevos parámetros
INSERT INTO stocks_config (key, value, description, category, editable, value_type)
VALUES
    ('max_total_risk_pct', '30',
     'Max. Tot Riesgo Inv. (% del capital base)', 'capital', true, 'number'),
    ('pct_per_operation', '10',
     '% Inversión por Operación del capital base', 'capital', true, 'number'),
    ('apex_min_score', '60',
     'Score mínimo APEX para Alta Prioridad (%)', 'apex', true, 'number'),
    ('apex_max_overbought_rsi', '75',
     'RSI máximo para considerar compra', 'apex', true, 'number'),
    ('apex_max_fib_zone', '3',
     'Banda Fibonacci máxima para compra (1-6)', 'apex', true, 'number'),
    ('apex_lock_cycles', '3',
     'Ciclos de 15m bloqueados después de compra', 'apex', true, 'number'),
    ('apex_composite_w_4h', '0.40',
     'Peso APEX 4H en Composite Rank', 'apex', true, 'number'),
    ('apex_composite_w_1d', '0.30',
     'Peso APEX 1D en Composite Rank', 'apex', true, 'number'),
    ('apex_composite_w_gain', '0.20',
     'Peso ganancia proyectada en Composite Rank', 'apex', true, 'number'),
    ('apex_composite_w_conf', '0.10',
     'Peso confianza en Composite Rank', 'apex', true, 'number'),
    ('apex_proportional_sizing', 'true',
     'Sizing proporcional al Composite Rank', 'apex', true, 'boolean'),
    ('apex_max_positions', '5',
     'Máximo de posiciones abiertas simultáneas', 'apex', true, 'number')
ON CONFLICT (key) DO NOTHING;
