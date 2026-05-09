-- ═══════════════════════════════════════════
-- VERIFICACIÓN — APEX Orchestrator
-- ═══════════════════════════════════════════

-- 1. Ver la cola de prioridad actual:
SELECT
    ticker,
    ROUND(apex_score_4h::numeric, 1)  AS apex_4h,
    ROUND(apex_score_1d::numeric, 1)  AS apex_1d,
    ROUND(composite_rank::numeric, 1) AS rank,
    ROUND(return_expected::numeric, 2) AS ret_exp,
    confidence,
    status,
    entry_reason,
    triggered_rule,
    is_overbought,
    ROUND(capital_assigned::numeric, 2) AS capital,
    entered_at
FROM stocks_priority_queue
ORDER BY composite_rank DESC
LIMIT 15;

-- 2. Ver precisión del APEX Orchestrator:
SELECT
    so.rule_code,
    COUNT(*)             AS compras,
    AVG(
      (sp.current_price - sp.avg_price)
      / sp.avg_price * 100
    )                    AS avg_return_pct,
    SUM(CASE
      WHEN sp.current_price > sp.avg_price
      THEN 1 ELSE 0 END)
      * 100.0 / COUNT(*) AS win_rate,
    AVG(spq.apex_score_4h) AS avg_apex_score
FROM stocks_orders so
JOIN stocks_positions sp
  ON sp.ticker = so.ticker
LEFT JOIN stocks_priority_queue spq
  ON spq.ticker = so.ticker
WHERE so.direction = 'buy'
  AND so.status IN ('filled','active')
GROUP BY so.rule_code
ORDER BY avg_return_pct DESC;

-- 3. Control de capital:
SELECT
    COUNT(*) AS posiciones_abiertas,
    SUM(shares * avg_price) AS total_invertido,
    AVG(shares * avg_price) AS avg_por_posicion
FROM stocks_positions
WHERE status = 'open';
