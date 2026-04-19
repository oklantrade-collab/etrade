import sys
import os
sys.path.append(os.path.abspath('.'))

from app.core.supabase_client import get_supabase

def setup_db():
    sb = get_supabase()
    sql = """
    CREATE TABLE IF NOT EXISTS universe_settings (
        id SERIAL PRIMARY KEY,
        fg_mcap_min NUMERIC DEFAULT 300,
        fg_mcap_max NUMERIC DEFAULT 10000,
        fg_rev_growth_min NUMERIC DEFAULT 25,
        fg_price_max NUMERIC DEFAULT 50,
        fg_rs_min NUMERIC DEFAULT 70,
        gl_mcap_min NUMERIC DEFAULT 5000,
        gl_rev_growth_min NUMERIC DEFAULT 12,
        gl_margin_min NUMERIC DEFAULT 30,
        gl_rs_min NUMERIC DEFAULT 75,
        gl_inst_min NUMERIC DEFAULT 40,
        gl_price_max NUMERIC DEFAULT 200,
        ex_vol_min NUMERIC DEFAULT 200000,
        ex_debt_equity_max NUMERIC DEFAULT 3.0,
        ex_eps_neg_quarters_max INT DEFAULT 4,
        w_rev_growth NUMERIC DEFAULT 25,
        w_gross_margin NUMERIC DEFAULT 20,
        w_eps_growth NUMERIC DEFAULT 20,
        w_rs_score NUMERIC DEFAULT 20,
        w_inst_ownership NUMERIC DEFAULT 15,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    INSERT INTO universe_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
    """
    try:
        res = sb.rpc('exec_sql', {'sql_query': sql}).execute()
        print("✅ Tabla universe_settings creada o verificada con éxito.")
    except Exception as e:
        print(f"❌ Error creando la tabla: {e}")

if __name__ == "__main__":
    setup_db()
