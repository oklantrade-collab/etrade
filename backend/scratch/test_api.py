from fastapi.testclient import TestClient
from app.main import app
import json

client = TestClient(app)
response = client.get("/api/v1/stocks/opportunities")
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Total opportunities: {data['total']}")
    print(f"Market Status: {data['market_status']}")
    pro_count = sum(1 for o in data['opportunities'] if o.get('is_pro_member'))
    print(f"Pro members count: {pro_count}")
else:
    print(f"Error: {response.text}")
