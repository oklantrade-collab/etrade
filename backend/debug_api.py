import requests

URLS = [
    "http://localhost:8080/api/v1/stocks/positions",
    "http://localhost:8080/api/v1/dashboard/summary"
]

for url in URLS:
    try:
        print(f"Testing {url}...")
        r = requests.get(url, timeout=5)
        print(f"STATUS: {r.status_code}")
        print(f"BODY: {r.text[:200]}...")
    except Exception as e:
        print(f"FAILED: {e}")
