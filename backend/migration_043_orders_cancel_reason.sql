-- Blindaje de Ejecución de Órdenes V4: trazabilidad de motivos de cancelación/rechazo en stocks_orders
ALTER TABLE stocks_orders ADD COLUMN IF NOT EXISTS cancel_reason TEXT;
