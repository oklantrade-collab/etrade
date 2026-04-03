
-- TABLA 1: Variables del sistema
CREATE TABLE IF NOT EXISTS strategy_variables (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(50)  UNIQUE NOT NULL,
    category     VARCHAR(20)  NOT NULL,
    timeframes   TEXT[],
    data_type    VARCHAR(20),
    description  TEXT,
    source_field VARCHAR(100),
    enabled      BOOLEAN DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- TABLA 2: Condiciones
CREATE TABLE IF NOT EXISTS strategy_conditions (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    variable_id    INTEGER REFERENCES strategy_variables(id),
    operator       VARCHAR(20)  NOT NULL,
    value_type     VARCHAR(20)  NOT NULL,
    value_literal  NUMERIC,
    value_variable VARCHAR(50),
    value_list     TEXT[],
    value_min      NUMERIC,
    value_max      NUMERIC,
    timeframe      VARCHAR(10),
    description    TEXT,
    enabled        BOOLEAN DEFAULT true,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- TABLA 3: Reglas v2
CREATE TABLE IF NOT EXISTS strategy_rules_v2 (
    id                  SERIAL PRIMARY KEY,
    rule_code           VARCHAR(20) UNIQUE NOT NULL,
    name                VARCHAR(200) NOT NULL,
    strategy_type       VARCHAR(20)  NOT NULL,
    direction           VARCHAR(10)  NOT NULL,
    cycle               VARCHAR(10)  NOT NULL,
    condition_ids       INTEGER[]    NOT NULL,
    condition_logic     TEXT         DEFAULT 'AND',
    min_score           NUMERIC      DEFAULT 0.60,
    condition_weights   JSONB,
    market_types        TEXT[]       DEFAULT '{crypto_futures}',
    enabled             BOOLEAN      DEFAULT true,
    priority            INTEGER      DEFAULT 1,
    confidence          NUMERIC      DEFAULT 0.70,
    version             INTEGER      DEFAULT 1,
    notes               TEXT,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- TABLA 4: Log de evaluaciones
CREATE TABLE IF NOT EXISTS strategy_evaluations (
    id          UUID    DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    rule_code   VARCHAR(20) NOT NULL,
    cycle       VARCHAR(10),
    direction   VARCHAR(10),
    score       NUMERIC,
    triggered   BOOLEAN,
    context     JSONB,
    conditions  JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_strat_eval_symbol ON strategy_evaluations(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strat_eval_triggered ON strategy_evaluations(triggered, created_at DESC);

-- INSERTAR VARIABLES
INSERT INTO strategy_variables (id, name, category, timeframes, data_type, description, source_field)
VALUES
(1,  'price',           'price',       '{5m,15m,4h}', 'float', 'Precio actual de mercado', 'price'),
(2,  'dist_basis_pct',  'price',       '{5m,15m,4h}', 'float', '% distancia desde el BASIS', 'dist_basis_pct'),
(3,  'adx',             'statistical', '{5m,15m,4h}', 'float', 'ADX (0-100)', 'adx'),
(4,  'adx_plus_di',     'statistical', '{5m,15m,4h}', 'float', '+DI presión compradora', 'plus_di'),
(5,  'adx_minus_di',    'statistical', '{5m,15m,4h}', 'float', '-DI presión vendedora', 'minus_di'),
(6,  'adx_velocity',    'system',      '{5m,15m,4h}', 'string', 'Velocidad mercado (debil/moderado/agresivo/explosivo)', 'adx_velocity'),
(7,  'ema3',            'ema',         '{5m,15m,4h}', 'float', 'EMA 3 períodos', 'ema3'),
(8,  'ema9',            'ema',         '{5m,15m,4h}', 'float', 'EMA 9 períodos', 'ema9'),
(9,  'ema20',           'ema',         '{5m,15m,4h}', 'float', 'EMA 20 períodos', 'ema20'),
(10, 'ema50',           'ema',         '{5m,15m,4h}', 'float', 'EMA 50 períodos', 'ema50'),
(11, 'ema200',          'ema',         '{5m,15m,4h}', 'float', 'EMA 200 períodos', 'ema200'),
(12, 'ema3_angle',      'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA3', 'ema3_angle'),
(13, 'ema9_angle',      'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA9', 'ema9_angle'),
(14, 'ema20_angle',     'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA20', 'ema20_angle'),
(15, 'ema50_angle',     'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA50', 'ema50_angle'),
(16, 'ema20_phase',     'ema',         '{15m,4h}',    'string', 'Fase EMA20 (nivel_1_long...nivel_3_short)', 'ema20_phase'),
(17, 'fib_zone',        'fibonacci',   '{5m,15m,4h}', 'integer', 'Zona Fibonacci (-6 a +6)', 'fibonacci_zone'),
(18, 'basis',           'fibonacci',   '{5m,15m,4h}', 'float', 'BASIS VWMA central', 'basis'),
(19, 'upper_1',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 1 (0.236)', 'upper_1'),
(20, 'upper_2',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 2 (0.382)', 'upper_2'),
(21, 'upper_3',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 3 (0.500)', 'upper_3'),
(22, 'upper_4',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 4 (0.618)', 'upper_4'),
(23, 'upper_5',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 5 (0.764)', 'upper_5'),
(24, 'upper_6',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 6 (1.000)', 'upper_6'),
(25, 'lower_1',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 1', 'lower_1'),
(26, 'lower_2',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 2', 'lower_2'),
(27, 'lower_3',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 3', 'lower_3'),
(28, 'lower_4',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 4', 'lower_4'),
(29, 'lower_5',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 5', 'lower_5'),
(30, 'lower_6',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 6', 'lower_6'),
(31, 'sar_trend_15m',   'sar',         '{15m}',       'integer', 'Tendencia SAR 15m (+1/-1)', 'sar_trend_15m'),
(32, 'sar_trend_4h',    'sar',         '{4h}',        'integer', 'Tendencia SAR 4h (+1/-1)', 'sar_trend_4h'),
(33, 'sar_ini_high_15m','sar',         '{15m}',       'boolean', 'SAR 15m recién cambió a alcista', 'sar_ini_high_15m'),
(34, 'sar_ini_low_15m', 'sar',         '{15m}',       'boolean', 'SAR 15m recién cambió a bajista', 'sar_ini_low_15m'),
(35, 'sar_ini_high_4h', 'sar',         '{4h}',        'integer', 'SAR 4h recién cambió a alcista', 'sar_ini_high_4h'),
(36, 'sar_ini_low_4h',  'sar',         '{4h}',        'integer', 'SAR 4h recién cambió a bajista', 'sar_ini_low_4h'),
(37, 'mtf_score',       'system',      '{15m}',       'float', 'MTF Score (-1 a +1)', 'mtf_score'),
(38, 'pine_signal',     'system',      '{5m,15m}',    'string', 'Señal PineScript', 'pinescript_signal'),
(39, 'spike_bullish',   'system',      '{5m,15m,4h}', 'boolean', 'Spike alcista', 'spike_bullish'),
(40, 'spike_bearish',   'system',      '{5m,15m,4h}', 'boolean', 'Spike bajista', 'spike_bearish'),
(41, 'spike_ratio',     'system',      '{5m,15m,4h}', 'float', 'Ratio volumen spike', 'spike_ratio'),
(42, 'regime',          'system',      '{15m}',       'string', 'Régimen de riesgo', 'regime'),
(43, 'structure_15m',   'structure',   '{15m}',       'string', 'Estructura 15m', 'structure_15m'),
(44, 'structure_4h',    'structure',   '{4h}',        'string', 'Estructura 4h', 'structure_4h'),
(45, 'allow_long_4h',   'structure',   '{4h}',        'boolean', 'Estructura 4h permite LONG', 'allow_long_4h'),
(46, 'allow_short_4h',  'structure',   '{4h}',        'boolean', 'Estructura 4h permite SHORT', 'allow_short_4h')
ON CONFLICT (id) DO NOTHING;

-- INSERTAR CONDICIONES
INSERT INTO strategy_conditions (id, name, variable_id, operator, value_type, value_literal, value_variable, value_list, value_min, value_max, timeframe, description)
VALUES
(1,  'ADX débil (<20)',       3,  '<',       'literal', 20,   NULL, NULL,  NULL,NULL,'15m','ADX < 20'),
(2,  'ADX moderado (20-35)',  3,  'BETWEEN', 'range',   NULL, NULL, NULL,  20,  35, '15m','20 <= ADX <= 35'),
(3,  'ADX agresivo (35-50)',  3,  'BETWEEN', 'range',   NULL, NULL, NULL,  35,  50, '15m','35 <= ADX <= 50'),
(4,  'ADX explosivo (>50)',   3,  '>',       'literal', 50,   NULL, NULL,  NULL,NULL,'15m','ADX > 50'),
(5,  'ADX cualquier fuerza',  3,  '>',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','ADX > 0'),
(6,  '+DI cruza > -DI',       4,  '>',       'variable',NULL, 'adx_minus_di',NULL,NULL,NULL,'15m','+DI > -DI'),
(7,  '-DI cruza > +DI',       5,  '>',       'variable',NULL, 'adx_plus_di', NULL,NULL,NULL,'15m','-DI > +DI'),
(8,  'EMA20 fase long (1-3)', 16, 'IN',      'list',    NULL, NULL, '{nivel_1_long,nivel_2_long,nivel_3_long}', NULL,NULL,'15m','EMA20 en fase alcista'),
(9,  'EMA20 fase short (1-3)',16, 'IN',      'list',    NULL, NULL, '{nivel_1_short,nivel_2_short,nivel_3_short}', NULL,NULL,'15m','EMA20 en fase bajista'),
(10, 'EMA20 nivel 1 long',    16, '==',      'list',    NULL, NULL, '{nivel_1_long}', NULL,NULL,'15m','EMA20 nivel 1 long'),
(11, 'EMA20 ángulo positivo', 14, '>=',      'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA20 apuntando arriba'),
(12, 'EMA20 ángulo negativo', 14, '<',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA20 apuntando abajo'),
(13, 'EMA9 ángulo positivo',  13, '>=',      'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA9 apuntando arriba'),
(14, 'EMA9 ángulo negativo',  13, '<',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA9 apuntando abajo'),
(15, 'EMA50 ángulo positivo', 15, '>=',      'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA50 apuntando arriba'),
(16, 'Zona positiva (>0)',    17, '>',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','Precio sobre basis'),
(17, 'Zona negativa (<0)',    17, '<',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','Precio bajo basis'),
(18, 'Zona extendida+ (>=3)', 17, '>=',      'literal', 3,    NULL, NULL,  NULL,NULL,'15m','Zona +3 o más'),
(19, 'Zona extendida- (<=-3)',17, '<=',      'literal', -3,   NULL, NULL,  NULL,NULL,'15m','Zona -3 o menos'),
(20, 'Precio toca lower_5',   1,  '<=',      'variable',NULL, 'lower_5',NULL,NULL,NULL,'15m','Precio <= lower_5'),
(21, 'Precio toca lower_6',   1,  '<=',      'variable',NULL, 'lower_6',NULL,NULL,NULL,'15m','Precio <= lower_6'),
(22, 'Precio toca upper_5',   1,  '>=',      'variable',NULL, 'upper_5',NULL,NULL,NULL,'15m','Precio >= upper_5'),
(23, 'Precio toca upper_6',   1,  '>=',      'variable',NULL, 'upper_6',NULL,NULL,NULL,'15m','Precio >= upper_6'),
(24, 'SAR 15m alcista',       31, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','SAR 15m +1'),
(25, 'SAR 15m bajista',       31, '==',      'literal', -1,   NULL, NULL,  NULL,NULL,'15m','SAR 15m -1'),
(26, 'SAR 4h alcista',        32, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'SAR 4h +1'),
(27, 'SAR 4h bajista',        32, '==',      'literal', -1,   NULL, NULL,  NULL,NULL,'4h', 'SAR 4h -1'),
(28, 'SAR 15m cambió LONG',   33, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','SAR 15m ini_high'),
(29, 'SAR 15m cambió SHORT',  34, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','SAR 15m ini_low'),
(30, 'SAR 4h cambió LONG',    35, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'SAR 4h ini_high'),
(31, 'SAR 4h cambió SHORT',   36, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'SAR 4h ini_low'),
(32, 'MTF fuerte+ (>=0.50)',  37, '>=',      'literal', 0.50, NULL, NULL,  NULL,NULL,'15m','MTF >= 0.50'),
(33, 'MTF débil+ (>=0.20)',   37, '>=',      'literal', 0.20, NULL, NULL,  NULL,NULL,'15m','MTF >= 0.20'),
(34, 'MTF fuerte- (<=-0.50)', 37, '<=',      'literal', -0.50,NULL, NULL,  NULL,NULL,'15m','MTF <= -0.50'),
(35, 'MTF débil- (<=-0.20)',  37, '<=',      'literal', -0.20,NULL, NULL,  NULL,NULL,'15m','MTF <= -0.20'),
(36, 'PineScript Buy',        38, 'IN',      'list',    NULL, NULL, '{Buy}',  NULL,NULL,'15m','Señal Buy'),
(37, 'PineScript Sell',       38, 'IN',      'list',    NULL, NULL, '{Sell}', NULL,NULL,'15m','Señal Sell'),
(38, 'Spike alcista',         39, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','spike_bullish=true'),
(39, 'Spike bajista',         40, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','spike_bearish=true'),
(40, 'Estructura 4h LONG ok', 45, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'allow_long_4h'),
(41, 'Estructura 4h SHORT ok',46, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'allow_short_4h'),
(42, 'Dist basis >1.5%',      2,  '>=',      'literal', 1.5,  NULL, NULL,  NULL,NULL,'15m','dist_basis_pct >= 1.5'),
(43, 'Dist basis >3.0%',      2,  '>=',      'literal', 3.0,  NULL, NULL,  NULL,NULL,'4h', 'dist_basis_pct >= 3.0'),
(44, 'Mercado débil',         6,  'IN',      'list',    NULL, NULL, '{debil}',    NULL,NULL,'15m','ADX velocity = debil'),
(45, 'Mercado moderado+',     6,  'IN',      'list',    NULL, NULL, '{moderado,agresivo,explosivo}',NULL,NULL,'15m','ADX velocity moderado o más')
ON CONFLICT (id) DO NOTHING;

-- INSERTAR REGLAS V2
INSERT INTO strategy_rules_v2 (id, rule_code, name, strategy_type, direction, cycle, condition_ids, condition_logic, min_score, condition_weights, market_types, enabled, priority, confidence, version, notes)
VALUES
(1001, 'Aa11', 'LONG débil: EMA20+ ADX<20 +DI cruza', 'scalping', 'long', '15m', '{11,1,6,24,26,40}', 'AND', 0.50, '{"11":0.15,"1":0.20,"6":0.25,"24":0.15,"26":0.15,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.65, 1, 'Mercado débil alcista con +DI cruzando'),
(1002, 'Aa12', 'LONG soporte: precio toca lower_5/6', 'scalping', 'long', '15m', '{11,20,24,26,36,40}', 'AND', 0.60, '{"11":0.10,"20":0.30,"24":0.15,"26":0.15,"36":0.20,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'Precio toca soporte lower_5 con confirmación'),
(1003, 'Aa21', 'LONG momentum: EMA9+EMA50 ángulos+', 'scalping', 'long', '15m', '{11,13,16,26,32,40}', 'AND', 0.65, '{"11":0.15,"13":0.15,"16":0.15,"26":0.20,"32":0.25,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'Momentum alcista multi-EMA'),
(1004, 'Aa22', 'LONG principal: EMA20 fase long + ADX fuerte', 'scalping', 'long', '15m', '{8,2,26,32,36,40}', 'AND', 0.60, '{"8":0.25,"2":0.15,"26":0.20,"32":0.20,"36":0.10,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.75, 1, 'Regla principal LONG — EMA20 fase long'),
(1005, 'Aa23', 'LONG scalp SAR 15m cambió + Pine Buy', 'scalping', 'long', '5m', '{28,26,36,40}', 'AND', 0.60, '{"28":0.35,"26":0.25,"36":0.30,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'SAR 15m cambió a alcista + PineScript Buy'),
(1006, 'Aa24', 'LONG agresivo: zona extendida + explosivo', 'scalping', 'long', '15m', '{18,32,26,36,45}', 'AND', 0.75, '{"18":0.20,"32":0.30,"26":0.20,"36":0.20,"45":0.10}', '{crypto_futures}', true, 2, 0.75, 1, 'Zona +3 con momentum explosivo'),
(1011, 'Bb11', 'SHORT débil: EMA20- ADX<20 -DI cruza', 'scalping', 'short', '15m', '{12,1,7,25,27,41}', 'AND', 0.50, '{"12":0.15,"1":0.20,"7":0.25,"25":0.15,"27":0.15,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.65, 1, 'Mercado débil bajista con -DI cruzando'),
(1012, 'Bb12', 'SHORT resistencia: precio toca upper_5/6', 'scalping', 'short', '15m', '{12,22,25,27,37,41}', 'AND', 0.60, '{"12":0.10,"22":0.30,"25":0.15,"27":0.15,"37":0.20,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'Precio toca resistencia upper_5'),
(1013, 'Bb21', 'SHORT momentum: EMA20 fase short + MTF-', 'scalping', 'short', '15m', '{9,14,17,27,34,41}', 'AND', 0.65, '{"9":0.25,"14":0.10,"17":0.10,"27":0.20,"34":0.25,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'EMA20 en fase short + MTF negativo'),
(1014, 'Bb22', 'SHORT principal: EMA20 fase short + ADX fuerte', 'scalping', 'short', '15m', '{9,2,27,34,37,41}', 'AND', 0.60, '{"9":0.25,"2":0.15,"27":0.20,"34":0.20,"37":0.10,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.75, 1, 'Regla principal SHORT'),
(1015, 'Bb23', 'SHORT scalp SAR 15m cambió + Pine Sell', 'scalping', 'short', '5m', '{29,27,37,41}', 'AND', 0.60, '{"29":0.35,"27":0.25,"37":0.30,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'SAR 15m cambió a bajista + PineScript Sell'),
(2001, 'Dd21_15m', 'SWING LONG 15m: caída madura banda lower', 'swing', 'long', '15m', '{42,26,40}', 'AND', 0.65, '{"42":0.40,"26":0.35,"40":0.25}', '{crypto_futures,forex_futures,crypto_spot,stocks_spot}', true, 2, 0.70, 1, 'LIMIT LONG extremo inferior maduro — 15m'),
(2002, 'Dd21_4h', 'SWING LONG 4h: caída madura macro', 'swing', 'long', '4h', '{43,26,40}', 'AND', 0.70, '{"43":0.45,"26":0.30,"40":0.25}', '{crypto_futures,forex_futures,crypto_spot,stocks_spot}', true, 2, 0.75, 1, 'LIMIT LONG extremo inferior macro — 4h'),
(2011, 'Dd11_15m', 'SWING SHORT 15m: subida madura banda upper', 'swing', 'short', '15m', '{42,27,41}', 'AND', 0.65, '{"42":0.40,"27":0.35,"41":0.25}', '{crypto_futures,forex_futures}', true, 2, 0.70, 1, 'LIMIT SHORT extremo superior maduro — 15m'),
(2012, 'Dd11_4h', 'SWING SHORT 4h: subida madura macro', 'swing', 'short', '4h', '{43,27,41}', 'AND', 0.70, '{"43":0.45,"27":0.30,"41":0.25}', '{crypto_futures,forex_futures}', true, 2, 0.75, 1, 'LIMIT SHORT extremo superior macro — 4h')
ON CONFLICT (id) DO NOTHING;

-- VERIFICACIÓN
SELECT 'strategy_variables' AS tabla, COUNT(*) AS registros FROM strategy_variables
UNION ALL
SELECT 'strategy_conditions', COUNT(*) FROM strategy_conditions
UNION ALL
SELECT 'strategy_rules_v2', COUNT(*) FROM strategy_rules_v2;
