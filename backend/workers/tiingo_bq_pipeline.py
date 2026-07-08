import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.cloud import bigquery
from google.oauth2 import service_account
from yfinance.screener import EquityQuery, screen
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuración y Credenciales
TIINGO_TOKEN = "b85e1cc70bdebeb95b3a876186df3dd3c315b046"
BQ_CREDENTIALS_PATH = r"C:\Fuentes\eTrade\backend\google-credentials.json"
BQ_TABLE_ID = "us_stocks_screener" # Ajustaremos luego si necesita Dataset ej: "project.dataset.us_stocks_screener"

# Parámetros del Filtro
MIN_MARKET_CAP = 800_000_000
MAX_PRICE = 200
MIN_AVG_VOL_20D = 500_000
HISTORY_DAYS = 50 # 50 días para asegurar cálculos de EMA20

def get_yfinance_candidates():
    """Usa Yahoo Finance Screener para un filtro inicial rápido"""
    logger.info("Obteniendo candidatos de Yahoo Finance (Filtro primario)...")
    try:
        # Consulta en Yahoo Finance
        query = EquityQuery('AND', [
            EquityQuery('EQ', ['region', 'us']),
            EquityQuery('GT', ['intradaymarketcap', MIN_MARKET_CAP]),
            EquityQuery('LT', ['intradayprice', MAX_PRICE]),
            EquityQuery('GT', ['dayvolume', 100_000]) # Filtro suave inicial
        ])
        
        # Obtenemos max 250 tickers (límite de Yahoo Finance)
        res = screen(query, size=250, sortField='dayvolume', sortAsc=False)
        if not res or 'quotes' not in res:
            logger.warning("No se encontraron resultados en YF Screener.")
            return []
            
        candidates = []
        for q in res['quotes']:
            sym = q.get('symbol', '')
            # Filtramos ADRs o warrants (que tienen punto en YF)
            if sym and '.' not in sym and '-' not in sym:
                candidates.append({
                    "ticker": sym.upper(),
                    "market_cap": q.get('marketCap', 0)
                })
                
        logger.info(f"YF devolvió {len(candidates)} candidatos.")
        return candidates
    except Exception as e:
        logger.error(f"Error en YF Screener: {e}")
        return []

def get_tiingo_historical_data(ticker, start_date, end_date):
    """Obtiene precios históricos de Tiingo para un ticker"""
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    params = {
        'startDate': start_date,
        'endDate': end_date,
        'format': 'json',
        'token': TIINGO_TOKEN
    }
    try:
        # Tiingo free tier: 50 requests/hour soft-limit, but can burst or 500/hour depending on plan.
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 429:
            logger.warning(f"Rate limit de Tiingo (429) alcanzado en {ticker}.")
            raise Exception("RATE_LIMIT")
            
        if response.status_code == 200:
            data = response.json()
            if data:
                return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"Error al conectar con Tiingo para {ticker}: {e}")
    return pd.DataFrame()

def process_and_calculate_emas(candidates):
    """Descarga de Tiingo, filtra por volumen de 20 días y calcula EMAs."""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=HISTORY_DAYS)).strftime('%Y-%m-%d')
    
    final_rows = []
    
    # Procesar con contador y límite
    for idx, cand in enumerate(candidates):
        ticker = cand['ticker']
        mcap = cand['market_cap']
        
        # Log cada 50 procesados
        if idx % 50 == 0:
            logger.info(f"Procesando ticker {idx}/{len(candidates)}...")
            
        try:
            df = get_tiingo_historical_data(ticker, start_date, end_date)
        except Exception as e:
            if str(e) == "RATE_LIMIT":
                logger.error("Interrumpiendo descargas por límite de API. Se guardarán los procesados hasta ahora.")
                break
            continue
            
        if df.empty or len(df) < 200:
            continue # Necesitamos al menos 200 días para EMA200
            
        # Ordenar por fecha por si acaso
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        # 1. Filtro Volumen Promedio 20 días
        last_20_days = df.tail(20)
        avg_vol_20d = last_20_days['volume'].mean()
        if avg_vol_20d < MIN_AVG_VOL_20D:
            continue
            
        # 2. Cálculos de EMAs
        df['ema_3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # Eliminar NAs si fuera necesario
        df.dropna(subset=['ema_20'], inplace=True)
        if df.empty:
            continue
            
        # Tomar la última fila (la más reciente)
        last_row = df.iloc[-1]
        
        # 3. Condición Técnica
        ema3 = float(last_row['ema_3'])
        ema9 = float(last_row['ema_9'])
        ema20 = float(last_row['ema_20'])
        condition_met = bool(ema3 > ema9 and ema9 > ema20)
        
        final_rows.append({
            "ticker": ticker,
            "date": last_row['date'].strftime('%Y-%m-%d'),
            "close_price": float(last_row['close']),
            "market_cap": float(mcap),
            "ema_3": ema3,
            "ema_9": ema9,
            "ema_20": ema20,
            "condition_met": condition_met
        })
        
        # Pequeño sleep para no saturar la API
        time.sleep(0.1)

    logger.info(f"Total empresas filtradas y procesadas: {len(final_rows)}")
    return final_rows

def load_to_bigquery(rows):
    """Carga los datos calculados a Google BigQuery limpiando la tabla."""
    if not rows:
        logger.warning("No hay datos para cargar en BigQuery.")
        return
        
    logger.info("Conectando a Google BigQuery...")
    try:
        credentials = service_account.Credentials.from_service_account_file(BQ_CREDENTIALS_PATH)
        client = bigquery.Client(credentials=credentials, project=credentials.project_id)
        
        # Determinar el nombre completo de la tabla
        # Si BQ_TABLE_ID no tiene dataset, asumimos un dataset llamado 'etrade_data' (Ajustar según necesidad)
        table_ref = BQ_TABLE_ID
        if '.' not in table_ref:
            dataset_id = "etrade_data"
            # Asegurar que el dataset existe
            dataset = bigquery.Dataset(f"{client.project}.{dataset_id}")
            dataset.location = "US"
            try:
                client.get_dataset(dataset_id)
            except Exception:
                client.create_dataset(dataset, timeout=30)
                logger.info(f"Dataset {dataset_id} creado.")
            table_ref = f"{client.project}.{dataset_id}.{BQ_TABLE_ID}"

        schema = [
            bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("close_price", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("market_cap", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("ema_3", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("ema_9", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("ema_20", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("condition_met", "BOOLEAN", mode="REQUIRED"),
        ]

        # Configurar el Job para que sobreescriba la tabla (Truncate)
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )

        df = pd.DataFrame(rows)
        # BQ requiere objeto datetime.date o str para campos tipo DATE
        df['date'] = pd.to_datetime(df['date']).dt.date

        logger.info(f"Cargando {len(df)} filas a la tabla {table_ref}...")
        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result() # Espera a que el trabajo termine
        
        logger.info("Carga exitosa en BigQuery.")
        
    except Exception as e:
        logger.error(f"Error cargando a BigQuery: {e}")

def main():
    logger.info("Iniciando Pipeline Tiingo -> BigQuery")
    start_t = time.time()
    
    candidates = get_yfinance_candidates()
    if not candidates:
        logger.error("Abortando por falta de candidatos iniciales.")
        return
        
    final_data = process_and_calculate_emas(candidates)
    
    load_to_bigquery(final_data)
    
    elapsed = (time.time() - start_t) / 60
    logger.info(f"Pipeline completado en {elapsed:.2f} minutos.")

if __name__ == "__main__":
    main()
