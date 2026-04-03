-- SPRINT 5: Backtest Engine Schema Fix
ALTER TABLE backtest_runs 
  ADD COLUMN IF NOT EXISTS status varchar(20) DEFAULT 'running',
  ADD COLUMN IF NOT EXISTS error_message text,
  ADD COLUMN IF NOT EXISTS equity_curve jsonb,
  ADD COLUMN IF NOT EXISTS winning_trades int DEFAULT 0,
  ADD COLUMN IF NOT EXISTS losing_trades int DEFAULT 0,
  ADD COLUMN IF NOT EXISTS avg_trade_duration_hrs float DEFAULT 0;
