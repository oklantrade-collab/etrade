import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def run_script():
    sb = get_supabase()
    
    queries = [
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS ema3_15m NUMERIC;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS ema9_15m NUMERIC;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS ema_trend_15m VARCHAR(10);",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS sipv_15m VARCHAR(10);",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS sipv_4h VARCHAR(10);",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS sar_15m_positive BOOLEAN DEFAULT true;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS current_fib_band INTEGER DEFAULT 0;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS mid_band_price NUMERIC;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS tp_mode VARCHAR(30) DEFAULT 'blocks';",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS tp_block_status JSONB;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS last_candle_open NUMERIC;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS last_candle_close NUMERIC;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS anti_gap_applied BOOLEAN DEFAULT false;"
    ]
    
    print("Applying TP v2 schema migrations...")
    for i, query in enumerate(queries):
        try:
            sb.rpc('exec_sql', {'sql_query': query}).execute()
        except Exception as e:
            try:
                sb.rpc('exec_sql', {'query': query}).execute()
            except Exception as e2:
                pass
    
    print("Schema updated successfully.\n")
    
    query1 = """
    SELECT
        rule_code                    AS trigger,
        COUNT(*)                     AS activaciones,
        AVG(filled_price - 
            sp.avg_price)            AS avg_ganancia_usd,
        SUM(so.shares)               AS shares_total
    FROM stocks_orders so
    JOIN stocks_positions sp
      ON sp.ticker = so.ticker
    WHERE so.rule_code LIKE 'tp_%'
      AND so.status = 'filled'
    GROUP BY rule_code
    ORDER BY activaciones DESC;
    """
    print("--------------------------------------------------")
    print("Decisiones de TP v2 por trigger:")
    try:
        res = sb.rpc('exec_sql_return', {'sql_query': query1}).execute()
        if hasattr(res, 'data') and res.data:
            for row in res.data:
                print(row)
        else:
            print("No data or empty result.")
    except Exception as e:
        try:
            res = sb.rpc('exec_sql_return', {'query': query1}).execute()
            if hasattr(res, 'data') and res.data:
                for row in res.data:
                    print(row)
            else:
                print("No data or empty result.")
        except Exception as e2:
            print("Could not fetch verification query 1:", e2)
            
    print("\n--------------------------------------------------")
    print("Estado actual de posiciones con EMA:")
    query2 = """
    SELECT
        ticker,
        ROUND(avg_price::numeric,2)     AS entry,
        ROUND(current_price::numeric,2) AS price,
        ROUND(((current_price-avg_price)
          /avg_price*100)::numeric,2)   AS gain_pct,
        ema_trend_15m                   AS ema_trend,
        current_fib_band                AS fib_band,
        ROUND(mid_band_price::numeric,2) AS mid_band,
        tp_block1_executed              AS b1,
        tp_block2_executed              AS b2,
        tp_block3_executed              AS b3
    FROM stocks_positions
    WHERE status = 'open'
    ORDER BY gain_pct DESC;
    """
    try:
        res = sb.rpc('exec_sql_return', {'sql_query': query2}).execute()
        if hasattr(res, 'data') and res.data:
            for row in res.data:
                print(row)
        else:
            print("No data or empty result.")
    except Exception as e:
        try:
            res = sb.rpc('exec_sql_return', {'query': query2}).execute()
            if hasattr(res, 'data') and res.data:
                for row in res.data:
                    print(row)
            else:
                print("No data or empty result.")
        except Exception as e2:
            print("Could not fetch verification query 2:", e2)

if __name__ == "__main__":
    run_script()
