-- APEX Score v1.0 — Migration 005

CREATE TABLE IF NOT EXISTS apex_scores (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker          VARCHAR(10) NOT NULL,
    calculated_at   TIMESTAMPTZ DEFAULT NOW(),
    price_at_calc   NUMERIC,
    b1_momentum     NUMERIC,
    b2_technical    NUMERIC,
    b3_fundamental  NUMERIC,
    b4_regime       NUMERIC,
    b5_sentiment    NUMERIC,
    apex_score_4h   NUMERIC,
    apex_score_1d   NUMERIC,
    return_expected_4h NUMERIC,
    return_expected_1d NUMERIC,
    confidence      VARCHAR(10),
    regime_type     VARCHAR(30),
    edge_pct        NUMERIC,
    scenario_bull   JSONB,
    scenario_base   JSONB,
    scenario_bear   JSONB,
    detail          JSONB,
    valid_until_4h  TIMESTAMPTZ,
    valid_until_1d  TIMESTAMPTZ,
    actual_return_4h  NUMERIC DEFAULT NULL,
    actual_return_1d  NUMERIC DEFAULT NULL,
    prediction_correct BOOLEAN DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_apex_ticker_date
    ON apex_scores(ticker, calculated_at DESC);

-- Vista de precisión del modelo APEX
CREATE OR REPLACE VIEW apex_accuracy AS
SELECT
    CASE
        WHEN apex_score_4h >= 75 THEN 'STRONG_BUY'
        WHEN apex_score_4h >= 60 THEN 'BUY'
        WHEN apex_score_4h >= 45 THEN 'NEUTRAL'
        ELSE 'AVOID'
    END AS signal,
    COUNT(*) AS predicciones,
    SUM(CASE WHEN prediction_correct THEN 1 ELSE 0 END)
        * 100.0 / COUNT(*) AS precision_pct,
    AVG(actual_return_4h) AS avg_return_real,
    AVG(apex_score_4h) AS avg_apex_score
FROM apex_scores
WHERE prediction_correct IS NOT NULL
GROUP BY signal
ORDER BY avg_apex_score DESC;
