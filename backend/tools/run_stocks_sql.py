import asyncio
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

sql = """
  -- ── TABLA DE GRUPOS DE ACCIONES ────────────
  CREATE TABLE IF NOT EXISTS stocks_groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    enabled     BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW()
  );

  INSERT INTO stocks_groups (name, description)
  VALUES
    ('inversiones_pro',
     'Acciones de largo plazo con análisis fundamental'),
    ('hot_by_volume',
     'Acciones con volumen inusual y momentum fuerte')
  ON CONFLICT (name) DO NOTHING;

  -- ── TABLA DE ACCIONES POR GRUPO ─────────────
  CREATE TABLE IF NOT EXISTS stocks_watchlist (
    id          SERIAL PRIMARY KEY,
    ticker      VARCHAR(10) NOT NULL,
    group_name  VARCHAR(50) REFERENCES stocks_groups(name),
    company_name VARCHAR(100),
    sector      VARCHAR(50),
    enabled     BOOLEAN DEFAULT true,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, group_name)
  );

  -- Insertar ejemplos iniciales
  INSERT INTO stocks_watchlist
    (ticker, group_name, company_name, sector)
  VALUES
    ('AAPL',  'inversiones_pro', 'Apple Inc.',         'Technology'),
    ('MSFT',  'inversiones_pro', 'Microsoft Corp.',    'Technology'),
    ('NVDA',  'inversiones_pro', 'NVIDIA Corp.',       'Technology'),
    ('AMZN',  'inversiones_pro', 'Amazon.com Inc.',    'Consumer'),
    ('JPM',   'inversiones_pro', 'JPMorgan Chase',     'Financial'),
    ('TSLA',  'hot_by_volume',   'Tesla Inc.',         'Automotive'),
    ('AMD',   'hot_by_volume',   'Advanced Micro Dev.','Technology'),
    ('SOFI',  'hot_by_volume',   'SoFi Technologies',  'Financial'),
    ('PLTR',  'hot_by_volume',   'Palantir Technologies','Technology'),
    ('MARA',  'hot_by_volume',   'Marathon Digital',   'Crypto/Mining')
  ON CONFLICT (ticker, group_name) DO NOTHING;

  -- ── TABLA DE REGLAS DE STOCKS ───────────────
  CREATE TABLE IF NOT EXISTS stocks_rules (
    id              SERIAL PRIMARY KEY,
    rule_code       VARCHAR(30) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    group_name      VARCHAR(50),  -- NULL = aplica a todos
    direction       VARCHAR(10) NOT NULL, -- buy | sell
    order_type      VARCHAR(10) NOT NULL, -- market | limit
    enabled         BOOLEAN DEFAULT true,
    priority        INTEGER DEFAULT 1,

    -- Condiciones numéricas
    ia_min          NUMERIC DEFAULT 7,
    tech_score_min  NUMERIC DEFAULT 60,

    -- Condiciones de movimiento (array)
    movements_allowed TEXT[],
    -- ej: '{lateral_ascending,asc_from_low}'

    -- Condiciones de señales
    pine_signal     VARCHAR(10),  -- Buy | Sell | NULL
    pine_required   BOOLEAN DEFAULT false,
    fib_trigger     INTEGER[],    -- ej: {-6,-5} o {5,6}

    -- RVOL para HOT BY VOLUME
    rvol_min        NUMERIC DEFAULT 0.0,

    -- Parámetros de ejecución
    limit_trigger_pct NUMERIC DEFAULT 0.005, -- 0.5%
    close_all        BOOLEAN DEFAULT false,
    dca_enabled      BOOLEAN DEFAULT false,
    dca_max_buys     INTEGER DEFAULT 3,
    dca_min_drop_pct NUMERIC DEFAULT 1.0,

    -- Metadata
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
  );

  -- Insertar las 8 reglas definidas
  INSERT INTO stocks_rules (
    rule_code, name, group_name, direction,
    order_type, ia_min, tech_score_min,
    movements_allowed, pine_signal,
    pine_required, fib_trigger, rvol_min,
    limit_trigger_pct, close_all, dca_enabled,
    dca_max_buys, notes
  ) VALUES

  -- ── INVERSIONES PRO — BUY MARKET ────────────
  ('PRO_BUY_MKT',
   'PRO — Compra Market: IA + Técnico + Pine',
   'inversiones_pro', 'buy', 'market',
   7, 60,
   '{lateral_ascending,asc_from_low,ascending}',
   'Buy', true,   
   NULL, 0.0,     
   0.005, false, true, 3,
   'Compra MARKET cuando IA>=7, Técnico>=60 y Pine=Buy en movimiento alcista. DCA hasta 3 recompras.'),

  -- ── INVERSIONES PRO — BUY LIMIT ─────────────
  ('PRO_BUY_LMT',
   'PRO — Compra Limit: Precio estimado en zona alcista',
   'inversiones_pro', 'buy', 'limit',
   7, 60,
   '{lateral_ascending,asc_from_low,ascending}',
   NULL, false,   
   NULL, 0.0,
   0.005, false, false, 1,
   'Orden LIMIT en banda lower calculada. Se activa cuando precio está 0.5% cerca del precio estimado.'),

  -- ── INVERSIONES PRO — SELL MARKET ───────────
  ('PRO_SELL_MKT',
   'PRO — Venta Market: Pine=S o Fibonacci(5,6)',
   'inversiones_pro', 'sell', 'market',
   0, 0,          
   '{lateral_at_top,descending_from_top}',
   'Sell', false, 
   ARRAY[5,6], 0.0,
   0.005, true, false, 0,
   'Vende TODAS las posiciones. Trigger: Pine=S OR precio en Fib(5,6) en movimiento techo.'),

  -- ── INVERSIONES PRO — SELL LIMIT ────────────
  ('PRO_SELL_LMT',
   'PRO — Venta Limit: Precio estimado en zona techo',
   'inversiones_pro', 'sell', 'limit',
   0, 0,
   '{lateral_at_top,descending_from_top}',
   NULL, false,
   NULL, 0.0,
   0.005, true, false, 0,
   'Orden LIMIT en banda upper calculada. Cierra TODAS las posiciones cuando precio 0.5% cerca.'),

  -- ── HOT BY VOLUME — BUY MARKET ──────────────
  ('HOT_BUY_MKT',
   'HOT — Compra Market: IA + Técnico + Pine/Fib(-6,-5)',
   'hot_by_volume', 'buy', 'market',
   7, 60,
   '{lateral_ascending,asc_from_low,ascending}',
   'Buy', false,  
   ARRAY[-6,-5], 2.0, 
   0.005, false, true, 3,
   'Compra MARKET: IA>=7, Técnico>=60, (Pine=B OR Fib en -6/-5) con volumen 2x. DCA hasta 3.'),

  -- ── HOT BY VOLUME — BUY LIMIT ───────────────
  ('HOT_BUY_LMT',
   'HOT — Compra Limit: Precio estimado + volumen',
   'hot_by_volume', 'buy', 'limit',
   7, 60,
   '{lateral_ascending,asc_from_low,ascending}',
   NULL, false,
   NULL, 1.5,     
   0.005, false, false, 1,
   'Orden LIMIT en zona alcista con volumen elevado. Se activa cuando precio 0.5% cerca.'),

  -- ── HOT BY VOLUME — SELL MARKET ─────────────
  ('HOT_SELL_MKT',
   'HOT — Venta Market: Pine=S o Fibonacci(5,6)',
   'hot_by_volume', 'sell', 'market',
   0, 0,
   '{lateral_at_top,descending_from_top}',
   'Sell', false,
   ARRAY[5,6], 0.0,
   0.005, true, false, 0,
   'Vende TODAS las posiciones HOT. Trigger: Pine=S OR Fib(5,6) en techo.'),

  -- ── HOT BY VOLUME — SELL LIMIT ──────────────
  ('HOT_SELL_LMT',
   'HOT — Venta Limit: Precio estimado en techo',
   'hot_by_volume', 'sell', 'limit',
   0, 0,
   '{lateral_at_top,descending_from_top}',
   NULL, false,
   NULL, 0.0,
   0.005, true, false, 0,
   'Orden LIMIT en banda upper. Cierra TODAS cuando precio 0.5% cerca del estimado.')

  ON CONFLICT (rule_code) DO NOTHING;

  -- ── TABLA DE POSICIONES POR TICKER ──────────
  CREATE TABLE IF NOT EXISTS stocks_positions (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker        VARCHAR(10) NOT NULL,
    group_name    VARCHAR(50),
    direction     VARCHAR(10) DEFAULT 'long',
    shares        NUMERIC NOT NULL,
    avg_price     NUMERIC NOT NULL,    
    total_cost    NUMERIC,             
    current_price NUMERIC,
    unrealized_pnl NUMERIC,
    unrealized_pnl_pct NUMERIC,
    dca_count     INTEGER DEFAULT 0,   
    first_buy_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    status        VARCHAR(20) DEFAULT 'open',
    UNIQUE(ticker, status)  
  );

  -- ── TABLA DE ÓRDENES STOCKS ─────────────────
  CREATE TABLE IF NOT EXISTS stocks_orders (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker        VARCHAR(10) NOT NULL,
    group_name    VARCHAR(50),
    rule_code     VARCHAR(30) REFERENCES stocks_rules(rule_code),
    order_type    VARCHAR(10) NOT NULL, 
    direction     VARCHAR(10) NOT NULL, 
    shares        NUMERIC,
    limit_price   NUMERIC,              
    market_price  NUMERIC,              
    trigger_price NUMERIC,              
    estimated_price NUMERIC,            
    target_band   VARCHAR(20),          
    status        VARCHAR(20) DEFAULT 'pending',
    filled_price  NUMERIC,
    filled_at     TIMESTAMPTZ,
    ia_score      NUMERIC,
    tech_score    NUMERIC,
    movement_type VARCHAR(30),
    rvol          NUMERIC,
    expires_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT NOW()
  );
"""

import requests
try:
    headers = {
        "apikey": os.getenv("SUPABASE_SERVICE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_KEY')}",
        "Content-Type": "application/json"
    }
    # Hack to execute arbitrary SQL since python client doesn't expose it directly:
    res = requests.post(
        f"{os.getenv('SUPABASE_URL')}/rest/v1/rpc/exec_sql", 
        json={"query": sql}, 
        headers=headers
    )
    if res.status_code == 404:
        # If exec_sql doesn't exist, we'll try postgres function query
        print("exec_sql RPC not found. creating tables directly from supabase postgrest is not supported out of box.")
        print("Please execute the sql via Supabase dashboard manually if needed.")
    else:
        print(f"SQL execution status: {res.status_code}")
except Exception as e:
    print(e)
