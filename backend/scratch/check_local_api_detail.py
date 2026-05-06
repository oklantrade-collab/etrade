import requests
import json

def check_local_api():
    url = "http://localhost:8080/api/v1/stocks/opportunities"
    try:
        resp = requests.get(url)
        data = resp.json()
        opps = data.get("opportunities", [])
        print(f"Total opportunities: {len(opps)}")
        if opps:
            # Print the first one in detail
            print(json.dumps(opps[0], indent=2))
        else:
            print("No opportunities found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_local_api()
