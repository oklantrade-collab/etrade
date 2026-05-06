import requests
url = "http://localhost:8080/api/v1/market/candles/BTCUSDT?timeframe=15m&limit=10"
try:
    r = requests.get(url)
    print(f"Status: {r.status_code}")
    print(f"Data: {r.json()}")
except Exception as e:
    print(f"Error: {e}")
