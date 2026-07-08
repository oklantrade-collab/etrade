from google.cloud import bigquery
from google.oauth2 import service_account

BQ_CREDENTIALS_PATH = r"C:\Fuentes\eTrade\backend\google-credentials.json"
table_ref = "etrade_data.us_stocks_screener"

try:
    credentials = service_account.Credentials.from_service_account_file(BQ_CREDENTIALS_PATH)
    client = bigquery.Client(credentials=credentials, project=credentials.project_id)
    
    query = f"""
        SELECT ticker, close_price, ema_3, ema_9, ema_20 
        FROM `{client.project}.{table_ref}`
        WHERE condition_met = TRUE
    """
    
    query_job = client.query(query)
    results = query_job.result()
    
    count = 0
    print("EMPRESAS CON EMA3 > EMA9 > EMA20:")
    for row in results:
        count += 1
        print(f"- {row.ticker}: Precio=${row.close_price:.2f} | EMA3={row.ema_3:.2f} | EMA9={row.ema_9:.2f} | EMA20={row.ema_20:.2f}")
    
    print(f"\nTOTAL ENCONTRADAS: {count}")
    
except Exception as e:
    print(f"Error querying BigQuery: {e}")
