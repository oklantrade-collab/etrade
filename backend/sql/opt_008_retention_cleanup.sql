-- ============================================================
-- eTrader APEX Options - migracion opt_008 (Limpieza y Retención Free Tier)
-- Protege el límite de 500 MB de disco y optimiza Egress en Supabase Free.
-- ============================================================

-- 1. Índices para acelerar el purgado sin bloqueos de tabla
CREATE INDEX IF NOT EXISTS idx_opt_snapshots_captured_at ON opt_snapshots (captured_at);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_status_created ON opt_candidates (eligibility_status, created_at);
CREATE INDEX IF NOT EXISTS idx_opt_aduana_created_at ON opt_aduana_decisions (created_at);

-- 2. Función de mantenimiento para purga periódica
CREATE OR REPLACE FUNCTION cleanup_options_data(
    p_snapshots_days INTEGER DEFAULT 7,
    p_candidates_days INTEGER DEFAULT 3,
    p_jobs_days INTEGER DEFAULT 14
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_snaps   INTEGER := 0;
    deleted_cands   INTEGER := 0;
    deleted_aduanas INTEGER := 0;
    deleted_jobs    INTEGER := 0;
    result          JSONB;
BEGIN
    -- A. Purgar snapshots antiguos (default: más de 7 días)
    -- Los precios vigentes se conservan intactos en opt_quotes_latest
    DELETE FROM opt_snapshots
    WHERE captured_at < NOW() - (p_snapshots_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_snaps = ROW_COUNT;

    -- B. Purgar candidatas descartadas o expiradas (default: más de 3 días)
    -- NUNCA se eliminan candidatas con estado 'selected' o con trades paper asociados
    DELETE FROM opt_candidates
    WHERE eligibility_status IN ('rejected', 'expired')
      AND created_at < NOW() - (p_candidates_days || ' days')::INTERVAL
      AND NOT EXISTS (
          SELECT 1 FROM opt_paper_trades pt WHERE pt.candidate_id = opt_candidates.id
      );
    GET DIAGNOSTICS deleted_cands = ROW_COUNT;

    -- C. Purgar decisiones ADUANA huérfanas o de candidatas descartadas (> 7 días)
    DELETE FROM opt_aduana_decisions
    WHERE created_at < NOW() - INTERVAL '7 days'
      AND (candidate_id IS NULL OR NOT EXISTS (
          SELECT 1 FROM opt_candidates oc WHERE oc.id = opt_aduana_decisions.candidate_id AND oc.eligibility_status = 'selected'
      ));
    GET DIAGNOSTICS deleted_aduanas = ROW_COUNT;

    -- D. Purgar jobs antiguos completados o con error (> 14 días)
    DELETE FROM opt_jobs
    WHERE status IN ('done', 'error')
      AND created_at < NOW() - (p_jobs_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_jobs = ROW_COUNT;

    result := jsonb_build_object(
        'deleted_snapshots', deleted_snaps,
        'deleted_candidates', deleted_cands,
        'deleted_aduana_decisions', deleted_aduanas,
        'deleted_jobs', deleted_jobs,
        'cleaned_at', NOW()
    );

    RETURN result;
END;
$$;

-- 3. Programación automática con pg_cron (si está habilitado en el proyecto Supabase)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        -- Eliminar schedule previo si existe para evitar duplicación
        BEGIN
            PERFORM cron.unschedule(jobid) FROM cron.job WHERE jobname = 'opt-daily-cleanup';
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
        -- Programar ejecución todos los días a las 03:00 UTC
        PERFORM cron.schedule('opt-daily-cleanup', '0 3 * * *', 'SELECT cleanup_options_data(7, 3, 14);');
    END IF;
EXCEPTION WHEN OTHERS THEN
    -- Si no hay permisos de superusuario para cron, el worker o backend lo ejecuta vía RPC
    NULL;
END;
$$;

-- ROLLBACK:
-- DROP FUNCTION IF EXISTS cleanup_options_data(INTEGER, INTEGER, INTEGER);
-- DROP INDEX IF EXISTS idx_opt_aduana_created_at;
-- DROP INDEX IF EXISTS idx_opt_candidates_status_created;
-- DROP INDEX IF EXISTS idx_opt_snapshots_captured_at;
