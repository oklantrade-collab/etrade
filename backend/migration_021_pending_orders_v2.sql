DROP TABLE IF EXISTS pending_orders;

CREATE TABLE IF NOT EXISTS pending_orders (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol        VARCHAR(20)    NOT NULL,
    direction     VARCHAR(10)    NOT NULL,
    order_type    VARCHAR(10)    DEFAULT 'limit',
    trade_type    VARCHAR(10)    DEFAULT 'swing',
    rule_code     VARCHAR(10),
    limit_price   NUMERIC(20,8),
    sl_price      NUMERIC(20,8),
    tp1_price     NUMERIC(20,8),
    tp2_price     NUMERIC(20,8),
    band_name     VARCHAR(20),
    basis_slope   NUMERIC(10,6), -- pendiente basis al crear
    status        VARCHAR(20)    DEFAULT 'pending',
    mode          VARCHAR(10)    DEFAULT 'paper',
    created_at    TIMESTAMPTZ    DEFAULT NOW(),
    updated_at    TIMESTAMPTZ    DEFAULT NOW(),
    triggered_at  TIMESTAMPTZ,
    cancelled_at  TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ,   -- TTL opcional
    version       INTEGER        DEFAULT 1
);

-- Index para búsqueda rápida en ciclo de 5m
CREATE INDEX IF NOT EXISTS idx_pending_orders_symbol ON pending_orders(symbol, status);
