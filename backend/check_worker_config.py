import requests
import json

API_KEY = "rnd_2AwzgeGzarYxVKArQi9KvyKXwzAM"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

def check_worker_details(service_id):
    url = f"https://api.render.com/v1/services/{service_id}"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        print(json.dumps(data, indent=2))
    else:
        print(f"Error: {res.status_code} - {res.text}")

if __name__ == "__main__":
    check_worker_details("srv-d6sdriq4d50c73bluh30")
