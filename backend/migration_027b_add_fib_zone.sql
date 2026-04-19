-- Add fibonacci_zone column to candle_signals table
ALTER TABLE candle_signals ADD COLUMN IF NOT EXISTS fib_zone INT DEFAULT 0;
COMMENT ON COLUMN candle_signals.fib_zone IS 'Fibonacci band zone at signal time (-6 to +6)';
