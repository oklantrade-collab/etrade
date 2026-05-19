import requests

try:
    res = requests.get("https://etrade-flame.vercel.app/api/v1/forex/positions?status=closed")
    print(f"Status Code: {res.status_code}")
    data = res.json()
    print(f"Type of returned data: {type(data)}")
    print(f"Length of returned data: {len(data)}")
    if len(data) > 0:
        print(f"First element: {data[0]}")
except Exception as e:
    print(f"Error querying Vercel endpoint: {e}")
