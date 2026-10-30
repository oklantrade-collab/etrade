-- =========================================================================
-- MIGRACIÓN 041: RANKING POR VELOCIDAD (Velocity Score) + GATE DEL PLAYBOOK
-- Claves en stocks_config editables desde Settings / STOCKS
-- =========================================================================
INSERT INTO stocks_config (key, value, description, category, editable, value_type)
VALUES
  ('scanner_min_change_pct',  '3.0',    'Variación mínima del día (%) para aparecer en el escáner de velocidad', 'scanner', true, 'number'),
  ('scanner_min_rvol',        '1.5',    'RVOL mínimo para aparecer en el escáner de velocidad',                  'scanner', true, 'number'),
  ('scanner_min_adx_5m',      '20',     'ADX 5m mínimo (fuerza de tendencia corta)',                             'scanner', true, 'number'),
  ('scanner_min_volume',      '300000', 'Volumen mínimo acumulado del día',                                      'scanner', true, 'number'),
  ('scanner_min_dp5m_pct',    '0.0',    'ΔP mínimo últimos 5 min (%). Bajo este valor + EMA3<EMA9 5m = descendente', 'scanner', true, 'number'),
  ('velocity_w_rvol',         '0.35',   'Peso RVOL en Velocity Score',                                           'scanner', true, 'number'),
  ('velocity_w_adx',          '0.25',   'Peso ADX 5m en Velocity Score',                                         'scanner', true, 'number'),
  ('velocity_w_dp5m',         '0.30',   'Peso ΔP 5m en Velocity Score',                                          'scanner', true, 'number'),
  ('velocity_w_vol',          '0.10',   'Peso Volumen en Velocity Score',                                        'scanner', true, 'number'),
  ('scanner_refresh_seconds', '60',     'Refresco del ranking por velocidad (segundos, mínimo 15)',              'scanner', true, 'number'),
  ('velocity_gate_min_score', '10',     'Velocity Score mínimo vigente al momento del disparo de compra',        'scalping', true, 'number'),
  ('playbook_gate_mode',      'enforce','Gate Playbook Ross Cameron antes de comprar: enforce (bloquea+tamaño) | observe (solo registra)', 'scalping', true, 'select'),
  ('cold_market_spy_pct',     '-0.3',   'Mercado frío si SPY o QQQ varían menos que este % en el día',           'scalping', true, 'number')
ON CONFLICT (key) DO NOTHING;
