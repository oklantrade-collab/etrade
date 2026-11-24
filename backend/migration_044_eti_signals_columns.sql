-- Blindaje Operativo V4.1: Alinear esquema de eti_signals con eti_storage.py
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS signal_id TEXT;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS cadence TEXT;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS asset_class TEXT;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb;
ALTER TABLE eti_signals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
CREATE UNIQUE INDEX IF NOT EXISTS uq_eti_signals_signal_id ON eti_signals(signal_id);
