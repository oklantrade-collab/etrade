import os
import httpx
import asyncio
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))

async def test_api(client, url, name):
    try:
        response = await client.get(url)
        if response.status_code == 200:
            print(f"[{name}] OK: Conexión exitosa y llave validada.")
        else:
            print(f"[{name}] Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[{name}] Error de conexión: {e}")

async def test_fred(client, api_key):
    if not api_key:
        print("FRED: API Key no encontrada en .env")
        return
    url = f"https://api.stlouisfed.org/fred/series?series_id=GNPCA&api_key={api_key}&file_type=json"
    await test_api(client, url, "FRED")

async def test_finnhub(client, api_key):
    if not api_key:
        print("FINNHUB: API Key no encontrada en .env")
        return
    url = f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={api_key}"
    await test_api(client, url, "FINNHUB")

async def test_fmp(client, api_key):
    if not api_key:
        print("FMP: API Key no encontrada en .env")
        return
    url = f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={api_key}"
    await test_api(client, url, "FMP")

async def test_sec(client, user_agent):
    if not user_agent:
        print("SEC: User Agent no encontrado en .env")
        return
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    headers = {
        'User-Agent': user_agent,
        'Accept-Encoding': 'gzip, deflate'
    }
    try:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            print("[SEC EDGAR] OK: Conexión exitosa. Respondió con datos de Apple (CIK: 0000320193).")
        else:
            print(f"[SEC EDGAR] Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[SEC EDGAR] Error de conexión: {e}")

async def main():
    fred_key = os.getenv("FRED_API_KEY")
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    fmp_key = os.getenv("FMP_API_KEY")
    sec_user_agent = os.getenv("SEC_USER_AGENT")

    async with httpx.AsyncClient(timeout=10.0) as client:
        print("Probando APIs...\n" + "-"*30)
        await test_fred(client, fred_key)
        await test_finnhub(client, finnhub_key)
        await test_fmp(client, fmp_key)
        await test_sec(client, sec_user_agent)
        print("-" * 30 + "\nPruebas finalizadas.")

if __name__ == "__main__":
    asyncio.run(main())
