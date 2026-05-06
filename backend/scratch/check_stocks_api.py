import requests
import json

def check_api():
    url = "http://localhost:8080/api/stocks/opportunities"
    try:
        resp = requests.get(url)
        data = resp.json()
        opps = data.get("opportunities", [])
        print(f"Total opportunities: {len(opps)}")
        for opp in opps[:5]:
            print(f"Ticker: {opp.get('ticker')}, CreatedAt: {opp.get('created_at')}, LastScan: {opp.get('last_scan_time')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_api()
