-- migration_019_sar_15m.sql
ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS sar_15m       NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS sar_trend_15m SMALLINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS sar_ini_high_15m BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS sar_ini_low_15m  BOOLEAN DEFAULT false;

INSERT INTO trading_rules (
    id, rule_code, name, direction,
    market_type, enabled, regime_allowed,
    priority, confidence, version
) VALUES
(1014, 'Cc21', 'LONG SAR scalp — SAR 15m + 4h + PineScript', 'long', 'futures', true, 'all', 1, 0.70, 1),
(1015, 'Cc11', 'SHORT SAR scalp — SAR 15m + 4h + PineScript', 'short', 'futures', true, 'all', 1, 0.70, 1)
ON CONFLICT (id) DO NOTHING;
