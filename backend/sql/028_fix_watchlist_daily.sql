-- eTrader v4.5 — Fix watchlist_daily schema
-- Adds missing columns required for advanced valuation display in the dashboard

ALTER TABLE watchlist_daily 
ADD COLUMN IF NOT EXISTS margin_of_safety NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS intrinsic_value NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_overvalued BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS analyst_rating NUMERIC DEFAULT 0;

COMMENT ON COLUMN watchlist_daily.margin_of_safety IS 'Margin of safety calculated by valuation engine (%)';
COMMENT ON COLUMN watchlist_daily.intrinsic_value IS 'Calculated intrinsic value for the ticker';
COMMENT ON COLUMN watchlist_daily.is_overvalued IS 'Flag indicating if current price is above intrinsic value';
COMMENT ON COLUMN watchlist_daily.analyst_rating IS 'IB/Yahoo Analyst consensus rating (1-10)';
