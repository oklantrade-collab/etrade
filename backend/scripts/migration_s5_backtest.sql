ALTER TABLE backtest_runs 
  ADD COLUMN IF NOT EXISTS status varchar(20) DEFAULT 'running',
  ADD COLUMN IF NOT EXISTS error_message text,
  ADD COLUMN IF NOT EXISTS equity_curve jsonb;
