
import requests
import json

url = "http://localhost:8080/api/v1/strategies/rules/Bb21"
payload = {
    "name": "SHORT Bb21: Range + Basis Fall + Pine Sell",
    "notes": "Actualizada: Eliminadas EMAs y MTF; agregados Range, Basis Fall y PineScript Sell Reciente"
}
headers = {'Content-Type': 'application/json'}

try:
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
