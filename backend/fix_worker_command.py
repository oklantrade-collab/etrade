import requests
import json

API_KEY = "rnd_2AwzgeGzarYxVKArQi9KvyKXwzAM"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def update_worker_command(service_id):
    url = f"https://api.render.com/v1/services/{service_id}"
    data = {
        "serviceDetails": {
            "envSpecificDetails": {
                "dockerCommand": "python app/workers/scheduler.py"
            }
        }
    }
    res = requests.patch(url, headers=headers, json=data)
    if res.status_code == 200:
        print("Worker command updated successfully.")
        # Trigger deploy
        requests.post(f"{url}/deploys", headers=headers, json={})
    else:
        print(f"Error: {res.status_code} - {res.text}")

if __name__ == "__main__":
    update_worker_command("srv-d6sdriq4d50c73bluh30")
