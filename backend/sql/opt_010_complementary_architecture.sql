-- ============================================================================
-- Migracion opt_010: Arquitectura Complementaria de Opciones
-- Salud, Control/Kill-Switch, Calendario de Eventos, Desglose de Score (Champion/Challenger),
-- Resultados ADUANA por regla, Libro Contrafactual y Ordenes Paper Multi-pata.
-- ============================================================================

-- 1. Salud del Sistema (Telemetria, p95 quote age, % stale, IBKR connection)
CREATE TABLE IF NOT EXISTS opt_system_health (
    id BIGSERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'NORMAL',  -- 'NORMAL' | 'DEGRADED' | 'HALTED'
    degraded_reasons JSONB DEFAULT '[]'::jsonb,
    p95_quote_age_sec NUMERIC(8,2) DEFAULT 0.0,
    stale_quotes_pct NUMERIC(5,2) DEFAULT 0.0,
    ibkr_connected BOOLEAN DEFAULT TRUE,
    consecutive_errors INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_sys_health_created ON opt_system_health(created_at DESC);

-- 2. Auditoria de Control y Kill-Switch
CREATE TABLE IF NOT EXISTS opt_control_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,              -- 'mode_change' | 'kill_switch_activated' | 'kill_switch_deactivated' | 'reconciliation_mismatch'
    old_state JSONB DEFAULT '{}'::jsonb,
    new_state JSONB DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL,
    triggered_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_control_events_created ON opt_control_events(created_at DESC);

-- 3. Calendario de Eventos Corporativos y Macro (Earnings, Dividendos, Macro FOMC/CPI)
CREATE TABLE IF NOT EXISTS opt_event_calendar (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,              -- 'earnings' | 'dividend' | 'macro_fomc' | 'split'
    event_time_utc TIMESTAMPTZ,
    source VARCHAR(50) NOT NULL DEFAULT 'hybrid', -- 'stocks_provider' | 'ib_scanner' | 'hybrid'
    verification_state VARCHAR(30) NOT NULL DEFAULT 'CLEAR_VERIFIED', -- 'CLEAR_VERIFIED' | 'EVENT_FOUND' | 'UNKNOWN' | 'STALE'
    details JSONB DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_event_cal_sym_checked ON opt_event_calendar(symbol, checked_at DESC);

-- 4. Puntuaciones y Componentes Desglosados (Champion vs Challenger)
CREATE TABLE IF NOT EXISTS opt_candidate_scores (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    score_version VARCHAR(50) NOT NULL,
    model_type VARCHAR(20) NOT NULL DEFAULT 'champion', -- 'champion' | 'challenger'
    score_total NUMERIC(6,2) NOT NULL,
    coverage NUMERIC(5,2) NOT NULL DEFAULT 1.0,
    components JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_cand_scores_cand_id ON opt_candidate_scores(candidate_id);

-- 5. Resultados de ADUANA por Regla Individual
CREATE TABLE IF NOT EXISTS opt_admission_results (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    rule_code VARCHAR(20) NOT NULL,               -- 'O-1'..'O-16'
    passed BOOLEAN NOT NULL,
    status_code VARCHAR(50) NOT NULL DEFAULT 'OK',
    detail TEXT,
    aduana_version VARCHAR(30) NOT NULL DEFAULT 'v2.0-comp',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_adm_res_cand_id ON opt_admission_results(candidate_id);

-- 6. Libro Contrafactual y Analitica Fuera de Muestra
CREATE TABLE IF NOT EXISTS opt_candidate_outcomes (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    book VARCHAR(30) NOT NULL DEFAULT 'counterfactual', -- 'selected_paper' | 'shadow' | 'counterfactual'
    symbol VARCHAR(20) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    entry_debit NUMERIC(10,4),
    entry_at TIMESTAMPTZ,
    exit_at TIMESTAMPTZ,
    pnl_gross NUMERIC(10,2),
    pnl_net NUMERIC(10,2),
    exit_reason VARCHAR(50),
    reconciled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_cand_outcomes_book ON opt_candidate_outcomes(book, symbol);

-- 7. Columnas adicionales en opt_candidates si no existen
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='ev_robust') THEN
        ALTER TABLE opt_candidates ADD COLUMN ev_robust BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='ev_range') THEN
        ALTER TABLE opt_candidates ADD COLUMN ev_range JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='greeks_net') THEN
        ALTER TABLE opt_candidates ADD COLUMN greeks_net JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='coverage') THEN
        ALTER TABLE opt_candidates ADD COLUMN coverage NUMERIC(5,2) DEFAULT 1.0;
    END IF;
END $$;
