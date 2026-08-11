import os
from dotenv import load_dotenv
import psycopg2
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL').replace('https://', '').replace('.supabase.co', '')
pwd = 'Jhon18213546'
conn_str = f'postgresql://postgres.{url}:{pwd}@aws-1-us-west-2.pooler.supabase.com:6543/postgres'

try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    
    # Forex Positions
    query_forex = """
    SELECT 
        symbol as ticker,
        DATE_TRUNC('month', closed_at) as month,
        COUNT(*) as total_trades,
        SUM(COALESCE(pnl_usd, 0)) as total_profit,
        SUM(CASE WHEN close_reason ILIKE '%erep%' THEN 1 ELSE 0 END) as erep_trades
    FROM forex_positions
    WHERE status = 'closed' AND closed_at IS NOT NULL
    GROUP BY 1, 2
    ORDER BY total_profit DESC;
    """
    
    cur.execute(query_forex)
    forex_rows = cur.fetchall()
    
    
    # Crypto from paper_trades
    query_crypto = """
    SELECT 
        symbol as ticker,
        DATE_TRUNC('month', closed_at) as month,
        COUNT(*) as total_trades,
        SUM(COALESCE(pnl_usd, COALESCE(total_pnl_usd, 0))) as total_profit,
        SUM(CASE WHEN close_reason ILIKE '%erep%' OR exit_reason ILIKE '%erep%' THEN 1 ELSE 0 END) as erep_trades
    FROM paper_trades
    WHERE closed_at IS NOT NULL AND symbol LIKE '%USDT%'
    GROUP BY 1, 2
    ORDER BY total_profit DESC;
    """
    
    try:
        cur.execute(query_crypto)
        crypto_rows = cur.fetchall()
    except Exception as e:
        conn.rollback()
        crypto_rows = []
        
    print("\n" + "="*100)
    print("RANKING MENSUAL DE CRIPTO Y FOREX (ORDENADO POR PNL)")
    print("="*100)
    
    def print_market(name, data):
        print(f"\n🌍 MERCADO: {name}")
        print("-" * 100)
        if not data:
            print("No hay datos históricos registrados para este mercado.")
            return
            
        print(f"{'TICKER':<15} | {'MES':<10} | {'TRADES':<8} | {'EREPs':<8} | {'GANANCIA USD':>12}")
        print("-" * 100)
        
        sorted_data = sorted(data, key=lambda x: x[3] or 0, reverse=True)
        
        for row in sorted_data:
            ticker, month, trades, profit, ereps = row
            month_str = month.strftime('%Y-%m') if month else 'N/A'
            profit_str = f"${float(profit):.2f}" if profit is not None else "$0.00"
            print(f"{ticker:<15} | {month_str:<10} | {trades:<8} | {ereps:<8} | {profit_str:>12}")

    print_market("FOREX (forex_positions)", forex_rows)
    print_market("CRYPTO (paper_trades)", crypto_rows)
    
    print("\n" + "="*100)
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error general: {e}")
