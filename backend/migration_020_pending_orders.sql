CREATE TABLE IF NOT EXISTS pending_orders (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) DEFAULT 'binance',
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) DEFAULT 'LIMIT',
    price NUMERIC(20,8) NOT NULL,
    size NUMERIC(20,8) NOT NULL,
    rule_code VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending', 
    external_order_id VARCHAR(100), 
    cycle_type VARCHAR(10), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    expires_at TIMESTAMP WITH TIME ZONE
);
