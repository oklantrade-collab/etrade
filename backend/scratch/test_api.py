import asyncio
import sys
import json
from fastapi.testclient import TestClient

sys.path.insert(0, 'c:/Fuentes/eTrade/backend')
from app.main import app

client = TestClient(app)

res = client.get("/api/v1/stocks/opportunities")
data = res.json()

for opp in data.get('opportunities', []):
    if opp.get('ticker') in ['NWG', 'MRNA']:
        print(f"ticker: {opp.get('ticker')} volume: {opp.get('volume')} pool: {opp.get('pool_type')}")
