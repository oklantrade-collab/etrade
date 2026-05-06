import requests
import json

def check_local_api():
    url = "http://localhost:8080/api/v1/stocks/opportunities"
    try:
        resp = requests.get(url)
        data = resp.json()
        opps = data.get("opportunities", [])
        for opp in opps:
            if opp.get("ticker") != "TESTDUMMY":
                print(json.dumps(opp, indent=2))
                break
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_local_api()
